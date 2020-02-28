"""
mesoSPIM Module for creating waveforms and analog output signals

Author: Fabian Voigt

#TODO
* Usage of amplitude is not consistent (peak-to-peak in single_pulse)
"""

#import nidaqmx
# from nidaqmx.constants import AcquisitionType, TaskMode
# from nidaqmx.constants import LineGrouping

from scipy import signal
import numpy as np

def single_pulse(
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

def tunable_lens_ramp(
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

def sawtooth(
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

def square(
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


def DO_signal(
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


def etl_stairs(amplitude, numberOfSteps, numberOfSamples, samplesPerStep, offset, direction):
    '''Later, stepAmplitude will be define by the ETL focus position as a function of the voltage applied
       Each ETL may have a different relation to the voltage applied'''
    if numberOfSteps !=1:
        stepAmplitude = amplitude/(numberOfSteps-1)
    
        print('Step amplitude: ' + str(stepAmplitude))
        
        array = np.zeros((int(numberOfSamples)))
        
        if direction == 'UP':
            for i in range(int(numberOfSteps)):
                stepValue = i*stepAmplitude*np.ones(int(samplesPerStep))
                array[i*int(samplesPerStep):i*int(samplesPerStep)+int(samplesPerStep)] = stepValue
        
        if direction == 'DOWN':
            for i in range(int(numberOfSteps)):
                stepValue = (numberOfSteps-1-i)*stepAmplitude*np.ones(int(samplesPerStep))
                array[i*int(samplesPerStep):i*int(samplesPerStep)+int(samplesPerStep)] = stepValue
        
        array = array+offset
    
    else:
        array = amplitude*np.ones((int(numberOfSamples)))+offset

    return np.array(array)


def galvo_trapeze(amplitude, samplesPerHalfPeriod, samplesPerDelay, numberOfSamples, numberOfSteps, samplesPerStep, samplesPerHalfDelay, offset):
    
    if amplitude !=0:
        print('samplesPerHalfPeriod: ' + str(samplesPerHalfPeriod))
        stepAmplitude = amplitude/(samplesPerHalfPeriod-1)
        print('amplitude: ' + str(amplitude))
        print('stepAmplitude: ' + str(stepAmplitude))
        riseVector = np.arange(0,amplitude+stepAmplitude,stepAmplitude)
        fallVector = np.arange(amplitude, 0-stepAmplitude, -stepAmplitude)
        amplitudeVector = amplitude*np.ones((int(samplesPerDelay)))
        
        array = np.zeros((int(numberOfSamples)))
        
        for i in range(int(numberOfSteps)):
            
            if i%2==0:   #Even step number, ramp rising
                if i == int(numberOfSteps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samplesLeft = numberOfSamples-(samplesPerHalfDelay+i*samplesPerStep)
                    if samplesLeft <= samplesPerHalfDelay:
                        pass
                    elif samplesLeft <= (samplesPerHalfDelay+samplesPerHalfPeriod):
                        pass    #If there is not enough samples to make a scan, we pass
                    else:
                        samplesHigh = samplesLeft-samplesPerHalfDelay-samplesPerHalfPeriod
                        amplitudeVector = amplitude*np.ones((int(samplesHigh)))
                        array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+len(riseVector))]=riseVector
                        array[int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod+samplesHigh)]=amplitudeVector
                else: 
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=riseVector    #Rising ramp
                    array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+len(riseVector))]=riseVector
                    array[int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod+samplesPerDelay)]=amplitudeVector  #Plateau
                
            else:     #Odd step number, ramp falling
                if i == int(numberOfSteps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samplesLeft = numberOfSamples-(samplesPerHalfDelay+i*samplesPerStep)
                    if samplesLeft <= samplesPerHalfDelay:
                        pass
                    elif samplesLeft <= (samplesPerHalfDelay+samplesPerHalfPeriod):
                        samplesHigh = samplesLeft-samplesPerHalfPeriod   #We stay high, not enough samples to make a scan
                        amplitudeVector = amplitude*np.ones((int(samplesHigh)))
                        array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+len(amplitudeVector))]=amplitudeVector
                    else:
                        array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+len(fallVector))]=fallVector
                
                else:        
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=fallVector    #Falling ramp
                    array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+len(fallVector))]=fallVector
        
        array = array + offset
    else:
        array = np.zeros((int(numberOfSamples))) + offset  
    
    return np.array(array)

def camera_DO_signal(samplesPerHalfPeriod, t_startExp, samplerate, samplesPerHalfDelay, numberOfSamples, numberOfSteps, samplesPerStep):
    
    samplesPerExposition = samplesPerHalfPeriod
    samplesBeforeExposition = np.round(t_startExp*samplerate)             #Round, ceil or floor?
    samplesBeforeHighLevel = samplesPerHalfDelay-samplesBeforeExposition             
    highLevelVector = np.full(int(samplesPerExposition), True)
    
    array = np.full(int(numberOfSamples), False)
    
    for i in range(int(numberOfSteps)):
        array[int(samplesBeforeHighLevel+i*samplesPerStep):int(samplesBeforeHighLevel+i*samplesPerStep+samplesPerExposition)]=highLevelVector
    
    return np.array(array)

def etl_live_mode_waveform(amplitude, numberOfSamples):
    
    array = amplitude*np.ones((int(numberOfSamples)))
    
    return np.array(array)
    

def galvo_live_mode_waveform(amplitude, samplesPerHalfPeriod, samplesPerDelay, numberOfSamples, samplesPerHalfDelay, offset):
    
    if amplitude !=0:
        #print('samplesPerHalfPeriod: ' + str(samplesPerHalfPeriod))
        stepAmplitude = amplitude/(samplesPerHalfPeriod-1)
        #print('amplitude: ' + str(amplitude))
        #print('stepAmplitude: ' + str(stepAmplitude))
        riseVector = np.arange(0,amplitude+stepAmplitude,stepAmplitude)
        fallVector = np.arange(amplitude, 0-stepAmplitude, -stepAmplitude)
        
        array = np.zeros((int(numberOfSamples)))
        
        array[int(samplesPerHalfDelay):int(samplesPerHalfDelay+len(riseVector))]=riseVector
        array[int(samplesPerHalfDelay+len(riseVector)):int(samplesPerHalfDelay+len(riseVector)+len(fallVector))]=fallVector
        
        array = array + offset  
    else:
        array = np.zeros((int(numberOfSamples))) + offset
    
    return np.array(array)

def camera_live_mode_waveform(samplesPerHalfPeriod, t_startExp, samplerate, samplesPerHalfDelay, numberOfSamples):
    
    samplesPerExposition = samplesPerHalfPeriod
    samplesBeforeExposition = np.round(t_startExp*samplerate)             #Round, ceil or floor?
    samplesBeforeHighLevel = samplesPerHalfDelay-samplesBeforeExposition             
    highLevelVector = np.full(int(samplesPerExposition), True)
    
    array = np.full(int(numberOfSamples), False)
    
    array[int(samplesBeforeHighLevel):int(samplesBeforeHighLevel+samplesPerExposition)]=highLevelVector
    
    return np.array(array)


def laser_signal(
            samplerate = 100000,    # in samples/second
            sweeptime = 0.4,        # in seconds
            voltage = 0.9           # in volts
            ):
    
    samples = int(np.floor(np.multiply(samplerate, sweeptime)))
    array = np.full((samples), voltage)
    
    return np.array(array)
    
    