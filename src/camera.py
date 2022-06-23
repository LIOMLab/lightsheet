'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import time
from datetime import datetime, timedelta
import numpy as np
import pco

from src.config import cfg_read, cfg_write, cfg_str2bool


class Camera:
    '''Class for PCO cameras'''

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults = {}
    _cfg_defaults['Shutter Mode']               = 'Lightsheet'
    _cfg_defaults['Exposure Time']              = '100'
    _cfg_defaults['Lightsheet Line Time']       = '48.80'
    _cfg_defaults['Lightsheet Exposed Lines']   = '16'
    _cfg_defaults['Lightsheet Delay Lines']     = '0'


    def __init__(self, verbose=False):
        self.verbose = verbose

        # Flags (bool)
        self.is_recording = False
        self.new_data_ready = False
        self.recorder_timeout = False

        # Other variables
        self.camera = None
        self.xsize = None
        self.ysize = None
        self.bytes_per_image = None
        self.line_time = None

        # read configurable settings from config.ini file
        self._cfg_filename = 'config.ini'
        self._cfg_section = 'Camera'
        self.cfg_load_ini()

        # Automatically open camera on instance creation
        self.open()


    def cfg_load_ini(self):
        # read configuration from ini file
        self._cfg = cfg_read(self._cfg_filename, self._cfg_section, self._cfg_defaults)
        # set instance variables from read configuration dictionary values
        self.shutter_mode                   = str(      self._cfg['Shutter Mode']               )
        self.exposure_time                  = float(    self._cfg['Exposure Time']              )   * 1e-3
        self.lightsheet_line_time           = float(    self._cfg['Lightsheet Line Time']       )   * 1e-6
        self.lightsheet_exposed_lines       = int(      self._cfg['Lightsheet Exposed Lines']   )
        self.lightsheet_delay_lines         = int(      self._cfg['Lightsheet Delay Lines']     )

    def cfg_save_ini(self):
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg['Shutter Mode']               = str( self.shutter_mode                        )
        self._cfg['Exposure Time']              = str( self.exposure_time               * 1e3   )       
        self._cfg['Lightsheet Line Time']       = str( self.lightsheet_line_time        * 1e6   ) 
        self._cfg['Lightsheet Exposed Lines']   = str( self.lightsheet_exposed_lines            )
        self._cfg['Lightsheet Delay Lines']     = str( self.lightsheet_delay_lines              )
        # write configuration to ini file
        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)


    def open(self):
        '''Open a camera'''
        if self.verbose:
            print("Opening camera...")
        if self.camera is None:
            try:
                self.camera = pco.Camera()
            except ValueError:
                if self.verbose:
                    print(" Failed to open camera.")
                self.camera = None
            else:
                sizes = {}
                sizes = self.camera.sdk.get_sizes()
                self.xsize = int(sizes.get('x'))
                self.ysize = int(sizes.get('y'))
                self.bytes_per_image = self.xsize * self.ysize * 2 # 16 bit images (2 bytes per pixel)
                self.camera.sdk.set_image_parameters(self.xsize, self.ysize)

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                self.line_time = cam_cmos_line_timing.get('line time')
                self.default_line_time = self.line_time
                if self.verbose:
                    print(" Camera opened.")
        else:
            if self.verbose:
                print(" Camera already opened.")
        return None

    def close(self):
        '''Closes an opened camera'''
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

    def arm(self):
        '''docstring'''
        if self.camera is not None:
            if self.verbose:
                print("Arming camera...")
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')
            self.camera.sdk.arm_camera()
            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.xsize = int(sizes.get('x'))
            self.ysize = int(sizes.get('y'))
            self.bytes_per_image = self.xsize * self.ysize * 2 # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.xsize, self.ysize)

            cam_cmos_line_timing = {}
            cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
            self.line_time = cam_cmos_line_timing.get('line time')

            if self.verbose:
                print(" Camera armed.")
                print(" Line time:", str(self.line_time))
        return None

    def arm_scan(self):
        if self.camera is not None:
            if self.shutter_mode == 'Lightsheet':
                if self.verbose:
                    print('Arming camera in Lightsheet mode...')
                if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                    self.camera.sdk.set_recording_state('off')
                self.set_trigger_mode('external')
                self.camera.sdk.set_cmos_line_timing('on', self.lightsheet_line_time)
                self.camera.sdk.set_cmos_line_exposure_delay(self.lightsheet_exposed_lines, self.lightsheet_delay_lines)
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get('parameter')
                self.line_time = cam_cmos_line_timing.get('line time')

                cam_cmos_line_exposure_delay = {}
                cam_cmos_line_exposure_delay = self.camera.sdk.get_cmos_line_exposure_delay()
                exposed_lines = cam_cmos_line_exposure_delay.get('lines exposure')
                delay_lines = cam_cmos_line_exposure_delay.get('lines delay')

                if self.verbose:
                    print(" Camera armed.")
                    print(" Lightsheet mode is:", str(parameter))
                    print(" Line time:", str(self.line_time))
                    print(" Exposed lines:", str(exposed_lines))
                    print(" Delay lines:", str(delay_lines))

            elif self.shutter_mode == 'Rolling':
                if self.verbose:
                    print('Arming camera in Rolling Shutter mode...')
                if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                    self.camera.sdk.set_recording_state('off')
                self.set_trigger_mode('external_exposure')
                self.camera.sdk.set_cmos_line_timing('off', self.default_line_time)
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get('parameter')
                self.line_time = cam_cmos_line_timing.get('line time')

                if self.verbose:
                    print(" Camera armed.")
                    print(" Line time:", str(self.line_time))

            elif self.shutter_mode == 'Global':
                if self.verbose:
                    print('Arming camera in Global Shutter mode...')
                if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                    self.camera.sdk.set_recording_state('off')
                self.set_trigger_mode('external_exposure')
                self.camera.sdk.set_cmos_line_timing('off', self.default_line_time)
                self.camera.sdk.arm_camera()

                cam_cmos_line_timing = {}
                cam_cmos_line_timing = self.camera.sdk.get_cmos_line_timing()
                parameter = cam_cmos_line_timing.get('parameter')
                self.line_time = cam_cmos_line_timing.get('line time')
            
                if self.verbose:
                    print(" Camera armed.")
                    print(" Line time:", str(self.line_time))

            else:
                raise Exception('Unknown shutter mode selected')

            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.xsize = int(sizes.get('x'))
            self.ysize = int(sizes.get('y'))
            self.bytes_per_image = self.xsize * self.ysize * 2 # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.xsize, self.ysize)
        return None

    def disarm(self):
        '''docstring'''
        if self.camera is not None:
            if self.verbose:
                print("Disarming camera...")
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')
            if self.verbose:
                print(" Camera disarmed.")
        return None

    # Managing recording sessions

    def start_recorder(self, number_of_images):
        '''docstring'''
        if self.camera is not None:
            try:
                if self.verbose:
                    print("Starting camera recording session...")
                self.camera.record(int(number_of_images), mode='sequence non blocking')
            except ValueError:
                if self.verbose:
                    print(" Exception while starting recorder.")
                self.is_recording = False
            else:
                self.is_recording = True
                self.recorder_timeout = False
                if self.verbose:
                    print(" Recording session started.")
        return None

    def monitor_recorder(self, number_of_images:int, timeout_s:int=5):
        '''docstring'''
        if self.is_recording:
            if self.verbose:
                print("Monitoring camera recording session status...")
            wait_until = datetime.now() + timedelta(seconds=timeout_s)
            while True:
                images_in_buffer = self.camera.rec.get_status()['dwProcImgCount']
                if images_in_buffer >= number_of_images:
                    self.new_data_ready = True
                    if self.verbose:
                        print(" Recording session succeeded:", images_in_buffer, "images in buffer")
                    break
                elif wait_until < datetime.now():
                    self.recorder_timeout = True
                    if self.verbose:
                        print(" Timeout :", images_in_buffer, "images in buffer after", timeout_s, "s.",)
                    break
                else:
                    time.sleep(0.01)
        return None

    def stop_recorder(self):
        '''docstring'''
        if self.is_recording:
            self.camera.stop()
            self.is_recording = False
        return None

    def copy_recorder_images(self, number_of_images):
        '''docstring'''
        if self.new_data_ready:
            images, metadatas = self.camera.images(blocksize=number_of_images)
            self.new_data_ready = False
        else:
            images = np.zeros((number_of_images,self.ysize,self.xsize), dtype=np.uint16)
        return images

    def delete_recorder(self):
        '''docstring'''
        if self.camera is not None:
            self.camera.rec.delete()
            # Deleting the recording session also deletes any remaining images
            self.new_data_ready = False
            self.recorder_timeout = False
        return None


    ### setters

    def set_exposure_time(self, exposure_time:int):
        '''Set the exposure time (in ms) for the camera'''
        if self.camera is not None:
            if self.verbose:
                print("Setting camera exposure time: " + str(exposure_time) + "ms")
            self.camera.sdk.set_delay_exposure_time(0, 'ms', exposure_time, 'ms')
        return None

    def set_lightsheet_mode(self):
        '''Set lightsheet timing according to current instance settings'''
        if self.camera is not None:
            self.camera.sdk.set_cmos_line_timing('on', self.lightsheet_line_time)
            self.camera.sdk.set_cmos_line_exposure_delay(self.lightsheet_exposed_lines, self.lightsheet_delay_lines)

            cam_line_timing = {}
            cam_line_timing = self.camera.sdk.get_cmos_line_timing()
            line_timing = cam_line_timing.get('line time')

            cam_line_exposure_delay = {}
            cam_line_exposure_delay = self.camera.sdk.get_cmos_line_exposure_delay()
            line_exposure = cam_line_exposure_delay.get('lines exposure')
            line_delay = cam_line_exposure_delay.get('lines delay')

            if self.verbose:
                print("Camera in lightsheet mode")
                print("Camera line timing is:", str(line_timing))
                print("Camera line exposure is:", str(line_exposure))
                print("Camera line delay is:", str(line_delay))
        return None


    def set_trigger_mode(self, trigger_mode:str):
        '''Set the trigger mode for the camera

        'auto_trigger':         Exposure of a new image is started automatically, according to the currently set
                                timing parameters. Signals at the trigger input line are irrelevant

        'external':             A delay / exposure sequence is started depending on the HW signal at the trigger
                                input line or by a force trigger software command

        'external_exposure':    An exposure sequence is started depending on the HW signal at the trigger input
                                line. The exposure time is defined by the pulse length of the HW signal. The delay
                                and exposure timing parameters are ineffective.
        '''
        if self.camera is not None:
            if self.verbose:
                print("Setting camera trigger mode:", trigger_mode)
            if self.is_recording:
                if self.verbose:
                    print(" Recording in progress. Trigger mode cannot be changed while recording.")
            else:
                if trigger_mode == 'auto_trigger':
                    self.camera.sdk.set_trigger_mode('auto sequence')
                elif trigger_mode == 'external':
                    self.camera.sdk.set_trigger_mode('external exposure start & software trigger')
                elif trigger_mode == 'external_exposure':
                    self.camera.sdk.set_trigger_mode('external exposure control')
        return None


    ### getters

    def get_name(self):
        '''Returns the camera name'''
        if self.camera is not None:
            cam_name = {}
            cam_name = self.camera.sdk.get_camera_name()
            name = str(cam_name.get('camera name'))
            if self.verbose:
                print("Camera name:", name)
        else:
            name = None
        return name

    def get_camera_temperature(self):
        '''Returns the current internal temperatures in Celcius'''
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            camera_temperature = float(cam_temperatures.get('camera temperature'))
            if self.verbose:
                print("Camera internal temperature:", camera_temperature)
        else:
            camera_temperature = None
        return camera_temperature

    def get_sensor_temperature(self):
        '''Returns the current sensor temperatures in Celcius'''
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            sensor_temperature = float(cam_temperatures.get('sensor temperature'))
            if self.verbose:
                print("Camera sensor temperature:", sensor_temperature)
        else:
            sensor_temperature = None
        return sensor_temperature

    def get_power_temperature(self):
        '''Returns the current power supply temperatures in Celcius'''
        if self.camera is not None:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            power_temperature = float(cam_temperatures.get('power temperature'))
            if self.verbose:
                print("Camera power supply temperature:", power_temperature)
        else:
            power_temperature = None
        return power_temperature

    def get_xsize(self):
        '''Returns the current armed image x-size of the camera'''
        if self.camera is not None:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_xsize = int(cam_sizes.get('x'))
            if self.verbose:
                print("Camera x-size:", current_xsize)
        else:
            current_xsize = None
        return current_xsize

    def get_ysize(self):
        '''Returns the current armed image y-size of the camera'''
        if self.camera is not None:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_ysize = int(cam_sizes.get('y'))
            if self.verbose:
                print("Camera y-size:", current_ysize)
        else:
            current_ysize = None
        return current_ysize

    def get_trigger_mode(self):
        '''Returns the current trigger mode'''
        if self.camera is not None:
            cam_trigger_mode = {}
            cam_trigger_mode = self.camera.sdk.get_trigger_mode()
            trigger_mode = str(cam_trigger_mode.get('trigger mode'))
            if self.verbose:
                print("Camera trigger mode:", trigger_mode)
        else:
            trigger_mode = None
        return trigger_mode

    def get_acquire_mode(self):
        '''Returns the current acquire mode'''
        if self.camera is not None:
            cam_acquire_mode = {}
            cam_acquire_mode = self.camera.sdk.get_acquire_mode()
            acquire_mode = str(cam_acquire_mode.get('acquire mode'))
            if self.verbose:
                print("Camera acquire mode:", acquire_mode)
        else:
            acquire_mode = None
        return acquire_mode

    def get_storage_mode(self):
        '''Returns the current storage mode'''
        if self.camera is not None:
            cam_storage_mode = {}
            cam_storage_mode = self.camera.sdk.get_storage_mode()
            storage_mode = str(cam_storage_mode.get('storage mode'))
            if self.verbose:
                print("Camera storage mode:", storage_mode)
        else:
            storage_mode = None
        return storage_mode

    def get_recorder_submode(self):
        '''Returns the current recorder mode (only possible if storage mode is recorder)'''
        if self.camera is not None:
            cam_recorder_mode = {}
            cam_recorder_mode = self.camera.sdk.get_recorder_submode()
            recorder_mode = str(cam_recorder_mode.get('recorder submode'))
            if self.verbose:
                print("Camera recorder mode:", recorder_mode)
        else:
            recorder_mode = None
        return recorder_mode

    def get_exposure_time(self):
        '''Returns the current exposure time'''
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_time = int(cam_delay_exposure_time.get('exposure'))
            if self.verbose:
                print("Camera exposure time:", exposure_time)
        else:
            exposure_time = None
        return exposure_time

    def get_exposure_timebase(self):
        '''Returns the exposure timebase'''
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_timebase = str(cam_delay_exposure_time.get('exposure timebase'))
            if self.verbose:
                print("Camera exposure timebase:", exposure_timebase)
        else:
            exposure_timebase = None
        return exposure_timebase

    def get_delay_time(self):
        '''Returns the current delay time'''
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_time = int(cam_delay_exposure_time.get('delay'))
            if self.verbose:
                print("Camera delay time:", delay_time)
        else:
            delay_time = None
        return delay_time

    def get_delay_timebase(self):
        '''Returns the delay timebase'''
        if self.camera is not None:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_timebase = str(cam_delay_exposure_time.get('delay timebase'))
            if self.verbose:
                print("Camera delay timebase:", delay_timebase)
        else:
            delay_timebase = None
        return delay_timebase


    def get_pixel_rates(self):
        '''Returns available pixel rates'''
        if self.camera is not None:
            cam_description = {}
            cam_description = self.camera.sdk.get_camera_description()
            pixel_rates = cam_description.get('pixel rate')
            if self.verbose:
                print("Camera available pixel rates:", pixel_rates)
        else:
            pixel_rates = {}
        return pixel_rates

    def get_pixel_rate(self):
        '''Returns the pixel rate'''
        if self.camera is not None:
            cam_pixel_rate = {}
            cam_pixel_rate = self.camera.sdk.get_pixel_rate()
            pixel_rate = str(cam_pixel_rate.get('pixel rate'))
            if self.verbose:
                print("Camera pixel rate:", pixel_rate)
        else:
            pixel_rate = None
        return pixel_rate

    def get_readout_format(self):
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
            cam_readout_format = self.camera.sdk.get_interface_output_format('edge')
            readout_format = str(cam_readout_format.get('format'))
            if self.verbose:
                print("Camera readout format:", readout_format)
        else:
            readout_format = None
        return readout_format

    # compounded methods

    def get_properties(self):
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
            cam_properties = {  **cam_name,
                                **cam_temperatures,
                                **cam_sizes,
                                **cam_trigger_mode,
                                **cam_acquire_mode,
                                **cam_storage_mode,
                                **cam_recorder_mode,
                                **cam_delay_exposure_time}
        else:
            cam_properties = {}
            if self.verbose:
                print("Camera not open - Cannot retrieve properties")
        return cam_properties
  

    def grab_image(self, exposure_time_ms:int=100):
        """
        All-in-one function to grab a single image from the camera
        """
        # Works but slow if repeated in a loop
        # (setting up trigger_mode and exposure_time takes time)

        if self.verbose:
            print("Attempting to grab an image...")

        img_buffer = np.zeros((1,1,1), dtype=np.uint16)
        if self.camera is not None:
            if self.is_recording:
                if self.verbose:
                    print(" Recording already in progress. Aborted.")
            else:
                self.disarm()                        # In case camera was previously armed
                self.set_trigger_mode('auto_trigger')       # Camera is internally triggered
                self.arm()                           # Required to apply tigger settings
                self.set_exposure_time(exposure_time_ms)    # Exposure time can be changed after arming the camera
                self.start_recorder(1)                      # Start a recording session to acquire one frame
                self.monitor_recorder(1)                    # Monitors the recording session and returns once one image is acquired (or after default timeout of 5s)
                self.stop_recorder()                        # Stop the recording session before image is copied to memory
                img_buffer = self.copy_recorder_images(1)   # Returns a list of images of length 'number_of_images' (in this case, one)

                # Check if we had a timeout before deleting the recorder
                if self.recorder_timeout:
                    if self.verbose:
                        print(" Timeout while acquiting image.")
                else:
                    if self.verbose:
                        print(" Image successfully obtained.")

                self.delete_recorder()                          # Recording session can now be deleted
        else:
            if self.verbose:
                print(" Camera not open. Aborted")
        return img_buffer[0]                                    # Returning first (and in this case only) image from the buffer


if __name__ == '__main__':
    testcam = Camera()
    testimage = testcam.grab_image(exposure_time_ms=50)
