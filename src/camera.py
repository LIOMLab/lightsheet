import sys
sys.path.append(".")

import os
import time
import ctypes as C
import numpy as np

class Camera:

    def __init__(self, verbose=True):
        # Error status
        self.error = 0
        self.error_message = ""

        # State flags
        self.is_open = False

        # Default attributes
        self.verbose = verbose
        self.camera_handle = C.c_void_p(0)

        if self.verbose: 
            print("Opening camera...")
        try:
            # This command opens the first PCO camera (not supporting multiple cameras)
            dll.open_camera(self.camera_handle, 0)
            assert self.camera_handle.value is not None
        except (WindowsError, AssertionError):
            if self.verbose:
                print("Failed to open the camera.")
                print(" *Is the camera on, and plugged into the computer?")
                print(" *Is CamWare running? It shouldn't be!")
            self.error = 1
            self.error_message = 'Failed to open the camera'
        else:
            self.is_open = True
            self._get_camera_type()
            if self.verbose:
                print(" PCO.%s camera open." % self.camera_type)
            dll.reset_settings_to_default(self.camera_handle)
            self.disarm()
            self._refresh_camera_setting_attributes()
        return None

    def close(self):
        if self.is_open:
            self.disarm()
            if self.verbose: 
                print("Closing PCO.%s camera..." % self.camera_type)
            dll.close_camera(self.camera_handle)
            if self.verbose: 
                print(" Camera closed.")
        return None

    def get_name(self):
        if self.is_open:
            name = self.camera_type
        else:
            name = 'No camera initialized'
        return name

    def get_xsize(self):
        if self.is_open:
            xsize = self.width
        else:
            xsize = 1
        return xsize
    
    def get_ysize(self):
        if self.is_open:
            ysize = self.height
        else:
            ysize = 1
        return ysize

    def get_camera_temperature(self):
        if self.is_open:
            camera_temperature = self.temperature['camera_temp']
        else:
            camera_temperature = 100
        return camera_temperature

    def get_sensor_temperature(self):
        if self.is_open:
            sensor_temperature = self.temperature['ccd_temp']
        else:
            sensor_temperature = 100
        return sensor_temperature

    def get_power_temperature(self):
        if self.is_open:
            power_temperature = self.temperature['power_supply_temp']
        else:
            power_temperature = 100
        return power_temperature

    def get_trigger_mode(self):
        if self.is_open:
            trigger_mode = self.trigger_mode
        else:
            trigger_mode = 'N/A'
        return trigger_mode

    def get_delay_time(self):
        if self.is_open:
            delay_time = self.delay_time_microseconds
        else:
            delay_time = 0
        return delay_time

    def get_delay_timebase(self):
        return '\u03BCs'

    def get_exposure_time(self):
        if self.is_open:
            exposure_time = self.exposure_time_microseconds
        else:
            exposure_time = 0
        return exposure_time

    def get_exposure_timebase(self):
        return '\u03BCs'
        
    def get_acquire_mode(self):
        if self.is_open:
            acquire_mode = self.acquire_mode
        else:
            acquire_mode = 'N/A'
        return acquire_mode

    def get_storage_mode(self):
        if self.is_open:
            storage_mode = self.storage_mode
        else:
            storage_mode = 'N/A'
        return storage_mode

    def get_recorder_submode(self):
        if self.is_open:
            recorder_submode = self.recorder_submode
        else:
            recorder_submode = 'N/A'
        return recorder_submode

    def apply_settings(self, trigger='auto_trigger', exposure_time_microseconds=10000, region_of_interest={'left': 1, 'right': 2560, 'top': 1, 'bottom': 2160}):
        """
        * 'trigger' can be 'auto_trigger' or 'external_trigger' See the
          comment block in _get_trigger_mode() for further details.
        * 'exposure_time_microseconds' can be as low as 100 and as high
          as 10000000.
        * 'region_of_interest' will be adjusted to match the nearest
          legal ROI that the camera supports. See _legalize_roi() for
          details.
        """
        if self.is_open:
            if trigger is None:
                trigger = self.trigger_mode
            if exposure_time_microseconds is None:
                exposure_time_microseconds = self.exposure_time_microseconds
            if region_of_interest is None:
                region_of_interest = self.roi
            if self.armed: 
                self.disarm()
            if self.verbose: 
                print("Applying settings to camera...")
            
            # These settings matter, but we don't expose their functionality
            # through apply_settings():
            dll.reset_settings_to_default(self.camera_handle)
            self._set_sensor_format('standard')
            self._set_acquire_mode('auto')
            self._set_pixel_rate({'edge 4.2': 272250000,
                                'edge 4.2 bi': 46000000,
                                'edge 5.5': 160000000,
                                }[self.camera_type])

            # I think these settings don't matter for the pco.edge, but just in case...
            self._set_storage_mode('recorder')
            self._set_recorder_submode('ring_buffer')

            # These settings change all the time:
            self._set_trigger_mode(trigger)
            self._set_exposure_time(exposure_time_microseconds)
            self._set_roi(region_of_interest)

            # It's good to check the camera health periodically.
            camera_health = self._get_camera_health()
            for k, v in camera_health.items():
                assert v == 0
        return None

    def arm(self, num_buffers=None):
        if self.is_open:
            if not hasattr(self, '_default_num_buffers'):
                self._default_num_buffers = 2
            if num_buffers is None:
                num_buffers = self._default_num_buffers
            assert 1 <= num_buffers <= 16
            self._default_num_buffers = num_buffers
            if self.armed:
                self.disarm()
            if self.verbose: 
                print("Arming camera...")
            dll.arm_camera(self.camera_handle)
            wXRes, wYRes, wXResMax, wYResMax = (C.c_uint16(), C.c_uint16(), C.c_uint16(), C.c_uint16())
            dll.get_sizes(self.camera_handle, wXRes, wYRes, wXResMax, wYResMax)
            self.width, self.height = wXRes.value, wYRes.value
            self.bytes_per_image = self.width * self.height * 2 # 16 bit images (2 bytes per pixel)

            # Allocate buffers that the camera will use to hold images.
            self.buffer_pointers = []
            for i in range(num_buffers):
                buffer_number = C.c_int16(-1)
                self.buffer_pointers.append(C.POINTER(C.c_uint16)()) #Woo!
                buffer_event = C.c_void_p(0)
                dll.allocate_buffer(self.camera_handle, buffer_number, self.bytes_per_image, self.buffer_pointers[-1], buffer_event)

            dll.set_image_parameters(self.camera_handle, self.width, self.height)
            dll.set_recording_state(self.camera_handle, 1)
            self.armed = True
            if self.verbose: print(" Camera armed.")

            # Add our allocated buffers to the camera's 'driver queue'
            self.added_buffers = []
            for buf_num in range(len(self.buffer_pointers)):
                dll.add_buffer(self.camera_handle, 0, 0, buf_num, self.width, self.height, 16)
                self.added_buffers.append(buf_num)
            self._dll_status = C.c_uint32()
            self._driver_status = C.c_uint32()
            self._image_datatype = C.c_uint16 * self.width * self.height
        return None

    def disarm(self):
        if self.is_open:
            if not hasattr(self, 'armed'):
                self.armed = False
            if self.verbose: 
                print("Disarming camera...")
            dll.set_recording_state(self.camera_handle, 0)
            dll.cancel_images(self.camera_handle)
            if hasattr(self, 'buffer_pointers'): #free allocated buffers
                for buf in range(len(self.buffer_pointers)):
                    dll.free_buffer(self.camera_handle, buf)
                self.buffer_pointers = []
            self.armed = False
            if self.verbose: 
                print(" Camera disarmed.")
        return None

    def record_to_memory(self, num_images, preframes=0, out=None, first_frame=0, sleep_timeout=1000):
        return_value = None
        if self.is_open:
            if not self.armed:
                self.arm()
            # We'll store our images in a numpy array. Did the user provide
            # one, or should we allocate one ourselves?
            if out is None:
                first_frame = 0
                out = np.zeros((num_images - preframes, self.height, self.width), 'uint16')
                out[:, 1, 1].fill(1) # For error checking empty images
                return_value = out
            else:
                return_value = None # Output is placed in the 'out' array
            try:
                assert len(out.shape) == 3
                assert (out.shape[0] - first_frame) >= (num_images - preframes)
                assert (out.shape[1], out.shape[2]) == (self.height, self.width)
                assert out.dtype == np.uint16
            except AssertionError:
                print("\nInput argument 'out' must have dimensions:")
                print("(>=num_images - preframes, y-resolution, x-resolution)")
                print(" and dtype='uint16'")
                raise
            except AttributeError:
                print("\nInput argument 'out' must be a numpy array",
                    "(to hold our images)")
                raise

            # Try to record some images, and try to tolerate the many
            # possible  ways this can fail.
            print("Acquiring", num_images, "images...")
            num_acquired = 0
            
            for which_im in range(num_images):
                # Hassle the camera until it gives us a buffer. The only
                # ways we exit this 'while' loop are by getting a buffer or
                # running out of patience.
                self.num_sleeps = 0
                start_time = time.perf_counter()
                while True:
                    # Check if a buffer is ready
                    self.num_polls += 1
                    dll.get_buffer_status(self.camera_handle, self.added_buffers[0], self._dll_status, self._driver_status)
                    if self._dll_status.value == 0xc0008000:
                        buffer_number = self.added_buffers.pop(0)#Removed from queue
                        break
                    # The buffer isn't ready. 
                    # How long should we wait to try again? 
                    time.sleep(0.001)
                    self.num_sleeps += 1
                    # At some point we have to admit we probably missed a
                    # trigger, and give up. Give up after too many sleeps
                    if self.num_sleeps > sleep_timeout:
                        elapsed_time = time.perf_counter() - start_time
                        raise TimeoutError("After %i polls,"%(self.num_polls) + " %i sleeps"%(self.num_sleeps) + " and %0.3f seconds,"%(elapsed_time) + " no buffer. (%i acquired)"%(num_acquired), num_acquired=num_acquired)
                
                try:
                    if self._driver_status.value == 0x0:
                        pass
                    elif self._driver_status.value == 0x80332028:
                        # Zero the rest of the buffer
                        out[max(0, first_frame + (which_im - preframes)):, :, :].fill(0)
                        raise DMAError('DMA error during record_to_memory')
                    else:
                        print("Driver status:", self._driver_status.value)
                        raise UserWarning("Buffer status error")
                    if which_im >= preframes:
                        # http://stackoverflow.com/a/13481676
                        image = np.ctypeslib.as_array(self._image_datatype.from_address(C.addressof(self.buffer_pointers[buffer_number].contents))) #Temporary!
                        out[first_frame + (which_im - preframes), :, :] = image
                        num_acquired += 1
                finally:
                    dll.add_buffer(self.camera_handle, 0, 0, buffer_number, self.width, self.height, 16) #Put the buffer back in the driver queue
                    self.added_buffers.append(buffer_number)
            if self.verbose: print("Done acquiring.")
        return return_value

    def _refresh_camera_setting_attributes(self):
        """
        There are two ways to access a camera setting:

         1. Ask the camera directly, using a self._get_*() - type method.

          This interrogates the camera via a DLL call, updates the
          relevant attribute(s) of the Edge object, and returns the
          relevant value(s). This is slower, because you have to wait for
          round-trip communication, but gets you up-to-date info.

         2. Access an attribute of the camera object, e.g. self.roi

          This ignores the camera, which is very fast, but the resulting
          value could potentially be inconsistent with the camera's true
          setting (although I hope it isn't!)

        _refresh_camera_setting_attributes() is a convenience function
        to update all the camera attributes at once. Call it if you're
        nervous, I guess.
        """
        if self.verbose: 
            print("Retrieving settings from camera...")
        self._get_camera_type()
        self._get_timestamp_mode()
        self._get_sensor_format()
        self._get_trigger_mode()
        self._get_storage_mode()
        self._get_recorder_submode()
        self._get_acquire_mode()
        self._get_pixel_rate()
        self._get_exposure_time()
        self._get_roi()
        self._get_temperature()
        self._get_camera_health()
        return None

    def _get_timestamp_mode(self):
        wTimeStamp = C.c_uint16(777) #777 is not an expected output
        dll.get_timestamp_mode(self.camera_handle, wTimeStamp)
        assert wTimeStamp.value in (0, 1, 2, 3) #wTimeStamp.value should change
        mode_names = {0: "off", 1: "binary", 2: "binary+ASCII", 3: "ASCII"}
        if self.verbose:
            print(" Timestamp mode:", mode_names[wTimeStamp.value])
        self.timestamp_mode = mode_names[wTimeStamp.value]
        return self.timestamp_mode

    def _set_timestamp_mode(self, mode='off'):
        mode_numbers = {"off": 0, "binary": 1, "binary+ASCII": 2, "ASCII": 3}
        if self.verbose:
            print(" Setting timestamp mode to:", mode)
        dll.set_timestamp_mode(self.camera_handle, mode_numbers[mode])
        assert self._get_timestamp_mode() == mode
        return self.timestamp_mode

    def _get_sensor_format(self):
        wSensor = C.c_uint16(777) #777 is not an expected output
        dll.get_sensor_format(self.camera_handle, wSensor)
        assert wSensor.value in (0, 1) #wSensor.value should change
        mode_names = {0: "standard", 1: "extended"}
        if self.verbose:
            print(" Sensor format:", mode_names[wSensor.value])
        self.sensor_format = mode_names[wSensor.value]
        return self.sensor_format

    def _set_sensor_format(self, mode='standard'):
        mode_numbers = {"standard": 0, "extended": 1}
        if self.verbose:
            print(" Setting sensor format to:", mode)
        dll.set_sensor_format(self.camera_handle, mode_numbers[mode])
        assert self._get_sensor_format() == mode
        return self.sensor_format

    def _get_camera_health(self):
        dwWarn, dwErr, dwStatus = (C.c_uint32(), C.c_uint32(), C.c_uint32())
        dll.get_camera_health(self.camera_handle, dwWarn, dwErr, dwStatus)
        if self.verbose:
            print(" Camera health status:", end='')
            print("  Warnings:", dwWarn.value, end='')
            if dwWarn.value == 0:
                print(" (good)", end='')
            else:
                print("***BAD***")
            print(" / Errors:", dwErr.value, end='')
            if dwErr.value == 0:
                print(" (good)", end='')
            else:
                print("***BAD***")
            print(" / Status:", dwStatus.value)
        self.camera_health = {'warnings': dwWarn.value, 'errors': dwErr.value, 'status': dwStatus.value}
        return self.camera_health

    def _get_temperature(self):
        ccdtemp, camtemp, powtemp = (C.c_int16(), C.c_int16(), C.c_int16())
        dll.get_temperature(self.camera_handle, ccdtemp, camtemp, powtemp)
        if self.verbose:
            print(" Temperatures:",
                  "CCD", ccdtemp.value * 0.1, "C /",
                  "camera", camtemp.value, "C /",
                  "power supply", powtemp.value, "C ")
        self.temperature = {'ccd_temp': ccdtemp.value * 0.1, 'camera_temp': camtemp.value, 'power_supply_temp': powtemp.value}
        return self.temperature

    def _get_trigger_mode(self):
        """
        0x0000 = [auto trigger]
        A new image exposure is automatically started best possible
        compared to the readout of an image. If a CCD is used and the
        images are taken in a sequence, then exposures and sensor readout
        are started simultaneously. Signals at the trigger input (<exp
        trig>) are irrelevant.
        - 0x0001 = [software trigger]:
        An exposure can only be started by a force trigger command.
        - 0x0002 = [extern exposure & software trigger]:
        A delay / exposure sequence is started at the RISING or FALLING
        edge (depending on the DIP switch setting) of the trigger input
        (<exp trig>).
        - 0x0003 = [extern exposure control]:
        The exposure time is defined by the pulse length at the trigger
        input(<exp trig>). The delay and exposure time values defined by
        the set/request delay and exposure command are ineffective.
        (Exposure time length control is also possible for double image
        mode; exposure time of the second image is given by the readout
        time of the first image.)
        """
        trigger_mode_names = {0: "auto_trigger", 1: "software_trigger", 2: "external_trigger", 3: "external_exposure"}
        wTriggerMode = C.c_uint16()
        dll.get_trigger_mode(self.camera_handle, wTriggerMode)
        if self.verbose:
            print(" Trigger mode:", trigger_mode_names[wTriggerMode.value])
        self.trigger_mode = trigger_mode_names[wTriggerMode.value]
        return self.trigger_mode

    def _set_trigger_mode(self, mode="auto_trigger"):
        trigger_mode_numbers = {"auto_trigger": 0, "software_trigger": 1, "external_trigger": 2, "external_exposure": 3}
        if self.verbose: 
            print(" Setting trigger mode to:", mode)
        dll.set_trigger_mode(self.camera_handle, trigger_mode_numbers[mode])
        assert self._get_trigger_mode() == mode
        return self.trigger_mode

    def _force_trigger(self):
        assert self.trigger_mode in ('software_trigger', 'external_trigger')
        wTriggerMode = C.c_uint16()
        dll.force_trigger(self.camera_handle, wTriggerMode)
        assert wTriggerMode.value in (0, 1)
        return bool(wTriggerMode.value)

    def _get_storage_mode(self):
        wStorageMode = C.c_uint16()
        dll.get_storage_mode(self.camera_handle, wStorageMode)
        storage_mode_names = {0: "recorder", 1: "FIFO_buffer"}
        if self.verbose:
            print(" Storage mode:", storage_mode_names[wStorageMode.value])
        self.storage_mode = storage_mode_names[wStorageMode.value]
        return self.storage_mode

    def _set_storage_mode(self, mode="recorder"):
        storage_mode_numbers = {"recorder": 0, "FIFO_buffer": 1}
        if self.verbose: 
            print(" Setting storage mode to:", mode)
        dll.set_storage_mode(self.camera_handle, storage_mode_numbers[mode])
        assert self._get_storage_mode() == mode
        return self.storage_mode

    def _get_recorder_submode(self):
        wRecSubmode = C.c_uint16(1)
        dll.get_recorder_submode(self.camera_handle, wRecSubmode)
        recorder_submode_names = {0: "sequence", 1: "ring_buffer"}
        if self.verbose:
            print(" Recorder submode:", recorder_submode_names[wRecSubmode.value])
        self.recorder_submode = recorder_submode_names[wRecSubmode.value]
        return self.recorder_submode

    def _set_recorder_submode(self, mode="ring_buffer"):
        recorder_mode_numbers = {"sequence": 0, "ring_buffer": 1}
        if self.verbose: 
            print(" Setting recorder submode to:", mode)
        dll.set_recorder_submode(self.camera_handle, recorder_mode_numbers[mode])
        assert self._get_recorder_submode() == mode
        return self.recorder_submode

    def _get_acquire_mode(self):
        wAcquMode = C.c_uint16(0)
        dll.get_acquire_mode(self.camera_handle, wAcquMode)
        acquire_mode_names = {0: "auto", 1: "external_static", 2: "external_dynamic"}
        if self.verbose:
            print(" Acquire mode:", acquire_mode_names[wAcquMode.value])
        self.acquire_mode = acquire_mode_names[wAcquMode.value]
        return self.acquire_mode

    def _set_acquire_mode(self, mode='auto'):
        acquire_mode_numbers = {"auto": 0, "external_static": 1, "external_dynamic": 2}
        if self.verbose: 
            print(" Setting acquire mode to:", mode)
        dll.set_acquire_mode(self.camera_handle, acquire_mode_numbers[mode])
        assert self._get_acquire_mode() == mode
        return self.acquire_mode

    def _get_pixel_rate(self):
        dwPixelRate = C.c_uint32(0)
        dll.get_pixel_rate(self.camera_handle, dwPixelRate)
        if self.verbose: 
            print(" Pixel rate:", dwPixelRate.value)
        self.pixel_rate = dwPixelRate.value
        assert dwPixelRate.value != 0
        return self.pixel_rate

    def _set_pixel_rate(self, rate=272250000):
        if self.verbose: 
            print(" Setting pixel rate to:", rate)
        dll.set_pixel_rate(self.camera_handle, rate)
        assert self._get_pixel_rate() == rate
        return self.pixel_rate

    def _get_exposure_time(self):
        dwDelay = C.c_uint32(0)
        wTimeBaseDelay = C.c_uint16(1)
        dwExposure = C.c_uint32(0)
        wTimeBaseExposure = C.c_uint16(1)
        dll.get_delay_exposure_time(self.camera_handle, dwDelay, dwExposure, wTimeBaseDelay, wTimeBaseExposure)
        time_base_mode_names = {0: "nanoseconds", 1: "microseconds", 2: "milliseconds"}
        if self.verbose:
            print(" Exposure:", dwExposure.value, time_base_mode_names[wTimeBaseExposure.value])
        if self.verbose:
            print(" Delay:", dwDelay.value, time_base_mode_names[wTimeBaseDelay.value])
        self.exposure_time_microseconds = (dwExposure.value * 10.**(3*wTimeBaseExposure.value - 3))
        self.delay_time_microseconds = (dwDelay.value * 10.**(3*wTimeBaseExposure.value - 3))
        return self.exposure_time_microseconds

    def _set_exposure_time(self, exposure_time_microseconds=10000):
        exposure_time_microseconds = int(exposure_time_microseconds)
        if self.camera_type in ('edge 4.2', 'edge 5.5'):
            assert 1e2 <= exposure_time_microseconds <= 1e7
        if self.verbose:
            print(" Setting exposure time to", exposure_time_microseconds, "us")
        dll.set_delay_exposure_time(self.camera_handle, 0, exposure_time_microseconds, 1, 1)
        self._get_exposure_time()
        if self.camera_type == 'edge 4.2 bi':
            tolerance = 6
        else:
            tolerance = 0
        assert abs(self.exposure_time_microseconds - exposure_time_microseconds) <= tolerance
        return self.exposure_time_microseconds

    def _get_roi(self):
        wRoiX0, wRoiY0, wRoiX1, wRoiY1 = (C.c_uint16(), C.c_uint16(), C.c_uint16(), C.c_uint16())
        dll.get_roi(self.camera_handle, wRoiX0, wRoiY0, wRoiX1, wRoiY1)
        if self.verbose:
            print(" Camera ROI:");
            print("  From pixel", wRoiX0.value, "to pixel", wRoiX1.value, "(left/right)")
            print("  From pixel", wRoiY0.value, "to pixel", wRoiY1.value, "(up/down)")
        self.roi = {'left': wRoiX0.value, 'top': wRoiY0.value, 'right': wRoiX1.value, 'bottom': wRoiY1.value}
        self.width = self.roi['right'] - self.roi['left'] + 1
        self.height = self.roi['bottom'] - self.roi['top'] + 1
        self.rolling_time_microseconds = self._calculate_rolling_time_us(wRoiY0.value, wRoiY1.value)
        return self.roi

    def _calculate_rolling_time_us(self, y0, y1):
        '''How long do we expect the chip to spend rolling, in microseconds?

        Both the 4.2 and the 5.5 take ~10 ms to roll the full chip. Calculate
        the fraction of the chip we're using and estimate the rolling
        time.
        '''
        if self.camera_type == 'edge 4.2':
            max_lines = 1024
            full_chip_rolling_time = 1e4
        elif self.camera_type == 'edge 5.5':
            max_lines = 1080
            full_chip_rolling_time = 1e4
        elif self.camera_type in ('edge 4.2 bi'):
            max_lines = 1024
            full_chip_rolling_time = 2.5e4 
        chip_fraction = max(y1 - max_lines, max_lines + 1 - y0) / max_lines
        return full_chip_rolling_time * chip_fraction

    def _set_roi(self, region_of_interest):
        roi = self._legalize_roi(region_of_interest)
        dll.set_roi(self.camera_handle, roi['left'], roi['top'], roi['right'], roi['bottom'])
        assert self._get_roi() == roi
        return self.roi

    def _get_camera_type(self):
        camera_name = C.c_char_p(b' '*40)
        dll.get_camera_name(self.camera_handle, camera_name, 40)
        name2type = {'pco.edge rolling shutter 4.2': 'edge 4.2',
                     'pco.edge 4.2 bi': 'edge 4.2 bi',
                     'pco.edge 5.5m USB global shutter': 'edge 5.5',
                    }
        try:
            self.camera_type = name2type[camera_name.value.decode('ascii')]
        except KeyError:
            raise UserWarning('Unexpected camera type - %s' % camera_name.value)
        return self.camera_type

    def _legalize_roi(self, roi, camera_type='edge 5.5', current_roi=None):
        """
        There are lots of ways a requested region of interest (ROI) can
        be illegal. This utility function returns a nearby legal ROI.

        Optionally, you can leave keys of 'roi' unspecified, and
        _legalize_roi() tries to return reasonable choices based on
        the values in current_roi.
        """
        left = roi.get('left')
        right = roi.get('right')
        bottom = roi.get('bottom')
        top = roi.get('top')
        if self.verbose:
            print(" Requested camera ROI:")
            print("  From pixel", left, "to pixel", right, "(left/right)")
            print("  From pixel", top, "to pixel", bottom, "(up/down)")
        min_lr, min_ud = 1, 1
        if camera_type == 'edge 4.2':
            min_width, min_height = 40, 10
            max_lr, max_ud, step_lr, = 2060, 2048, 20
        elif camera_type == 'edge 4.2 bi':
            min_width, min_height = 32, 16
            max_lr, max_ud, step_lr, = 2048, 2048, 32
        elif camera_type == 'edge 5.5':
            min_width, min_height = 160, 10
            max_lr, max_ud, step_lr = 2560, 2160, 160
        if current_roi is None:
            current_roi = {'left': min_lr, 'right':  max_lr,
                        'top':  min_ud, 'bottom': max_ud}
        # Legalize left/right
        if left is None and right is None:
            # User isn't trying to change l/r ROI; use existing ROI.
            left, right = current_roi['left'], current_roi['right']
        elif left is not None:
            # 'left' is specified, 'left' is the master.
            if left < min_lr: #Legalize 'left'
                left = min_lr
            elif left > max_lr - min_width + 1:
                left = max_lr - min_width + 1
            else:
                left = 1 + step_lr*((left - 1) // step_lr)
            if right is None: #Now legalize 'right'
                right = current_roi['right']
            if right < left + min_width - 1:
                right = left + min_width - 1
            elif right > max_lr:
                right = max_lr
            else:
                right = left - 1 + step_lr*((right - (left - 1)) // step_lr)
        else:
            # 'left' is unspecified, 'right' is specified. 'right' is the master.
            if right > max_lr: #Legalize 'right'
                right = max_lr
            elif right < min_lr - 1 + min_width:
                right = min_width
            else:
                right = step_lr * (right  // step_lr)
            left = current_roi['left'] #Now legalize 'left'
            if left > right - min_width + 1:
                left = right - min_width + 1
            elif left < min_lr:
                left = min_lr
            else:
                left = right + 1 - step_lr * ((right - (left - 1)) // step_lr)
        assert min_lr <= left < left + min_width - 1 <= right <= max_lr
        # Legalize top/bottom
        if top is None and bottom is None:
            # User isn't trying to change u/d ROI; use existing ROI.
            top, bottom = current_roi['top'], current_roi['bottom']
        elif top is not None:
            # 'top' is specified, 'top' is the master.
            if top < min_ud: #Legalize 'top'
                top = min_ud
            if top > (max_ud - min_height)//2 + 1:
                top = (max_ud - min_height)//2 + 1
            bottom = max_ud - top + 1 #Now bottom is specified
        else:
            # 'top' is unspecified, 'bottom' is specified, 'bottom' is the master.
            if bottom > max_ud: #Legalize 'bottom'
                bottom = max_ud
            if bottom < (max_ud + min_height)//2:
                bottom = (max_ud + min_height)//2
            top = max_ud - bottom + 1 #Now 'top' is specified
        assert min_ud <= top < top + min_height - 1 <= bottom <= max_ud
        new_roi = {'left': left, 'top': top, 'right': right, 'bottom': bottom}
        if self.verbose and new_roi != roi:
            print(" ***Requested ROI must be adjusted to match the camera***")
        return new_roi


def reboot_camera(verbose=False):
    """ Reboot the attached camera. 

        While this appears to work and recover the camera from a number
        of error states, until recently, we always ran this as a
        stand-alone script.

        If you need to reboot the camera from within a script, the steps are:
            * dll.reboot_camera
            * dll.close_camera
            * wait for reboot to complete
            * dll.reset_dll
            * dll.open_camera
    """
    if verbose:
        print('Rebooting camera...')
    camera_handle = C.c_void_p(0)
    dll.open_camera(camera_handle, 0)
    dll.reboot_camera(camera_handle)
    dll.close_camera(camera_handle)

    if verbose:
        print('Reconnecting to camera...', flush=True)
    t0, timeout = time.perf_counter(), 10
    while True:
        # Reboot time is approximate, keep trying to open the camera until 
        # we are sucessful or timeout has elapsed.
        try:
            dll.reset_dll()
            dll.open_camera(camera_handle, 0)
        except OSError as e:
            if time.perf_counter() - t0 > timeout: 
                raise
            time.sleep(0.2)
        else:
            dll.close_camera(camera_handle)
            if verbose:
                print('Done reconnecting.')
            return


def decode_timestamps(image_stack):
    """Decode PCO image timestamps from binary-coded decimal."""
    assert len(image_stack.shape) == 3
    assert image_stack.dtype == 'uint16'
    timestamps = image_stack[:, 0, :14]
    timestamps = (timestamps & 0x0F) + (timestamps >> 4) * 10
    ts = {}
    ts['image_number'] = np.sum(timestamps[:, :4] * np.array((1e6, 1e4, 1e2, 1)), axis=1, dtype='uint32')
    ts['year'] = np.sum(timestamps[:, 4:6] * np.array((1e2, 1)), axis=1, dtype='uint32')
    ts['month'] = timestamps[:, 6].astype('uint32')
    ts['day'] = timestamps[:, 7].astype('uint32')
    ts['microseconds'] = np.sum(timestamps[:, 8:14] * np.array((3600e6, 60e6, 1e6, 1e4, 1e2, 1)), axis=1, dtype='uint64')
    return ts



# A few types of exception we'll use during recording:
class TimeoutError(Exception):
    def __init__(self, value, num_acquired=0):
        self.value = value
        self.num_acquired = num_acquired
    def __str__(self):
        return repr(self.value)

class DMAError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


# DLL management
try:
    dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SC2_Cam.dll')
    dll = C.oledll.LoadLibrary(dll_path)
except WindowsError:
    print("Failed to load SC2_Cam.dll")
    print("You need this to run camera.py")
    raise

dll.get_error_text = dll.PCO_GetErrorText
dll.get_error_text.argtypes = [C.c_uint32, C.c_char_p, C.c_uint32]
def check_error(error_code):
    if error_code == 0:
        return 0
    else:
        error_description = C.c_char_p(b'*'*1000)
        dll.get_error_text(error_code, error_description, 1000)
        raise OSError(error_description.value.decode('ascii'))

dll.open_camera = dll.PCO_OpenCamera
dll.open_camera.argtypes = [C.POINTER(C.c_void_p), C.c_uint16]
dll.open_camera.restype = check_error

dll.close_camera = dll.PCO_CloseCamera
dll.close_camera.argtypes = [C.c_void_p]
dll.close_camera.restype = check_error

dll.arm_camera = dll.PCO_ArmCamera
dll.arm_camera.argtypes = [C.c_void_p]
dll.arm_camera.restype = check_error

dll.allocate_buffer = dll.PCO_AllocateBuffer
dll.allocate_buffer.argtypes = [C.c_void_p, C.POINTER(C.c_int16), C.c_uint32, C.POINTER(C.POINTER(C.c_uint16)), C.POINTER(C.c_void_p)]
dll.allocate_buffer.restype = check_error

dll.add_buffer = dll.PCO_AddBufferEx
dll.add_buffer.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_int16, C.c_uint16, C.c_uint16, C.c_uint16]
dll.add_buffer.restype = check_error

dll.get_buffer_status = dll.PCO_GetBufferStatus
dll.get_buffer_status.argtypes = [C.c_void_p, C.c_int16, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)]
dll.get_buffer_status.restype = check_error

dll.set_image_parameters = dll.PCO_CamLinkSetImageParameters
dll.set_image_parameters.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16]
dll.set_image_parameters.restype = check_error

dll.set_recording_state = dll.PCO_SetRecordingState
dll.set_recording_state.argtypes = [C.c_void_p, C.c_uint16]
dll.set_recording_state.restype = check_error

dll.get_sizes = dll.PCO_GetSizes
dll.get_sizes.argtypes = [C.c_void_p, C.POINTER(C.c_uint16), C.POINTER(C.c_uint16), C.POINTER(C.c_uint16), C.POINTER(C.c_uint16)]
dll.get_sizes.restype = check_error

dll.get_timestamp_mode = dll.PCO_GetTimestampMode
dll.get_timestamp_mode.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_timestamp_mode.restype = check_error

dll.get_sensor_format = dll.PCO_GetSensorFormat
dll.get_sensor_format.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_sensor_format.restype = check_error

dll.get_camera_health = dll.PCO_GetCameraHealthStatus
dll.get_camera_health.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)]
dll.get_camera_health.restype = check_error

