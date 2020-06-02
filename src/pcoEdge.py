'''
Created on August 9, 2019

@author: Pierre Girard-Collins
'''

import sys
from array import ArrayType, array
sys.path.append("..")

import ctypes
import numpy as np
import time

'''Saving Dynamic Link Library functions from the manufacturer for Python use '''

dll = ctypes.cdll.LoadLibrary("SC2_Cam.dll")

open_camera = dll.PCO_OpenCamera
open_camera.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint16]

close_camera = dll.PCO_CloseCamera
close_camera.argtypes = [ctypes.c_void_p]

get_camera_name = dll.PCO_GetCameraName
get_camera_name.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint16]

get_camera_health_status = dll.PCO_GetCameraHealthStatus
get_camera_health_status.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]

get_temperature = dll.PCO_GetTemperature
get_temperature.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.POINTER(ctypes.c_int16), ctypes.POINTER(ctypes.c_int16)]

arm_camera = dll.PCO_ArmCamera
arm_camera.argtypes = [ctypes.c_void_p]

set_image_parameters = dll.PCO_SetImageParameters
set_image_parameters.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]

set_trigger_mode = dll.PCO_SetTriggerMode
set_trigger_mode.argtypes = [ctypes.c_void_p, ctypes.c_uint16]

get_trigger_mode = dll.PCO_GetTriggerMode
get_trigger_mode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16)]

set_delay_exposure_time = dll.PCO_SetDelayExposureTime
set_delay_exposure_time.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint16, ctypes.c_uint16]

get_delay_exposure_time = dll.PCO_GetDelayExposureTime
get_delay_exposure_time.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16)]

set_roi = dll.PCO_SetROI
set_roi.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16]

get_roi = dll.PCO_GetROI
get_roi.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16)]

get_sizes = dll.PCO_GetSizes
get_sizes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16), ctypes.POINTER(ctypes.c_uint16)]

get_sensor_format = dll.PCO_GetSensorFormat
get_sensor_format.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16)]

get_acquire_mode = dll.PCO_GetAcquireMode
get_acquire_mode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16)]

get_pixel_rate = dll.PCO_GetPixelRate
get_pixel_rate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]

arm_camera = dll.PCO_ArmCamera
arm_camera.argtypes = [ctypes.c_void_p]

get_single_image = dll.PCO_GetImageEx
get_single_image.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16]

set_recording_state = dll.PCO_SetRecordingState
set_recording_state.argtypes = [ctypes.c_void_p, ctypes.c_uint16]

allocate_buffer = dll.PCO_AllocateBuffer
allocate_buffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_uint32, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint16)), ctypes.POINTER(ctypes.c_void_p)]

cancel_images = dll.PCO_CancelImages
cancel_images.argtypes = [ctypes.c_void_p]

free_buffer = dll.PCO_FreeBuffer
free_buffer.argtypes = [ctypes.c_void_p, ctypes.c_int16]

add_buffer_ex = dll.PCO_AddBufferEx
add_buffer_ex.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16]

get_buffer_status = dll.PCO_GetBufferStatus
get_buffer_status.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]



class PCO_Buflist(ctypes.Structure):
    _fields_=[("SBufNr", ctypes.c_int16), ("reserved", ctypes.c_uint16), ("dwStatusDll", ctypes.c_uint32), ("DwStatusDrv", ctypes.c_uint32)]

wait_for_buffer = dll.PCO_WaitforBuffer
wait_for_buffer.argtypes = [ctypes.c_void_p, ctypes.c_int16, ctypes.POINTER(PCO_Buflist), ctypes.c_int16]




