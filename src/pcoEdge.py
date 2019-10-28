import sys
from array import ArrayType, array
sys.path.append("..")

import ctypes
import numpy as np


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
        
    def get_temperature(self):
        ''' Gives the temperature in Celcius'''
        self.ccdTemp = ctypes.c_int16()
        self.camTemp = ctypes.c_int16()
        self.powTemp = ctypes.c_int16()
        get_temperature(self.handle, self.ccdTemp, self.camTemp, self.powTemp)
        
    def get_health_status(self):
        self.warn = ctypes.c_uint32()
        self.err = ctypes.c_uint32()
        self.status = ctypes.c_uint32()
        get_camera_health_status(self.handle, self.warn, self.err, self.status)
        
    def get_trigger_mode(self):
        self.triggerMode = ctypes.c_uint16()
        get_trigger_mode(self.handle, self.triggerMode)
        
    def get_exposure_time(self):
        self.delay = ctypes.c_uint32(0)
        self.exposure = ctypes.c_uint32(0)
        self.timeBaseDelay = ctypes.c_uint16(0)
        self.timeBaseExposure = ctypes.c_uint16(1)
        get_delay_exposure_time(self.handle, self.delay, self.exposure, self.timeBaseDelay, self.timeBaseExposure)
        
    def get_sensor_format(self):
        self.sensor = ctypes.c_uint16()
        get_sensor_format(self.handle, self.sensor)
    
    def get_acquire_mode(self):
        self.acquireMode = ctypes.c_uint16()
        get_acquire_mode(self.handle, self.acquireMode)
    
    def get_pixel_rate(self):
        self.pixelRate = ctypes.c_uint32()
        get_pixel_rate(self.handle, self.pixelRate)
        
    def get_roi(self):
        '''Gives the coordinates of the ROI '''
        self.roiX0 = ctypes.c_uint16()
        self.roiY0 = ctypes.c_uint16()
        self.roiX1 = ctypes.c_uint16()
        self.roiY1 = ctypes.c_uint16()
        get_roi(self.handle, self.roiX0, self.roiY0, self.roiX1, self.roiY1)
        
    def get_sizes(self):
        ''' Res : resolution in pixels '''
        self.xCurrentRes = ctypes.c_uint16()
        self.yCurrentRes = ctypes.c_uint16()
        self.xMaxRes = ctypes.c_uint16()
        self.yMaxRes = ctypes.c_uint16()
        get_sizes(self.handle, self.xCurrentRes, self.yCurrentRes, self.xMaxRes, self.yMaxRes)
        
    def arm_camera(self):
        arm_camera(self.handle)
        
    def allocate_buffer(self, numberOfBuffers=2):
        self.numberOfBuffers = numberOfBuffers
        self.pointers = []  #Contains all the buffer pointers
        bytesInBuffer = self.xCurrentRes.value*self.yCurrentRes.value*2   #Times 2 for 16bit images 
        for i in range(numberOfBuffers):
            sBufNr = ctypes.c_int16(-1)   #Index value attributed by allocate_buffer
            self.pointers.append(ctypes.POINTER(ctypes.c_uint16)())
            hEvent = ctypes.c_void_p(0)   #Not useful for us
            allocate_buffer(self.handle, sBufNr, bytesInBuffer, self.pointers[-1], hEvent)
        
    def set_recording_state(self, state):
        ''' state = 0 (recording off) ; state = 1 (recordind on)'''
        set_recording_state(self.handle, state)
        
    def add_buffer_ex(self,bufferIndex):
        add_buffer_ex(self.handle, 0, 0, bufferIndex, self.xCurrentRes.value, self.yCurrentRes.value, 16)
        
    def cancel_images(self):
        cancel_images(self.handle)
        
    def free_buffer(self):
        for i in range(self.numberOfBuffers):
            free_buffer(self.handle, i)
        
    def close_camera(self):
        close_camera(self.handle)
        
    def insert_buffers_in_queue(self):
        self.buffersInQueue = []
        for i in range(len(self.pointers)):
            self.add_buffer_ex(i)
            self.buffersInQueue.append(i)    
            
    def retrieve_single_image(self):
        ''' Return the image, a 3D numpy array '''
        imageDatatype = ctypes.c_uint16*self.xCurrentRes.value*self.yCurrentRes.value
        
        self.numberOfLoopsReached = False
        self.z=0
        while True:
            self.get_buffer_status()
            
            if self.dwStatusDll.value == 0xc0008000:
                bufferNumber = self.buffersInQueue.pop(0)
                break
            
            if self.z == 1000:
                self.numberOfLoopsReached = True
                break
            self.z=+1
        
        
        
        
        #bufferNumber = self.buffersInQueue.pop(0)
        
        #reserved = ctypes.c_uint16()
        #dwStatusDll = ctypes.c_uint32()
        #dwStatusDrv = ctypes.c_uint32()
        #buflist = PCO_Buflist(ctypes.c_int16(bufferNumber), reserved, dwStatusDll, dwStatusDrv)
        #wait_for_buffer(self.handle, self.numberOfBuffers, buflist, 1000)
        
        #out = np.ones((3, self.yCurrentRes.value, self.xCurrentRes.value), dtype=np.uint16)
        #image =np.ctypeslib.as_array(imageDatatype.from_address(ctypes.addressof(self.pointers[bufferNumber].contents)))
        #out[1,:,:]=image
        
        pixelsPerFrame = ctypes.c_uint32(self.yCurrentRes.value*self.xCurrentRes.value)
        ArrayType = ctypes.c_uint16*pixelsPerFrame.value
        bufferPTR=ctypes.cast(self.pointers[bufferNumber], ctypes.POINTER(ArrayType))
        image = np.frombuffer(bufferPTR.contents, dtype=np.uint16).reshape((self.yCurrentRes.value, self.xCurrentRes.value))
        self.add_buffer_ex(bufferNumber)
        self.buffersInQueue.append(bufferNumber)  
        
        return image
    
    def open_camera(self):
        open_camera(self.handle,0)
    
    def get_buffer_status(self):
        self.dwStatusDll = ctypes.c_uint32()
        self.dwStatusDrv = ctypes.c_uint32()
        get_buffer_status(self.handle, self.buffersInQueue[0], self.dwStatusDll, self.dwStatusDrv)
        
    def set_trigger_mode(self, triggerMode):
        
        if triggerMode == 'AutoSequence':
            set_trigger_mode(self.handle, 0)
        elif triggerMode == 'ExternalExposureStart':
            set_trigger_mode(self.handle, 2)
        elif triggerMode == 'ExternalExposureControl':
            set_trigger_mode(self.handle, 3)
            
                    
    



