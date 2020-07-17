"""
Module for creating waveforms and analog output signals

Authors: Pierre Girard-Collins & Fabian Voigt

#TODO
* Usage of amplitude is not consistent (peak-to-peak in single_pulse)
"""

#import nidaqmx
# from nidaqmx.constants import AcquisitionType, TaskMode
# from nidaqmx.constants import LineGrouping

from scipy import signal
import numpy as np



def camera_digital_output_signal(samples_per_half_period, t_start_exp, samplerate, samples_per_half_delay, number_of_samples, number_of_steps, samples_per_step, min_samples_per_delay):
    '''Set the high level time interval (samples), i.e. the time when the camera 
       exposure is on, each time the galvos are in motion. The waveform is 
       coded by taking into account the mechanism of frame acquisition by the CMOS
       PCO edge 5.5m camera of the light-sheet in external exposure control mode 
       (the camera trigger mode chosen to operate the microscope). See the 
       camera documentation for more infos.'''
    
    samples_per_exposition = samples_per_half_period
    samples_before_exposition = np.round(t_start_exp*samplerate)             #Round, ceil or floor?
    samples_before_high_level = samples_per_half_delay-samples_before_exposition             
    high_level_vector = np.full(int(samples_per_exposition), True)
    
    array = np.full(int(number_of_samples), False)
    
    for i in range(int(number_of_steps)):
        if i == int(number_of_steps-1): #Last loop
            samples_left = number_of_samples-(samples_before_high_level+i*samples_per_step)
            #print('Camera')
            #print('i: {}'.format(i))
            #print('samples_left: {}'.format(samples_left))
            #print('min_samples_per_delay: {}'.format(min_samples_per_delay))
            #print('samples_per_half_period: {}'.format(samples_per_half_period))
            #print('samples_per_half_delay: {}'.format(samples_per_half_delay))
            if samples_left < (min_samples_per_delay+samples_per_half_period):
                pass  #No enough samples for another acquisition, we pass
            else:
                array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_exposition)]=high_level_vector
        else:
            array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_exposition)]=high_level_vector
    
    return np.array(array)


def camera_live_mode_waveform(samples_per_half_period, t_start_exp, samplerate, samples_per_half_delay, number_of_samples): ###pas utilisé
    '''Not in use anymore, was useful for calibrating purposes, kept for reference'''
    
    samples_per_exposition = samples_per_half_period
    samples_before_exposition = np.round(t_start_exp*samplerate)             #Round, ceil or floor?
    samples_before_high_level = samples_per_half_delay-samples_before_exposition             
    high_level_vector = np.full(int(samples_per_exposition), True)
    
    array = np.full(int(number_of_samples), False)
    
    array[int(samples_before_high_level):int(samples_before_high_level+samples_per_exposition)]=high_level_vector
    
    return np.array(array)

def digital_output_signal( ###pas utilisé
    samplerate = 100000,    # in samples/second
    sweeptime = 0.4,        # in seconds
    delay = 7.5,            # in percent
    rise = 85,              # in percent
    fall = 2.5,             # in percent
    ):
    ''' Create the digital trigger signal sent to the camera. The camera is set in a mode where the exposition time corresponds
        to the high time of the signal. 
        
        High time: lasts until the rising ramp of the galvo/ETL is complete
        Low time: must include the fall time of the galvo/ETL ramp, because we do not want the camera to acquire during the falling ramp.
        
        Note: the rising ramp here lasts longer than the falling ramp. For the ETL/glavo of the other arm, the falling edge lasts longer 
              because they are reversed for the focal of the ETLs are synchronized. So care must be taken when assigning the rise and fall
              
        parameters: 
            low_level_time_added: additional inactive time (seconds) we want to add between each tunable_lens_ramp waveform (can be used to 
                                complete the processing, saving or display of the image acquired)
            high_level_voltage: voltage value (volts) that will be recognized as a high level (bit=1) for the camera. The camera used is
                                3.3V LVTTL (5V tolerant), so 3 V should be enough to generate the high level.
                                
            Note: the low_level_time_added is added in half before and after the high signal, so we do not start (first data) with a high signal
              '''
    samples = int(np.floor(np.multiply(samplerate, sweeptime)))
    delaysamples = int(samples*delay/100)
    highlevelsamples = int(samples*rise/100)
    
    array = np.full((samples), False)
    array[delaysamples:delaysamples+highlevelsamples]=True
    
    
    return np.array(array)

