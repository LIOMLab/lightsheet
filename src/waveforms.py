"""
Module for creating waveforms and analog output signals

Rewrite on April 8th 2022
"""

import numpy as np


def camera_squarewave(samples_exposure:int, samples_readout:int, samples_reset:int, repeat:int, samples_trigger_to_exposure:int):
    """
    Camera squarewave function generator for external exposure control
    """
    samples_dead = samples_readout + samples_reset
    samples_dead_pre = int(samples_dead/2)
    samples_before_exposure = samples_dead_pre - samples_trigger_to_exposure
    samples_after_exposure = samples_dead - samples_before_exposure

    pre_vector = np.full(samples_before_exposure, False)
    scan_vector = np.full(samples_exposure, True)
    post_vector = np.full(samples_after_exposure, False)
    period_vector = np.concatenate((pre_vector, scan_vector, post_vector))
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def galvo_ramp(samples_exposure:int, samples_readout:int, samples_reset:int, repeat:int, amplitude:float, offset:float, inverted:bool=False, filtered:bool=True):
    """
    Galvo ramp function generator for one-way scanning 
    """
    samples_dead = samples_readout + samples_reset
    samples_dead_pre = int(samples_dead/2)
    samples_flyback = samples_dead - samples_dead_pre

    pre_vector = np.zeros(samples_dead_pre)
    scan_vector = np.linspace(0, 1, samples_exposure)
    flyback_vector = np.linspace(1, 0, samples_flyback)
    period_vector = np.concatenate((pre_vector, scan_vector, flyback_vector))
    if filtered:
        # filtering using sliding average with window width ~half reset
        pad = samples_reset//4
        win = 2*(samples_reset//4) + 1
        tmpvec = np.concatenate((period_vector[-pad:], period_vector, period_vector[:pad]))
        cusum = np.cumsum(np.insert(tmpvec, 0, 0))
        period_vector = (cusum[win:] - cusum[:-win]) / win
    if inverted:
        period_vector = amplitude * (-period_vector + 1) + offset
    else:
        period_vector = amplitude * period_vector + offset
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def etl_staircase(samples_total_scan:int, steps:int, floor:float, rise:float, direction:str='up', filtered:bool=True):
    """ 
    Staircase function generator for ETL
    
    samples_total_scan  Number of samples for the complete acquisition sequence
    steps               Number of step (focus regions)
    floor               Lower level of the staircase
    rise                Rise of the staircase (from floor level) -> Signal maximum amplitude = floor + rise
    direction           Either 'up' (ascending) or down (descending)

    Special case : For a staircase consisting of a single step, level is equal to (floor + 0.5 * rise)
    """

    if steps != 1:
        step_run = int(samples_total_scan/steps)
        step_rise = rise/(steps-1)
        if direction == 'down':
            output_array = np.ones(samples_total_scan) * (floor + rise)
            for step in range(steps):
                step_level = (floor + rise) - step * step_rise * np.ones(step_run)
                ## making sure we do not to send >5V to the ETL
                #step_level = np.where(step_level > 5, 5, step_level) 
                ## making sure we do not to send <0V to the ETL
                #step_level = np.where(step_level < 0, 0, step_level)
                output_array[step*step_run:(step+1)*step_run] = step_level
        else:
            output_array = np.ones(samples_total_scan) * floor
            for step in range(steps):
                step_level = floor + step * step_rise * np.ones(step_run)
                ## making sure we do not to send >5V to the ETL
                #step_level = np.where(step_level > 5, 5, step_level) 
                ## making sure we do not to send <0V to the ETL
                #step_level = np.where(step_level < 0, 0, step_level)
                output_array[step*step_run:(step+1)*step_run] = step_level
        if filtered:
            # First pass (phase shifted)
            pad = step_run//25
            win = 2*(step_run//25) + 1
            tmpvec = np.concatenate((output_array, output_array[-2*pad:]))
            cusum = np.cumsum(np.insert(tmpvec, 0, 0))
            output_array = (cusum[win:] - cusum[:-win]) / win
            # Second pass (centered)
            pad = step_run//25
            win = 2*(step_run//25) + 1
            tmpvec = np.concatenate((output_array[:pad], output_array, output_array[-pad:]))
            cusum = np.cumsum(np.insert(tmpvec, 0, 0))
            output_array = (cusum[win:] - cusum[:-win]) / win
    else:
        output_array = np.ones(samples_total_scan) * (floor + rise/2)
    return output_array



# -------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    from matplotlib import pyplot as plt

    # Hardware parameters
    sample_clock_rate = 40000           # [samples/s]
    camera_line_time = 16.40 * 1e-6     # [s]
    camera_ysize = 2160                 # number of lines
    camera_xsize = 2560                 # number of columns

    # User selected experiment parameters
    exposure_time = 0.050               # [s]
    reset_delay_ratio = 10              # [% of image time]
    etl_steps = 6
    etl_floor = 2
    etl_rise = 2.25
    etl_direction = 'up'
    galvo_amplitude = 2
    galvo_offset = 1
    galvo_inverted = False

    # From PCO documentation for pco.edge 5.5 USB 3.0
    # Line readout time = 16.40 us
    # In Global Shutter Mode, image acquisition requires readout of two frames (dark + exposed frame)
    # Image readout time = 2 * Frame readout time (dark frame + exposed frame) + Jitter time
    # with,
    #   Frame readout time = 0.5 * nbr_of_line * line_time
    #   Jitter time = line_time
    # Image readout time = (nbr_of_lines + 1) * line_time
    camera_readout_time = (camera_ysize + 1) * camera_line_time

    # In Global Shutter Mode with External Exposure Control
    # A delay exist between exposure trigger signal and actual start of exposure (due to dark frame readout)
    # Trigger-to-exposure time delay = Frame readout time + Jitter time 
    # Trigger-to-exposure time delay = 0.5 nbr_of_line * line_time + line_time
    camera_trigger_to_exposure_time = (0.5 * camera_ysize + 1) * camera_line_time

    # Number of samples for image exposure time
    samples_exposure = int(np.ceil(exposure_time * sample_clock_rate))
    # Number of samples for image readout time
    samples_readout = int(np.ceil(camera_readout_time * sample_clock_rate))
    # Number of samples for trigger to exposure delay
    samples_trigger_to_exposure = int(np.ceil(camera_trigger_to_exposure_time * sample_clock_rate))
    # Number of samples for image exposure and readout
    samples_image = samples_exposure + samples_readout
    # Number of samples for rest time between images (reset camera, galvo flyback, etl focus update)
    samples_reset = int(np.ceil(samples_image * reset_delay_ratio/100))
    # Number of samples for one period (image acquisition samples + system reset samples)
    samples_period = samples_image + samples_reset
    # Number of samples where no active exposure is taking place (image readout + system reset)
    samples_dead = samples_readout + samples_reset
    # Number of samples for acquistion sequence (period * number of etl focus positions)
    samples_total_scan = samples_period * etl_steps
    # Time required for an acquisition sequence
    total_scan_time = samples_total_scan / sample_clock_rate

    camera_function = camera_squarewave(samples_exposure, samples_readout, samples_reset, etl_steps, samples_trigger_to_exposure)
    galvo_function = galvo_ramp(samples_exposure, samples_readout, samples_reset, etl_steps, galvo_amplitude, galvo_offset, galvo_inverted)
    etl_function = etl_staircase(samples_total_scan, etl_steps, etl_floor, etl_rise, etl_direction)
    etl_function2 = etl_staircase(samples_total_scan, etl_steps, etl_floor, etl_rise, etl_direction, False)

    time_axis = np.arange(0, camera_function.size)
    plt.plot(time_axis, camera_function)
    plt.plot(time_axis, galvo_function)
    plt.plot(time_axis, etl_function)
    plt.plot(time_axis, etl_function2)
    plt.show()