dll.get_temperature = dll.PCO_GetTemperature
dll.get_temperature.argtypes = [C.c_void_p, C.POINTER(C.c_int16), C.POINTER(C.c_int16), C.POINTER(C.c_int16)]
dll.get_temperature.restype = check_error

dll.get_trigger_mode = dll.PCO_GetTriggerMode
dll.get_trigger_mode.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_trigger_mode.restype = check_error

dll.get_storage_mode = dll.PCO_GetStorageMode
dll.get_storage_mode.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_storage_mode.restype = check_error

dll.get_recorder_submode = dll.PCO_GetRecorderSubmode
dll.get_recorder_submode.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_recorder_submode.restype = check_error

dll.get_acquire_mode = dll.PCO_GetAcquireMode
dll.get_acquire_mode.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.get_acquire_mode.restype = check_error

dll.get_pixel_rate = dll.PCO_GetPixelRate
dll.get_pixel_rate.argtypes = [C.c_void_p, C.POINTER(C.c_uint32)]
dll.get_pixel_rate.restype = check_error

dll.set_pixel_rate = dll.PCO_SetPixelRate
dll.set_pixel_rate.argtypes = [C.c_void_p, C.c_uint32]
dll.set_pixel_rate.restype = check_error

dll.get_delay_exposure_time = dll.PCO_GetDelayExposureTime
dll.get_delay_exposure_time.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint16), C.POINTER(C.c_uint16)]
dll.get_delay_exposure_time.restype = check_error

