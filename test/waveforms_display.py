import matplotlib.pyplot as plt
import numpy as np

parameters = dict()
parameters["samplerate"]=40000          # In samples/seconds
parameters["sweeptime"]=0.4             # In seconds
parameters["galvo_l_frequency"]=5#100     # In Hertz
parameters["galvo_l_amplitude"]=2       # In Volts
parameters["galvo_l_offset"]=0.6          # In Volts
parameters["galvo_r_frequency"]=100     # In Hertz
parameters["galvo_r_amplitude"]=2       # In Volts
parameters["galvo_r_offset"]=0.6           # In Volts
parameters["etl_l_amplitude"]=2         # In Volts
parameters["etl_l_offset"]=0            # In Volts
parameters["etl_r_amplitude"]=2         # In Volts
parameters["etl_r_offset"]=0            # In Volts
parameters["laser_l_voltage"]=0.905     # In Volts
parameters["laser_r_voltage"]=0.935     # In Volts
parameters["columns"] = 2560            # In pixels
parameters["rows"] = 2160               # In pixels 
parameters["etl_step"] =  400            # In pixels
parameters["camera_delay"] = 10         # In %
parameters["min_t_delay"] = 0.0354404   # In seconds
parameters["t_start_exp"] = 0.017712    # In seconds




'''FUNCTIONS'''

def camera_busy_status(samples_per_half_period, t_start_exp, samplerate, samples_per_half_delay, number_of_samples, number_of_steps, samples_per_step, min_samples_per_delay):
    '''Digital signal. High signal indicates when the camera is busy for frame 
       acquisition. Each pulse is for the acquisition of one frame only.'''
    samples_per_exposition = samples_per_half_period
    samples_before_exposition = np.round(t_start_exp*samplerate)             #Round, ceil or floor?
    samples_per_high_level = samples_per_exposition + min_samples_per_delay
    samples_before_high_level = samples_per_half_delay-samples_before_exposition             
    high_level_vector = np.full(int(samples_per_high_level), True)
    
    array = np.full(int(number_of_samples), False)
    
    for i in range(int(number_of_steps)):
        if i == int(number_of_steps-1): #Last loop
            samples_left = number_of_samples-(samples_before_high_level+i*samples_per_step)
            
            if samples_left < (min_samples_per_delay+samples_per_half_period):
                pass  #No enough samples for another acquisition, we pass
            else:
                array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_high_level)]=high_level_vector
        else:
            array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_high_level)]=high_level_vector
    
    return np.array(array)
    
    


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
            
            if samples_left < (min_samples_per_delay+samples_per_half_period):
                pass  #No enough samples for another acquisition, we pass
            else:
                array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_exposition)]=high_level_vector
        else:
            array[int(samples_before_high_level+i*samples_per_step):int(samples_before_high_level+i*samples_per_step+samples_per_exposition)]=high_level_vector
    
    return np.array(array)


def camera_exposure_status(samples_per_half_period,samples_per_half_delay,number_of_samples, number_of_steps, samples_per_step, t_start_exp,samplerate):
    '''Digital signal. High signal indicates the camera exposition'''
    samples_before_exposition = np.round(t_start_exp*samplerate)
    samples_per_exposition = samples_per_half_period           
    high_level_vector = np.full(int(samples_per_exposition), True)
    
    array = np.full(int(number_of_samples), False)
    
    for i in range(int(number_of_steps)):
        if i == int(number_of_steps-1): #Last loop
            samples_left = number_of_samples-(samples_per_half_delay+i*samples_per_step-samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the rising vector
            if samples_left < (min_samples_per_delay+samples_per_half_period): #We stay low, not enough samples to make a scan
                pass #There is not enough samples to make a scan, we pass
            else:
                array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+samples_per_exposition)] = high_level_vector
                
        else: 
            array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+samples_per_exposition)] = high_level_vector
            
    return np.array(array)


