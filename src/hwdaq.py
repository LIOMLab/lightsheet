'''
Created on May 16, 2019

@author: Pierre Girard-Collins
'''
import sys
sys.path.append(".")

import copy
import numpy as np

# National Instruments Imports
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge

from src.config import cfg_read, cfg_write, cfg_str2bool
from src.waveforms import galvo_ramp, etl_staircase, camera_squarewave


class HwDAQ:
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera'''

    # Configurable settings defaults
    # Used as base dictionnary for .ini file allowable keys
    _cfg_defaults = {}
    _cfg_defaults['AO Terminals']             = '/Dev1/ao0:3'         # DAQ board AO terminals for Galvo + ETL scan ramps
    _cfg_defaults['DO Terminals']             = '/Dev1/port0/line1'   # DAQ board DO terminals for Camera Exposure Control
    _cfg_defaults['Sample Rate']              = '40000'               # In samples/second
    _cfg_defaults['Reset Delay']              = '10'                  # In % of acquisition time (exposure + readout time)
    _cfg_defaults['Exposure Time']            = '50.0'                # In milliseconds
    _cfg_defaults['Camera Shutter Mode']      = 'Global'              # Either 'Global' or 'Lightsheet' (top-to-bottom rolling)
    _cfg_defaults['Camera Line Time']         = '16.40'               # In microseconds
    _cfg_defaults['Camera XSize']             = '2560'                # In pixels
    _cfg_defaults['Camera YSize']             = '2160'                # In pixels
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

    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ''

        self.scan_tasks_active = False
        self.galvo_etl_task = None
        self.camera_task = None

        self.waveform_metadata = None
        self.waveform_cycles = None
        self.waveform_camera = None
        self.waveform_galvo_left = None
        self.waveform_galvo_right = None
        self.waveform_etl_left = None
        self.waveform_etl_right = None

        # read configurable settings from config.ini file
        self._cfg_filename = 'config.ini'
        self._cfg_section = 'HwDAQ'
        self.cfg_load_ini()


    def cfg_load_ini(self):
        self._cfg = cfg_read(self._cfg_filename, self._cfg_section, self._cfg_defaults)
        self.cfg_dict2var()


    def cfg_save_ini(self):
        self.cfg_var2dict()
        self._cfg = cfg_write(self._cfg_filename, self._cfg_section, self._cfg)


    def cfg_dict2var(self):
        # set instance variables from configuration dictionary values
        self.ao_terminals           = str(     self._cfg['AO Terminals']         )
        self.do_terminals           = str(     self._cfg['DO Terminals']         )
        self.sample_rate            = int(     self._cfg['Sample Rate']          )
        self.reset_delay            = float(   self._cfg['Reset Delay']          )
        self.exposure_time          = float(   self._cfg['Exposure Time']        ) * 1e-3
        self.camera_shutter_mode    = str(     self._cfg['Camera Shutter Mode']  )
        self.camera_line_time       = float(   self._cfg['Camera Line Time']     ) * 1e-6
        self.camera_xsize           = int(     self._cfg['Camera XSize']         )
        self.camera_ysize           = int(     self._cfg['Camera YSize']         )
        self.galvo_activated        = cfg_str2bool( self._cfg['Galvo Activated'] )
        self.galvo_inverted         = cfg_str2bool( self._cfg['Galvo Inverted']  )
        self.galvo_left_amplitude   = float(   self._cfg['Galvo Left Amplitude'] )
        self.galvo_left_offset      = float(   self._cfg['Galvo Left Offset']    )
        self.galvo_right_amplitude  = float(   self._cfg['Galvo Right Amplitude'])
        self.galvo_right_offset     = float(   self._cfg['Galvo Right Offset']   )
        self.etl_activated          = cfg_str2bool( self._cfg['ETL Activated']   )
        self.etl_steps              = int(     self._cfg['ETL Steps']            )
        self.etl_left_amplitude     = float(   self._cfg['ETL Left Amplitude']   )
        self.etl_left_offset        = float(   self._cfg['ETL Left Offset']      )
        self.etl_right_amplitude    = float(   self._cfg['ETL Right Amplitude']  )
        self.etl_right_offset       = float(   self._cfg['ETL Right Offset']     )

        ao_device                   = self.ao_terminals.rsplit('/', 1)[0]
        ao_channels                 = self.ao_terminals.rsplit('/',1)[1][2:].rsplit(':')
        self.do_start_trigger       = ao_device + '/ao/StartTrigger'
        self.galvo_terminals        = ao_device + '/ao' + ao_channels[0] + ':' + str(int(ao_channels[0])+1)
        self.etl_terminals          = ao_device + '/ao' + str(int(ao_channels[1])-1) + ':' + ao_channels[1]


    def cfg_var2dict(self):
        # pack current instance variables into configuration dictionary
        self._cfg = {}
        self._cfg['AO Terminals']             = str( self.ao_terminals                 )
        self._cfg['DO Terminals']             = str( self.do_terminals                 )
        self._cfg['Sample Rate']              = str( self.sample_rate                  )
        self._cfg['Reset Delay']              = str( self.reset_delay                  )
        self._cfg['Exposure Time']            = str( self.exposure_time         * 1e3  )
        self._cfg['Camera Shutter Mode']      = str( self.camera_shutter_mode          )
        self._cfg['Camera Line Time']         = str( self.camera_line_time      * 1e6  )
        self._cfg['Camera XSize']             = str( self.camera_xsize                 )
        self._cfg['Camera YSize']             = str( self.camera_ysize                 )
        self._cfg['Galvo Activated']          = str( self.galvo_activated              )
        self._cfg['Galvo Inverted']           = str( self.galvo_inverted               )
        self._cfg['Galvo Left Amplitude']     = str( self.galvo_left_amplitude         )
        self._cfg['Galvo Left Offset']        = str( self.galvo_left_offset            )
        self._cfg['Galvo Right Amplitude']    = str( self.galvo_right_amplitude        )
        self._cfg['Galvo Right Offset']       = str( self.galvo_right_offset           )
        self._cfg['ETL Activated']            = str( self.etl_activated                )
        self._cfg['ETL Steps']                = str( self.etl_steps                    )
        self._cfg['ETL Left Amplitude']       = str( self.etl_left_amplitude           )
        self._cfg['ETL Left Offset']          = str( self.etl_left_offset              )
        self._cfg['ETL Right Amplitude']      = str( self.etl_right_amplitude          )
        self._cfg['ETL Right Offset']         = str( self.etl_right_offset             )


    def compute_scan_waveforms(self):
        '''Compute Galvo + ETL scan ramps and Camera Exposure waveforms based on instance variables'''

        # Save current settings to waveform metadata
        # Essentially self._cfg minus the terminals entries
        self.waveform_metadata = {}
        self.waveform_metadata['Sample Rate']              = str( self.sample_rate                  )
        self.waveform_metadata['Reset Delay']              = str( self.reset_delay                  )
        self.waveform_metadata['Exposure Time']            = str( self.exposure_time         * 1e3  )
        self.waveform_metadata['Camera Shutter Mode']      = str( self.camera_shutter_mode          )
        self.waveform_metadata['Camera Line Time']         = str( self.camera_line_time      * 1e6  )
        self.waveform_metadata['Camera XSize']             = str( self.camera_xsize                 )
        self.waveform_metadata['Camera YSize']             = str( self.camera_ysize                 )
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

        # From PCO documentation for pco.edge 5.5 USB 3.0
        # In Global Shutter Mode, image acquisition requires readout of two frames (dark + exposed frame)
        # Image readout time = 2 * Frame readout time (dark frame + exposed frame) + Jitter time
        # with,
        #   nbr_lines = Number of sensor lines to read = 2160
        #   line_time = Line readout time = 16.40 us
        # Frame readout time = 0.5 * nbr_of_line * line_time
        # Jitter time = line_time
        # Image readout time = (nbr_of_lines + 1) * line_time
        self._camera_readout_time = (self.camera_ysize + 1) * self.camera_line_time

        # In Global Shutter Mode with External Exposure Control
        # A delay exist between exposure trigger signal and actual start of exposure (due to dark frame readout)
        # Trigger-to-exposure time delay = Frame readout time + Jitter time 
        # with,
        #   nbr_lines = Number of sensor lines to read = 2160
        #   line_time = Line readout time = 16.40 us
        # Frame readout time = 0.5 * nbr_of_line * line_time
        # Jitter time = line_time
        # Trigger-to-exposure time delay = (0.5 nbr_of_line + 1) * line_time
        self._camera_trigger_to_exposure_time = (0.5 * self.camera_ysize + 1) * self.camera_line_time

        # Number of samples for image exposure time
        self._samples_exposure = int(np.ceil(self.exposure_time * self.sample_rate))
        # Number of samples for image readout time
        self._samples_readout = int(np.ceil(self._camera_readout_time * self.sample_rate))
        # Number of samples for rest time between images (reset camera, galvo flyback, etl focus update)
        self._samples_reset = int(np.ceil((self._samples_exposure + self._samples_readout) * self.reset_delay/100))
        # Number of samples for one period (image acquisition samples + system reset samples)
        self._samples_period = self._samples_exposure + self._samples_readout + self._samples_reset
        # Number of period cycles over the complete waveform (equal to current etl_steps value, but only updated with waveform generation)
        self.waveform_cycles = self.etl_steps
        # Number of samples for acquistion sequence (period * number of etl focus positions)
        self._samples_total = self._samples_period * self.waveform_cycles
        # Number of samples for trigger to exposure delay
        self._samples_trigger_to_exposure = int(np.ceil(self._camera_trigger_to_exposure_time * self.sample_rate))

        # Compute camera waveform
        self.waveform_camera = camera_squarewave(   samples_exposure = self._samples_exposure,
                                                    samples_readout = self._samples_readout,
                                                    samples_reset = self._samples_reset,
                                                    repeat = self.waveform_cycles,
                                                    samples_trigger_to_exposure = self._samples_trigger_to_exposure)

        # Compute galvo waveform
        if self.galvo_activated:
            self.waveform_galvo_left = galvo_ramp(  samples_exposure = self._samples_exposure,
                                                    samples_readout = self._samples_readout,
                                                    samples_reset = self._samples_reset,
                                                    repeat = self.waveform_cycles,
                                                    amplitude = self.galvo_left_amplitude, 
                                                    offset = self.galvo_left_offset, 
                                                    inverted = self.galvo_inverted)
            self.waveform_galvo_right = galvo_ramp( samples_exposure = self._samples_exposure,
                                                    samples_readout = self._samples_readout,
                                                    samples_reset = self._samples_reset,
                                                    repeat = self.waveform_cycles, 
                                                    amplitude = self.galvo_right_amplitude, 
                                                    offset = self.galvo_right_offset, 
                                                    inverted = self.galvo_inverted)
        else:
            self.waveform_galvo_left = np.ones((self._samples_total)) * self.galvo_left_offset
            self.waveform_galvo_right = np.ones((self._samples_total)) * self.galvo_right_offset

        # Compute etl waveform
        if self.etl_activated:
            self.waveform_etl_left = etl_staircase( samples_total_scan = self._samples_total,
                                                    steps = self.waveform_cycles,
                                                    floor = self.etl_left_offset,
                                                    rise = self.etl_left_amplitude,
                                                    direction = 'down')
            self.waveform_etl_right = etl_staircase(samples_total_scan = self._samples_total,
                                                    steps = self.waveform_cycles,
                                                    floor = self.etl_right_offset,
                                                    rise = self.etl_right_amplitude,
                                                    direction = 'up')
        else:
            self.waveform_etl_left = np.ones((self._samples_total)) * self.etl_left_offset
            self.waveform_etl_right = np.ones((self._samples_total)) * self.etl_right_offset




    def ao_update(self):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_setpoints     = np.stack((    np.array([self.galvo_right_offset]),
                                                np.array([self.galvo_left_offset]),
                                                np.array([self.etl_left_offset]),
                                                np.array([self.etl_right_offset])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'galvo_etl_setpoint') as galvo_etl_task:
                galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
                galvo_etl_task.write(galvo_etl_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'ao_update error'
            print('HwDAQ - ao_update error')


    def ao_galvo_update(self, left_setpoint:float, right_setpoint:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_setpoints     = np.stack((    np.array([right_setpoint]),
                                            np.array([left_setpoint])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'galvo_single') as galvo_task:
                galvo_task.ao_channels.add_ao_voltage_chan(self.etl_terminals)
                galvo_task.write(galvo_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'ao_galvo_update error'
            print('HwDAQ - ao_galvo_update error')


    def ao_etl_update(self, left_setpoint:float, right_setpoint:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        etl_setpoints     = np.stack((  np.array([left_setpoint]),
                                        np.array([right_setpoint])   ))
        # Running task
        try:
            with nidaqmx.Task(new_task_name = 'etl_single') as etl_task:
                etl_task.ao_channels.add_ao_voltage_chan(self.etl_terminals)
                etl_task.write(etl_setpoints, auto_start = True)
        except:
            self.error = 1
            self.error_message = 'ao_etl_update error'
            print('HwDAQ - ao_etl_update error')


    def create_scanner(self):
        '''Creates Galvo + ETL scan task (AO) + Camera Exposure Control task (DO)'''
        
        # Stack galvo and etl waveforms into single array
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_waveforms = np.stack((self.waveform_galvo_right, self.waveform_galvo_left, self.waveform_etl_left, self.waveform_etl_right))

        try:
            # Creating and setting up the galvo + ETL scan task (AO)
            self.galvo_etl_task = nidaqmx.Task(new_task_name = 'galvo_etl_scan')
            self.galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            self.galvo_etl_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self._samples_total)

            # Creating and setting up the camera exposure control task (DO)
            self.camera_task = nidaqmx.Task(new_task_name = 'camera_scan')
            self.camera_task.do_channels.add_do_chan(self.do_terminals, line_grouping = LineGrouping.CHAN_PER_LINE)
            self.camera_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self._samples_total)

            # Setup DO task to be triggered by AO start_trigger signal (AO is master task)
            self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig(self.do_start_trigger, trigger_edge = Edge.RISING)

            # Write waveforms to AO and DO tasks (to be started later)
            self.camera_task.write(self.waveform_camera, auto_start = False)
            self.galvo_etl_task.write(galvo_etl_waveforms, auto_start = False)
        except:
            self.galvo_etl_task = None
            self.camera_task = None
            self.error = 1
            self.error_message = 'create_scan error'
            print('HwDAQ - create_scan error')


    def start_scanner(self):
        '''Start both AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            # Master task needs to be started last
            self.camera_task.start()
            self.galvo_etl_task.start()

    def monitor_scanner(self):
        '''Wait for AO and DO tasks to complete'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.wait_until_done()
            self.galvo_etl_task.wait_until_done()

    def stop_scanner(self):
        '''Stop AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.stop()
            self.galvo_etl_task.stop()

    def delete_scanner(self):
        '''Delete AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.close()
            self.camera_task = None
            self.galvo_etl_task.close()
            self.galvo_etl_task = None

if __name__ == '__main__':
    testdaq = HwDAQ()
    print(testdaq.exposure_time)
    testdaq.compute_scan_waveforms()
    print(testdaq.waveform_cfg)
    testdaq.etl_steps = 10
    testdaq.cfg_var2dict()
    print(testdaq.waveform_cfg)
    print(testdaq._cfg)
