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


# ------------------------------------------------------------------------
# ------------------------------------------------------------------------


def camera_squarewave2(pre_samples:int, active_samples:int, post_samples:int, shift:int, repeat:int, inverted:bool=False):
    """
    Camera squarewave function generator for external exposure control
    """
    pre_vector = np.full(pre_samples, False)
    scan_vector = np.full(active_samples, True)
    post_vector = np.full(post_samples, False)
    period_vector = np.concatenate((pre_vector, scan_vector, post_vector))

    if shift!=0:
        period_vector = np.concatenate((period_vector[-shift:], period_vector[:-shift]))
    if inverted:
        period_vector = ~period_vector
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def galvo_ramp2(activated:bool, pre_samples:int, scan_samples:int, reset_samples:int, post_samples:int, shift:int, repeat:int, amplitude:float, offset:float, inverted:bool, filtered:bool=True):
    """
    Galvo ramp function generator for one-way scanning 
    """
    period_samples = pre_samples + scan_samples + reset_samples + post_samples
    if activated:
        flyback_samples = int(0.75*reset_samples)
        dead_samples = reset_samples - flyback_samples + post_samples

        pre_vector = np.zeros(pre_samples)
        scan_vector = np.linspace(0, 1, scan_samples)
        flyback_vector = np.linspace(1, 0, flyback_samples)
        dead_vector = np.zeros(dead_samples)
        period_vector = np.concatenate((pre_vector, scan_vector, flyback_vector, dead_vector))

        if shift!=0:
            period_vector = np.concatenate((period_vector[-shift:], period_vector[:-shift]))
        if inverted:
            period_vector = amplitude * (-period_vector + 1) + offset
        else:
            period_vector = amplitude * period_vector + offset
        if filtered:
            # filtering using sliding average
            pad = reset_samples//10
            win = 2*pad + 1
            tmpvec = np.concatenate((period_vector[-pad:], period_vector, period_vector[:pad]))
            cusum = np.cumsum(np.insert(tmpvec, 0, 0))
            period_vector = (cusum[win:] - cusum[:-win]) / win
    else:
        period_vector = np.ones((period_samples)) * offset
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def etl_staircase2(activated:bool, step_samples:int, nbr_steps:int, shift:int, amplitude:float, offset:float, direction:str='up', filtered:bool=True):
    """ 
    Staircase function generator for ETL
    
    samples_total_scan  Number of samples for the complete acquisition sequence
    steps               Number of step (focus regions)
    amplitude           Height of the staircase (above floor level) -> Signal maximum amplitude = floor + rise
    offset              Floor level of the staircase
    direction           Either 'up' (ascending) or down (descending)

    Special case : For a staircase consisting of a single step, level is equal to (floor + 0.5 * rise)
    """
    total_samples = step_samples * nbr_steps
    if activated:
        if nbr_steps != 1:
            step_run = step_samples
            step_rise = amplitude/(nbr_steps-1)
            if direction == 'down':
                output_vector = np.ones(total_samples) * (offset + amplitude)
                for step in range(nbr_steps):
                    step_level = (offset + amplitude) - step * step_rise * np.ones(step_run)
                    output_vector[step*step_run:(step+1)*step_run] = step_level
            else:
                output_vector = np.ones(total_samples) * offset
                for step in range(nbr_steps):
                    step_level = offset + step * step_rise * np.ones(step_run)
                    output_vector[step*step_run:(step+1)*step_run] = step_level
            if shift!=0:
                output_vector = np.concatenate((output_vector[-shift:], output_vector[:-shift]))
            if filtered:
                # Filtering using sliding average
                # Compute padding and window width
                pad = step_run//25
                win = 2*(step_run//25) + 1
                # First pass (centered)
                tmpvec = np.concatenate((output_vector[:pad], output_vector, output_vector[-pad:]))
                cusum = np.cumsum(np.insert(tmpvec, 0, 0))
                output_vector = (cusum[win:] - cusum[:-win]) / win
                # Second pass (centered)
                tmpvec = np.concatenate((output_vector[:pad], output_vector, output_vector[-pad:]))
                cusum = np.cumsum(np.insert(tmpvec, 0, 0))
                output_vector = (cusum[win:] - cusum[:-win]) / win
        else:
            output_vector = np.ones(total_samples) * (offset + amplitude/2)
    else:
        output_vector = np.ones((total_samples)) * offset
    return output_vector


