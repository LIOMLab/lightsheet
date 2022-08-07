import datetime
import time
time_string = time.strftime("%H%M%S", time.localtime(time.time()))
datetime_string = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
print(time_string)
print(datetime_string)