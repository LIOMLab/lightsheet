
import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType

class DAQmx:
    def __init__(self):
        self.galvo_task      = None
        self.galvo_waveform  = None

        self.ao_terminals   = '/Dev1/ao0:1'
        self.sample_rate    = 4000
        self.scan_amplitude = 2.0
        self.scan_offset    = 0

    def compute_galvo_waveform(self, samples_exposure:int, samples_readout:int, samples_reset:int, amplitude:float, offset:float, filtered:bool=True):
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
        period_vector = amplitude * period_vector + offset
        self.galvo_waveform = period_vector
        return None

    def create_scanner(self):
        try:
            # Creating and setting up the galvo + ETL scan task (AO)
            self.galvo_task = nidaqmx.Task(new_task_name = 'galvo_scan')
            self.galvo_task.ao_channels.add_ao_voltage_chan(self.ao_terminals)
            self.galvo_task.timing.cfg_samp_clk_timing(rate = self.sample_rate, sample_mode = AcquisitionType.FINITE, samps_per_chan = self.galvo_waveform.size)

            # Write waveforms to AO and DO tasks (to be started later)
            self.galvo_task.write(self.galvo_waveform, auto_start = False)
        except:
            self.galvo_task.close()
            self.galvo_task = None
            print('Create_scanner error. Terminals invalid?')

    def start_scanner(self):
        if self.galvo_task is not None:
            self.galvo_task.start()

    def monitor_scanner(self):
        if self.galvo_task is not None:
            self.galvo_task.wait_until_done()

    def stop_scanner(self):
        if self.galvo_task is not None:
            self.galvo_task.stop()

    def delete_scanner(self):
        if self.galvo_task is not None:
            self.galvo_task.close()
            self.galvo_task = None




# -------------------------------------------------------------------------------------------------
if __name__ == '__main__':

    from matplotlib import pyplot as plt

    testdaq = DAQmx()
    testdaq.compute_galvo_waveform(1250, 500, 250, 1.0, 0.0, False)
    testdaq.create_scanner()
    testdaq.start_scanner()
    testdaq.monitor_scanner()
    testdaq.stop_scanner()
    testdaq.delete_scanner()

    time_axis = np.arange(0, testdaq.galvo_waveform.size)
    plt.plot(time_axis, testdaq.galvo_waveform)
    plt.show()