dll.set_delay_exposure_time = dll.PCO_SetDelayExposureTime
dll.set_delay_exposure_time.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint16, C.c_uint16]
dll.set_delay_exposure_time.restype = check_error

dll.get_roi = dll.PCO_GetROI
dll.get_roi.argtypes = [C.c_void_p, C.POINTER(C.c_uint16), C.POINTER(C.c_uint16), C.POINTER(C.c_uint16), C.POINTER(C.c_uint16)]
dll.get_roi.restype = check_error

dll.set_roi = dll.PCO_SetROI
dll.set_roi.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16, C.c_uint16, C.c_uint16]
dll.set_roi.restype = check_error

dll.get_camera_name = dll.PCO_GetCameraName
dll.get_camera_name.argtypes = [C.c_void_p, C.c_char_p, C.c_uint16]
dll.get_camera_name.restype = check_error

dll.reset_settings_to_default = dll.PCO_ResetSettingsToDefault
dll.reset_settings_to_default.argtypes = [C.c_void_p]
dll.reset_settings_to_default.restype = check_error

dll.remove_buffer = dll.PCO_RemoveBuffer
dll.remove_buffer.argtypes = [C.c_void_p]
dll.remove_buffer.restype = check_error

dll.cancel_images = dll.PCO_CancelImages
dll.cancel_images.argtypes = [C.c_void_p]
dll.cancel_images.restype = check_error

