
from configparser import ConfigParser
import copy

class Configuration:
    
    '''Default settings'''
    _galvo = {}
    _galvo['Left Galvo Amplitude']  = 2         # In Volts
    _galvo['Right Galvo Amplitude'] = 2         # In Volts
    _galvo['Left Galvo Offset']     = 0.6       # In Volts
    _galvo['Right Galvo Offset']    = 0.6       # In Volts
    _galvo['Galvo Frequency']       = 20        # In Hertz
    _galvo['Sample Rate']           = 40000     # In samples/seconds

    _etl = {}
    _etl['Left ETL Amplitude']    = 2         # In Volts
    _etl['Right ETL Amplitude']   = 2         # In Volts
    _etl['Left ETL Offset']       = 0         # In Volts
    _etl['Right ETL Offset']      = 0         # In Volts
    _etl['ETL Step']              = 400       # In pixels

    _laser = {}
    _laser['Left Laser Voltage']    = 0.900     # In Volts
    _laser['Right Laser Voltage']   = 0.900     # In Volts

    _motors = {}
    _motors['Port']       = 'COM3'
    _motors['Vertical']   = 1
    _motors['Horizontal'] = 2
    _motors['Camera']     = 3


    def __init__(self):
        self.default()
        self.read_ini()

    def default(self):
        # Copy default values to current values
        self.galvo = copy.deepcopy(self._galvo)
        self.etl = copy.deepcopy(self._etl)
        self.laser = copy.deepcopy(self._laser)
        self.motors = copy.deepcopy(self._motors)

    def read_ini(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')
        
        #print('Reading config.ini file')
        #for section in cfg:
        #    print('Section: %s' % section)
        #    for key, value in cfg[section].items():
        #        print('Key: %s, Value: %s' % (key, value))

        for key, value in cfg['Galvo'].items():
            self.galvo[key] = value
        for key, value in cfg['ETL'].items():
            self.etl[key] = value
        for key, value in cfg['Lasers'].items():
            self.laser[key] = value
        for key, value in cfg['Motors'].items():
            self.motors[key] = value

    def write_ini(self):
        cfg = ConfigParser()
        cfg.optionxform = str
        cfg.read('config.ini')

        for key in self.galvo:
            cfg.set('Galvo', str(key), str(self.galvo[key]))
        for key in self.etl:
            cfg.set('ETL', str(key), str(self.etl[key]))            
        for key in self.laser:
            cfg.set('Laser', str(key), str(self.laser[key]))
        for key in self.motors:
            cfg.set('Motors', str(key), str(self.motors[key]))

        with open('config.ini', 'w') as output_file:
            cfg.write(output_file)

    def update(self):
        self.galvo['Left Galvo Amplitude'] = 10
        self.galvo['Right Galvo Amplitude'] = 20
        self.motors['Port'] = 'COM6'


if __name__ == "__main__":
    mycfg = Configuration()
    mycfg.read_ini()
    mycfg.update()
    mycfg.default()
    mycfg.write_ini()