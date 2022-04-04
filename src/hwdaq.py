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
    _cfg_settings['AOTerminals'] = '/Dev1/ao0:3'        # DAQ board terminals for Analog Output (Galvo + ETL)
    _cfg_settings['DOTerminals'] = '/Dev1/port0/line1'  # DAQ board terminals for Digital Output (Camera Sync)
    _cfg_settings['Sample Clock Rate'] = '40000'        # In samples/second
    _cfg_settings['Galvo Frequency'] = '20'             # In Hertz
    _cfg_settings['Galvo Left Amplitude'] = '2'         # In Volts
    _cfg_settings['Galvo Right Amplitude'] = '2'        # In Volts
    _cfg_settings['Galvo Left Offset'] = '0.6'          # In Volts
    _cfg_settings['Galvo Right Offset'] = '0.6'         # In Volts
    _cfg_settings['ETL Left Amplitude'] = '2.0'         # In Volts
    _cfg_settings['ETL Right Amplitude'] = '2.0'        # In Volts
    _cfg_settings['ETL Left Offset'] = '0'              # In Volts
    _cfg_settings['ETL Right Offset'] = '0'             # In Volts
    _cfg_settings['ETL Steps'] = '8'                    # In # of steps (focus regions over FOV)
    _cfg_settings['Image XSize'] = '2560'               # In pixels
    _cfg_settings['Image YSize'] = '2160'               # In pixels
    _cfg_settings['Camera Delay Ratio'] = '10'          # In % (duty cycle)
    _cfg_settings['Camera Delay Minimum'] = '0.0354404' # In seconds
    _cfg_settings['Camera Start Time'] = '0.017712'     # In seconds


    def __init__(self):
        # Error status
        self.error = 0
        self.error_message = ''

        self.galvo_etl_task = None
        self.galvo_and_etl_waveforms  = None
        self.camera_task = None
        self.camera_waveform = None

        # Set configurable settings to default values
        self.cfg_settings = copy.deepcopy(self._cfg_settings)

        # Update configurable settings with values found in config file
        self.cfg_settings = cfg_read('config.ini', 'HwDAQ', self.cfg_settings)

        # Assign configurable settings to instance variables
        self.aoterminals            = str(self.cfg_settings['AOTerminals'])
        self.doterminals            = str(self.cfg_settings['DOTerminals'])
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
        self.etl_activate           = bool(self.cfg_settings['ETL Activate'])
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


    def create_tasks(self, acquisition='FINITE'):
        '''Creates a total of four tasks for the lightsheet:

        These are:
        - the master trigger task, a digital out task that only provides a trigger pulse for the others
        - the camera trigger task, a counter task that triggers the camera in lightsheet mode
        - the galvo task (analog out) that controls the left & right galvos for creation of
          the light-sheet and shadow avoidance
        - the ETL & Laser task (analog out) that controls all the laser intensities (Laser should only
          be on when the camera is acquiring) and the left/right ETL waveforms

        7/26/2019: acquisition parameter was added, options are; 'FINITE' or 'CONTINUOUS'
        '''

        # Set up NiDAQ acquisition mode
        mode = 'NONE'
        if acquisition == 'FINITE':
            mode = AcquisitionType.FINITE
        elif acquisition == 'CONTINUOUS':
            mode = AcquisitionType.CONTINUOUS

        # Create tasks for galvos, ETLs and camera
        self.galvo_etl_task = nidaqmx.Task(new_task_name = 'ao_galvo_etl_ramps')
        self.camera_task = nidaqmx.Task(new_task_name = 'do_camera_sync')

        # Housekeeping: Setting up the AO task for the Galvo and ETLs. It is the master task
        self.galvo_etl_task.ao_channels.add_ao_voltage_chan(self.aoterminals)
        self.galvo_etl_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = mode, samps_per_chan = self.samples)

        # Housekeeping: Setting up the DO task for the camera. It is the slave task
        self.camera_task.do_channels.add_do_chan(self.doterminals, line_grouping = LineGrouping.CHAN_PER_LINE)
        self.camera_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = mode, samps_per_chan = self.samples)

        # Configures the task to start acquiring/generating samples on a rising/falling edge of a digital signal.
        #    args: terminal of the trigger source (master), which edge of the digital signal the task start (optionnal)
        #    Important to do this configuration for each slave task'''
        # TOFIX - We are hardcoding the terminal
        self.camera_task.triggers.start_trigger.cfg_dig_edge_start_trig('/Dev1/ao/StartTrigger', trigger_edge = Edge.RISING)

    def start_tasks(self):
        '''Master task needs to always be started last'''
        self.camera_task.start()
        self.galvo_etl_task.start()

    def monitor_tasks(self):
        '''Wait until everything is done - this is effectively a sleep function.
           Master task always last'''
        self.camera_task.wait_until_done()
        self.galvo_etl_task.wait_until_done()

    def stop_tasks(self):
        '''Stops the tasks for triggering, analog and counter outputs
           Master task always last'''
        self.camera_task.stop()
        self.galvo_etl_task.stop()

    def delete_tasks(self):
        '''Closes the tasks for triggering, analog and counter outputs.
           Tasks should only be closed after they are stopped.
           Master task always last. '''
        self.camera_task.close()
        self.galvo_etl_task.close()

    def write_waveforms_to_tasks(self):
        '''Write the waveforms to the tasks'''
        self.galvo_and_etl_waveforms = np.stack((self.galvo_r_waveform, self.galvo_l_waveform, self.etl_r_waveform, self.etl_l_waveform))
        self.galvo_etl_task.write(self.galvo_and_etl_waveforms)
        self.camera_task.write(self.camera_waveform, auto_start = False)



    def create_camera_waveform(self, waveform_type:str):
        if waveform_type == 'STAIRS_FITTING':
            self.camera_waveform = camera_digital_output_signal(samples_per_half_period = self.samples_per_half_period,
                                                                t_start_exp = self.camera_start_time,
                                                                samplerate = self.sample_rate,
                                                                samples_per_half_delay = self.samples_per_half_delay,
                                                                number_of_samples = self.number_of_samples,
                                                                number_of_steps = self.number_of_steps,
                                                                samples_per_step = self.samples_per_step,
                                                                min_samples_per_delay = self.min_samples_per_delay)


    def create_galvo_waveform(self, waveform_typ:str):
        if waveform_typ == 'TRAPEZE':
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
                                                        invert = self.galvo_inverted)

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
                                                        invert = self.galvo_inverted)


    def create_etl_waveform(self, waveform_typ:str):
        if waveform_typ == 'STAIRS':
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



    def create_digital_output_camera_waveform(self, case = 'NONE'):
        if case == 'STAIRS_FITTING':
            self.camera_waveform = camera_digital_output_signal(samples_per_half_period = self.samples_per_half_period,
                                                                t_start_exp = self.camera_start_time,
                                                                samplerate = self.sample_rate,
                                                                samples_per_half_delay = self.samples_per_half_delay,
                                                                number_of_samples = self.number_of_samples,
                                                                number_of_steps = self.number_of_steps,
                                                                samples_per_step = self.samples_per_step,
                                                                min_samples_per_delay = self.min_samples_per_delay)

    def create_calibrated_etl_waveforms(self, left_slope, left_intercept, right_slope, right_intercept, activate=False):
        self.etl_l_waveform = calibrated_etl_stairs(left_slope,
                                                    left_intercept,
                                                    right_slope,
                                                    right_intercept,
                                                    etl_step = self.etl_step_size,
                                                    amplitude = self.etl_left_amplitude,
                                                    number_of_steps = self.number_of_steps,
                                                    number_of_samples = self.number_of_samples,
                                                    samples_per_step = self.samples_per_step,
                                                    offset = self.etl_left_offset,
                                                    direction = 'UP',
                                                    activate=activate)

        self.etl_r_waveform = calibrated_etl_stairs(left_slope,
                                                    left_intercept,
                                                    right_slope,
                                                    right_intercept,
                                                    etl_step = self.etl_step_size,
                                                    amplitude = self.etl_right_amplitude,
                                                    number_of_steps = self.number_of_steps,
                                                    number_of_samples = self.number_of_samples,
                                                    samples_per_step = self.samples_per_step,
                                                    offset = self.etl_right_offset,
                                                    direction = 'DOWN',
                                                    activate = activate)

    def create_galvos_waveforms(self, case = 'NONE', invert = False):
        if case == 'TRAPEZE':
            self.galvo_l_waveform = galvo_trapeze(  amplitude = self.galvo_left_amplitude,
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
                                                    invert = invert)

            self.galvo_r_waveform = galvo_trapeze(  amplitude = self.galvo_right_amplitude,
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
                                                    invert = invert)
