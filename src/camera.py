'''
Created on February 8, 2022
'''

import os
import sys
sys.path.append(".")

import pco

class Camera:
    
    def __init__(self):
        try:
            self.camera = pco.Camera()
        except:
            self.error = 1
            self.error_message = 'Camera not found'
        else:
            self.error = 0
            self.error_message = ''
            self.open_camera()
        
    def open_camera(self):
        '''Returns  a connection to a camera'''
        self.camera.sdk.open_camera()
    
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
        
        if trigger_mode == 'AutoSequence':
            self.camera.sdk.set_trigger_mode(0)
        elif trigger_mode == 'ExternalExposureStart':
            self.camera.sdk.set_trigger_mode(2)
        elif trigger_mode == 'ExternalExposureControl':
            self.camera.sdk.set_trigger_mode(3)

    def arm_camera(self):
        '''Prepare the camera for a following recording (with the current settings)'''
        self.camera.sdk.arm_camera()
    
    def get_sizes(self):
        '''Returns (as arguments) the current armed image size of the camera
            'res' : resolution in pixels '''
        cam_sizes = {}
        cam_sizes = self.camera.sdk.get_sizes()
        self.x_current_res = cam_sizes.get('x')
        self.y_current_res = cam_sizes.get('y')
        self.x_max_res = cam_sizes.get('x max')
        self.y_max_res = cam_sizes.get('y max')

    def set_recording_state(self, state):
        '''Set the recording state for the camera
            0: recording off
            1: recording on'''
        self.camera.sdk.set_recording_state(state)
     
   
    def close_camera(self):
        '''Closes an opened camera'''
        self.camera.sdk.close_camera()
        

    '''Get Camera Properties'''
    def get_name(self):
        '''Gives the camera name'''
        cam_name = {}
        cam_name = self.camera.sdk.get_camera_name()
        self.cam_name = cam_name.get('camera name')
        print(self.cam_name)
    
    def get_temperature(self):
        ''' Gives the current internal, sensor and power supply temperatures in Celcius'''
        cam_temperature = {}
        cam_temperature = self.camera.sdk.get_temperature()
        self.ccd_temp = cam_temperature.get('sensor temperature')
        self.cam_temp = cam_temperature.get('camera temperature')
        self.pow_temp = cam_temperature.get('power temperature')
        
    def get_trigger_mode(self):
        '''Gives the current trigger mode'''
        cam_trigger = {}
        cam_trigger = self.camera.sdk.get_trigger_mode()
        self.trigger_mode = cam_trigger.get('trigger mode')
    
    def get_exposure_time(self):
        '''Gives the current delay time and exposure time'''
        cam_delay_exposure_time = {}
        cam_delay_exposure_time = self.camera.sdk.get_delay_exposure_time()
        self.delay = cam_delay_exposure_time.get('delay')
        self.exposure = cam_delay_exposure_time.get('exposure')
        self.time_base_delay_code = cam_delay_exposure_time.get('delay timebase')
        self.time_base_exposure_code = cam_delay_exposure_time.get('exposure timebase')
         
    def get_acquire_mode(self):
        '''Gives the current acquire mode'''
        cam_acquire_mode = {}
        cam_acquire_mode = self.camera.sdk.get_acquire_mode()
        self.acquire_mode = cam_acquire_mode.get('acquire mode')
        
    def get_storage_mode(self):
        '''Gives the current storage mode'''
        cam_storage_mode = {}
        cam_storage_mode = self.camera.sdk.get_storage_mode()
        self.storage_mode = cam_storage_mode.get('storage mode')
        
    def get_recorder_submode(self):
        '''Gives the current recorder mode (only possible if storage mode is recorder)'''
        cam_recorder_mode = {}
        cam_recorder_mode = self.camera.sdk.get_recorder_submode()
        self.recorder_mode = cam_recorder_mode.get('recorder submode')
    
    '''Debugging methods'''
    def get_roi(self):
        '''Gives the coordinates of the ROI '''
        cam_roi = {}
        cam_roi = self.camera.sdk.get_roi()
        self.roiX0 = cam_roi.get('x0')
        self.roiY0 = cam_roi.get('y0')
        self.roiX1 = cam_roi.get('x1')
        self.roiY1 = cam_roi.get('y1')
        
    def get_pixel_rate(self):
        '''Gives the camera pixel rate in Hz, which determines the sensor readout speed'''
        cam_pixel_rate = {}
        cam_pixel_rate = self.camera.sdk.get_pixel_rate()
        self.pixel_rate = cam_pixel_rate.get('pixel rate')

    def get_sensor_format(self):
        '''Gives the current sensor format'''
        cam_sensor = {}
        self.camera.sdk.get_sensor_format()
        self.sensor = cam_sensor.get('sensor format')
    
    def get_health_status(self):
        '''Retrieves info about the current camera status (warnings, errors and status)'''
        cam_health = {}
        cam_health = self.camera.sdk.get_camera_health_status()
        self.warn = cam_health.get('warning')
        self.err = cam_health.get('error')
        self.status = cam_health.get('status')


