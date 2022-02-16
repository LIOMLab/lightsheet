'''
Created on February 8, 2022
'''

import sys
sys.path.append(".")

import pco
import time

class Camera:
    
    '''Defaults attributes'''
    open = False
    name = ''
    trigger_mode = 'auto sequence'
    x_max_res = 0
    y_max_res = 0
    x_current_res = 0
    y_current_res = 0
    delay = 0
    time_base_delay_code = 'us'
    exposure = 0
    time_base_exposure_code = 'us'
    acquire_mode = 'auto'
    storage_mode = 'recorder'
    recorder_mode = 'sequence'
    temperature_power = 0
    temperature_camera = 0
    temperature_sensor = 0


    def __init__(self):
        try:
            self.camera = pco.Camera()
        except:

            self.error = 1
            self.error_message = 'Camera not found'
        else:
            self.open = True
            self.error = 0
            self.error_message = ''
    

    def close(self):
        '''Closes an opened camera'''
        if self.open:
            self.camera.sdk.close_camera()
            self.open = False


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
        if self.open:
            if trigger_mode == 'AutoSequence':
                self.camera.sdk.set_trigger_mode('auto sequence')
            elif trigger_mode == 'ExternalExposureStart':
                self.camera.sdk.set_trigger_mode('external exposure start & software trigger')
            elif trigger_mode == 'ExternalExposureControl':
                self.camera.sdk.set_trigger_mode('external exposure control')


#    def arm_camera(self):
#        '''Prepare the camera for a following recording (with the current settings)'''
#        self.camera.sdk.arm_camera()

    def start_recording_single(self):
        if self.open:
            self.camera.record(1, mode='sequence non blocking')

    def start_recording_multiple(self, number_of_images):
        if self.open:
            self.camera.record(int(number_of_images), mode='sequence non blocking')

    def get_image(self):
        if self.open:
            while True:
                if self.camera.rec.get_status()['dwProcImgCount'] >= 1:
                    break
                time.sleep(0.001)
            image, meta = self.camera.image()
            return image

    def get_images(self, number_of_images):
        if self.open:
            while True:
                if self.camera.rec.get_status()['dwProcImgCount'] >= number_of_images:
                    break
                time.sleep(0.001)
            images, metadatas = self.camera.images()
            return images

    def get_sizes(self):
        '''Returns (as arguments) the current armed image size of the camera
            'res' : resolution in pixels '''
        if self.open:
            cam_sizes = {}
            cam_sizes = self.camera.sdk.get_sizes()
            self.x_current_res = int(cam_sizes.get('x'))
            self.y_current_res = int(cam_sizes.get('y'))
            self.x_max_res = int(cam_sizes.get('x max'))
            self.y_max_res = int(cam_sizes.get('y max'))

    def set_recording_state(self, state):
        '''Set the recording state for the camera
            0: recording off
            1: recording on'''
        if self.open:
            self.camera.sdk.set_recording_state(state)


    '''Get Camera Properties'''
    def get_name(self):
        '''Gives the camera name'''
        if self.open:
            cam_name = {}
            cam_name = self.camera.sdk.get_camera_name()
            self.name = str(cam_name.get('camera name'))

    def get_temperature(self):
        ''' Gives the current internal, sensor and power supply temperatures in Celcius'''
        if self.open:
            cam_temperature = {}
            cam_temperature = self.camera.sdk.get_temperature()
            self.temperature_sensor = float(cam_temperature.get('sensor temperature'))
            self.temperature_camera = float(cam_temperature.get('camera temperature'))
            self.temperature_power  = float(cam_temperature.get('power temperature'))

    def get_trigger_mode(self):
        '''Gives the current trigger mode'''
        if self.open:
            cam_trigger = {}
            cam_trigger = self.camera.sdk.get_trigger_mode()
            self.trigger_mode = str(cam_trigger.get('trigger mode'))

    def get_exposure_time(self):
        '''Gives the current delay time and exposure time'''
        if self.open:
            cam_delay_exposure_time = {}
            cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
            self.delay = int(cam_delay_exposure_time.get('delay'))
            self.exposure = int(cam_delay_exposure_time.get('exposure'))
            self.time_base_delay_code = str(cam_delay_exposure_time.get('delay timebase'))
            self.time_base_exposure_code = str(cam_delay_exposure_time.get('exposure timebase'))

    def get_acquire_mode(self):
        '''Gives the current acquire mode'''
        if self.open:
            cam_acquire_mode = {}
            cam_acquire_mode = self.camera.sdk.get_acquire_mode()
            self.acquire_mode = str(cam_acquire_mode.get('acquire mode'))

    def get_storage_mode(self):
        '''Gives the current storage mode'''
        if self.open:
            cam_storage_mode = {}
            cam_storage_mode = self.camera.sdk.get_storage_mode()
            self.storage_mode = str(cam_storage_mode.get('storage mode'))

    def get_recorder_submode(self):
        '''Gives the current recorder mode (only possible if storage mode is recorder)'''
        if self.open:
            cam_recorder_mode = {}
            cam_recorder_mode = self.camera.sdk.get_recorder_submode()
            self.recorder_mode = str(cam_recorder_mode.get('recorder submode'))

    '''Debugging methods'''
    def get_roi(self):
        '''Gives the coordinates of the ROI '''
        if self.open:
            cam_roi = {}
            cam_roi = self.camera.sdk.get_roi()
            self.roiX0 = int(cam_roi.get('x0'))
            self.roiY0 = int(cam_roi.get('y0'))
            self.roiX1 = int(cam_roi.get('x1'))
            self.roiY1 = int(cam_roi.get('y1'))

    def get_pixel_rate(self):
        '''Gives the camera pixel rate in Hz, which determines the sensor readout speed'''
        if self.open:
            cam_pixel_rate = {}
            cam_pixel_rate = self.camera.sdk.get_pixel_rate()
            self.pixel_rate = int(cam_pixel_rate.get('pixel rate'))

    def get_sensor_format(self):
        '''Gives the current sensor format'''
        if self.open:
            cam_sensor = {}
            self.camera.sdk.get_sensor_format()
            self.sensor = cam_sensor.get('sensor format')

    def get_health_status(self):
        '''Retrieves info about the current camera status (warnings, errors and status)'''
        if self.open:
            cam_health = {}
            cam_health = self.camera.sdk.get_camera_health_status()
            self.warn = int(cam_health.get('warning'))
            self.err = int(cam_health.get('error'))
            self.status = int(cam_health.get('status'))



