import time
import ctypes as C
import os
import numpy as np

class Camera:
    '''
    Basic device adaptor for PCO.edge 5.5 USB sCMOS camera. Many more
    commands are available and have not been implemented.
    '''
    def __init__(self, name='PCO.edge5.5', cameras=1, verbose=True, very_verbose=False):
        assert cameras == 1, 'currently only 1 camera supported'
        self.name = name
        self.verbose = verbose
        self.very_verbose = very_verbose
        if self.verbose: print("%s: opening..."%self.name)
        try:
            self.handle = C.c_void_p(0)
            dll.open_camera(self.handle, 0)
            assert self.handle.value is not None
        except:
            print("%s: failed to open;"%self.name)
            print("%s: - is the camera on and connected?"%self.name)
            print("%s: - is CamWare running? (close it)"%self.name)
            print("%s: - is 'sc2_cl_me4.dll' in the 'SC2_Cam.dll'"%self.name,
                  "directory? (CamLink)")
            raise
        wSZCameraNameLen = 40
        camera_name = C.c_char_p(wSZCameraNameLen * b'')
        dll.get_camera_name(self.handle, camera_name, wSZCameraNameLen)
        assert camera_name.value == b'pco.edge 5.5m USB global shutter'
        self._num_buffers = 16 # default to maximum
        self._armed = False
        self._disarm()
        self._reset_settings_to_default()
        self._get_health_status(check=True)
        self._get_temperature()
        self._set_sensor_format('standard')
        self._set_acquire_mode('auto')
        self._set_pixel_rate(160000000)
        self._set_storage_mode('recorder')
        self._set_recorder_submode('sequence')
        self._set_timestamp_mode('off')
        self._set_trigger_mode('auto')
        self._set_exposure_time_us(10000)
        roi = legalize_image_size('max', 'max', self.name, very_verbose)[2]
        self._set_roi(roi)
        self._get_image_size()
        self.num_images = 1
        if self.verbose: print("%s: -> open and ready."%self.name)

    def _reboot(self, polling_time_s=0.2, timeout_s=15): # (5-12)s! 9s typical 
        if self.very_verbose: print("%s: rebooting..."%self.name, end='')
        dll.reboot_camera(self.handle)
        dll.close_camera(self.handle)
        t0 = time.perf_counter()
        while True:
            print(end='.')
            try:
                dll.reset_dll()
                time.sleep(polling_time_s)
                dll.open_camera(self.handle, 0)
            except OSError as e:
                t = time.perf_counter() - t0
                if t > timeout_s:
                    raise
            else:
                break
        if self.very_verbose: print(" done. (%0.2fs)"%t)
        return None

    def _reset_settings_to_default(self):
        if self.very_verbose:
            print("%s: reseting settings to default..."%self.name, end='')
        dll.reset_settings_to_default(self.handle)
        if self.very_verbose: print(" done.")

    def _get_health_status(self, check=False):
        if self.very_verbose:
            print("%s: getting health status;"%self.name)
        dwWarn, dwErr, dwStatus = C.c_uint32(), C.c_uint32(), C.c_uint32()
        dll.get_camera_health(self.handle, dwWarn, dwErr, dwStatus)
        self.health = {'warnings': dwWarn.value,
                       'errors': dwErr.value,
                       'status': dwStatus.value}
        if self.very_verbose:
            print("%s:  - warnings = %s"%(self.name, self.health['warnings']))
            print("%s:  - errors   = %s"%(self.name, self.health['errors']))
            print("%s:  - status   = %s"%(self.name, self.health['status']))
        if check:
            if self.health['warnings'] != 0 or self.health['errors'] != 0:
                print("%s: -> health status check = bad (fail)"%self.name)
                raise
            if self.very_verbose:
                print("%s: -> health status = good (pass)"%self.name)
        return self.health

    def _get_temperature(self):
        if self.very_verbose:
            print("%s: getting temperature;"%self.name)
        ccdtemp, camtemp, powtemp = C.c_int16(), C.c_int16(), C.c_int16()
        dll.get_temperature(self.handle, ccdtemp, camtemp, powtemp)
        self.temperature = {'ccd_degC'   : ccdtemp.value * 0.1,
                            'camera_degC': camtemp.value,
                            'psu_degC'   : powtemp.value}
        if self.very_verbose:
            print("%s:  - CCD          = %s (degC)"%(
                self.name, self.temperature['ccd_degC']))
            print("%s:  - camera       = %s (degC)"%(
                self.name, self.temperature['camera_degC']))
            print("%s:  - power supply = %s (degC)"%(
                self.name, self.temperature['psu_degC']))
        return self.temperature

    def _get_sensor_format(self):
        if self.very_verbose:
            print("%s: getting sensor format"%self.name, end='')
        number_to_mode = {0:"standard", 1:"extended"}
        wSensor = C.c_uint16(777) # 777 not valid -> should change
        dll.get_sensor_format(self.handle, wSensor)
        self.sensor_format = number_to_mode[wSensor.value]
        if self.very_verbose:
            print(" = %s"%self.sensor_format)
        return self.sensor_format

    def _set_sensor_format(self, mode):
        if self.very_verbose:
            print("%s: setting sensor format = %s"%(self.name, mode))
        mode_to_number = {"standard":0, "extended":1}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_sensor_format(self.handle, mode_to_number[mode])
        assert self._get_sensor_format() == mode
        if self.very_verbose:
            print("%s: -> done setting sensor format."%self.name)
        return None

    def _get_acquire_mode(self):
        if self.very_verbose:
            print("%s: getting acquire mode"%self.name, end='')
        number_to_mode = {0:"auto", 1:"external", 2:"external_modulate"}
        wAcquMode = C.c_uint16(777) # 777 not valid -> should change
        dll.get_acquire_mode(self.handle, wAcquMode)
        self.acquire_mode = number_to_mode[wAcquMode.value]
        if self.very_verbose:
            print(" = %s"%self.acquire_mode)
        return self.acquire_mode

    def _set_acquire_mode(self, mode):
        if self.very_verbose:
            print("%s: setting acquire mode = %s"%(self.name, mode))
        mode_to_number = {"auto":0, "external":1, "external_modulate":2}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_acquire_mode(self.handle, mode_to_number[mode])
        assert self._get_acquire_mode() == mode
        if self.very_verbose:
            print("%s: -> done setting acquire mode."%self.name)
        return None

    def _get_pixel_rate(self):
        if self.very_verbose:
            print("%s: getting pixel rate"%self.name, end='')
        dwPixelRate = C.c_uint32(0)
        dll.get_pixel_rate(self.handle, dwPixelRate)
        self.pixel_rate = dwPixelRate.value
        assert self.pixel_rate != 0
        if self.very_verbose:
            print(" = %i (Hz)"%self.pixel_rate)
        return self.pixel_rate

    def _set_pixel_rate(self, rate):
        if self.very_verbose:
            print("%s: setting pixel rate = %i (Hz)"%(self.name, rate))
        assert rate == 160000000, "rate '%s' not allowed"%rate
        dll.set_pixel_rate(self.handle, rate)
        assert self._get_pixel_rate() == rate
        if rate == 160000000:  self.line_time_us = 16.400
        if self.very_verbose:
            print("%s: -> done setting pixel rate."%self.name)
        return None

    def _get_storage_mode(self):
        if self.very_verbose:
            print("%s: getting storage mode"%self.name, end='')
        number_to_mode = {0:"recorder", 1:"FIFO_buffer"}
        wStorageMode = C.c_uint16(777) # 777 not valid -> should change
        dll.get_storage_mode(self.handle, wStorageMode)
        self.storage_mode = number_to_mode[wStorageMode.value]
        if self.very_verbose:
            print(" = %s"%self.storage_mode)
        return self.storage_mode

    def _set_storage_mode(self, mode):
        if self.very_verbose:
            print("%s: setting storage mode = %s"%(self.name, mode))
        mode_to_number = {"recorder":0, "FIFO_buffer":1}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_storage_mode(self.handle, mode_to_number[mode])
        assert self._get_storage_mode() == mode
        if self.very_verbose:
            print("%s: -> done setting storage mode."%self.name)
        return None

    def _get_recorder_submode(self):
        if self.very_verbose:
            print("%s: getting recorder submode"%self.name, end='')
        number_to_mode = {0:"sequence", 1:"ring_buffer"}
        wRecSubmode = C.c_uint16(777) # 777 not valid -> should change
        dll.get_recorder_submode(self.handle, wRecSubmode)
        self.recorder_submode = number_to_mode[wRecSubmode.value]
        if self.very_verbose:
            print(" = %s"%self.recorder_submode)
        return self.recorder_submode

    def _set_recorder_submode(self, mode):
        if self.very_verbose:
            print("%s: setting recorder submode = %s"%(self.name, mode))
        mode_to_number = {"sequence":0, "ring_buffer":1}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_recorder_submode(self.handle, mode_to_number[mode])
        assert self._get_recorder_submode() == mode
        if self.very_verbose:
            print("%s: -> done setting recorder submode."%self.name)
        return None

    def _get_timestamp_mode(self):
        if self.very_verbose:
            print("%s: getting timestamp mode"%self.name, end='')
        number_to_mode = {0:"off", 1:"binary", 2:"binary+ASCII"}
        wTimeStamp = C.c_uint16(777) # 777 not valid -> should change
        dll.get_timestamp_mode(self.handle, wTimeStamp)
        self.timestamp_mode = number_to_mode[wTimeStamp.value]
        if self.very_verbose:
            print(" = %s"%self.timestamp_mode)
        return self.timestamp_mode

    def _set_timestamp_mode(self, mode):
        if self.very_verbose:
            print("%s: setting timestamp mode = %s"%(self.name, mode))
        mode_to_number = {"off":0, "binary":1, "binary+ASCII":2}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_timestamp_mode(self.handle, mode_to_number[mode])
        assert self._get_timestamp_mode() == mode
        if self.very_verbose:
            print("%s: -> done setting timestamp mode"%self.name)
        return None

    def _get_trigger_mode(self):
        if self.very_verbose:
            print("%s: getting trigger mode"%self.name, end='')
        number_to_mode = {
            0:"auto", 1: "software", 2:"external", 3:"external_exposure"}
        wTriggerMode = C.c_uint16(777) # 777 not valid -> should change
        dll.get_trigger_mode(self.handle, wTriggerMode)
        self.trigger_mode = number_to_mode[wTriggerMode.value]
        if self.very_verbose:
            print(" = %s"%self.trigger_mode)
        return self.trigger_mode

    def _set_trigger_mode(self, mode):
        """
        Modes:
        - 'auto trigger': new exposure is automatically started immediatly after
        readout (or simultaneously for CCD). Trigger in signals ignored.
        - 'software trigger': exposure can only be started by force trigger
        command.
        - 'external_trigger': a delay / exposure sequence is started at the
        RISING or FALLING edge of the trigger input (<exp trig> = SMA input #1).
        - 'external_exposure': exposure time defined by pulse length at the
        trigger input (delay and exposure cmds are ineffective).
        """
        if self.very_verbose:
            print("%s: setting trigger mode = %s"%(self.name, mode))
        mode_to_number = {
            "auto":0, "software":1, "external":2, "external_exposure":3}
        assert mode in mode_to_number, "mode '%s' not allowed"%mode
        dll.set_trigger_mode(self.handle, mode_to_number[mode])
        assert self._get_trigger_mode() == mode
        if self.very_verbose:
            print("%s: -> done setting trigger mode"%self.name)
        return None

    def _force_trigger(self):
        assert self.trigger_mode in ('software', 'external', 'external_exposure')
        wTriggerMode = C.c_uint16(777) # 777 not valid -> should change
        dll.force_trigger(self.handle, wTriggerMode)
        assert wTriggerMode.value in (0, 1)
        return bool(wTriggerMode.value) # True = new exposure triggered

    def _get_exposure_time_us(self): # should we use 'PCO_GetImageTiming'?
        if self.very_verbose:
            print("%s: getting delay and exposure times (us)"%self.name)
        number_to_factor = {0:1e-3, 1:1, 2:1e3} # {0:ns, 1:us, 2:ms}
        dwDelay, dwExposure  = C.c_uint32(777), C.c_uint32(777) # 777 -> change
        wTimeBaseDelay, wTimeBaseExposure = C.c_uint16(777), C.c_uint16(777)
        dll.get_delay_exposure_time(
            self.handle, dwDelay, dwExposure, wTimeBaseDelay, wTimeBaseExposure)
        self.delay_us = int(
            dwDelay.value * number_to_factor[wTimeBaseDelay.value])
        self.exposure_us = int(
            dwExposure.value * number_to_factor[wTimeBaseExposure.value])
        if self.very_verbose:
            print("%s:  delay    = %08i"%(self.name, self.delay_us))
            print("%s:  exposure = %08i"%(self.name, self.exposure_us))
        return self.exposure_us

    def _set_exposure_time_us(self, exposure_us, delay_us=0):
        if self.very_verbose:
            print("%s: setting exposure time (us) = %08i (delay=%08i)"%(
                self.name, exposure_us, delay_us))
        assert type(exposure_us) is int and type(delay_us) is int
        assert 1e2 <= exposure_us <= 1e7, 'exposure %i out of range'%exposure_us
        assert 0 <= delay_us <= 1e6, 'delay %i out of range'%delay_us
        dll.set_delay_exposure_time(
            self.handle, delay_us, exposure_us, 1, 1) # 1 -> us
        assert self._get_exposure_time_us() == exposure_us
        self.delay_us = delay_us
        if self.very_verbose:
            print("%s: -> done setting exposure time."%self.name)
        return None

    def _get_roi(self):
        if self.very_verbose:
            print("%s: getting roi pixels"%self.name)
        wRoiX0, wRoiY0, wRoiX1, wRoiY1 =(
            C.c_uint16(777), C.c_uint16(777), C.c_uint16(777), C.c_uint16(777))
        dll.get_roi(self.handle, wRoiX0, wRoiY0, wRoiX1, wRoiY1)
        self.roi_px = {'left':wRoiX0.value, 'right'  : wRoiX1.value,
                       'top' :wRoiY0.value,  'bottom': wRoiY1.value}
        self.height_px = self.roi_px['bottom'] - self.roi_px['top'] + 1
        self.width_px =  self.roi_px['right'] - self.roi_px['left'] + 1
        self.bytes_per_image = 2 * self.height_px * self.width_px # 16 bit
        self.rolling_time_us = self.line_time_us * (self.height_px / 2)
        if self.very_verbose:
            print("%s:  = %s"%(self.name, self.roi_px))
        return self.roi_px

    def _set_roi(self, roi_px):
        # only certain values and combinations allowed -> use legalizer!
        if self.very_verbose:
            print("%s: setting roi pixels"%(self.name))
            print("%s:  = %s"%(self.name, roi_px))
        dll.set_roi(self.handle,
                    roi_px['left'], roi_px['top'],
                    roi_px['right'], roi_px['bottom'])
        assert self._get_roi() == roi_px
        if self.very_verbose:
            print("%s: -> done setting roi pixels"%self.name)
        return None

    def _get_image_size(self):
        if self.very_verbose:
            print("%s: getting image sizes"%self.name)
        wXRes, wYRes, wXResMax, wYResMax = (
            C.c_uint16(777), C.c_uint16(777), C.c_uint16(777), C.c_uint16(777))
        dll.get_sizes(self.handle, wXRes, wYRes, wXResMax, wYResMax)
        height_px, width_px = wYRes.value, wXRes.value
        if self.very_verbose:
            print("%s:  = %i x %i (height x width)"%(
                self.name, height_px, width_px))
        return height_px, width_px

    def _disarm(self):
        if self.very_verbose: print("%s: disarming..."%self.name, end='')
        dll.set_recording_state(self.handle, 0)
        dll.cancel_images(self.handle)
        if self._armed:
            for i in range(self._num_buffers):
                dll.free_buffer(self.handle, i)
        self._armed = False
        if self.very_verbose: print(" done.")
        return None

    def _arm(self, num_buffers):
        if self.very_verbose: print("%s: arming..."%self.name)
        assert not self._armed, 'the camera is already armed...'
        assert 1 <= num_buffers <= 16
        dll.arm_camera(self.handle)
        assert self._get_image_size() == (self.height_px, self.width_px)
        # allocate buffers for camera to use for images
        h_px, w_px = self.height_px, self.width_px
        self.buffers = []
        for i in range(num_buffers):
            buffer_index = C.c_int16(-1) # create new
            self.buffers.append(np.zeros((h_px, w_px), 'uint16')) # -> image
            c_buffer = np.ctypeslib.as_ctypes(self.buffers[i]) # -> to c
            c_buffer_pointer = C.cast(c_buffer, C.POINTER(C.c_ushort)) # pointer
            buffer_event = C.c_void_p(0) # internal creation
            dll.allocate_buffer(
                self.handle,
                buffer_index,
                self.bytes_per_image,
                c_buffer_pointer,
                buffer_event)
            assert buffer_index.value == i
        dll.set_image_parameters(self.handle, w_px, h_px, 1, C.c_void_p(), 0)
        dll.set_recording_state(self.handle, 1)
        # add allocated buffers to the camera 'driver queue'
        self.added_buffers = []
        for i in range(num_buffers):
            dll.add_buffer(self.handle, 0, 0, i, w_px, h_px, 16)
            self.added_buffers.append(i)
        self._armed = True
        self._num_buffers = num_buffers
        self.timeout_ms = int(1000 + 2 * 1e-3 * self.exposure_us)
        if self.very_verbose: print("%s: -> done arming."%self.name)
        return None

    def apply_settings(
        self,
        num_images=None,    # total number of images to record, type(int)
        exposure_us=None,   # 100 <= type(int) <= 10,000,000
        height_px=None,     # adjusted by legalize_image_size(), type(int)
        width_px=None,      # adjusted by legalize_image_size(), type(int)
        timestamp=None,     # "off"/"binary"/"binary+ASCII"       
        trigger=None,       # "auto"/"software"/"external"/"external_exposure"
        num_buffers=None,   # 1 <= type(int) <= 16
        timeout_ms=None,    # buffer timeout, type(int) (default set by ._arm())
        check_health=True,  # optional health check
        ):
        if self.verbose: print("%s: applying settings..."%self.name)
        if self._armed: self._disarm()
        if num_images is not None:
            assert type(num_images) is int
            self.num_images = num_images
        if exposure_us is not None: self._set_exposure_time_us(exposure_us)
        if height_px is not None or width_px is not None:
            if height_px is None: height_px = self.height_px
            if width_px  is None: width_px  = self.width_px
            roi_px = legalize_image_size(
                height_px, width_px, name=self.name, verbose=self.verbose)[2]
            self._set_roi(roi_px)
        if timestamp is not None: self._set_timestamp_mode(timestamp) 
        if trigger is not None: self._set_trigger_mode(trigger)
        if check_health: self._get_health_status(check=True)
        if num_buffers is not None: self._num_buffers = num_buffers
        self._arm(self._num_buffers)
        if timeout_ms is not None:
            assert type(timeout_ms) is int
            self.timeout_ms = timeout_ms
        if self.verbose: print("%s: -> done applying settings."%self.name)
        return None

    def record_to_memory(
        self,
        allocated_memory=None,  # optionally pass numpy array for images
        software_trigger=False,  # False -> external trigger needed
        ):
        if self.verbose:
            print("%s: recording to memory..."%self.name)
        assert self._armed, 'camera not armed -> call .apply_settings()'
        h_px, w_px = self.height_px, self.width_px
        if allocated_memory is None: # make numpy array if none given
            allocated_memory = np.zeros((self.num_images, h_px, w_px), 'uint16')
            output = allocated_memory # no memory provided so return some images
        else: # images placed in provided array
            assert isinstance(allocated_memory, np.ndarray)
            assert allocated_memory.dtype == np.uint16
            assert allocated_memory.shape == (self.num_images, h_px, w_px)
            output = None # avoid returning potentially large array
        buflist = (PCO_Buflist * 1)() # make a PCO list of buffers
        for i in range(self.num_images):
            if software_trigger:
                assert self._force_trigger(), 'software trigger failed'
            buffer_index = self.added_buffers.pop(0) # get next available buffer
            buflist[0].SBufNr = buffer_index # pass index into buffer list
            try:
                dll.wait_for_buffer(self.handle, 1, buflist, self.timeout_ms)
            except Exception as e:
                print("%s: -> buffer timeout?"%self.name)
                raise
            assert buflist[0].dwStatusDll == 0xe0008000 # buffer event set
            if buflist[0].dwStatusDrv != 0: # image transfer failed
                err = buflist[0].dwStatusDrv.value
                if err == 0x80332028: err = 'DMA error'
                print("%s:  error during record to memory: %s"%(self.name, err))
                raise
            allocated_memory[i, :, :] = self.buffers[buffer_index] # get image
            remaining_images = self.num_images - i - 1
            # put the buffer back in the driver queue -> ready for multi-record
            dll.add_buffer(self.handle, 0, 0, buffer_index, w_px, h_px, 16)
            self.added_buffers.append(buffer_index)
        assert remaining_images == 0, 'acquired images != requested'
        if self.verbose:
            print("%s: -> done recording to memory."%self.name)
        return output

    def close(self):
        self._disarm()
        if self.verbose: print("%s: closing..."%self.name, end='')
        dll.close_camera(self.handle)
        if self.verbose: print(" done.")
        return None

