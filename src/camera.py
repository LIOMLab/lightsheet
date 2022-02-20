'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import pco
import time
from datetime import datetime
from datetime import timedelta

class Camera:
    
    # State flags
    is_open = False

    # Error status
    error = 0
    error_message = ""

    def __init__(self):
        try:
            self.camera = pco.Camera()
        except:
            self.error = 1
            self.error_message = 'Camera not found'
        else:
            self.is_open = True


    def close(self):
        '''Closes an opened camera'''
        if self.is_open:
            self.camera.sdk.close_camera()
            self.is_open = False


    def set_trigger_mode(self, trigger_mode):
        '''Set the trigger mode for the camera
        
        'AutoSequence':    An exposure of a new image is started automatically best possible compared to the
                           readout of an image and the current timing parameters. If a CCD is used and
                           images are taken in a sequence, exposure and sensor readout are started
                           simultaneously. Signals at the trigger input line are irrelevant
                           
        'ExternalExposureStart':    A delay / exposure sequence is started depending on the HW signal at the trigger
                                    input line or by a force trigger command
        
        'ExternalExposureControl':  An exposure sequence is started depending on the HW signal at the trigger input
                                    line. The exposure time is defined by the pulse length of the HW signal. The delay
                                    and exposure time values defined by the set / request delay and exposure
                                    command are ineffective. In double image mode exposure time length of the first
                                    image is controlled through the HW signal, exposure time of the second image is
                                    given by the readout time of the first image
        '''
        if self.is_open:
            if trigger_mode == 'AutoSequence':
                self.camera.sdk.set_trigger_mode('auto sequence')
            elif trigger_mode == 'ExternalExposureStart':
                self.camera.sdk.set_trigger_mode('external exposure start & software trigger')
            elif trigger_mode == 'ExternalExposureControl':
                self.camera.sdk.set_trigger_mode('external exposure control')


    def start_recording_single(self):
        if self.is_open:
            self.camera.record(1, mode='sequence non blocking')
            # makes sure record is started before we keep going (bug investigation) 
            while True:
                running = self.camera.rec.get_status()['is running']
                if running is True:
                    break

    def start_recording_multiple(self, number_of_images):
        if self.is_open:
            self.camera.record(int(number_of_images), mode='sequence non blocking')
            # makes sure record is started before we keep going (bug investigation) 
            while True:
                running = self.camera.rec.get_status()['is running']
                if running is True:
                    break

    def get_image(self):
        if self.is_open:
            # implement a 2s timeout in case we never receive the frame (bug investigation)
            delete_TO = 2
            wait_until = datetime.now() + timedelta(seconds=delete_TO)
            break_loop = False
            while not break_loop:
                running = self.camera.rec.get_status()['is running']
                if running is False:
                    break_loop = True
                elif wait_until < datetime.now():
                    print('Timeout! no frame received')
                    break_loop = True
                time.sleep(0.01)
            # 2do: deal with missing data in case of timeout
            image, meta = self.camera.image()
            return image

    def get_images(self, number_of_images):
        if self.is_open:
            # implement a 2s timeout in case we never receive enough frames (bug investigation)
            delete_TO = 2
            wait_until = datetime.now() + timedelta(seconds=delete_TO)
            break_loop = False
            while not break_loop:
                running = self.camera.rec.get_status()['is running']
                frames = self.camera.rec.get_status()['dwProcImgCount']
                if running is False:
                    break_loop = True
                elif wait_until < datetime.now():
                    print('Timeout! frames in buffer: ' + str(frames))
                    break_loop = True
                time.sleep(0.01)
            # 2do: deal with partial data in case of timeout
            images, metadatas = self.camera.images()
            return images




    '''Get Camera Properties'''

    def get_name(self):
        '''Gives the camera name'''
        if self.is_open:
            cam_name = {}
            cam_name = self.camera.sdk.get_camera_name()
            name = str(cam_name.get('camera name'))
        else:
            name = str('No camera initialized')
        return name

    def get_camera_temperature(self):
        ''' Gives the current internal temperatures in Celcius'''
        if self.is_open:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            camera_temperature = float(cam_temperatures.get('camera temperature'))
        else:
            camera_temperature = float(1000)
        return camera_temperature

    def get_sensor_temperature(self):
        ''' Gives the current sensor temperatures in Celcius'''
        if self.is_open:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            sensor_temperature = float(cam_temperatures.get('sensor temperature'))
        else:
            sensor_temperature = float(1000)
        return sensor_temperature

    def get_power_temperature(self):
        ''' Gives the current power supply temperatures in Celcius'''
        if self.is_open:
            cam_temperatures = {}
            cam_temperatures = self.camera.sdk.get_temperature()
            power_temperature = float(cam_temperatures.get('power temperature'))
        else:
            power_temperature = float(1000)
        return power_temperature

    def get_xsize(self):
        '''Returns the current armed image x-size of the camera'''
        if self.is_open:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_xsize = int(cam_sizes.get('x'))
        else:
            current_xsize = 0
        return current_xsize
    
    def get_ysize(self):
        '''Returns the current armed image y-size of the camera'''
        if self.is_open:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            current_ysize = int(cam_sizes.get('y'))
        else:
            current_ysize = 0
        return current_ysize

    def get_trigger_mode(self):
        '''Gives the current trigger mode'''
        if self.is_open:
            cam_trigger_mode = {}
            cam_trigger_mode = self.camera.sdk.get_trigger_mode()
            trigger_mode = str(cam_trigger_mode.get('trigger mode'))
        else:
            trigger_mode = str('N/A')
        return trigger_mode

    def get_acquire_mode(self):
        '''Gives the current acquire mode'''
        if self.is_open:
            cam_acquire_mode = {}
            cam_acquire_mode = self.camera.sdk.get_acquire_mode()
            acquire_mode = str(cam_acquire_mode.get('acquire mode'))
        else:
            acquire_mode = str('N/A')
        return acquire_mode

    def get_storage_mode(self):
        '''Gives the current storage mode'''
        if self.is_open:
            cam_storage_mode = {}
            cam_storage_mode = self.camera.sdk.get_storage_mode()
            storage_mode = str(cam_storage_mode.get('storage mode'))
        else:
            storage_mode = str('N/A')
        return storage_mode

    def get_recorder_submode(self):
        '''Gives the current recorder mode (only possible if storage mode is recorder)'''
        if self.is_open:
            cam_recorder_mode = {}
            cam_recorder_mode = self.camera.sdk.get_recorder_submode()
            recorder_mode = str(cam_recorder_mode.get('recorder submode'))
        else:
            recorder_mode = str('N/A')
        return recorder_mode

    def get_exposure_time(self):
        if self.is_open:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_time = int(cam_delay_exposure_time.get('exposure'))
        else:
            exposure_time = 0
        return exposure_time

    def get_exposure_timebase(self):
        if self.is_open:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            exposure_timebase = str(cam_delay_exposure_time.get('exposure timebase'))
        else:
            exposure_timebase = str('')
        return exposure_timebase

    def get_delay_time(self):
        if self.is_open:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_time = int(cam_delay_exposure_time.get('delay'))
        else:
            delay_time = 0
        return delay_time

    def get_delay_timebase(self):
        if self.is_open:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            delay_timebase = str(cam_delay_exposure_time.get('delay timebase'))
        else:
            delay_timebase = str('')
        return delay_timebase