def etl_stairs(amplitude, number_of_steps, number_of_samples, samples_per_step, offset, direction):
    '''Step function. The stairs are defined to be upwards or downwards depending 
       on the ETL.
    
       Later, stepAmplitude will be define by the ETL focus position as a function of the voltage applied
       Each ETL may have a different relation to the voltage applied'''
    if number_of_steps !=1:
        #step_column = 2560/(number_of_steps-1) ###
        step_column=400
    
        print('Step column: ' + str(step_column)) #debugging
        
        array = np.zeros((int(number_of_samples)))
        
        for i in range(int(number_of_steps)):
            if direction == 'UP': ###DOWN
                #print('left')
                if i == int(number_of_steps-1): #Last loop, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    column_value = 2559*np.ones(int(samples_per_step))###
                else:
                    column_value = i*step_column*np.ones(int(samples_per_step))###
                step_value = -0.001282893174259485 * column_value + 4.920315064788371###
        
            if direction == 'DOWN': ###UP
                #print('right')
                if i == int(number_of_steps-1): #Last loop, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    column_value = 2559*np.ones(int(samples_per_step))###
                else:
                    column_value = i*step_column*np.ones(int(samples_per_step))###
                step_value = 0.0013507132995247916 * column_value + 1.8730880902476752###
        
            #print('column_value:'+ str(column_value))#debugging
            step_value = np.where(step_value > 5, 5, step_value)
            step_value = np.where(step_value < 0, 0, step_value)
            #print('step_value:'+str(step_value))#debugging
            array[i*int(samples_per_step):i*int(samples_per_step)+int(samples_per_step)] = step_value
        
        array = array+offset
    
    else:
        array = amplitude*np.ones((int(number_of_samples)))+offset
    
    return np.array(array)



def galvo_trapeze(amplitude, samples_per_half_period, samples_per_delay, number_of_samples, number_of_steps, samples_per_step, samples_per_half_delay, min_samples_per_delay, t_start_exp, samplerate, offset):
    '''Trapeze waveform for the galvos. Camera acquires frames only when the 
       galvos are in motion, i.e. when they are scanning.'''
    
    samples_before_exposition = np.round(t_start_exp*samplerate)
    
    if amplitude !=0:
        step_amplitude = amplitude/(samples_per_half_period-1)
        rise_vector = np.arange(0,amplitude+step_amplitude,step_amplitude)
        fall_vector = np.arange(amplitude, 0-step_amplitude, -step_amplitude)
        amplitude_vector = amplitude*np.ones((int(samples_per_delay)))
        
        array = np.zeros((int(number_of_samples)))
        
        for i in range(int(number_of_steps)):
            
            if i%2==0:   #Even step number, ramp rising
                if i == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(samples_per_half_delay+i*samples_per_step-samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the rising vector
                    if samples_left < (min_samples_per_delay+samples_per_half_period): #We stay low, not enough samples to make a scan
                        pass #There is not enough samples to make a scan, we pass
                    else:
                        samples_left -= samples_before_exposition  #Retrieves samples_before_exposition for proper calculations in the galvo cycle
                        samples_high = samples_left-samples_per_half_period
                        amplitude_vector = amplitude*np.ones((int(samples_high)))
                        array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+len(rise_vector))]=rise_vector
                        array[int(samples_per_half_delay+i*samples_per_step+samples_per_half_period):int(samples_per_half_delay+i*samples_per_step+samples_per_half_period+samples_high)]=amplitude_vector
                else: 
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=riseVector    #Rising ramp
                    array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+len(rise_vector))]=rise_vector
                    array[int(samples_per_half_delay+i*samples_per_step+samples_per_half_period):int(samples_per_half_delay+i*samples_per_step+samples_per_half_period+samples_per_delay)]=amplitude_vector  #Plateau
                
            else:     #Odd step number, ramp falling
                if i == int(number_of_steps-1):  #Last iteration, deals with a shorter step (in case ETL step is not a multiple of the number of columns)
                    samples_left = number_of_samples-(samples_per_half_delay+i*samples_per_step-samples_before_exposition) #samples_before_exposition takes into account the beginning of the camera cycle starting before the falling vector

                    if samples_left < (min_samples_per_delay+samples_per_half_period): #We stay high, not enough samples to make a scan 
                        samples_left -= samples_before_exposition #Retrieves samples_before_exposition for proper calculations in the galvo cycle 
                        amplitude_vector = amplitude*np.ones((int(samples_left)))
                        array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+samples_left)]=amplitude_vector
                    else:
                        array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+len(fall_vector))]=fall_vector
                
                else:        
                    #array[int(samplesPerHalfDelay+i*samplesPerStep):int(samplesPerHalfDelay+i*samplesPerStep+samplesPerHalfPeriod)]=fallVector    #Falling ramp
                    array[int(samples_per_half_delay+i*samples_per_step):int(samples_per_half_delay+i*samples_per_step+len(fall_vector))]=fall_vector
        
        array = array + offset
    else:
        array = np.zeros((int(number_of_samples))) + offset  
    
    array = array *-1 + amplitude + 2*offset 
    
    return np.array(array)





'''MAIN'''


'''Initializing'''
t_half_period = 0.5*(1/parameters["galvo_l_frequency"])     #It is our exposure time (is in the range of the camera)
print('t_half_period:'+str(t_half_period))
samples_per_half_period = np.ceil(t_half_period*parameters["samplerate"])