def legalize_image_size(
    height_px='max', width_px='max', name='PCO.edge5.5', verbose=True):
    """returns a nearby legal image size at the *center* of the camera chip"""
    height_step, width_step = 1, 4
    min_height, min_width, max_height, max_width = 16, 64, 2160, 2560
    ud_center = (max_height / 2)
    lr_center = (max_width  / 2)
    if verbose:
        print("%s: requested image size (pixels)"%name)
        print("%s:  = %s x %s (height x width)"%(name, height_px, width_px))
    if height_px == 'min': height_px = min_height
    if height_px == 'max': height_px = max_height        
    if width_px  == 'min': width_px  = min_width
    if width_px  == 'max': width_px  = max_width
    assert type(height_px) is int and type(width_px) is int
    assert min_height <= height_px <= max_height    
    assert min_width  <= width_px  <= max_width
    num_height_steps = (height_px // height_step)
    num_width_steps  = (width_px  // width_step)
    if num_height_steps % 2 != 0: num_height_steps += 1 # must be even for chip
    if num_width_steps  % 2 != 0: num_width_steps  += 1 # must be even for chip 
    height_px = height_step * num_height_steps # now legalized
    width_px  = width_step  * num_width_steps  # now legalized
    left   = int(lr_center - (width_px  / 2)) + 1
    right  = int(lr_center + (width_px  / 2))
    top    = int(ud_center - (height_px / 2)) + 1
    bottom = int(ud_center + (height_px / 2))
    roi_px = {'left': left, 'right': right, 'top': top, 'bottom': bottom}
    if verbose:
        print("%s: legal image size (pixels)"%name)
        print("%s:  = %i x %i (height x width)"%(name, height_px, width_px))
        print("%s: roi px"%name)
        print("%s:  = %s"%(name, roi_px))
    return height_px, width_px, roi_px


### Tidy and store DLL calls away from main program:

os.add_dll_directory(os.getcwd())
dll = C.oledll.LoadLibrary('SC2_Cam') # needs "SC2_Cam.dll" in directory

dll.get_error_text = dll.PCO_GetErrorText
dll.get_error_text.argtypes = [
    C.c_uint32,             # dwerr (error number)
    C.c_char_p,             # pbuf (error description as ascii string)
    C.c_uint32]             # dwlen (size of description in bytes)

def check_error(error_code):
    if error_code == 0:
        return 0
    else:
        dwlen = 1000
        error_description = C.c_char_p(dwlen * b'')
        dll.get_error_text(error_code, error_description, dwlen)
        raise OSError(error_description.value.decode('ascii'))

dll.reboot_camera = dll.PCO_RebootCamera
dll.reboot_camera.argtypes = [
    C.c_void_p]             # ph (Pointer to a HANDLE)

dll.reset_dll = dll.PCO_ResetLib
dll.reset_dll.restype = check_error

dll.open_camera = dll.PCO_OpenCamera
dll.open_camera.argtypes = [
    C.POINTER(C.c_void_p),  # ph (Pointer to a HANDLE)
    C.c_uint16]             # wCamNum (Not used)
dll.open_camera.restype = check_error

dll.get_camera_name = dll.PCO_GetCameraName
dll.get_camera_name.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_char_p,             # szCameraName (Pointer to 40 byte character array)
    C.c_uint16]             # wSZCameraNameLen (Size of array)
dll.get_camera_name.restype = check_error

dll.reset_settings_to_default = dll.PCO_ResetSettingsToDefault
dll.reset_settings_to_default.argtypes = [
    C.c_void_p]             # ph (Handle to an open camera)
dll.reset_settings_to_default.restype = check_error

dll.get_camera_health = dll.PCO_GetCameraHealthStatus
dll.get_camera_health.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint32),  # dwWarn (Pointer to Warning Bits)
    C.POINTER(C.c_uint32),  # dwErr (Pointer to Error Bits)
    C.POINTER(C.c_uint32)]  # dwStatus (Pointer to Status Bits)
