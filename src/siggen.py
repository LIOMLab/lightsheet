'''
Created on May 16, 2019

@author: Pierre Girard-Collins
'''
import sys
sys.path.append(".")

import numpy as np

# National Instruments Imports
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge

from src.camera import Camera

from src.config import cfg_read, cfg_write, cfg_str2bool
from src.waveforms import squarewave, sawtooth, staircase


class SigGen:
    """
    Class for generating and sending timing signals to galvos, etls and camera
    
    """

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults = {}
    _cfg_defaults['AO Terminals']             = '/Dev1/ao0:3'         # DAQ board AO terminals for Galvo + ETL scan ramps
    _cfg_defaults['DO Terminals']             = '/Dev1/port0/line1'   # DAQ board DO terminals for Camera Exposure Control
    _cfg_defaults['Sample Rate']              = '40000'               # In samples/second
    _cfg_defaults['Galvo Pre Time']           = '0.001'               # [s]
    _cfg_defaults['Galvo Scan Time']          = '0.100'               # [s]
    _cfg_defaults['Galvo Reset Time']         = '0.025'               # [s]
    _cfg_defaults['Galvo Post Time']          = '0.001'               # [s]
    _cfg_defaults['Galvo Activated']          = 'True'                # Boolean
    _cfg_defaults['Galvo Inverted']           = 'False'               # Boolean
    _cfg_defaults['Galvo Left Amplitude']     = '1.0'                 # In volts
    _cfg_defaults['Galvo Left Offset']        = '0.5'                 # In volts
    _cfg_defaults['Galvo Right Amplitude']    = '1.0'                 # In volts
    _cfg_defaults['Galvo Right Offset']       = '0.5'                 # In volts
    _cfg_defaults['ETL Activated']            = 'False'               # Boolean
    _cfg_defaults['ETL Steps']                = '5'                   # Number of focus regions over FOV
    _cfg_defaults['ETL Left Amplitude']       = '1.0'                 # In volts
    _cfg_defaults['ETL Left Offset']          = '0.5'                 # In volts
    _cfg_defaults['ETL Right Amplitude']      = '1.0'                 # In volts
    _cfg_defaults['ETL Right Offset']         = '0.5'                 # In volts


    def __init__(self, camera:Camera):
        # Error status
        self.error = 0
        self.error_message = ''

        # We need to know about camera settings to generate the proper waveforms
        self.camera = camera
        
        self.task_galvo_etl = None
        self.task_camera = None

        self.waveform_metadata = None
        self.waveform_cycles = None
        self.waveform_camera = None
        self.waveform_galvo_left = None
        self.waveform_galvo_right = None
        self.waveform_etl_left = None
        self.waveform_etl_right = None

        # read configurable settings from config.ini file
        self._cfg_filename = 'config.ini'
        self._cfg_section = 'SigGen'
        self.cfg_load_ini()


    def cfg_load_ini(self):
        self._cfg = cfg_read(self._cfg_filename, self._cfg_section, self._cfg_defaults)

        # set instance variables from configuration dictionary values
        self.ao_terminals           = str(          self._cfg['AO Terminals']           )
        self.do_terminals           = str(          self._cfg['DO Terminals']           )
        self.sample_rate            = int(          self._cfg['Sample Rate']            )
        self.galvo_pre_time         = float(        self._cfg['Galvo Pre Time']         )
        self.galvo_scan_time        = float(        self._cfg['Galvo Scan Time']        )
        self.galvo_reset_time       = float(        self._cfg['Galvo Reset Time']       )
        self.galvo_post_time        = float(        self._cfg['Galvo Post Time']        )
        self.galvo_activated        = cfg_str2bool( self._cfg['Galvo Activated']        )
        self.galvo_inverted         = cfg_str2bool( self._cfg['Galvo Inverted']         )
        self.galvo_left_amplitude   = float(        self._cfg['Galvo Left Amplitude']   )
        self.galvo_left_offset      = float(        self._cfg['Galvo Left Offset']      )
        self.galvo_right_amplitude  = float(        self._cfg['Galvo Right Amplitude']  )
        self.galvo_right_offset     = float(        self._cfg['Galvo Right Offset']     )
        self.etl_activated          = cfg_str2bool( self._cfg['ETL Activated']          )
        self.etl_steps              = int(          self._cfg['ETL Steps']              )
        self.etl_left_amplitude     = float(        self._cfg['ETL Left Amplitude']     )
        self.etl_left_offset        = float(        self._cfg['ETL Left Offset']        )
        self.etl_right_amplitude    = float(        self._cfg['ETL Right Amplitude']    )
        self.etl_right_offset       = float(        self._cfg['ETL Right Offset']       )

        ao_device                   = self.ao_terminals.rsplit('/', 1)[0]
        ao_channels                 = self.ao_terminals.rsplit('/',1)[1][2:].rsplit(':')
        self.do_start_trigger       = ao_device + '/ao/StartTrigger'
        self.galvo_terminals        = ao_device + '/ao' + ao_channels[0] + ':' + str(int(ao_channels[0])+1)
        self.etl_terminals          = ao_device + '/ao' + str(int(ao_channels[1])-1) + ':' + ao_channels[1]



    def cfg_save_ini(self):
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg['AO Terminals']             = str( self.ao_terminals                  )
        self._cfg['DO Terminals']             = str( self.do_terminals                  )
        self._cfg['Sample Rate']              = str( self.sample_rate                   )
        self._cfg['Galvo Pre Time']           = str( self.galvo_pre_time                )
        self._cfg['Galvo Scan Time']          = str( self.galvo_scan_time               )
        self._cfg['Galvo Reset Time']         = str( self.galvo_reset_time              )
        self._cfg['Galvo Post Time']          = str( self.galvo_post_time               )
        self._cfg['Galvo Activated']          = str( self.galvo_activated               )  
        self._cfg['Galvo Inverted']           = str( self.galvo_inverted                )
        self._cfg['Galvo Left Amplitude']     = str( self.galvo_left_amplitude          )
        self._cfg['Galvo Left Offset']        = str( self.galvo_left_offset             )
        self._cfg['Galvo Right Amplitude']    = str( self.galvo_right_amplitude         )
        self._cfg['Galvo Right Offset']       = str( self.galvo_right_offset            )
        self._cfg['ETL Activated']            = str( self.etl_activated                 )
        self._cfg['ETL Steps']                = str( self.etl_steps                     )
        self._cfg['ETL Left Amplitude']       = str( self.etl_left_amplitude            )
        self._cfg['ETL Left Offset']          = str( self.etl_left_offset               )
        self._cfg['ETL Right Amplitude']      = str( self.etl_right_amplitude           )
        self._cfg['ETL Right Offset']         = str( self.etl_right_offset              )

        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)



    def update_all(self, left_galvo:float, right_galvo:float, left_etl:float, right_etl:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_setpoints     = np.stack((    np.array([right_galvo]),
                                                np.array([left_galvo]),
                                                np.array([left_etl]),
                                                np.array([right_etl])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'galvo_etl_setpoint') as task_update_all:
                task_update_all.ao_channels.add_ao_voltage_chan(self.ao_terminals)
                task_update_all.write(galvo_etl_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'update_all error'
            print('SigGen - update_all error')


    def update_galvos(self, left_galvo:float, right_galvo:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_setpoints     = np.stack((    np.array([right_galvo]),
                                            np.array([left_galvo])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'galvo_single') as task_update_galvos:
                task_update_galvos.ao_channels.add_ao_voltage_chan(self.galvo_terminals)
                task_update_galvos.write(galvo_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'update_galvos error'
            print('SigGen - update_galvos error')


    def update_etls(self, left_etl:float, right_etl:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        etl_setpoints     = np.stack((  np.array([left_etl]),
                                        np.array([right_etl])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'etl_single') as task_update_etls:
                task_update_etls.ao_channels.add_ao_voltage_chan(self.etl_terminals)
                task_update_etls.write(etl_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'update_etls error'
            print('SigGen - update_etls error')


    def create_scanner(self):
        '''Creates Galvo + ETL scan task (AO) + Camera Exposure Control task (DO)'''
        
        # Stack galvo and etl waveforms into single array
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_waveforms = np.stack((self.waveform_galvo_right, self.waveform_galvo_left, self.waveform_etl_left, self.waveform_etl_right))

        try:
            # Creating and setting up the galvo + ETL scan task (AO)
            self.task_galvo_etl = nidaqmx.Task(new_task_name = 'galvo_etl_scan')
            self.task_galvo_etl.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            self.task_galvo_etl.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.total_samples)

            # Creating and setting up the camera exposure control task (DO)
            self.task_camera = nidaqmx.Task(new_task_name = 'camera_scan')
            self.task_camera.do_channels.add_do_chan(self.do_terminals, line_grouping = LineGrouping.CHAN_PER_LINE)
            self.task_camera.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.total_samples)

            # Setup DO task to be triggered by AO start_trigger signal (AO is master task)
            self.task_camera.triggers.start_trigger.cfg_dig_edge_start_trig(self.do_start_trigger, trigger_edge = Edge.RISING)

            # Write waveforms to AO and DO tasks (to be started later)
            self.task_camera.write(self.waveform_camera, auto_start = False)
            self.task_galvo_etl.write(galvo_etl_waveforms, auto_start = False)
        except:
            self.task_galvo_etl = None
            self.task_camera = None
            self.error = 1
            self.error_message = 'create_scan error'
            print('SigGen - create_scan error')


    def start_scanner(self):
        '''Start both AO and DO tasks'''
        if self.task_galvo_etl is not None and self.task_camera is not None:
            # Master task needs to be started last
            self.task_camera.start()
            self.task_galvo_etl.start()


    def monitor_scanner(self):
        '''Wait for AO and DO tasks to complete'''
        if self.task_galvo_etl is not None and self.task_camera is not None:
            self.task_camera.wait_until_done()
            self.task_galvo_etl.wait_until_done()


    def stop_scanner(self):
        '''Stop AO and DO tasks'''
        if self.task_galvo_etl is not None and self.task_camera is not None:
            self.task_camera.stop()
            self.task_galvo_etl.stop()


    def delete_scanner(self):
        '''Delete AO and DO tasks'''
        if self.task_galvo_etl is not None and self.task_camera is not None:
            self.task_camera.close()
            self.task_camera = None
            self.task_galvo_etl.close()
            self.task_galvo_etl = None


    def compute_scan_waveforms(self):
        '''Compute Galvo + ETL scan ramps and Camera Exposure waveforms based on instance variables'''

        # Save current settings to waveform metadata
        self.waveform_metadata = {}
        self.waveform_metadata['Galvo Activated']          = str( self.galvo_activated              )
        self.waveform_metadata['Galvo Inverted']           = str( self.galvo_inverted               )
        self.waveform_metadata['Galvo Left Amplitude']     = str( self.galvo_left_amplitude         )
        self.waveform_metadata['Galvo Left Offset']        = str( self.galvo_left_offset            )
        self.waveform_metadata['Galvo Right Amplitude']    = str( self.galvo_right_amplitude        )
        self.waveform_metadata['Galvo Right Offset']       = str( self.galvo_right_offset           )
        self.waveform_metadata['ETL Activated']            = str( self.etl_activated                )
        self.waveform_metadata['ETL Steps']                = str( self.etl_steps                    )
        self.waveform_metadata['ETL Left Amplitude']       = str( self.etl_left_amplitude           )
        self.waveform_metadata['ETL Left Offset']          = str( self.etl_left_offset              )
        self.waveform_metadata['ETL Right Amplitude']      = str( self.etl_right_amplitude          )
        self.waveform_metadata['ETL Right Offset']         = str( self.etl_right_offset             )

        # Number of period cycles over the complete waveform (equal to current etl_steps value, but only updated with waveform generation)
        self.waveform_cycles = self.etl_steps

        if self.camera.shutter_mode == 'Lightsheet':
            # Assuming vertical scan amplitude exactly matching camera FOV, galvo line speed must match camera line speed
            # TODO Add correction for potential galvo oversan (will require voltage to optical displacement conversion)
            self.galvo_scan_time = self.camera.line_time * self.camera.ysize
            # In Lightsheet mode, exposure time is overriden by the line time and exposed lines settings
            camera_exposure_time = self.camera.line_time * self.camera.lightsheet_exposed_lines
            camera_delay_time = 3 * self.camera.line_time
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
        
        elif self.camera.shutter_mode == 'Rolling':
            # In Rolling mode, we adjust galvo_scan_time according to requested camera exposure time
            self.galvo_scan_time = self.camera.exposure_time + (self.camera.line_time * 0.5 * self.camera.ysize)
            #FIXME clean things up with galvo_scan_time
            camera_exposure_time = self.galvo_scan_time - (self.camera.line_time * 0.5 * self.camera.ysize)
            camera_delay_time = 3 * self.camera.line_time + (self.camera.line_time * 0.5 * self.camera.ysize)
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
            camera_data_readout_time = (0.5 * self.camera.ysize + 1) * self.camera.line_time
            assert self.galvo_pre_time + self.galvo_reset_time + self.galvo_post_time >= camera_data_readout_time, "Time between galvo scan [reset_time + post_time + next pre-time] is not long enough for camera to complete data readout"
        
        elif self.camera.shutter_mode == 'Global':
            camera_exposure_time = self.galvo_scan_time
            camera_delay_time = (0.5 * self.camera.ysize + 1) * self.camera.line_time
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
            camera_data_readout_time = (0.5 * self.camera.ysize + 1) * self.camera.line_time
            assert self.galvo_pre_time + self.galvo_reset_time + self.galvo_post_time >= camera_data_readout_time, "Time between galvo scan [reset_time + post_time + next pre-time] is not long enough for camera to complete data readout"
        
        else:
            raise Exception('camera shutter mode not supported')

        # galvo waveform generator inputs
        galvo_activated = self.galvo_activated
        galvo_pre_samples = int(np.ceil(self.galvo_pre_time * self.sample_rate))
        galvo_scan_samples = int(np.ceil(self.galvo_scan_time * self.sample_rate))
        galvo_reset_samples = int(np.ceil(self.galvo_reset_time * self.sample_rate))
        galvo_post_samples = int(np.ceil(self.galvo_post_time * self.sample_rate))
        galvo_period_samples = galvo_pre_samples + galvo_scan_samples + galvo_reset_samples + galvo_post_samples
        galvo_shift = camera_delay_samples
        galvo_repeat = self.waveform_cycles
        galvo_inverted = self.galvo_inverted

        # etl waveform generator inputs
        etl_activated = self.etl_activated
        etl_step_samples = galvo_period_samples
        etl_steps = self.waveform_cycles
        etl_shift = camera_delay_samples  - int(np.ceil(galvo_reset_samples/2)) - galvo_post_samples

        # camera waveform generator inputs
        camera_pre_samples = galvo_pre_samples
        camera_active_samples = int(np.ceil(camera_exposure_time * self.sample_rate))
        camera_post_samples = galvo_period_samples - camera_pre_samples - camera_active_samples 
        camera_shift = 0
        camera_repeat = self.waveform_cycles
        camera_inverted = False

        # Number of samples for acquistion sequence (period * number of etl focus positions)
        self.total_samples = galvo_period_samples * self.waveform_cycles
        
        # Time required for an acquisition sequence
        self.total_time = self.total_samples / self.sample_rate

        # Compute camera waveform
        self.waveform_camera = squarewave(      pre_samples = camera_pre_samples,
                                                active_samples = camera_active_samples,
                                                post_samples = camera_post_samples,
                                                shift = camera_shift,
                                                repeat = camera_repeat,
                                                inverted = camera_inverted)
        # Compute galvos waveforms
        self.waveform_galvo_left = sawtooth(    activated = galvo_activated,
                                                pre_samples = galvo_pre_samples,
                                                trace_samples = galvo_scan_samples,
                                                retrace_samples = galvo_reset_samples,
                                                post_samples = galvo_post_samples,
                                                shift = galvo_shift,
                                                repeat = galvo_repeat,
                                                amplitude = self.galvo_left_amplitude, 
                                                offset = self.galvo_left_offset, 
                                                inverted = galvo_inverted)
        
        self.waveform_galvo_right = sawtooth(   activated = galvo_activated,
                                                pre_samples = galvo_pre_samples,
                                                trace_samples = galvo_scan_samples,
                                                retrace_samples = galvo_reset_samples,
                                                post_samples = galvo_post_samples,
                                                shift = galvo_shift,
                                                repeat = galvo_repeat,
                                                amplitude = self.galvo_right_amplitude, 
                                                offset = self.galvo_right_offset, 
                                                inverted = galvo_inverted)
        # Compute etls waveforms
        self.waveform_etl_left = staircase(     activated = etl_activated,
                                                step_samples = etl_step_samples,
                                                nbr_steps = etl_steps,
                                                shift = etl_shift,
                                                amplitude = self.etl_left_amplitude, 
                                                offset = self.etl_left_offset, 
                                                direction = 'down')

        self.waveform_etl_right = staircase(    activated = etl_activated,
                                                step_samples = etl_step_samples,
                                                nbr_steps = etl_steps,
                                                shift = etl_shift,
                                                amplitude = self.etl_right_amplitude, 
                                                offset = self.etl_right_offset, 
                                                direction = 'up')


if __name__ == '__main__':
    
    from matplotlib import pyplot as plt
    test_camera = Camera()
    if test_camera.camera is None:
        test_camera.xsize = 2048
        test_camera.ysize = 2048
        test_camera.line_time = 16.40 * 1e-6
    test_scanner = SigGen(test_camera)
    test_scanner.compute_scan_waveforms()
    print(test_scanner.waveform_metadata)

    time_axis = np.arange(0, test_scanner.waveform_camera.size)
    plt.plot(time_axis, test_scanner.waveform_camera)
    plt.plot(time_axis, test_scanner.waveform_galvo_left)
    plt.plot(time_axis, test_scanner.waveform_galvo_right)
    plt.plot(time_axis, test_scanner.waveform_etl_left)
    plt.plot(time_axis, test_scanner.waveform_etl_right)
    plt.show()

