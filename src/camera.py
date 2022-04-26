'''
Created on February 8, 2022
'''

import sys
import time
from datetime import datetime, timedelta

import pco

sys.path.append(".")

class Camera:
    '''Class for PCO cameras'''

    def __init__(self, verbose=False):
        self.verbose = verbose

        # Error status
        self.error = 0
        self.error_message = ""

        # Flags
        self.is_armed = False
        self.is_recording = False
        self.new_data_ready = False

        # Other variables
        self.camera = None
        self.width = None
        self.height = None
        self.bytes_per_image = None

        self.open_camera()

    # compounded methods

    # Works but slow if repeated in a loop
    # Setting up trigger_mode and exposure time takes time
    def grab_single_image(self, exposure_time:int=100):
        '''docstring'''
        single_image = [0]
        if self.verbose:
            print("Attempting to grab a single image...")
        if self.camera is not None:
            if self.is_recording:
                if self.verbose:
                    print(" Recording in progress. Aborted.")
            else:
                self.disarm_camera()
                self.set_trigger_mode('auto_trigger')
                self.arm_camera()
                self.set_exposure_time(exposure_time)
                self.start_recorder(1)
                self.monitor_recorder(1)
                self.stop_recorder()
                single_image = self.copy_recorder_images()
                self.delete_recorder()
                if self.verbose:
                    print(" Single image obtained.")
        else:
            if self.verbose:
                print(" Camera not open. Aborted")
        return single_image

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


    # base methods

    def open_camera(self):
        '''Open a camera'''
        if self.camera is None:
            try:
                if self.verbose:
                    print("Opening camera...")
                self.camera = pco.Camera()
            except ValueError:
                if self.verbose:
                    print(" Failed to open camera.")
                self.error = 1
                self.error_message = "Failed to open the camera"
            else:
                if self.verbose:
                    print(' Camera opened.')
        return None

    def close_camera(self):
        '''Closes an opened camera'''
        if self.camera is not None:
            if self.verbose:
                print("Closing camera...")
            self.camera.close()
            self.camera = None
            if self.verbose:
                print(" Camera closed.")
        return None

    def arm_camera(self):
        '''docstring'''
        if self.camera is not None:
            if self.verbose:
                print("Arming camera...")
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')
            self.camera.sdk.arm_camera()
            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.width = int(sizes.get('x'))
            self.height = int(sizes.get('y'))
            self.bytes_per_image = self.width * self.height * 2 # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.width, self.height)
            self.is_armed = True
            if self.verbose:
                print(" Camera armed.")
        return None

    def disarm_camera(self):
        '''docstring'''
        if self.camera is not None:
            if self.verbose:
                print('Disarming camera...')
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')
            self.is_armed = False
            if self.verbose:
                print(' Camera disarmed.')
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
                    print(' Exception while starting recorder.')
                self.error = 1
                self.error_message = 'Failed to start recorder.'
                self.is_recording = False
            else:
                self.is_recording = True
                if self.verbose:
                    print(' Recording session started.')
        return None

    def monitor_recorder(self, number_of_images):
        '''docstring'''
        if self.is_recording:
            if self.verbose:
                print('Monitoring camera recording session status...')
            acq_timeout = 2
            wait_until = datetime.now() + timedelta(seconds=acq_timeout)
            while True:
                images_in_buffer = self.camera.rec.get_status()['dwProcImgCount']
                if images_in_buffer >= number_of_images:
                    if self.verbose:
                        print(' Recording session succeeded:', images_in_buffer, 'images in buffer')
                    self.new_data_ready = True
                    break
                elif wait_until < datetime.now():
                    if self.verbose:
                        print(' Timeout :', images_in_buffer, 'images in buffer after', acq_timeout, 's.',)
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
            images = [0]
        return images

    def delete_recorder(self):
        '''docstring'''
        if self.camera is not None:
            self.camera.rec.delete()
            # Deleting the recording session also deletes any remaining images
            self.new_data_ready = False
        return None


    ### setters

    def set_exposure_time(self, exposure_time:int):
        '''Set the exposure time (in ms) for the camera'''
        if self.camera is not None:
            if self.verbose:
                print("Setting camera exposure time: " + str(exposure_time) + "ms")
            self.camera.sdk.set_delay_exposure_time(0, 'ms', exposure_time, 'ms')
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