dll.get_camera_health.restype = check_error

dll.get_temperature = dll.PCO_GetTemperature
dll.get_temperature.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_int16),   # sCCDTemp (10x image sensor temp in degC)
    C.POINTER(C.c_int16),   # sCamTemp (internal camera temp in degC)
    C.POINTER(C.c_int16)]   # sPowTemp (power supply temp in degC)
dll.get_temperature.restype = check_error

dll.get_sensor_format = dll.PCO_GetSensorFormat
dll.get_sensor_format.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wSensor (0=standard, 1=extended)
dll.get_sensor_format.restype = check_error

dll.set_sensor_format = dll.PCO_SetSensorFormat
dll.set_sensor_format.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wSensor (0=standard, 1=extended)
dll.set_sensor_format.restype = check_error

dll.get_acquire_mode = dll.PCO_GetAcquireMode
dll.get_acquire_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wAcquMode (0=auto, 1=external, 2=ext modulate)
dll.get_acquire_mode.restype = check_error

dll.set_acquire_mode = dll.PCO_SetAcquireMode
dll.set_acquire_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wAcquMode (0=auto, 1=external, 2=ext modulate)
dll.set_acquire_mode.restype = check_error

dll.get_pixel_rate = dll.PCO_GetPixelRate
dll.get_pixel_rate.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint32)]  # dwPixelRate (pixel rate in Hz)
dll.get_pixel_rate.restype = check_error