min_samples_per_delay = np.ceil(parameters["min_t_delay"]*parameters["samplerate"])

min_samples_per_step = min_samples_per_delay +  samples_per_half_period

rest_samples_added = np.ceil(min_samples_per_step*parameters["camera_delay"]/100)  #Samples added to allow down time for the camera
samples_per_step = min_samples_per_step + rest_samples_added

samples_per_delay = samples_per_step-samples_per_half_period

samples_per_half_delay = np.floor(samples_per_delay/2)

number_of_steps = np.ceil(parameters["columns"]/parameters["etl_step"])

number_of_samples = number_of_steps*samples_per_step

sweeptime = number_of_samples/parameters["samplerate"]

samples = int(number_of_samples)




'''Generating waveforms'''
camera_waveform = camera_digital_output_signal(samples_per_half_period = samples_per_half_period, 
                                                    t_start_exp = parameters["t_start_exp"], 
                                                    samplerate = parameters["samplerate"], 
                                                    samples_per_half_delay = samples_per_half_delay, 
                                                    number_of_samples = number_of_samples, 
                                                    number_of_steps = number_of_steps,
                                                    min_samples_per_delay = min_samples_per_delay, 
                                                    samples_per_step = samples_per_step)

etl_l_waveform = etl_stairs(amplitude = parameters["etl_l_amplitude"], 
                                             number_of_steps = number_of_steps, 
                                             number_of_samples = number_of_samples, 
                                             samples_per_step = samples_per_step, 
                                             offset = parameters["etl_l_offset"], 
                                             direction = 'UP')

etl_r_waveform = etl_stairs(amplitude = parameters["etl_r_amplitude"], 
                                             number_of_steps = number_of_steps, 
                                             number_of_samples = number_of_samples, 
                                             samples_per_step = samples_per_step, 
                                             offset = parameters["etl_r_offset"], 
                                             direction = 'DOWN')

galvo_waveform = galvo_trapeze(amplitude = parameters["galvo_l_amplitude"], 
                                                  samples_per_half_period = samples_per_half_period, 
                                                  samples_per_delay = samples_per_delay, 
                                                  number_of_samples = number_of_samples, 
                                                  number_of_steps = number_of_steps, 
                                                  samples_per_step = samples_per_step, 
                                                  samples_per_half_delay = samples_per_half_delay,
                                                  min_samples_per_delay = min_samples_per_delay,
                                                  t_start_exp = parameters["t_start_exp"], 
                                                  samplerate = parameters["samplerate"],
                                                  offset = parameters["galvo_l_offset"])

camera_exposure_status_waveform = camera_exposure_status(samples_per_half_period = samples_per_half_period, 
                                                         samples_per_half_delay = samples_per_half_delay, 
                                                         number_of_samples = number_of_samples, 
                                                         number_of_steps = number_of_steps, 
                                                         samples_per_step = samples_per_step, 
                                                         t_start_exp = parameters["t_start_exp"], 
                                                         samplerate = parameters["samplerate"])

camera_busy_status_waveform = camera_busy_status(samples_per_half_period = samples_per_half_period, 
                                                 t_start_exp = parameters["t_start_exp"], 
                                                 samplerate = parameters["samplerate"], 
                                                 samples_per_half_delay = samples_per_half_delay, 
                                                 number_of_samples = number_of_samples, 
                                                 number_of_steps = number_of_steps, 
                                                 samples_per_step = samples_per_step, 
                                                 min_samples_per_delay = min_samples_per_delay)

array = np.arange(int(number_of_samples))
print('Waveforms length should be: {} samples'.format(len(array)))
print('Camera waveform length: {} samples'.format(len(camera_waveform)))
print('Galvo waveform length: {} samples'.format(len(galvo_waveform)))
print('Right ETL waveform length: {} samples'.format(len(etl_r_waveform)))
print('Left ETL waveform length: {} samples'.format(len(etl_l_waveform)))
print('Camera exposure status waveform length: {} samples'.format(len(camera_exposure_status_waveform)))
print('Camera busy status waveform length: {} samples \n'.format(len(camera_busy_status_waveform)))

print('sweeptime: {} s'.format(sweeptime))




'''Waveforms display'''
plt.plot(array,camera_waveform, label = 'Camera DO')
plt.plot(array,camera_busy_status_waveform, label = 'Camera Busy Status')
plt.plot(array,camera_exposure_status_waveform, label = 'Camera Exp Status')
plt.plot(array,galvo_waveform, label = 'Galvos')
plt.plot(array,etl_r_waveform, label = 'Right ETL')
plt.plot(array,etl_l_waveform, label = 'Left ETL')

plt.legend(loc = 'upper right')
plt.show()


