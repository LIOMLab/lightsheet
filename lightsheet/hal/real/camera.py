"""
Created on February 8, 2022
"""

import logging
import time
from datetime import datetime, timedelta

import numpy as np
import pco

from lightsheet.config import cfg_read, cfg_write
from lightsheet.hal.interfaces import ICamera

logger = logging.getLogger(__name__)


class Camera(ICamera):
    """Class for PCO cameras"""

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults: dict[str, str] = {}  # noqa: RUF012 - class-level config template, populated at definition, never mutated at runtime
    _cfg_defaults["Shutter Mode"] = "Rolling"
    _cfg_defaults["Exposure Time"] = "100"
    _cfg_defaults["Lightsheet Line Time"] = "48.80"
    _cfg_defaults["Lightsheet Exposed Lines"] = "16"
    _cfg_defaults["Lightsheet Delay Lines"] = "0"
    _cfg_defaults["Recorder Timeout"] = "5"
    _cfg_defaults["Recorder Timeout Floor"] = "5"
    _cfg_defaults["Recorder Timeout Safety Factor"] = "3.0"

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

        # HAL error surface -- a physically-absent device sets
        # error/error_message instead of raising.
        self.error = 0
        self.error_message = ""

        # Flags (bool)
        self.is_recording = False
        self.new_data_ready = False
        self.recorder_timeout_status = False

        # Other variables
        self.camera = None
        self.xsize = None
        self.ysize = None
        # Binning readback defaults to 1x1 so attrs exist if open() fails;
        # open()/arm() overwrite with live SDK readback.
        self.binning_x = 1
        self.binning_y = 1
        self.bytes_per_image = None
        self.line_time = None

        # read configurable settings from config.ini file
        self._cfg_filename = "config.ini"
        self._cfg_section = "Camera"
        self.cfg_load_ini()

        # Automatically open camera on instance creation
        self.open()

    def cfg_load_ini(self) -> None:
        # read configuration from ini file
        self._cfg = cfg_read(self._cfg_filename, self._cfg_section, self._cfg_defaults)
        # set instance variables from read configuration dictionary values
        self.shutter_mode = str(self._cfg["Shutter Mode"])
        self.exposure_time = float(self._cfg["Exposure Time"]) * 1e-3
        self.lightsheet_line_time = float(self._cfg["Lightsheet Line Time"]) * 1e-6
        self.lightsheet_exposed_lines = int(self._cfg["Lightsheet Exposed Lines"])
        self.lightsheet_delay_lines = int(self._cfg["Lightsheet Delay Lines"])
        self.recorder_timeout_interval = int(self._cfg["Recorder Timeout"])
        self.recorder_timeout_floor = int(self._cfg["Recorder Timeout Floor"])
        self.recorder_timeout_safety_factor = float(
            self._cfg["Recorder Timeout Safety Factor"]
        )

    def cfg_save_ini(self) -> None:
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg["Shutter Mode"] = str(self.shutter_mode)
        self._cfg["Exposure Time"] = str(self.exposure_time * 1e3)
        self._cfg["Lightsheet Line Time"] = str(self.lightsheet_line_time * 1e6)
        self._cfg["Lightsheet Exposed Lines"] = str(self.lightsheet_exposed_lines)
        self._cfg["Lightsheet Delay Lines"] = str(self.lightsheet_delay_lines)
        self._cfg["Recorder Timeout"] = str(self.recorder_timeout_interval)
        self._cfg["Recorder Timeout Floor"] = str(self.recorder_timeout_floor)
        self._cfg["Recorder Timeout Safety Factor"] = str(
            self.recorder_timeout_safety_factor
        )
        # write configuration to ini file
        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)

    def open(self) -> None:
        """Open a camera"""
        if self.verbose:
            print("Opening camera...")
        if self.camera is None:
            try:
                self.camera = pco.Camera()
            except (ValueError, SystemError, OSError, RuntimeError):
                logger.exception("Failed to open camera.")
                self.camera = None
                self.error = 1
                self.error_message = "Camera not available on this platform"
            else:
                sizes = {}
                sizes = self.camera.sdk.get_sizes()
                self.xsize = int(sizes.get("x"))
                self.ysize = int(sizes.get("y"))
                self.bytes_per_image = (
                    self.xsize * self.ysize * 2
                )  # 16 bit images (2 bytes per pixel)
                self.camera.sdk.set_image_parameters(self.xsize, self.ysize)

                # Binning readback -- XY voxel-size source for ZarrSaver;
                # .get(...,1) handles missing keys.
                binning = self.camera.sdk.get_binning()
                self.binning_x = int(binning.get("binning x", 1))
                self.binning_y = int(binning.get("binning y", 1))

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                self.line_time = cam_cmos_line_timing.get("line time")
                self.default_line_time = self.line_time
                if self.verbose:
                    print(" Camera opened.")
        else:
            if self.verbose:
                print(" Camera already opened.")
        return None

    def close(self) -> None:
        """Closes an opened camera"""
        if self.verbose:
            print("Closing camera...")
        if self.camera is not None:
            self.camera.close()
            self.camera = None
            if self.verbose:
                print(" Camera closed.")
        else:
            if self.verbose:
                print(" Camera already closed.")
        return None

    def arm(self) -> None:
        """docstring"""
        if self.camera is not None:
            if self.verbose:
                print("Arming camera...")
            if self.camera.sdk.get_recording_state()["recording state"] == "on":
                self.camera.sdk.set_recording_state("off")
            self.camera.sdk.arm_camera()
            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.xsize = int(sizes.get("x"))
            self.ysize = int(sizes.get("y"))
            self.bytes_per_image = (
                self.xsize * self.ysize * 2
            )  # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.xsize, self.ysize)

            # Binning re-read after arm -- operator may change binning
            # between open and arm.
            binning = self.camera.sdk.get_binning()
            self.binning_x = int(binning.get("binning x", 1))
            self.binning_y = int(binning.get("binning y", 1))

            cam_cmos_line_timing = {}
            cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
            self.line_time = cam_cmos_line_timing.get("line time")

            if self.verbose:
                print(" Camera armed.")
                print(" Line time:", str(self.line_time))
        return None

    def arm_scan(self) -> None:
        # Clear stale timeout flag before the hardware-present guard so
        # every scan starts clean.
        self.recorder_timeout_status = False
        if self.camera is not None:
            if self.shutter_mode == "Lightsheet":
                if self.verbose:
                    print("Arming camera in Lightsheet mode...")
                if self.camera.sdk.get_recording_state()["recording state"] == "on":
                    self.camera.sdk.set_recording_state("off")
                self.set_trigger_mode("external")
                self.camera.sdk.set_cmos_line_timing("on", self.lightsheet_line_time)
                self.camera.sdk.set_cmos_line_exposure_delay(
                    self.lightsheet_exposed_lines, self.lightsheet_delay_lines
                )
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get("parameter")
                self.line_time = cam_cmos_line_timing.get("line time")

                cam_cmos_line_exposure_delay = {}
                cam_cmos_line_exposure_delay = (
                    self.camera.sdk.get_cmos_line_exposure_delay()
                )
                exposed_lines = cam_cmos_line_exposure_delay.get("lines exposure")
                delay_lines = cam_cmos_line_exposure_delay.get("lines delay")

                if self.verbose:
                    print(" Camera armed.")
                    print(" Lightsheet mode is:", str(parameter))
                    print(" Line time:", str(self.line_time))
                    print(" Exposed lines:", str(exposed_lines))
                    print(" Delay lines:", str(delay_lines))

            elif self.shutter_mode == "Rolling":
                if self.verbose:
                    print("Arming camera in Rolling Shutter mode...")
                if self.camera.sdk.get_recording_state()["recording state"] == "on":
                    self.camera.sdk.set_recording_state("off")
                self.set_trigger_mode("external_exposure")
                self.camera.sdk.set_cmos_line_timing("off", self.default_line_time)
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get("parameter")
                self.line_time = cam_cmos_line_timing.get("line time")

                if self.verbose:
                    print(" Camera armed.")
                    print(" Lightsheet mode is:", str(parameter))
                    print(" Line time:", str(self.line_time))

            elif self.shutter_mode == "Global":
                if self.verbose:
                    print("Arming camera in Global Shutter mode...")
                if self.camera.sdk.get_recording_state()["recording state"] == "on":
                    self.camera.sdk.set_recording_state("off")
                self.set_trigger_mode("external_exposure")
                self.camera.sdk.set_cmos_line_timing("off", self.default_line_time)
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get("parameter")
                self.line_time = cam_cmos_line_timing.get("line time")

                if self.verbose:
                    print(" Camera armed.")
                    print(" Line time:", str(self.line_time))

            else:
                raise Exception("Unknown shutter mode selected")

            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.xsize = int(sizes.get("x"))
            self.ysize = int(sizes.get("y"))
            self.bytes_per_image = (
                self.xsize * self.ysize * 2
            )  # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.xsize, self.ysize)
        return None

    def disarm(self) -> None:
        """docstring"""
        if self.camera is not None:
            if self.verbose:
                print("Disarming camera...")
            if self.camera.sdk.get_recording_state()["recording state"] == "on":
                self.camera.sdk.set_recording_state("off")
            if self.verbose:
                print(" Camera disarmed.")
        return None

    # Managing recording sessions

    def start_recorder(self, number_of_images: int) -> None:
        """docstring"""
        if self.camera is not None:
            try:
                if self.verbose:
                    print("Starting camera recording session...")
                self.camera.record(int(number_of_images), mode="sequence non blocking")
            except ValueError:
                logger.exception("Exception while starting recorder.")
                self.is_recording = False
            else:
                self.is_recording = True
                self.recorder_timeout_status = False
                if self.verbose:
                    print(" Recording session started.")
        return None

    def _compute_per_image_time(self) -> float:
        """Estimate per-image acquisition time (seconds), shutter-mode dependent."""
        if self.shutter_mode == "Lightsheet":
            return self.line_time * self.lightsheet_exposed_lines  # ty: ignore[unsound-return-statement, unsupported-operator]
        else:  # Rolling or Global
            return self.exposure_time

    def monitor_recorder(self, number_of_images: int) -> None:
        """Monitor recorder until all images arrive or timeout expires.

        Timeout scales with image count and per-image time, floored by both
        Recorder Timeout Floor and the legacy Recorder Timeout interval, and
        multiplied by a safety factor. On timeout, recorder_timeout_status
        is set so the caller can abort before zero-filled frames are saved.
        """
        if self.is_recording:
            per_image_time = self._compute_per_image_time()
            timeout_s = max(
                self.recorder_timeout_floor,
                self.recorder_timeout_interval,
                number_of_images * per_image_time * self.recorder_timeout_safety_factor,
            )
            if self.verbose:
                print("Monitoring camera recording session status...")
                print("Timeout interval is " + str(timeout_s) + "s")
            wait_until = datetime.now() + timedelta(seconds=timeout_s)
            while True:
                images_in_buffer = self.camera.rec.get_status()["dwProcImgCount"]  # ty: ignore[unresolved-attribute]
                if images_in_buffer >= number_of_images:
                    self.new_data_ready = True
                    if self.verbose:
                        print(
                            " Recording session succeeded:",
                            images_in_buffer,
                            "images in buffer",
                        )
                    break
                elif wait_until < datetime.now():
                    self.recorder_timeout_status = True
                    if self.verbose:
                        print(
                            " Timeout occurred:",
                            images_in_buffer,
                            "images in buffer after",
                            timeout_s,
                            "s.",
                        )
                    break
                else:
                    time.sleep(0.01)
        return None

    def stop_recorder(self) -> None:
        """docstring"""
        if self.is_recording:
            self.camera.stop()  # ty: ignore[unresolved-attribute]
            self.is_recording = False
        return None

    def copy_recorder_images(self, number_of_images: int) -> np.ndarray | None:
        """Return recorded images from the camera recorder.

        Returns ``number_of_images`` as a uint16 ndarray when
        ``new_data_ready`` is set, then clears the ready flag so the next
        call cannot return stale data. Returns ``None`` when no data is
        ready, making a missing recorder explicit instead of returning a
        synthetic dark frame.
        """
        if self.new_data_ready:
            images, _metadatas = self.camera.images(blocksize=number_of_images)  # ty: ignore[unresolved-attribute]
            self.new_data_ready = False
            return images
        return None

    def delete_recorder(self) -> None:
        """Delete the camera recorder session.

        Does NOT reset recorder_timeout_status — it must survive for the
        acquisition worker to inspect after acquire_scan returns and abort.
        start_recorder resets the flag at the beginning of each plane.
        """
        if self.camera is not None:
            self.camera.rec.delete()
            # Deleting the recording session also deletes any remaining images
            self.new_data_ready = False
        return None

    ### setters

    def set_exposure_time(self, exposure_time_ms: int) -> None:
        """Set the exposure time (in ms) for the camera"""
        if self.camera is not None:
            if self.verbose:
                print("Setting camera exposure time: " + str(exposure_time_ms) + "ms")
            self.camera.sdk.set_delay_exposure_time(0, "ms", exposure_time_ms, "ms")
        self.exposure_time = float(exposure_time_ms) * 1e-3
        return None

    def set_lightsheet_mode(self) -> None:
        """Set lightsheet timing according to current instance settings"""
        if self.camera is not None:
            self.camera.sdk.set_cmos_line_timing("on", self.lightsheet_line_time)
            self.camera.sdk.set_cmos_line_exposure_delay(
                self.lightsheet_exposed_lines, self.lightsheet_delay_lines
            )

            cam_line_timing = {}
            cam_line_timing = self.camera.sdk.get_cmos_line_timing()
            line_timing = cam_line_timing.get("line time")

            cam_line_exposure_delay = {}
            cam_line_exposure_delay = self.camera.sdk.get_cmos_line_exposure_delay()
            line_exposure = cam_line_exposure_delay.get("lines exposure")
            line_delay = cam_line_exposure_delay.get("lines delay")

            if self.verbose:
                print("Camera in lightsheet mode")
                print("Camera line timing is:", str(line_timing))
                print("Camera line exposure is:", str(line_exposure))
                print("Camera line delay is:", str(line_delay))
        return None

    def set_trigger_mode(self, trigger_mode: str) -> None:
        """Set the trigger mode: 'auto_trigger', 'external', or 'external_exposure'."""
        if self.camera is not None:
            if self.verbose:
                print("Setting camera trigger mode:", trigger_mode)
            if self.is_recording:
                if self.verbose:
                    print(
                        " Recording in progress. Trigger mode cannot be"
                        " changed while recording."
                    )
            else:
                if trigger_mode == "auto_trigger":
                    self.camera.sdk.set_trigger_mode("auto sequence")
                elif trigger_mode == "external":
                    self.camera.sdk.set_trigger_mode(
                        "external exposure start & software trigger"
                    )
                elif trigger_mode == "external_exposure":
                    self.camera.sdk.set_trigger_mode("external exposure control")
        return None

    ### getters

    def get_name(self) -> str | None:
        """Returns the camera name"""
        if self.camera is not None:
            cam_name = {}
            cam_name = self.camera.sdk.get_camera_name()
            name = str(cam_name.get("camera name"))
            if self.verbose:
                print("Camera name:", name)
        else:
            name = None
        return name

    def get_camera_temperature(self) -> float | None:
        """Returns the current internal temperatures in Celcius"""
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            camera_temperature = float(cam_temperatures.get("camera temperature"))
            if self.verbose:
                print("Camera internal temperature:", camera_temperature)
        else:
            camera_temperature = None
        return camera_temperature

    def get_sensor_temperature(self) -> float | None:
        """Returns the current sensor temperatures in Celcius"""
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            sensor_temperature = float(cam_temperatures.get("sensor temperature"))
            if self.verbose:
                print("Camera sensor temperature:", sensor_temperature)
        else:
            sensor_temperature = None
        return sensor_temperature

    def get_power_temperature(self) -> float | None:
        """Returns the current power supply temperatures in Celcius"""
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            power_temperature = float(cam_temperatures.get("power temperature"))
            if self.verbose:
                print("Camera power supply temperature:", power_temperature)
        else:
            power_temperature = None
        return power_temperature

    def get_xsize(self) -> int | None:
        """Returns the current armed image x-size of the camera"""
        if self.camera is not None:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_xsize = int(cam_sizes.get("x"))
            if self.verbose:
                print("Camera x-size:", current_xsize)
        else:
            current_xsize = None
        return current_xsize

    def get_ysize(self) -> int | None:
        """Returns the current armed image y-size of the camera"""
        if self.camera is not None:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_ysize = int(cam_sizes.get("y"))
            if self.verbose:
                print("Camera y-size:", current_ysize)
        else:
            current_ysize = None
        return current_ysize

    def get_trigger_mode(self) -> str | None:
        """Returns the current trigger mode"""
        if self.camera is not None:
            cam_trigger_mode = {}
            cam_trigger_mode = self.camera.sdk.get_trigger_mode()
            trigger_mode = str(cam_trigger_mode.get("trigger mode"))
            if self.verbose:
                print("Camera trigger mode:", trigger_mode)
        else:
            trigger_mode = None
        return trigger_mode

    def get_acquire_mode(self) -> str | None:
        """Returns the current acquire mode"""
        if self.camera is not None:
            cam_acquire_mode = {}
            cam_acquire_mode = self.camera.sdk.get_acquire_mode()
            acquire_mode = str(cam_acquire_mode.get("acquire mode"))
            if self.verbose:
                print("Camera acquire mode:", acquire_mode)
        else:
            acquire_mode = None
        return acquire_mode

    def get_storage_mode(self) -> str | None:
        """Returns the current storage mode"""
        if self.camera is not None:
            cam_storage_mode = {}
            cam_storage_mode = self.camera.sdk.get_storage_mode()
            storage_mode = str(cam_storage_mode.get("storage mode"))
            if self.verbose:
                print("Camera storage mode:", storage_mode)
        else:
            storage_mode = None
        return storage_mode

    def get_recorder_submode(self) -> str | None:
        """Returns the current recorder mode (only if storage mode is recorder)"""
        if self.camera is not None:
            cam_recorder_mode = {}
            cam_recorder_mode = self.camera.sdk.get_recorder_submode()
            recorder_mode = str(cam_recorder_mode.get("recorder submode"))
            if self.verbose:
                print("Camera recorder mode:", recorder_mode)
        else:
            recorder_mode = None
        return recorder_mode

    def get_exposure_time(self) -> int | None:
        """Returns the current exposure time"""
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_time = int(cam_delay_exposure_time.get("exposure"))
            if self.verbose:
                print("Camera exposure time:", exposure_time)
        else:
            exposure_time = None
        return exposure_time

    def get_exposure_timebase(self) -> str | None:
        """Returns the exposure timebase"""
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_timebase = str(cam_delay_exposure_time.get("exposure timebase"))
            if self.verbose:
                print("Camera exposure timebase:", exposure_timebase)
        else:
            exposure_timebase = None
        return exposure_timebase

    def get_delay_time(self) -> int | None:
        """Returns the current delay time"""
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_time = int(cam_delay_exposure_time.get("delay"))
            if self.verbose:
                print("Camera delay time:", delay_time)
        else:
            delay_time = None
        return delay_time

    def get_delay_timebase(self) -> str | None:
        """Returns the delay timebase"""
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_timebase = str(cam_delay_exposure_time.get("delay timebase"))
            if self.verbose:
                print("Camera delay timebase:", delay_timebase)
        else:
            delay_timebase = None
        return delay_timebase

    def get_pixel_rates(self) -> dict[str, object] | list:  # ty: ignore[missing-type-argument]
        """Returns available pixel rates"""
        if self.camera is not None:
            cam_description = {}
            cam_description = self.camera.sdk.get_camera_description()
            pixel_rates = cam_description.get("pixel rate")
            if self.verbose:
                print("Camera available pixel rates:", pixel_rates)
        else:
            pixel_rates = {}
        return pixel_rates

    def get_pixel_rate(self) -> str | None:
        """Returns the pixel rate"""
        if self.camera is not None:
            cam_pixel_rate = {}
            cam_pixel_rate = self.camera.sdk.get_pixel_rate()
            pixel_rate = str(cam_pixel_rate.get("pixel rate"))
            if self.verbose:
                print("Camera pixel rate:", pixel_rate)
        else:
            pixel_rate = None
        return pixel_rate

    def get_readout_format(self) -> str | None:
        """
        Returns the SCCMOS readout format
            0x0000  SCCMOS_FORMAT_TOP_BOTTOM
            0x0100  SCCMOS_FORMAT_TOP_CENTER_BOTTOM_CENTER
            0x0200  SCCMOS_FORMAT_CENTER_TOP_CENTER_BOTTOM
            0x0300  SCCMOS_FORMAT_CENTER_TOP_BOTTOM_CENTER
            0x0400  SCCMOS_FORMAT_TOP_CENTER_CENTER_BOTTOM

        For lightsheet mode, we need 0x0000 (top to bottom rolling shutter)
        """
        if self.camera is not None:
            cam_readout_format = {}
            cam_readout_format = self.camera.sdk.get_interface_output_format("edge")
            readout_format = str(cam_readout_format.get("format"))
            if self.verbose:
                print("Camera readout format:", readout_format)
        else:
            readout_format = None
        return readout_format

    # compounded methods

    def get_properties(self) -> dict[str, object]:
        if self.camera is not None:
            if self.verbose:
                print("Retrieving camera properties and current settings...")
            cam_name = {}
            cam_name = self.camera.sdk.get_camera_name()
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            cam_trigger_mode = {}
            cam_trigger_mode = self.camera.sdk.get_trigger_mode()
            cam_acquire_mode = {}
            cam_acquire_mode = self.camera.sdk.get_acquire_mode()
            cam_storage_mode = {}
            cam_storage_mode = self.camera.sdk.get_storage_mode()
            cam_recorder_mode = {}
            cam_recorder_mode = self.camera.sdk.get_recorder_submode()
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            cam_properties = {
                **cam_name,
                **cam_temperatures,
                **cam_sizes,
                **cam_trigger_mode,
                **cam_acquire_mode,
                **cam_storage_mode,
                **cam_recorder_mode,
                **cam_delay_exposure_time,
            }
        else:
            cam_properties = {}
            if self.verbose:
                print("Camera not open - Cannot retrieve properties")
        return cam_properties  # ty: ignore[unsound-return-statement]

    def grab_image(self, exposure_time_ms: int = 100) -> np.ndarray | None:
        """
        All-in-one function to grab a single image from the camera
        """
        # Works but slow if repeated in a loop
        # (setting up trigger_mode and exposure_time takes time)

        if self.verbose:
            print("Attempting to grab an image...")

        img_buffer: np.ndarray | None = None
        if self.camera is not None:
            if self.is_recording:
                if self.verbose:
                    print(" Recording already in progress. Aborted.")
            else:
                self.disarm()  # In case camera was previously armed
                self.set_trigger_mode("auto_trigger")  # Camera is internally triggered
                self.arm()  # Required to apply tigger settings
                self.set_exposure_time(
                    exposure_time_ms
                )  # Exposure time can be changed after arming the camera
                self.start_recorder(1)  # Start a recording session to acquire one frame
                self.monitor_recorder(
                    1
                )  # Monitors recording; returns once one image is acquired
                self.stop_recorder()  # Stop recording before image is copied to memory
                img_buffer = self.copy_recorder_images(
                    1
                )  # Returns recorded images or None when no data is ready

                if (
                    self.recorder_timeout_status
                ):  # Check if we had a timeout before deleting the recorder
                    if self.verbose:
                        print(" Timeout while acquiring image.")
                elif img_buffer is None:
                    if self.verbose:
                        print(" No image data available.")
                else:
                    if self.verbose:
                        print(" Image successfully obtained.")

                self.delete_recorder()  # Recording session can now be deleted
        else:
            if self.verbose:
                print(" Camera not open. Aborted")
        if img_buffer is not None:
            # Returning first (and only) image from the buffer.
            return img_buffer[0]
        return None


if __name__ == "__main__":
    testcam = Camera()
    testimage = testcam.grab_image(exposure_time_ms=50)
