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

    def __init__(self, verbose=False):
        # Error status
        self.error = 0
        self.error_message = ""
    
        # State flags
        self.is_open = False
        self.is_recording = False
        self.new_images = False

        self.verbose = verbose

    def open(self):
        '''Open a camera'''
        if not self.is_open:
            try:
                if self.verbose:
                    print('Opening camera...')
                self.camera = pco.Camera()
            except:
                if self.verbose:
                    print(' Failed to open camera.')
                self.error = 1
                self.error_message = 'Failed to open the camera'
            else:
                if self.verbose:
                    print(' Camera opened.')
                self.is_open = True
        return None

    def close(self):
        '''Closes an opened camera'''
        if self.is_open:
            if self.verbose: 
                print('Closing camera...')
            self.camera.close()
            self.is_open = False
            if self.verbose: 
                print(' Camera closed.')
        return None

    def arm(self, num_buffers=None):
        if self.is_open:
            if self.verbose: 
                print('Arming camera...')
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')
            self.camera.sdk.arm_camera()
            sizes = {}
            sizes = self.camera.sdk.get_sizes()
            self.width = int(sizes.get('x'))
            self.height = int(sizes.get('y'))
            self.bytes_per_image = self.width * self.height * 2 # 16 bit images (2 bytes per pixel)
            self.camera.sdk.set_image_parameters(self.width, self.height)
            if self.verbose: 
                print(' Camera armed.')
        return None

    def disarm(self):
        if self.is_open:
            if self.verbose: 
                print('Disarming camera...')
            if self.camera.sdk.get_recording_state()['recording state'] == 'on':
                self.camera.sdk.set_recording_state('off')            
            self.armed = False
            if self.verbose: 
                print(' Camera disarmed.')
        return None


    def set_trigger_mode(self, trigger_mode):
        '''Set the trigger mode for the camera
        
        'auto_trigger':         An exposure of a new image is started automatically best possible compared to the
                                readout of an image and the current timing parameters. If a CCD is used and
                                images are taken in a sequence, exposure and sensor readout are started
                                simultaneously. Signals at the trigger input line are irrelevant
                           
        'external':             A delay / exposure sequence is started depending on the HW signal at the trigger
                                input line or by a force trigger command
        
        'external_exposure':    An exposure sequence is started depending on the HW signal at the trigger input
                                line. The exposure time is defined by the pulse length of the HW signal. The delay
                                and exposure time values defined by the set / request delay and exposure
                                command are ineffective. In double image mode exposure time length of the first
                                image is controlled through the HW signal, exposure time of the second image is
                                given by the readout time of the first image
        '''
        if self.is_open:
            if self.verbose: 
                print('Setting camera trigger mode ', trigger_mode, '...')
            if self.is_recording:
                if self.verbose: 
                    print(' Cannot set trigger mode while recording.')
            else:
                if trigger_mode == 'auto_trigger':
                    self.camera.sdk.set_trigger_mode('auto sequence')
                elif trigger_mode == 'external':
                    self.camera.sdk.set_trigger_mode('external exposure start & software trigger')
                elif trigger_mode == 'external_exposure':
                    self.camera.sdk.set_trigger_mode('external exposure control')
                if self.verbose: 
                    print(' ', trigger_mode, ' set.')

    def start_recorder(self, number_of_images):
        if self.is_open:
            try:
                if self.verbose: 
                    print('Starting camera recording session...')
                self.camera.record(int(number_of_images), mode='fifo')
            except:
                if self.verbose: 
                    print(' Exception while starting recorder.')
                self.error = 1
                self.error_message = 'Failed to start recorder.'
                self.is_recording = False
            else:
                if self.verbose: 
                    print(' Recording session started.')
                self.is_recording = True
        return None
             
    def monitor_recorder(self, number_of_images):
        if self.is_open and self.is_recording:
            if self.verbose: 
                print('Monitoring camera recording session status...')
            acq_timeout = 2
            wait_until = datetime.now() + timedelta(seconds=acq_timeout)
            while True:
                images_in_buffer = self.camera.rec.get_status()['dwProcImgCount']
                if images_in_buffer >= number_of_images:
                    if self.verbose: 
                        print(' Recording session succeeded:', images_in_buffer, 'images in buffer')
                    self.new_images = True
                    break
                elif wait_until < datetime.now():
                    if self.verbose: 
                        print(' Still recording after', acq_timeout, 's.', images_in_buffer, 'images in buffer')
                    break
                else:
                    time.sleep(0.01)

    def stop_recorder(self):
        if self.is_open and self.is_recording:
            self.camera.stop()
            self.is_recording = False

    def get_images(self):
        if self.is_open and not(self.is_recording) and self.new_images:
            images, metadatas = self.camera.images()
            self.new_images = False
            return images, metadatas

    def cleanup_recorder(self):
        if self.is_open:
            self.camera.rec.cleanup()

    def delete_recorder(self):
        if self.is_open:
            self.camera.rec.delete()


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





