"""
Module for creating waveforms and analog output signals

Authors: Pierre Girard-Collins & Fabian Voigt

#TODO
* Usage of amplitude is not consistent (peak-to-peak in single_pulse)
"""

#import nidaqmx
# from nidaqmx.constants import AcquisitionType, TaskMode
# from nidaqmx.constants import LineGrouping

#from scipy import signal
import numpy as np

def camera_digital_output_signal(samples_per_half_period, t_start_exp, samplerate, samples_per_half_delay, number_of_samples, number_of_steps, samples_per_step, min_samples_per_delay):
    '''Set the high level time interval (samples), i.e. the time when the camera 
       exposure is on, each time the galvos are in motion. The waveform is 
       coded by taking into account the mechanism of frame acquisition by the CMOS
       PCO edge 5.5m camera of the light-sheet in external exposure control mode 
       (the camera trigger mode chosen to operate the microscope). See the 
       camera documentation for more infos.'''
    
    samples_per_exposition = samples_per_half_period
    samples_before_exposition = np.round(t_start_exp*samplerate) #Number of samples to read dark image            #Round, ceil or floor?
    samples_before_high_level = samples_per_half_delay - samples_before_exposition             
    high_level_vector = np.full(int(samples_per_exposition), True)
    
    array = np.full(int(number_of_samples), False)
    
    for step in range(int(number_of_steps)):
        high_level_start = int(samples_before_high_level + step*samples_per_step)
        high_level_end = int(high_level_start + samples_per_exposition)
        if step == int(number_of_steps-1): #Last loop
            samples_left = number_of_samples - high_level_start
            #print('Camera')
            #print('i: {}'.format(i))
            #print('samples_left: {}'.format(samples_left))
            #print('min_samples_per_delay: {}'.format(min_samples_per_delay))
            #print('samples_per_half_period: {}'.format(samples_per_half_period))
            #print('samples_per_half_delay: {}'.format(samples_per_half_delay))
            if samples_left < (min_samples_per_delay + samples_per_exposition):
                pass  #No enough samples for another acquisition, we pass
            else:
                #if step%2 == 0: ###
                array[high_level_start:high_level_end] = high_level_vector
        else:
            #if step%2 == 0: ###
            array[high_level_start:high_level_end] = high_level_vector
    
    return np.array(array)

def calibrated_etl_stairs(left_slope, left_intercept, right_slope, right_intercept, etl_step, amplitude, number_of_steps, number_of_samples, samples_per_step, offset, direction,activate=False):
    '''Step function. The stairs are defined to be upwards or downwards depending 
       on the ETL.
    
       Later, stepAmplitude will be define by the ETL focus position as a function of the voltage applied
       Each ETL may have a different relation to the voltage applied'''
    
    if activate: ###
        if number_of_steps != 1:
            #step_column = 2560/(number_of_steps-1) ###
            step_column = etl_step
        
            #print('Step column: ' + str(step_column)) #debugging
            
            array = np.zeros((int(number_of_samples)))
            
            for step in range(int(number_of_steps)):
                column_value = step * step_column * np.ones(int(samples_per_step))
                if direction == 'UP': ###DOWN
                    step_value = left_slope * column_value + left_intercept
                if direction == 'DOWN': ###UP
                    step_value = right_slope * column_value + right_intercept
            
                #print('column_value:'+ str(column_value))#debugging
                step_value = np.where(step_value > 5, 5, step_value) #To make sure not to send >5V to the ETL
                step_value = np.where(step_value < 0, 0, step_value) #To make sure not to send <0V to the ETL
                #print('step_value:'+str(step_value))#debugging
                step_first_column = int(step * samples_per_step)
                step_last_column = int(step_first_column + samples_per_step)
                array[step_first_column:step_last_column] = step_value
            
            array = array + offset
        else:
            array = amplitude * np.ones((int(number_of_samples))) + offset
    else: ###
        #print('ETL focus deactivated')
        array = amplitude * np.ones((int(number_of_samples))) + offset
    
    return np.array(array)

def galvo_trapeze(amplitude, samples_per_half_period, samples_per_delay, number_of_samples, number_of_steps, samples_per_step, samples_per_half_delay, min_samples_per_delay, t_start_exp, samplerate, offset,invert=False):
    '''Trapeze waveform for the galvos. Camera acquires frames only when the 
       galvos are in motion, i.e. when they are scanning.'''
    
    samples_before_exposition = np.round(t_start_exp * samplerate)
    
    if amplitude !=0:
        #print('samplesPerHalfPeriod: ' + str(samples_per_half_period))
        step_amplitude = amplitude/(samples_per_half_period-1)
        #print('amplitude: ' + str(amplitude))
        #print('stepAmplitude: ' + str(step_amplitude))
        rise_vector = np.arange(0,(amplitude + step_amplitude),step_amplitude)
        fall_vector = np.arange(amplitude,(0 - step_amplitude),-step_amplitude)
        amplitude_vector = amplitude * np.ones((int(samples_per_delay)))
        
        array = np.zeros((int(number_of_samples)))
        
        for step in range(int(number_of_steps)):
            step_ramp_start = int(samples_per_half_delay + (step * samples_per_step))
            step_ramp_end = int(step_ramp_start + len(rise_vector))
            step_high_start = int(step_ramp_start + samples_per_half_period)
            
            if step %2 == 0:   #Even step number, ramp rising
                if step == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples - (step_ramp_start - samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the rising vector
                    if samples_left < (min_samples_per_delay + samples_per_half_period): #We stay low, not enough samples to make a scan
                        pass #There is not enough samples to make a scan, we pass
                    else:
                        samples_high = samples_left - samples_before_exposition - samples_per_half_period #Retrieves samples_before_exposition for proper calculations in the galvo cycle
                        amplitude_vector = amplitude * np.ones((int(samples_high)))
                        step_high_end = int(step_ramp_start + samples_per_half_period + samples_high)
                        array[step_ramp_start:step_ramp_end] = rise_vector
                        array[step_high_start:step_high_end] = amplitude_vector  #Plateau
                else:
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=riseVector    #Rising ramp
                    step_high_end = int(step_ramp_start + samples_per_half_period + samples_per_delay)
                    array[step_ramp_start:step_ramp_end] = rise_vector
                    array[step_high_start:step_high_end] = amplitude_vector  #Plateau
                
            else:     #Odd step number, ramp falling
                if step == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples - (step_ramp_start - samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the falling vector
                    #print('Galvo')
                    #print('i: {}'.format(i))
                    #print('samples_left: {}'.format(samples_left))
                    #print('min_samples_per_delay: {}'.format(min_samples_per_delay))
                    #print('samples_per_half_period: {}'.format(samples_per_half_period))
                    #print('samples_per_half_delay: {}'.format(samples_per_half_delay))
                    #print('samples_before_exposition: {}'.format(samples_before_exposition))
                    if samples_left < (min_samples_per_delay + samples_per_half_period): #We stay high, not enough samples to make a scan 
                        samples_left -= samples_before_exposition #Retrieves samples_before_exposition for proper calculations in the galvo cycle 
                        amplitude_vector = amplitude * np.ones((int(samples_left)))
                        array[step_ramp_start:int(step_ramp_start + samples_left)] = amplitude_vector
                    else:
                        array[step_ramp_start:step_ramp_end] = fall_vector
                
                else:        
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=fallVector    #Falling ramp
                    array[step_ramp_start:step_ramp_end] = fall_vector
        
        array = array + offset
    else:
        array = np.zeros((int(number_of_samples))) + offset  
    
    if invert:
        array = array * -1 + amplitude + 2*offset
        print('inverted')
    return np.array(array)
