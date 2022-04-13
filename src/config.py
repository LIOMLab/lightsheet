'''
Created on April 1st, 2022
'''


from configparser import ConfigParser

def cfg_read(cfg_filename, cfg_section, cfg_dictionary):
    """
    Reads in a specific section of a configuration file and returns updated config dictionary
    Must provide a base dictionnary of values to read
    Will ignore extraneous keys found in the configuration file
    """
    tmp_dictionary = {}
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(cfg_filename)
    if cfg.has_section(cfg_section):
        for key, value in cfg[cfg_section].items():
            tmp_dictionary[key] = value
    for key in cfg_dictionary:
        if key in tmp_dictionary:
            cfg_dictionary[key] = tmp_dictionary[key]
    return cfg_dictionary

def cfg_write(cfg_filename, cfg_section, cfg_dictionary):
    """
    Write config dictionary to a specified section of a configuration file
    Will not erase other keys found in the same section
    """
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(cfg_filename)
    if not cfg.has_section(cfg_section):
        cfg.add_section(cfg_section)
    for key in cfg_dictionary:
        cfg.set(cfg_section, str(key), str(cfg_dictionary[key]))
    with open(cfg_filename, 'w', encoding='utf-8') as output_file:
        cfg.write(output_file)
    return cfg_dictionary



# -------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    cfg_in = {}
    cfg_in['AO Terminals'] = '/Dev1/ao0:3'
    cfg_in['Sample Rate'] = '10000'
    cfg_in['Galvo Left Amplitude'] = '2'
    cfg_in['Galvo Right Amplitude'] = '2'
    cfg_in['Galvo Left Offset'] = '0.6'
    cfg_in['Galvo Right Offset'] = '0.6'
    cfg_in['ETL Left Amplitude'] = '2.0'
    cfg_in['ETL Right Amplitude'] = '2.0'
    cfg_in['ETL Left Offset'] = '0'
    cfg_in['ETL Right Offset'] = '0'
    cfg_in['ETL Steps'] = '8'

    cfg_out = cfg_read('config.ini', 'HwDAQ', cfg_in)
    cfg_write('test.ini', 'HwDAQ', cfg_out)
    print(cfg_out)
