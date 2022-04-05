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
from src.waveforms import galvo_trapeze, calibrated_etl_stairs, camera_digital_output_signal

class HwDAQ:
    '''Class for generating and sending AO ramps to ETLs and galvos
       Update: Also includes the ramp for the camera'''

    # Default configurable settings
    _cfg_settings = {}
    _cfg_settings['GalvoETL Terminals'] = '/Dev1/ao0:3'         # DAQ board terminals for Galvo + ETL scan ramps (Analog Output)
    _cfg_settings['Camera Terminals'] = '/Dev1/port0/line1'     # DAQ board terminals for Camera Exposure Control (Digital Output)
    _cfg_settings['Camera Trigger'] = '/Dev1/ao/StartTrigger'   # DAQ board terminals for Camera Start Trigger
    _cfg_settings['Sample Clock Rate'] = '40000'                # In samples/second
    _cfg_settings['Galvo Frequency'] = '20'                     # In Hertz
    _cfg_settings['Galvo Left Amplitude'] = '2'                 # In Volts
    _cfg_settings['Galvo Left Offset'] = '0.6'                  # In Volts
    _cfg_settings['Galvo Right Amplitude'] = '2'                # In Volts
    _cfg_settings['Galvo Right Offset'] = '0.6'                 # In Volts
    _cfg_settings['Galvo Inverted'] = 'False'                   # Boolean
    _cfg_settings['ETL Left Amplitude'] = '2.0'                 # In Volts
    _cfg_settings['ETL Right Amplitude'] = '2.0'                # In Volts
    _cfg_settings['ETL Left Offset'] = '0'                      # In Volts
    _cfg_settings['ETL Right Offset'] = '0'                     # In Volts
    _cfg_settings['ETL Steps'] = '8'                            # Number of focus regions over FOV
    _cfg_settings['ETL Left Slope'] = '-0.0009'
    _cfg_settings['ETL Left Intercept'] = '4.25'                # In Volts
    _cfg_settings['ETL Right Slope'] = '0.0009'
    _cfg_settings['ETL Right Intercept'] = '2.38'               # In Volts
    _cfg_settings['Image XSize'] = '2560'                       # In pixels
    _cfg_settings['Image YSize'] = '2160'                       # In pixels
    _cfg_settings['Camera Delay Ratio'] = '10'                  # In % (duty cycle)
    _cfg_settings['Camera Delay Minimum'] = '0.0354404'         # In seconds
    _cfg_settings['Camera Start Time'] = '0.017712'             # In seconds


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

        # Assign configurable settings to instance variables
        self.ao_terminals           = str(self.cfg_settings['GalvoETL Terminals'])
        self.do_terminals           = str(self.cfg_settings['Camera Terminals'])
        self.do_start_trigger       = str(self.cfg_settings['Camera Trigger'])
        self.sample_rate            = int(self.cfg_settings['Sample Clock Rate'])
        self.galvo_frequency        = float(self.cfg_settings['Galvo Frequency'])
        self.galvo_left_amplitude   = float(self.cfg_settings['Galvo Left Amplitude'])
        self.galvo_left_offset      = float(self.cfg_settings['Galvo Left Offset'])
        self.galvo_right_amplitude  = float(self.cfg_settings['Galvo Right Amplitude'])
        self.galvo_right_offset     = float(self.cfg_settings['Galvo Right Offset'])
        self.galvo_inverted         = bool(self.cfg_settings['Galvo Inverted'])
        self.etl_left_amplitude     = float(self.cfg_settings['ETL Left Amplitude'])
        self.etl_left_offset        = float(self.cfg_settings['ETL Left Offset'])
        self.etl_right_amplitude    = float(self.cfg_settings['ETL Right Amplitude'])
        self.etl_right_offset       = float(self.cfg_settings['ETL Right Offset'])
        self.etl_steps              = int(self.cfg_settings['ETL Steps'])
        self.etl_left_slope         = float(self.cfg_settings['ETL Left Slope'])
        self.etl_left_intercept     = float(self.cfg_settings['ETL Left Intercept'])
        self.etl_right_slope        = float(self.cfg_settings['ETL Right Slope'])
        self.etl_right_intercept    = float(self.cfg_settings['ETL Right Intercept'])
        self.image_xsize            = int(self.cfg_settings['Image XSize'])
        self.image_ysize            = int(self.cfg_settings['Image YSize'])
        self.camera_delay_ratio     = float(self.cfg_settings['Camera Delay Ratio'])
        self.camera_delay_min       = float(self.cfg_settings['Camera Delay Minimum'])
        self.camera_start_time      = float(self.cfg_settings['Camera Start Time'])
        # Hardcoded defaults
        self.galvo_activate         = True
        self.etl_activate           = False
        self.compute_scan_waveforms()

    def compute_scan_waveforms(self):
        '''Compute Galvo + ETL scan ramps and Camera Exposure waveforms based on instance variables'''

        # Compute defining parameters
        # The width in pixel of each ETL focus window
        self.etl_step_size              = np.ceil(self.image_xsize / self.etl_steps)
        # The half period is the exposure time, the time taken for a single upwards or downwards galvo scan
        self.t_half_period              = 0.5 * (1 / self.galvo_frequency)
        # Number of samples per exposure time
        self.samples_per_half_period    = np.ceil(self.t_half_period * self.sample_rate)
        # Number of samples per camera internal delay (delay for acquiring image, excluding exposure time)
        self.min_samples_per_delay      = np.ceil(self.camera_delay_min * self.sample_rate)
        # Number of samples per image acquisition (including exposure time)
        self.min_samples_per_step       = self.min_samples_per_delay + self.samples_per_half_period
        # Number of samples added to each step to allow down time for the camera
        self.rest_samples_added         = np.ceil(self.min_samples_per_step * self.camera_delay_ratio/100)
        # Number of samples per step (including all delay)
        self.samples_per_step           = self.min_samples_per_step + self.rest_samples_added
        # Number of samples per total delay (internal + added), between each camera exposition
        self.samples_per_delay          = self.samples_per_step - self.samples_per_half_period
        # Number of samples per half total delay
        self.samples_per_half_delay     = np.floor(self.samples_per_delay/2)
        # Number of focal length values needed for each ETL to achieve a full scan
        self.number_of_steps            = np.ceil(self.image_xsize / self.etl_step_size)
        # Total number of samples for acquisition
        self.number_of_samples          = self.number_of_steps * self.samples_per_step
        self.samples                    = int(self.number_of_samples)
        # Total time for acquisition
        self.sweeptime                  = self.number_of_samples / self.sample_rate

        # Compute waveforms
        self.galvo_left_waveform = galvo_trapeze(   amplitude = self.galvo_left_amplitude,
                                                    samples_per_half_period = self.samples_per_half_period,
                                                    samples_per_delay = self.samples_per_delay,
                                                    number_of_samples = self.number_of_samples,
                                                    number_of_steps = self.number_of_steps,
                                                    samples_per_step = self.samples_per_step,
                                                    samples_per_half_delay = self.samples_per_half_delay,
                                                    min_samples_per_delay = self.min_samples_per_delay,
                                                    t_start_exp = self.camera_start_time,
                                                    samplerate = self.sample_rate,
                                                    offset = self.galvo_left_offset,
                                                    invert = self.galvo_inverted,
                                                    activate = self.galvo_activate)

        self.galvo_right_waveform = galvo_trapeze(  amplitude = self.galvo_right_amplitude,
                                                    samples_per_half_period = self.samples_per_half_period,
                                                    samples_per_delay = self.samples_per_delay,
                                                    number_of_samples = self.number_of_samples,
                                                    number_of_steps = self.number_of_steps,
                                                    samples_per_step = self.samples_per_step,
                                                    samples_per_half_delay = self.samples_per_half_delay,
                                                    min_samples_per_delay = self.min_samples_per_delay,
                                                    t_start_exp = self.camera_start_time,
                                                    samplerate = self.sample_rate,
                                                    offset = self.galvo_right_offset,
                                                    invert = self.galvo_inverted,
                                                    activate = self.galvo_activate)

        self.etl_left_waveform = calibrated_etl_stairs( left_slope = self.etl_left_slope,
                                                        left_intercept = self.etl_left_intercept,
                                                        right_slope = self.etl_right_slope,
                                                        right_intercept = self.etl_right_intercept,
                                                        etl_step = self.etl_step_size,
                                                        amplitude = self.etl_left_amplitude,
                                                        number_of_steps = self.number_of_steps,
                                                        number_of_samples = self.number_of_samples,
                                                        samples_per_step = self.samples_per_step,
                                                        offset = self.etl_left_offset,
                                                        direction = 'UP',
                                                        activate = self.etl_activate)

        self.etl_right_waveform = calibrated_etl_stairs(left_slope = self.etl_left_slope,
                                                        left_intercept = self.etl_left_intercept,
                                                        right_slope = self.etl_right_slope,
                                                        right_intercept = self.etl_right_intercept,
                                                        etl_step = self.etl_step_size,
                                                        amplitude = self.etl_right_amplitude,
                                                        number_of_steps = self.number_of_steps,
                                                        number_of_samples = self.number_of_samples,
                                                        samples_per_step = self.samples_per_step,
                                                        offset = self.etl_right_offset,
                                                        direction = 'DOWN',
                                                        activate = self.etl_activate)

        self.camera_waveform = camera_digital_output_signal(samples_per_half_period = self.samples_per_half_period,
                                                            t_start_exp = self.camera_start_time,
                                                            samplerate = self.sample_rate,
                                                            samples_per_half_delay = self.samples_per_half_delay,
                                                            number_of_samples = self.number_of_samples,
                                                            number_of_steps = self.number_of_steps,
                                                            samples_per_step = self.samples_per_step,
                                                            min_samples_per_delay = self.min_samples_per_delay)


    def etl_enable(self):
        self.etl_activate = True

    def etl_disable(self):
        self.etl_activate = False


    def update_setpoint(self):
        # Computing Galvo + ETL setpoints
        galvo_left_setpoint     = self.galvo_left_amplitude + self.galvo_left_offset
        galvo_right_setpoint    = self.galvo_right_amplitude + self.galvo_right_offset
        etl_left_setpoint       = self.etl_left_amplitude + self.etl_left_offset
        etl_right_setpoint      = self.etl_right_amplitude + self.etl_right_offset
        galvo_etl_setpoints     = np.stack((    np.array([galvo_right_setpoint]),
                                                np.array([galvo_left_setpoint]),
                                                np.array([etl_left_setpoint]),
                                                np.array([etl_right_setpoint])   ))
        # Running task
        with nidaqmx.Task(new_task_name = 'galvo_etl_setpoint') as galvo_etl_task:
            galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            galvo_etl_task.write(galvo_etl_setpoints, auto_start = True)


    def create_scan(self):
        '''Creates Galvo + ETL scan task (AO) + Camera Exposure Control task (DO)'''

        # Makes sure instance variables are consistant before proceeding with tasks creation & waveforms assignement
        self.compute_scan_waveforms()

        # Creating and setting up the galvo + ETL scan task (AO)
        self.galvo_etl_task = nidaqmx.Task(new_task_name = 'galvo_etl_scan')
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.samples)

        # Creating and setting up the camera exposure control task (DO)
        self.camera_task = nidaqmx.Task(new_task_name = 'camera_scan')
        self.camera_task.do_channels.add_do_chan(self.do_terminals, line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.samples)
        # Setup DO task to be triggered by AO start_trigger signal (AO is master task)
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig(self.do_start_trigger, trigger_edge = Edge.RISING)

        # Write waveforms to AO and DO tasks
        galvo_etl_waveforms = np.stack((self.galvo_right_waveform, self.galvo_left_waveform, self.etl_right_waveform, self.etl_left_waveform))
        self.galvo_etl_task.write(galvo_etl_waveforms)
        self.camera_task.write(self.camera_waveform, auto_start = False)

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

