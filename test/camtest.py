import sys
sys.path.append(".")

import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType, LineGrouping, Edge
from matplotlib import pyplot as plt

from src.camera import Camera
from src.siggen import SigGen
from src.config import cfg_read, cfg_write, cfg_str2bool
from src.waveforms import squarewave, sawtooth, staircase

test_camera = Camera()
if test_camera.camera is None:
    test_camera.xsize = 2048
    test_camera.ysize = 2048
    test_camera.line_time = 12.174 * 1e-6
test_camera.exposure_time = 0.500
test_camera.shutter_mode = "Rolling"
test_scanner = SigGen(test_camera)
test_scanner.etl_steps = 2
test_scanner.sample_rate = 1000
test_scanner.test = False
test_scanner.compute_scan_waveforms()
print(test_scanner.waveform_metadata)

test_camera.arm_scan()
test_scanner.compute_scan_waveforms()

# Number of images to be acquired from the camera
number_of_images = test_scanner.waveform_cycles

# Creating acquisition tasks
test_scanner.create_scanner()

# Prime the camera recorder before we start the acquisition taks
test_camera.start_recorder(number_of_images)
test_scanner.start_scanner()

# Monitor completion of acquisition tasks and camera recorder
test_camera.monitor_recorder(number_of_images)
test_scanner.monitor_scanner()

# Stop tasks and recorder
test_camera.stop_recorder()
test_scanner.stop_scanner()

# Recover images from the recorder
# Note: Images must be recovered before deleting the recorder
recorded_images = test_camera.copy_recorder_images(number_of_images)
buffer = np.asarray(recorded_images)

# Delete tasks and recorder
test_camera.delete_recorder()
test_scanner.delete_scanner()


test_scanner.update_etls(left_etl=2.5, right_etl=2.5)
test_camera.disarm()

time_axis = np.arange(0, test_scanner.waveform_camera.size)
plt.plot(time_axis, test_scanner.waveform_camera)
plt.plot(time_axis, test_scanner.waveform_galvo_left)
plt.plot(time_axis, test_scanner.waveform_galvo_right)
plt.plot(time_axis, test_scanner.waveform_etl_left)
plt.plot(time_axis, test_scanner.waveform_etl_right)
plt.show()