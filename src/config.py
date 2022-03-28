from configparser import ConfigParser

def cfgReadSection(config_file, section):
    values_dict = {}
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(config_file)
    if cfg.has_section(section):
        for key, value in cfg[section].items():
            values_dict[key] = value
    return values_dict

def cfgWriteSection(config_file, section, values_dict):
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(config_file)
    if not cfg.has_section(section):
        cfg.add_section(section)
    for key in values_dict:
        cfg.set(section, str(key), str(values_dict[key]))
    with open(config_file, 'w') as output_file:
        cfg.write(output_file)
    return None

if __name__ == "__main__":
    configuration = cfgReadSection('test.ini', 'Test')
    cfgWriteSection('test.ini', 'Test', configuration)

