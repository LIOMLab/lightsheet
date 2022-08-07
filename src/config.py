'''
Created on April 1st, 2022
'''

import configparser

def cfg_read(cfg_filename:str, cfg_section:str, cfg_dictionary:dict):
    """
    Reads a specific section of a configuration file and returns an updated config dictionary
    Must provide a base dictionnary of values to update
    Will ignore extraneous keys found in the configuration file
    """
    tmp_dictionary = {}
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read(cfg_filename)
    if cfg.has_section(cfg_section):
        for key, value in cfg[cfg_section].items():
            tmp_dictionary[key] = value
    for key in cfg_dictionary:
        if key in tmp_dictionary:
            cfg_dictionary[key] = tmp_dictionary[key]
    return cfg_dictionary

def cfg_write(cfg_filename:str, cfg_section:str, cfg_dictionary:dict):
    """
    Write config dictionary to a specified section of a configuration file
    Will write or update keys from the dictionnary without erasing other keys found in the same section
    """
    cfg = configparser.ConfigParser()
    cfg.optionxform = str
    cfg.read(cfg_filename)
    if not cfg.has_section(cfg_section):
        cfg.add_section(cfg_section)
    for key in cfg_dictionary:
        cfg.set(cfg_section, str(key), str(cfg_dictionary[key]))
    with open(cfg_filename, 'w', encoding='utf-8') as output_file:
        cfg.write(output_file)
    return cfg_dictionary

def cfg_str2bool(v:str):
    """
    Convert a string to bool by checking against a 'True' list of words
    [ bool(str) always returns True except for the empty string ]
    """
    return v.lower() in ('true', 't', 'yes', '1')


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