dll.free_buffer = dll.PCO_FreeBuffer
dll.free_buffer.argtypes = [C.c_void_p, C.c_int16]
dll.free_buffer.restype = check_error

dll.set_timestamp_mode = dll.PCO_SetTimestampMode
dll.set_timestamp_mode.argtypes = [C.c_void_p, C.c_uint16]
dll.set_timestamp_mode.restype = check_error

dll.set_sensor_format = dll.PCO_SetSensorFormat
dll.set_sensor_format.argtypes = [C.c_void_p, C.c_uint16]
dll.set_sensor_format.restype = check_error

dll.set_trigger_mode = dll.PCO_SetTriggerMode
dll.set_trigger_mode.argtypes = [C.c_void_p, C.c_uint16]
dll.set_trigger_mode.restype = check_error

dll.force_trigger = dll.PCO_ForceTrigger
dll.force_trigger.argtypes = [C.c_void_p, C.POINTER(C.c_uint16)]
dll.force_trigger.restype = check_error

dll.set_recorder_submode = dll.PCO_SetRecorderSubmode
dll.set_recorder_submode.argtypes = [C.c_void_p, C.c_uint16]
dll.set_recorder_submode.restype = check_error

dll.set_acquire_mode = dll.PCO_SetAcquireMode
dll.set_acquire_mode.argtypes = [C.c_void_p, C.c_uint16]
dll.set_acquire_mode.restype = check_error

dll.set_storage_mode = dll.PCO_SetStorageMode
dll.set_storage_mode.argtypes = [C.c_void_p, C.c_uint16]
dll.set_storage_mode.restype = check_error

dll.reboot_camera = dll.PCO_RebootCamera
dll.reboot_camera.argtypes = [C.c_void_p]

dll.reset_dll = dll.PCO_ResetLib
dll.reset_dll.restype = check_error




if __name__ == '__main__':
    camera = Camera(verbose=True)
    blank_frames = 0
    for i in range(1):
        exposure = 50000
        camera.apply_settings(exposure_time_microseconds=exposure)
        camera.arm()
        images = np.zeros((1, camera.get_ysize(),camera.get_xsize()), dtype=np.uint16)
        for i in range(10):
            camera.record_to_memory(num_images=images.shape[0], out=images)
            print(i, images.min(axis=(1, 2)), images.max(axis=(1, 2)), images.shape)
            if not 0 < images.min() < images.max():
                blank_frames += 1
                print('Blank frame received (%d total)' % blank_frames)
        camera.disarm()
    print("%d blank frames received during test" % (blank_frames))
    camera.close()