dll.set_pixel_rate = dll.PCO_SetPixelRate
dll.set_pixel_rate.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint32]             # dwPixelRate (pixel rate in Hz)
dll.set_pixel_rate.restype = check_error

dll.get_storage_mode = dll.PCO_GetStorageMode
dll.get_storage_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wStorageMode (0=recorder, 1=FIFO buffer)
dll.get_storage_mode.restype = check_error

dll.set_storage_mode = dll.PCO_SetStorageMode
dll.set_storage_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wStorageMode (0=recorder, 1=FIFO buffer)
dll.set_storage_mode.restype = check_error

dll.get_recorder_submode = dll.PCO_GetRecorderSubmode
dll.get_recorder_submode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wRecSubmode (0=sequence, 1=ring buffer)
dll.get_recorder_submode.restype = check_error

dll.set_recorder_submode = dll.PCO_SetRecorderSubmode
dll.set_recorder_submode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wRecSubmode (0=sequence, 1=ring buffer)
dll.set_recorder_submode.restype = check_error

dll.get_timestamp_mode = dll.PCO_GetTimestampMode
dll.get_timestamp_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wTimeStampMode (0=off,1=bin,2=bin+ascii,3=ascii)
dll.get_timestamp_mode.restype = check_error

dll.set_timestamp_mode = dll.PCO_SetTimestampMode
dll.set_timestamp_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wTimeStampMode (0=off,1=bin,2=bin+ascii,3=ascii)
dll.set_timestamp_mode.restype = check_error