class Camera:
    
    def __init__(self):
        
        self.handle = ctypes.c_void_p(0)
        self.name = ctypes.c_char_p(b''*40)
        open_camera(self.handle,0)
        #get_camera_name(self.handle, self.name, 40)
        #self.name = self.name.value.decode('ascii')
        
    def allocate_buffer(self, number_of_buffers=2):
        self.number_of_buffers = number_of_buffers
        self.pointers = []  #Contains all the buffer pointers
        bytes_in_buffer = self.x_current_res.value*self.y_current_res.value*2   #Times 2 for 16bit images 
        for i in range(number_of_buffers):
            sBufNr = ctypes.c_int16(-1)   #Index value attributed by allocate_buffer
            self.pointers.append(ctypes.POINTER(ctypes.c_uint16)())
            hEvent = ctypes.c_void_p(0)   #Not useful for us
            allocate_buffer(self.handle, sBufNr, bytes_in_buffer, self.pointers[-1], hEvent)
            
    def add_buffer_ex(self,buffer_index):
        add_buffer_ex(self.handle, 0, 0, buffer_index, self.x_current_res.value, self.y_current_res.value, 16)
        
    def arm_camera(self):
        arm_camera(self.handle)
        
    def cancel_images(self):
        cancel_images(self.handle)
        
    def close_camera(self):
        close_camera(self.handle)
            
    def free_buffer(self):
        for i in range(self.number_of_buffers):
            free_buffer(self.handle, i)
            
    def get_acquire_mode(self):
        self.acquire_mode = ctypes.c_uint16()
        get_acquire_mode(self.handle, self.acquire_mode)
        
    def get_buffer_status(self):
        self.dwStatusDll = ctypes.c_uint32()
        self.dwStatusDrv = ctypes.c_uint32()
        get_buffer_status(self.handle, self.buffers_in_queue[0], self.dwStatusDll, self.dwStatusDrv)
        
    def get_exposure_time(self):
        self.delay = ctypes.c_uint32(0)
        self.exposure = ctypes.c_uint32(0)
        self.time_base_delay = ctypes.c_uint16(0)
        self.time_base_exposure = ctypes.c_uint16(1)
        get_delay_exposure_time(self.handle, self.delay, self.exposure, self.time_base_delay, self.time_base_exposure)
     
    def get_health_status(self):
        self.warn = ctypes.c_uint32()
        self.err = ctypes.c_uint32()
        self.status = ctypes.c_uint32()
        get_camera_health_status(self.handle, self.warn, self.err, self.status)
        
    def get_pixel_rate(self):
        self.pixel_rate = ctypes.c_uint32()
        get_pixel_rate(self.handle, self.pixel_rate)
        
    def get_roi(self):
        '''Gives the coordinates of the ROI '''
        self.roiX0 = ctypes.c_uint16()
        self.roiY0 = ctypes.c_uint16()
        self.roiX1 = ctypes.c_uint16()
        self.roiY1 = ctypes.c_uint16()
        get_roi(self.handle, self.roiX0, self.roiY0, self.roiX1, self.roiY1)
    
    def get_sensor_format(self):
        self.sensor = ctypes.c_uint16()
        get_sensor_format(self.handle, self.sensor)
        
    def get_sizes(self):
        ''' Res : resolution in pixels '''
        self.x_current_res = ctypes.c_uint16()
        self.y_current_res = ctypes.c_uint16()
        self.x_max_res = ctypes.c_uint16()
        self.y_max_res = ctypes.c_uint16()
        get_sizes(self.handle, self.x_current_res, self.y_current_res, self.x_max_res, self.y_max_res) 
        
    def get_temperature(self):
        ''' Gives the temperature in Celcius'''
        self.ccd_temp = ctypes.c_int16()
        self.cam_temp = ctypes.c_int16()
        self.pow_temp = ctypes.c_int16()
        get_temperature(self.handle, self.ccd_temp, self.cam_temp, self.pow_temp)
        
    def get_trigger_mode(self):
        self.trigger_mode = ctypes.c_uint16()
        get_trigger_mode(self.handle, self.trigger_mode)
        
    def insert_buffers_in_queue(self):
        self.buffers_in_queue = []
        for i in range(len(self.pointers)):
            self.add_buffer_ex(i)
            self.buffers_in_queue.append(i) 
            
    def open_camera(self):
        open_camera(self.handle,0)
        
    def retrieve_multiple_images(self, number_of_frames, 
                                 exposure_time_in_seconds, 
                                 sleep_timeout = 40, 
                                 poll_timeout = 5e5, 
                                 first_trigger_timeout_in_seconds = 10):
        
        frame_buffer = np.ones((int(number_of_frames), int(self.y_current_res.value),int(self.x_current_res.value)), dtype = np.uint16)
        pixels_per_frame = ctypes.c_uint32(self.y_current_res.value*self.x_current_res.value)
        ArrayType = ctypes.c_uint16*pixels_per_frame.value
    
        for i in range(int(number_of_frames)):
    
            buffer_number = self.buffers_in_queue.pop(0) #Removed from queue
                        
            bufferPTR=ctypes.cast(self.pointers[buffer_number], ctypes.POINTER(ArrayType))
            frame_buffer[i,:,:] =  np.frombuffer(bufferPTR.contents, dtype=np.uint16).reshape((self.y_current_res.value, self.x_current_res.value))*1.0
                    
            self.add_buffer_ex(buffer_number)   #Put the buffer back in the queue
            self.buffers_in_queue.append(buffer_number)
            retrieving_allowed = True
                
        return frame_buffer
        
    def retrieve_single_image(self):
        ''' Return the image, a 3D numpy array '''
        #imageDatatype = ctypes.c_uint16*self.xCurrentRes.value*self.yCurrentRes.value
        
        self.number_of_loops_reached = False
        self.z=0
        while True:
            self.get_buffer_status()
            
            if self.dwStatusDll.value == 0xc0008000:
                buffer_number = self.buffers_in_queue.pop(0)  #Removed from queue
                break
            
            if self.z == 1000:
                self.number_of_loops_reached = True
                break
            self.z=+1
        
        pixels_per_frame = ctypes.c_uint32(self.y_current_res.value*self.x_current_res.value)
        ArrayType = ctypes.c_uint16*pixels_per_frame.value
        bufferPTR=ctypes.cast(self.pointers[buffer_number], ctypes.POINTER(ArrayType))
        image = np.frombuffer(bufferPTR.contents, dtype=np.uint16).reshape((self.y_current_res.value, self.x_current_res.value))
        self.add_buffer_ex(buffer_number)   #Put the buffer back in the queue
        self.buffers_in_queue.append(buffer_number)  
        
        return image
     
    def set_recording_state(self, state):
        ''' state = 0 (recording off) ; state = 1 (recordind on)'''
        set_recording_state(self.handle, state)
        
    def set_trigger_mode(self, trigger_mode):
        
        if trigger_mode == 'AutoSequence':
            set_trigger_mode(self.handle, 0)
        elif trigger_mode == 'ExternalExposureStart':
            set_trigger_mode(self.handle, 2)
        elif trigger_mode == 'ExternalExposureControl':
            set_trigger_mode(self.handle, 3)