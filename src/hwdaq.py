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
    _cfg_settings['Camera Line Readout'] = '16.40'          # In microseconds
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

        self.galvo_left_waveform = None
        self.galvo_right_waveform = None
        self.etl_left_waveform = None
        self.etl_right_waveform = None
        self.camera_waveform = None

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_settings)

        # Update configurable settings with values found in config file
        self.cfg_settings = cfg_read('config.ini', 'HwDAQ', self.cfg_settings)

        # Assign configurable initial settings to instance variables
        self.ao_terminals           = str(self.cfg_settings['AO Terminals'])
        self.do_terminals           = str(self.cfg_settings['DO Terminals'])
        self.sample_rate            = int(self.cfg_settings['Sample Rate'])
        self.reset_delay            = float(self.cfg_settings['Reset Delay'])
        self.camera_line_time       = float(self.cfg_settings['Camera Line Readout']) * 1e-6
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

        
        #self.compute_scan_waveforms()


    def compute_scan_waveforms(self):
        '''Compute Galvo + ETL scan ramps and Camera Exposure waveforms based on instance variables'''

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

        # Compute waveforms
        self.camera_waveform = camera_squarewave(   samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps,
                                                    samples_trigger_to_exposure = self.samples_trigger_to_exposure)

        if self.galvo_activated:
            self.galvo_left_waveform = galvo_ramp(  samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps,
                                                    amplitude = self.galvo_left_amplitude, 
                                                    offset = self.galvo_left_offset, 
                                                    inverted = self.galvo_inverted)
            self.galvo_right_waveform = galvo_ramp( samples_exposure = self.samples_exposure,
                                                    samples_readout = self.samples_readout,
                                                    samples_reset = self.samples_reset,
                                                    repeat = self.etl_steps, 
                                                    amplitude = self.galvo_right_amplitude, 
                                                    offset = self.galvo_right_offset, 
                                                    inverted = self.galvo_inverted)
        else:
            self.galvo_left_waveform = np.ones((self.samples_total)) * self.galvo_left_offset
            self.galvo_right_waveform = np.ones((self.samples_total)) * self.galvo_right_offset

        if self.etl_activated:
            self.etl_left_waveform = etl_staircase( samples_total_scan = self.samples_total,
                                                    steps = self.etl_steps,
                                                    floor = self.etl_left_offset,
                                                    rise = self.etl_left_amplitude,
                                                    direction = 'down')
            self.etl_right_waveform = etl_staircase(samples_total_scan = self.samples_total,
                                                    steps = self.etl_steps,
                                                    floor = self.etl_right_offset,
                                                    rise = self.etl_right_amplitude,
                                                    direction = 'up')
        else:
            self.etl_left_waveform = np.ones((self.samples_total)) * self.etl_left_offset
            self.etl_right_waveform = np.ones((self.samples_total)) * self.etl_right_offset


    def ao_update(self):
        # Computing Galvo + ETL setpoints
        galvo_left_setpoint     = self.galvo_left_offset
        galvo_right_setpoint    = self.galvo_right_offset
        etl_left_setpoint       = self.etl_left_offset
        etl_right_setpoint      = self.etl_right_offset
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_setpoints     = np.stack((    np.array([galvo_right_setpoint]),
                                                np.array([galvo_left_setpoint]),
                                                np.array([etl_left_setpoint]),
                                                np.array([etl_right_setpoint])   ))
        # Running task
        with nidaqmx.Task(new_task_name = 'galvo_etl_setpoint') as galvo_etl_task:
            galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            galvo_etl_task.write(galvo_etl_setpoints, auto_start = True)


    def ao_galvo_update(self, left_setpoint:float, right_setpoint:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_setpoints     = np.stack((    np.array([right_setpoint]),
                                            np.array([left_setpoint])   ))
        # Running task
        with nidaqmx.Task(new_task_name = 'galvo_single') as galvo_task:
            galvo_task.ao_channels.add_ao_voltage_chan(self.etl_terminals)
            galvo_task.write(galvo_setpoints, auto_start = True)


    def ao_etl_update(self, left_setpoint:float, right_setpoint:float):
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        etl_setpoints     = np.stack((  np.array([left_setpoint]),
                                        np.array([right_setpoint])   ))
        # Running task
        with nidaqmx.Task(new_task_name = 'etl_single') as etl_task:
            etl_task.ao_channels.add_ao_voltage_chan(self.etl_terminals)
            etl_task.write(etl_setpoints, auto_start = True)


    def create_scan(self):
        '''Creates Galvo + ETL scan task (AO) + Camera Exposure Control task (DO)'''
        
        # Makes sure instance variables are consistant before proceeding with tasks creation & waveforms assignement
        self.compute_scan_waveforms()

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

        # Write waveforms to AO and DO tasks
        # FIXME (HARDWARE) - LOOKS LIKE ETL OR GALVO ARE REVERSED (LEFT VS RIGHT)
        galvo_etl_waveforms = np.stack((self.galvo_right_waveform, self.galvo_left_waveform, self.etl_left_waveform, self.etl_right_waveform))
        self.camera_task.write(self.camera_waveform, auto_start = False)
        self.galvo_etl_task.write(galvo_etl_waveforms, auto_start = False)

    def start_scan(self):
        '''Start both AO and DO tasks'''
        # Master task needs to be started last
        self.camera_task.start()
        self.galvo_etl_task.start()

    def monitor_scan(self):
        '''Wait for AO and DO tasks to complete'''
        self.camera_task.wait_until_done()
        self.galvo_etl_task.wait_until_done()

    def stop_scan(self):
        '''Stop AO and DO tasks'''
        self.camera_task.stop()
        self.galvo_etl_task.stop()

    def delete_scan(self):
        '''Delete AO and DO tasks'''
        self.camera_task.close()
        self.galvo_etl_task.close()


# -------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    testhw = HwDAQ()
    print(testhw.do_start_trigger)
    print(testhw.galvo_terminals)
    print(testhw.etl_terminals)