dll.get_trigger_mode = dll.PCO_GetTriggerMode
dll.get_trigger_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wTriggerMode (0=auto,1=software,2=ext,3=ext_exp)
dll.get_trigger_mode.restype = check_error

dll.set_trigger_mode = dll.PCO_SetTriggerMode
dll.set_trigger_mode.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wTriggerMode (0=auto,1=software,2=ext,3=ext_exp)
dll.set_trigger_mode.restype = check_error

dll.force_trigger = dll.PCO_ForceTrigger
dll.force_trigger.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16)]  # wTriggered (0=unsuccessful, 1=new exp. triggered)
dll.force_trigger.restype = check_error

dll.get_delay_exposure_time = dll.PCO_GetDelayExposureTime
dll.get_delay_exposure_time.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint32),  # dwDelay (integer delay time)
    C.POINTER(C.c_uint32),  # dwExposure (exposure delay time)
    C.POINTER(C.c_uint16),  # wTimeBaseDelay (0:ns, 1:us, 2:ms)
    C.POINTER(C.c_uint16)]  # wTimeBaseExposure (0:ns, 1:us, 2:ms)
dll.get_delay_exposure_time.restype = check_error

dll.set_delay_exposure_time = dll.PCO_SetDelayExposureTime
dll.set_delay_exposure_time.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint32,             # dwDelay (integer delay time)
    C.c_uint32,             # dwExposure (exposure delay time)
    C.c_uint16,             # wTimeBaseDelay (0:ns, 1:us, 2:ms)
    C.c_uint16]             # wTimeBaseExposure (0:ns, 1:us, 2:ms)
