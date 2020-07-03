'''Default parameters'''
parameters = dict()
#parameters["sample_name"]='No Sample Name'
#parameters["samplerate"]=40000          # In samples/seconds
#parameters["sweeptime"]=0.4             # In seconds
#parameters["galvo_l_frequency"]=100     # In Hertz
#parameters["galvo_l_amplitude"]=6.5 #2       # In Volts
#parameters["galvo_l_offset"]=-3         # In Volts
#parameters["galvo_r_frequency"]=100     # In Hertz
#parameters["galvo_r_amplitude"]=6.5 #2       # In Volts
#parameters["galvo_r_offset"]=-3         # In Volts
#parameters["etl_l_amplitude"]=2         # In Volts
#parameters["etl_l_offset"]=0            # In Volts
#parameters["etl_r_amplitude"]=2         # In Volts
#parameters["etl_r_offset"]=0            # In Volts
#parameters["laser_l_voltage"]=0.905#1.3      # In Volts
#parameters["laser_r_voltage"]=0.935     # In Volts
#parameters["columns"] = 2560            # In pixels
#parameters["rows"] = 2160               # In pixels 
#parameters["etl_step"] = 100#50            # In pixels
#parameters["camera_delay"] = 10         # In %
#parameters["min_t_delay"] = 0.0354404   # In seconds
#parameters["t_start_exp"] = 0.017712    # In seconds


with open(r"C:\git-projects\lightsheet\src\configuration.txt") as file:
    parameters["etl_l_amplitude"] = float(file.readline())
    parameters["etl_r_amplitude"] = float(file.readline())
    parameters["etl_l_offset"] = float(file.readline())
    parameters["etl_r_offset"] = float(file.readline())
    parameters["galvo_l_amplitude"] = float(file.readline())
    parameters["galvo_r_amplitude"] = float(file.readline())
    parameters["galvo_l_offset"] = float(file.readline())
    parameters["galvo_r_offset"] = float(file.readline())
    parameters["galvo_l_frequency"] = float(file.readline())
    parameters["galvo_r_frequency"] = float(file.readline())
    parameters["samplerate"] = float(file.readline())
    
with open(r"C:\git-projects\lightsheet\src\configuration.txt","w") as file:
    file.write(str(parameters["etl_l_amplitude"])+'\n'+
               str(parameters["etl_r_amplitude"])+'\n'+
               str(parameters["etl_l_offset"])+'\n'+
               str(parameters["etl_r_offset"])+'\n'+
               str(parameters["galvo_l_amplitude"])+'\n'+
               str(parameters["galvo_r_amplitude"])+'\n'+
               str(parameters["galvo_l_offset"])+'\n'+
               str(parameters["galvo_r_offset"])+'\n'+
               str(parameters["galvo_l_frequency"])+'\n'+
               str(parameters["galvo_r_frequency"])+'\n'+
               str(parameters["samplerate"])
               )

print(parameters)
