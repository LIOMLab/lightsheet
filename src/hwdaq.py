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

from src.config import cfg_read, cfg_write
from src.waveforms import galvo_ramp, etl_staircase, camera_squarewave


class HwDAQ:
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera'''

    # Default configurable settings
    _cfg_settings = {}
    _cfg_settings['AO Terminals'] = '/Dev1/ao0:3'           # DAQ board AO terminals for Galvo + ETL scan ramps
    _cfg_settings['DO Terminals'] = '/Dev1/port0/line1'     # DAQ board DO terminals for Camera Exposure Control
    _cfg_settings['Sample Rate'] = '40000'                  # In samples/second
    _cfg_settings['Reset Delay'] = '10'                     # In % of acquisition time (exposure + readout time)
    _cfg_settings['Camera Shutter Mode'] = 'Global'         # Either 'Global' or 'Lightsheet' (top-to-bottom rolling)
    _cfg_settings['Camera Line Time'] = '16.40'             # In microseconds
    _cfg_settings['Camera XSize'] = '2560'                  # In pixels
    _cfg_settings['Camera YSize'] = '2160'                  # In pixels
    _cfg_settings['Galvo Left Amplitude'] = '2.0'           # In volts
    _cfg_settings['Galvo Left Offset'] = '0.5'              # In volts
    _cfg_settings['Galvo Right Amplitude'] = '2.0'          # In volts
    _cfg_settings['Galvo Right Offset'] = '0.5'             # In volts
    _cfg_settings['Galvo Inverted'] = 'False'               # Boolean
    _cfg_settings['ETL Steps'] = '5'                        # Number of focus regions over FOV
    _cfg_settings['ETL Left Amplitude'] = '2.0'             # In volts
    _cfg_settings['ETL Right Amplitude'] = '2.0'            # In volts
    _cfg_settings['ETL Left Offset'] = '0.5'                # In volts
    _cfg_settings['ETL Right Offset'] = '0.5'               # In volts

    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ''

        self.scan_tasks_active = False
        self.galvo_etl_task = None
        self.camera_task = None

        self.waveform_galvo_left = None
        self.waveform_galvo_right = None
        self.waveform_etl_left = None
        self.waveform_etl_right = None
        self.waveform_camera = None
        self.waveform_parameters = None

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_settings)

        # Update configurable settings with values found in config file
        self.cfg_settings = cfg_read('config.ini', 'HwDAQ', self.cfg_settings)

        # Assign configurable initial settings to instance variables
        self.ao_terminals           = str(self.cfg_settings['AO Terminals'])
        self.do_terminals           = str(self.cfg_settings['DO Terminals'])
        self.sample_rate            = int(self.cfg_settings['Sample Rate'])
        self.reset_delay            = float(self.cfg_settings['Reset Delay'])
        self.camera_shutter_mode    = str(self.cfg_settings['Camera Shutter Mode'])
        self.camera_line_time       = float(self.cfg_settings['Camera Line Time']) * 1e-6
        self.camera_xsize           = int(self.cfg_settings['Camera XSize'])
        self.camera_ysize           = int(self.cfg_settings['Camera YSize'])
        self.galvo_left_amplitude   = float(self.cfg_settings['Galvo Left Amplitude'])
        self.galvo_left_offset      = float(self.cfg_settings['Galvo Left Offset'])
        self.galvo_right_amplitude  = float(self.cfg_settings['Galvo Right Amplitude'])
        self.galvo_right_offset     = float(self.cfg_settings['Galvo Right Offset'])
        self.galvo_inverted         = bool(self.cfg_settings['Galvo Inverted'])
        self.etl_steps              = int(self.cfg_settings['ETL Steps'])
        self.etl_left_amplitude     = float(self.cfg_settings['ETL Left Amplitude'])
        self.etl_left_offset        = float(self.cfg_settings['ETL Left Offset'])
        self.etl_right_amplitude    = float(self.cfg_settings['ETL Right Amplitude'])
        self.etl_right_offset       = float(self.cfg_settings['ETL Right Offset'])

        # Non-configurable initial settings
        ao_device                   = self.ao_terminals.rsplit('/', 1)[0]
        ao_channels                 = self.ao_terminals.rsplit('/',1)[1][2:].rsplit(':')
        self.do_start_trigger       = ao_device + '/ao/StartTrigger'
        self.galvo_terminals        = ao_device + '/ao' + ao_channels[0] + ':' + str(int(ao_channels[0])+1)
        self.etl_terminals          = ao_device + '/ao' + str(int(ao_channels[1])-1) + ':' + ao_channels[1]
        self.exposure_time          = 0.050     # in seconds
        self.galvo_activated        = True      # boolean
        self.etl_activated          = False     # boolean


    def compute_scan_waveforms(self):
        '''Compute Galvo + ETL scan ramps and Camera Exposure waveforms based on instance variables'''

        # Saving all parameters used to compute the waveforms
        self.waveform_parameters = {}
        self.waveform_parameters['Sample Rate']  = self.sample_rate
        self.waveform_parameters['Reset Delay']  = self.reset_delay
        self.waveform_parameters['Exposure Time'] = self.exposure_time
        self.waveform_parameters['Camera Shutter Mode']  = self.camera_shutter_mode
        self.waveform_parameters['Camera Line Time']  = self.camera_line_time * 1e6
        self.waveform_parameters['Camera XSize']  = self.camera_xsize
        self.waveform_parameters['Camera YSize']  = self.camera_ysize
        self.waveform_parameters['Galvo Activated']  = self.galvo_activated
        self.waveform_parameters['Galvo Inverted']  = self.galvo_inverted
        self.waveform_parameters['Galvo Left Amplitude']  = self.galvo_left_amplitude
        self.waveform_parameters['Galvo Letf Offset']  = self.galvo_left_offset
        self.waveform_parameters['Galvo Right Amplitude']  = self.galvo_right_amplitude
        self.waveform_parameters['Galvo Right Offset']  = self.galvo_right_offset
        self.waveform_parameters['ETL Activated']  = self.etl_activated
        self.waveform_parameters['ETL Steps']  = self.etl_steps
        self.waveform_parameters['ETL Left Amplitude']  = self.etl_left_amplitude
        self.waveform_parameters['ETL Letf Offset']  = self.etl_left_offset
        self.waveform_parameters['ETL Right Amplitude']  = self.etl_right_amplitude
        self.waveform_parameters['ETL Right Offset']  = self.etl_right_offset

        # From PCO documentation for pco.edge 5.5 USB 3.0
        # In Global Shutter Mode, image acquisition requires readout of two frames (dark + exposed frame)
        # Image readout time = 2 * Frame readout time (dark frame + exposed frame) + Jitter time
        # with,
        #   nbr_lines = Number of sensor lines to read = 2160
        #   line_time = Line readout time = 16.40 us
        # Frame readout time = 0.5 * nbr_of_line * line_time
        # Jitter time = line_time
        # Image readout time = (nbr_of_lines + 1) * line_time
        self.camera_readout_time = (self.camera_ysize + 1) * self.camera_line_time

        # In Global Shutter Mode with External Exposure Control
        # A delay exist between exposure trigger signal and actual start of exposure (due to dark frame readout)
        # Trigger-to-exposure time delay = Frame readout time + Jitter time 
        # with,
        #   nbr_lines = Number of sensor lines to read = 2160
        #   line_time = Line readout time = 16.40 us
        # Frame readout time = 0.5 * nbr_of_line * line_time
        # Jitter time = line_time
        # Trigger-to-exposure time delay = (0.5 nbr_of_line + 1) * line_time
        self.camera_trigger_to_exposure_time = (0.5 * self.camera_ysize + 1) * self.camera_line_time

        # Number of samples for image exposure time
        self.samples_exposure = int(np.ceil(self.exposure_time * self.sample_rate))
        # Number of samples for image readout time
        self.samples_readout = int(np.ceil(self.camera_readout_time * self.sample_rate))
        # Number of samples for rest time between images (reset camera, galvo flyback, etl focus update)
        self.samples_reset = int(np.ceil((self.samples_exposure + self.samples_readout) * self.reset_delay/100))
        # Number of samples for one period (image acquisition samples + system reset samples)
        self.samples_period = self.samples_exposure + self.samples_readout + self.samples_reset
        # Number of samples for acquistion sequence (period * number of etl focus positions)
        self.samples_total = self.samples_period * self.etl_steps
        # Number of samples for trigger to exposure delay
        self.samples_trigger_to_exposure = int(np.ceil(self.camera_trigger_to_exposure_time * self.sample_rate))

        # Compute camera waveform
        self.waveform_camera = camera_squarewave(   samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps,
                                                    samples_trigger_to_exposure = self.samples_trigger_to_exposure)

        # Compute galvo waveform
        if self.galvo_activated:
            self.waveform_galvo_left = galvo_ramp(  samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps,
                                                    amplitude = self.galvo_left_amplitude, 
                                                    offset = self.galvo_left_offset, 
                                                    inverted = self.galvo_inverted)
            self.waveform_galvo_right = galvo_ramp( samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps, 
                                                    amplitude = self.galvo_right_amplitude, 
                                                    offset = self.galvo_right_offset, 
                                                    inverted = self.galvo_inverted)
        else:
            self.waveform_galvo_left = np.ones((self.samples_total)) * self.galvo_left_offset
            self.waveform_galvo_right = np.ones((self.samples_total)) * self.galvo_right_offset

        # Compute etl waveform
        if self.etl_activated:
            self.waveform_etl_left = etl_staircase( samples_total_scan = self.samples_total,
                                                    steps = self.etl_steps,
                                                    floor = self.etl_left_offset,
                                                    rise = self.etl_left_amplitude,
                                                    direction = 'down')
            self.waveform_etl_right = etl_staircase(samples_total_scan = self.samples_total,
                                                    steps = self.etl_steps,
                                                    floor = self.etl_right_offset,
                                                    rise = self.etl_right_amplitude,
                                                    direction = 'up')
        else:
            self.waveform_etl_left = np.ones((self.samples_total)) * self.etl_left_offset
            self.waveform_etl_right = np.ones((self.samples_total)) * self.etl_right_offset


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


    def create_scan_tasks(self):
        '''Creates Galvo + ETL scan task (AO) + Camera Exposure Control task (DO)'''
        
        # Stack galvo and etl waveforms into single array
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_waveforms = np.stack((self.waveform_galvo_right, self.waveform_galvo_left, self.waveform_etl_left, self.waveform_etl_right))

        try:
            # Creating and setting up the galvo + ETL scan task (AO)
            self.galvo_etl_task = nidaqmx.Task(new_task_name = 'galvo_etl_scan')
            self.galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            self.galvo_etl_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.samples_total)

            # Creating and setting up the camera exposure control task (DO)
            self.camera_task = nidaqmx.Task(new_task_name = 'camera_scan')
            self.camera_task.do_channels.add_do_chan(self.do_terminals, line_grouping = LineGrouping.CHAN_PER_LINE)
            self.camera_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.samples_total)

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


    def start_scan_tasks(self):
        '''Start both AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            # Master task needs to be started last
            self.camera_task.start()
            self.galvo_etl_task.start()

    def monitor_scan_tasks(self):
        '''Wait for AO and DO tasks to complete'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.wait_until_done()
            self.galvo_etl_task.wait_until_done()

    def stop_scan_tasks(self):
        '''Stop AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.stop()
            self.galvo_etl_task.stop()

    def delete_scan_tasks(self):
        '''Delete AO and DO tasks'''
        if self.galvo_etl_task is not None and self.camera_task is not None:
            self.camera_task.close()
            self.camera_task = None
            self.galvo_etl_task.close()
            self.galvo_etl_task = None