dll.set_delay_exposure_time.restype = check_error

dll.get_roi = dll.PCO_GetROI
dll.get_roi.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16),  # wRoiX0 (horizontal start co-ord)
    C.POINTER(C.c_uint16),  # wRoiY0 (vertical start co-ord)
    C.POINTER(C.c_uint16),  # wRoiX1 (horizontal end co-ord)
    C.POINTER(C.c_uint16)]  # wRoiY1 (vertical end co-ord)
dll.get_roi.restype = check_error

dll.set_roi = dll.PCO_SetROI
dll.set_roi.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16,             # wRoiX0 (horizontal start co-ord)
    C.c_uint16,             # wRoiY0 (vertical start co-ord)
    C.c_uint16,             # wRoiX1 (horizontal end co-ord)
    C.c_uint16]             # wRoiY1 (vertical end co-ord)
dll.set_roi.restype = check_error

dll.arm_camera = dll.PCO_ArmCamera
dll.arm_camera.argtypes = [
    C.c_void_p]             # ph (Handle to an open camera)
dll.arm_camera.restype = check_error

dll.get_sizes = dll.PCO_GetSizes
dll.get_sizes.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_uint16),  # wXResAct (current horizontal resolution)
    C.POINTER(C.c_uint16),  # wYResAct (current vertical resolution)
    C.POINTER(C.c_uint16),  # wXResMax (maximum horizontal resolution)
    C.POINTER(C.c_uint16)]  # wYResMax (maximum vertical resolution)