def etl_live_mode_waveform(amplitude, number_of_samples): ###pas utilisé
    '''Not in use anymore, was useful for calibrating purposes, kept for reference'''
    
    array = amplitude*np.ones((int(number_of_samples)))
    
    return np.array(array)

def etl_stairs(amplitude, number_of_steps, number_of_samples, samples_per_step, offset, direction): ###Plus utilisé
    '''Step function. The stairs are defined to be upwards or downwards depending 
       on the ETL.
    
       Later, stepAmplitude will be define by the ETL focus position as a function of the voltage applied
       Each ETL may have a different relation to the voltage applied'''
    if number_of_steps !=1:
        step_amplitude = amplitude/(number_of_steps-1)
    
        #print('Step amplitude: ' + str(step_amplitude))
        
        array = np.zeros((int(number_of_samples)))
        
        if direction == 'UP':
            for i in range(int(number_of_steps)):
                if i == int(number_of_steps-1): #Last loop, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(i*samples_per_step)
                    step_value = i*step_amplitude*np.ones(int(samples_left))
                    array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_left)] = step_value
                else:
                    step_value = i*step_amplitude*np.ones(int(samples_per_step))
                    array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_per_step)] = step_value
        
        if direction == 'DOWN':
            for i in range(int(number_of_steps)):
                if i == int(number_of_steps-1): #Last loop, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(i*samples_per_step)
                    step_value = (number_of_steps-1-i)*step_amplitude*np.ones(int(samples_left))
                    array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_left)] = step_value
                else:
                    step_value = (number_of_steps-1-i)*step_amplitude*np.ones(int(samples_per_step))
                    array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_per_step)] = step_value
        
        array = array+offset
    
    else:
        array = amplitude*np.ones((int(number_of_samples)))+offset

    return np.array(array)

def calibrated_etl_stairs(left_slope, left_intercept, right_slope, right_intercept, etl_step, amplitude, number_of_steps, number_of_samples, samples_per_step, offset, direction):
    '''Step function. The stairs are defined to be upwards or downwards depending 
       on the ETL.
    
       Later, stepAmplitude will be define by the ETL focus position as a function of the voltage applied
       Each ETL may have a different relation to the voltage applied'''
    if number_of_steps !=1:
        #step_column = 2560/(number_of_steps-1) ###
        step_column=etl_step
    
        #print('Step column: ' + str(step_column)) #debugging
        
        array = np.zeros((int(number_of_samples)))
        
        for i in range(int(number_of_steps)):
            column_value = i*step_column*np.ones(int(samples_per_step))
            if direction == 'UP': ###DOWN
                step_value = left_slope * column_value + left_intercept
            if direction == 'DOWN': ###UP
                step_value = right_slope * column_value + right_intercept
        
            #print('column_value:'+ str(column_value))#debugging
            step_value = np.where(step_value > 5, 5, step_value)
            step_value = np.where(step_value < 0, 0, step_value)
            #print('step_value:'+str(step_value))#debugging
            array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_per_step)] = step_value
        
        array = array+offset
    
    else:
        array = amplitude*np.ones((int(number_of_samples)))+offset

    return np.array(array)


def galvo_live_mode_waveform(amplitude, samples_per_half_period, samples_per_delay, number_of_samples, samples_per_half_delay, offset): ###pas utilisé
    '''Not in use anymore, was useful for calibrating purposes, kept for reference'''
    
    if amplitude !=0:
        #print('samplesPerHalfPeriod: ' + str(samplesPerHalfPeriod))
        step_amplitude = amplitude/(samples_per_half_period-1)
        #print('amplitude: ' + str(amplitude))
        #print('stepAmplitude: ' + str(stepAmplitude))
        rise_vector = np.arange(0,amplitude+step_amplitude,step_amplitude)
        fall_vector = np.arange(amplitude, 0-step_amplitude, -step_amplitude)
        
        array = np.zeros((int(number_of_samples)))
        
        array[int(samples_per_half_delay):int(samples_per_half_delay+len(rise_vector))]=rise_vector
        array[int(samples_per_half_delay+len(rise_vector)):int(samples_per_half_delay+len(rise_vector)+len(fall_vector))]=fall_vector
        
        array = array + offset  
    else:
        array = np.zeros((int(number_of_samples))) + offset
    
    return np.array(array)

