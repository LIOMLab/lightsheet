"""
Module for creating waveforms and analog output signals

Rewrite on April 8th 2022
"""

import numpy as np


def squarewave(pre_samples:int, active_samples:int, post_samples:int, shift:int, repeat:int, inverted:bool=False):
    """
    Camera squarewave function generator for external exposure start or control
    """
    pre_vector = np.full(pre_samples, False)
    active_vector = np.full(active_samples, True)
    post_vector = np.full(post_samples, False)
    period_vector = np.concatenate((pre_vector, active_vector, post_vector))

    if shift!=0:
        period_vector = np.concatenate((period_vector[-shift:], period_vector[:-shift]))
    if inverted:
        period_vector = ~period_vector
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def sawtooth(activated:bool, pre_samples:int, trace_samples:int, retrace_samples:int, post_samples:int, shift:int, repeat:int, amplitude:float, offset:float, inverted:bool, filtered:bool=True):
    """
    Galvo sawtooth function generator for one-way scanning
    """
    period_samples = pre_samples + trace_samples + retrace_samples + post_samples
    if activated:
        # TODO: for two-way scanning, we would need to add a 'hold' between trace and retrace
        pre_vector = np.zeros(pre_samples)
        trace_vector = np.linspace(0, 1, trace_samples)
        retrace_vector = np.linspace(1, 0, retrace_samples)
        post_vector = np.zeros(post_samples)
        period_vector = np.concatenate((pre_vector, trace_vector, retrace_vector, post_vector))

        if shift!=0:
            period_vector = np.concatenate((period_vector[-shift:], period_vector[:-shift]))
        if inverted:
            period_vector = amplitude * (-period_vector + 1) + offset
        else:
            period_vector = amplitude * period_vector + offset
        if filtered:
            # filtering using sliding average
            # TODO: optimize filter window width
            pad = retrace_samples//10
            win = 2*pad + 1
            tmpvec = np.concatenate((period_vector[-pad:], period_vector, period_vector[:pad]))
            cusum = np.cumsum(np.insert(tmpvec, 0, 0))
            period_vector = (cusum[win:] - cusum[:-win]) / win
    else:
        period_vector = np.ones((period_samples)) * offset
    output_vector = np.tile(period_vector, repeat)
    return output_vector


def staircase(activated:bool, step_samples:int, nbr_steps:int, shift:int, amplitude:float, offset:float, direction:str='up', filtered:bool=True):
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