dll.get_sizes.restype = check_error

dll.allocate_buffer = dll.PCO_AllocateBuffer
dll.allocate_buffer.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.POINTER(C.c_int16),   # sBufNr (buffer index -> set to '-1' to create new)
    C.c_uint32,             # dwSize (buffer size in bytes)
    C.POINTER(C.POINTER(C.c_uint16)),    
                            # wBuf (pointer to a pointer of valid memory block,
                            # -> set to NULL for internal allocation)
    C.POINTER(C.c_void_p)]  # hEvent (event handle for created buffer,
                            # -> set to NULL for internal handle creation)
dll.allocate_buffer.restype = check_error

dll.set_image_parameters = dll.PCO_SetImageParameters
dll.set_image_parameters.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16,             # wxres (current horizontal resolution of image)
    C.c_uint16,             # wyres (current vertical resolution of image)
    C.c_uint32,             # dwFlags (Soft ROI action bit field)
    C.POINTER(C.c_void_p),  # reserved
    C.c_int32]              # reserved
dll.set_image_parameters.restype = check_error

dll.set_image_parameters.restype = check_error

dll.set_recording_state = dll.PCO_SetRecordingState
dll.set_recording_state.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint16]             # wRecState (0x0000 = stop, 0x0001 = start)
dll.set_recording_state.restype = check_error