def galvo_trapeze(amplitude, samples_per_half_period, samples_per_delay, number_of_samples, number_of_steps, samples_per_step, samples_per_half_delay, min_samples_per_delay, t_start_exp, samplerate, offset):
    '''Trapeze waveform for the galvos. Camera acquires frames only when the 
       galvos are in motion, i.e. when they are scanning.'''
    
    samples_before_exposition = np.round(t_start_exp*samplerate)
    
    if amplitude !=0:
        #print('samplesPerHalfPeriod: ' + str(samples_per_half_period))
        step_amplitude = amplitude/(samples_per_half_period-1)
        #print('amplitude: ' + str(amplitude))
        #print('stepAmplitude: ' + str(step_amplitude))
        rise_vector = np.arange(0,amplitude+step_amplitude,step_amplitude)
        fall_vector = np.arange(amplitude, 0-step_amplitude, -step_amplitude)
        amplitude_vector = amplitude*np.ones((int(samples_per_delay)))
        
        array = np.zeros((int(number_of_samples)))
        
        for i in range(int(number_of_steps)):
            sample_i = samples_per_half_delay + (i * samples_per_step)
            if i%2==0:   #Even step number, ramp rising
                if i == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(sample_i-samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the rising vector
                    if samples_left < (min_samples_per_delay+samples_per_half_period): #We stay low, not enough samples to make a scan
                        pass #There is not enough samples to make a scan, we pass
                    else:
                        samples_left -= samples_before_exposition  #Retrieves samples_before_exposition for proper calculations in the galvo cycle
                        samples_high = samples_left-samples_per_half_period
                        amplitude_vector = amplitude*np.ones((int(samples_high)))
                        array[int(sample_i):int(sample_i+len(rise_vector))]=rise_vector
                        array[int(sample_i+samples_per_half_period):int(sample_i+samples_per_half_period+samples_high)]=amplitude_vector
                else:
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=riseVector    #Rising ramp
                    array[int(sample_i):int(sample_i+len(rise_vector))]=rise_vector
                    array[int(sample_i+samples_per_half_period):int(sample_i+samples_per_half_period+samples_per_delay)]=amplitude_vector  #Plateau
                
            else:     #Odd step number, ramp falling
                if i == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(sample_i-samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the falling vector
                    #print('Galvo')
                    #print('i: {}'.format(i))
                    #print('samples_left: {}'.format(samples_left))
                    #print('min_samples_per_delay: {}'.format(min_samples_per_delay))
                    #print('samples_per_half_period: {}'.format(samples_per_half_period))
                    #print('samples_per_half_delay: {}'.format(samples_per_half_delay))
                    #print('samples_before_exposition: {}'.format(samples_before_exposition))
                    if samples_left < (min_samples_per_delay+samples_per_half_period): #We stay high, not enough samples to make a scan 
                        samples_left -= samples_before_exposition #Retrieves samples_before_exposition for proper calculations in the galvo cycle 
                        amplitude_vector = amplitude*np.ones((int(samples_left)))
                        array[int(sample_i):int(sample_i+samples_left)]=amplitude_vector
                    else:
                        array[int(sample_i):int(sample_i+len(fall_vector))]=fall_vector
                
                else:        
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=fallVector    #Falling ramp
                    array[int(sample_i):int(sample_i+len(fall_vector))]=fall_vector
        
        array = array + offset
    else:
        array = np.zeros((int(number_of_samples))) + offset  
    
    return np.array(array)

def laser_signal( ###Pas utilisé
            samplerate = 100000,    # in samples/second
            sweeptime = 0.4,        # in seconds
            voltage = 0.9           # in volts
            ):
    '''Generates a constant value waveform at the voltage specified'''
    
    samples = int(np.floor(np.multiply(samplerate, sweeptime)))
    array = np.full((samples), voltage)
    
    return np.array(array)

def sawtooth( ###Pas utilisé
    samplerate = 100000,    # in samples/second
    sweeptime = 0.4,        # in seconds
    frequency = 10,         # in Hz
    amplitude = 0,          # in V
    offset = 0,             # in V
    dutycycle = 50,          # dutycycle in percent
    phase = np.pi/2,          # in rad
    ):
    '''
    Returns a numpy array with a sawtooth function

    Used for creating the galvo signal.

    Example:
    galvosignal =  sawtooth(100000, 0.4, 199, 3.67, 0, 50, np.pi)
    '''

    samples =  int(samplerate*sweeptime)
    dutycycle = dutycycle/100       # the signal.sawtooth width parameter has to be between 0 and 1
    t = np.linspace(0, sweeptime, samples)
    # Using the signal toolbox from scipy for the sawtooth:
    waveform = signal.sawtooth(2 * np.pi * frequency * t + phase, width=dutycycle)
    # Scale the waveform to a certain amplitude and apply an offset:
    waveform = amplitude * waveform + offset

    return waveform

def single_pulse( ###Pas utilisé
    samplerate=100000,  # in samples/second
    sweeptime=0.4,      # in seconds
    delay=10,           # in percent
    pulsewidth=1,       # in percent
    amplitude=0,        # in volts
    offset=0            # in volts
    ):

    '''
    Returns a numpy array with a single pulse

    Used for creating TTL pulses out of analog outputs and laser intensity
    pulses.

    Units:
    samplerate: Integer
    sweeptime:  Seconds
    delay:      Percent
    pulsewidth: Percent
    amplitude:  Volts
    offset:     Volts

    Examples:

    typical_TTL_pulse = single_pulse(samplerate, sweeptime, 10, 1, 5, 0)
    typical_laser_pulse = single_pulse(samplerate, sweeptime, 10, 80, 1.25, 0)
    '''

    # get an integer number of samples
    samples = int(np.floor(np.multiply(samplerate, sweeptime)))
    # create an array just containing the offset voltage:
    array = np.zeros((samples))+offset

    # convert pulsewidth and delay in % into number of samples
    pulsedelaysamples = int(samples * delay / 100)
    pulsesamples = int(samples * pulsewidth / 100)

    # modify the array
    array[pulsedelaysamples:pulsesamples+pulsedelaysamples] = amplitude
    return np.array(array)

def square( ###Pas utilisé
    samplerate = 100000,    # in samples/second
    sweeptime = 0.4,        # in seconds
    frequency = 10,         # in Hz
    amplitude = 0,          # in V
    offset = 0,             # in V
    dutycycle = 50,         # dutycycle in percent
    phase = np.pi,          # in rad
    ):
    """
    Returns a numpy array with a rectangular waveform
    """

    samples =  int(samplerate*sweeptime)
    dutycycle = dutycycle/100       # the signal.square duty parameter has to be between 0 and 1
    t = np.linspace(0, sweeptime, samples)

    # Using the signal toolbox from scipy for the sawtooth:
    waveform = signal.square(2 * np.pi * frequency * t + phase, duty=dutycycle)
    # Scale the waveform to a certain amplitude and apply an offset:
    waveform = amplitude * waveform + offset

    return waveform

def tunable_lens_ramp( ###Pas utilisé
    samplerate = 100000,    # in samples/second
    sweeptime = 0.4,        # in seconds
    delay = 7.5,            # in percent
    rise = 85,              # in percent
    fall = 2.5,             # in percent
    amplitude = 0,          # in volts
    offset = 0              # in volts
    ):

    '''
    Returns a numpy array with a ETL ramp

    The waveform starts at offset and stays there for the delay period, then
    rises linearly to 2x amplitude (amplitude here refers to 1/2 peak-to-peak)
    and drops back down to the offset voltage during the fall period.

    Switching from a left to right ETL ramp is possible by exchanging the
    rise and fall periods.

    Units of parameters
    samplerate: Integer
    sweeptime:  Seconds
    delay:      Percent
    rise:       Percent
    fall:       Percent
    amplitude:  Volts
    offset:     Volts
    '''
    # get an integer number of samples
    samples = int(np.floor(np.multiply(samplerate, sweeptime)))
    # create an array just containing the negative amplitude voltage:
    array = np.zeros((samples))-amplitude + offset

    # convert rise, fall, and delay in % into number of samples
    delaysamples = int(samples * delay / 100)
    risesamples = int(samples * rise / 100)
    fallsamples = int(samples * fall / 100)

    risearray = np.arange(0,risesamples)
    risearray = amplitude * (2 * np.divide(risearray, risesamples) - 1) + offset

    fallarray = np.arange(0,fallsamples)
    fallarray = amplitude * (1-2*np.divide(fallarray, fallsamples)) + offset

    # rise phase
    array[delaysamples:delaysamples+risesamples] = risearray
    # fall phase
    array[delaysamples+risesamples:delaysamples+risesamples+fallsamples] = fallarray

    return np.array(array)