dll.add_buffer = dll.PCO_AddBufferEx
dll.add_buffer.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_uint32,             # dw1stImage (image num = 0 for 'run', n for 'stop')
    C.c_uint32,             # dwLastImage (set to dw1stImage)
    C.c_int16,              # sBufNr (buffer index)
    C.c_uint16,             # wXRes (current horizontal resolution of image)
    C.c_uint16,             # wYRes (current vertical resolution of image)
    C.c_uint16]             # wBitPerPixel (bit resolution of image = 16)
dll.add_buffer.restype = check_error

dll.get_buffer_status = dll.PCO_GetBufferStatus
dll.get_buffer_status.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_int16,              # sBufNr (buffer index)
    C.POINTER(C.c_uint32),  # dwStatusDll (status inside SDK dll)
    C.POINTER(C.c_uint32)]  # dwStatusDrv (image transfer status, 0 = success!)
dll.get_buffer_status.restype = check_error

class PCO_Buflist(C.Structure):
    _fields_ = [
        ("SBufNr", C.c_int16),      # "size of this struct" -> buffer index
        ("reserved", C.c_uint16),   # reserved...
        ("dwStatusDll", C.c_uint32),# (status inside SDK dll)
        ("dwStatusDrv", C.c_uint32)]# (image transfer status, 0 = success!)

dll.wait_for_buffer = dll.PCO_WaitforBuffer
dll.wait_for_buffer.argytpes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_int,                # nr_of_buffer (number of PCO_Buflist entries)
    C.POINTER(PCO_Buflist), # bl (pointer to a list of PCO_Buflist structures)
    C.c_int]                # timeout (timeout in ms)
dll.wait_for_buffer.restype = check_error

dll.cancel_images = dll.PCO_CancelImages
dll.cancel_images.argtypes = [
    C.c_void_p]             # ph (Handle to an open camera)
dll.cancel_images.restype = check_error

dll.free_buffer = dll.PCO_FreeBuffer
dll.free_buffer.argtypes = [
    C.c_void_p,             # ph (Handle to an open camera)
    C.c_int16]              # sBufNr (Buffer index)
dll.free_buffer.restype = check_error

dll.close_camera = dll.PCO_CloseCamera
dll.close_camera.argtypes = [
    C.c_void_p]             # ph (Handle to an open camera)
dll.close_camera.restype = check_error


if __name__ == '__main__':
    from tifffile import imwrite
    camera = Camera(verbose=True, very_verbose=False)
##    camera._reboot()

    # take some pictures:
    camera.apply_settings(num_images=10, exposure_us=100, height_px='max', width_px='max', trigger='auto')
    images = camera.record_to_memory(software_trigger=False)
    imwrite('test0.tif', images, imagej=True)

    # max fps test:
    frames = 100
    camera.apply_settings(frames, 100, 'max', 'max', 'binary+ASCII', 'auto')
    images = np.zeros(
        (camera.num_images, camera.height_px, camera.width_px), 'uint16')
    t0 = time.perf_counter()
    camera.record_to_memory(allocated_memory=images, software_trigger=False)
    time_s = time.perf_counter() - t0
    print("\nMax fps = %0.2f\n"%(frames/time_s)) # ~ 100 -> 9000 typical
    imwrite('test1.tif', images, imagej=True)

    # max fps test -> multiple recordings:
    iterations = 5
    frames = 100
    camera.apply_settings(frames, 100, 'max', 'max', 'binary+ASCII', 'auto')
    images = np.zeros(
        (camera.num_images, camera.height_px, camera.width_px), 'uint16')
    t0 = time.perf_counter()
    for i in range(iterations):
        camera.record_to_memory(
            allocated_memory=images, software_trigger=False)
    time_s = time.perf_counter() - t0
    total_frames = iterations * frames
    print("\nMax fps = %0.2f\n"%(total_frames/time_s)) # ~ 100 -> 9000 typical
    imwrite('test2.tif', images, imagej=True)
    
    camera.close()
