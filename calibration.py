import json


###############################################################################
# Open the calibration data file. If such file does not exists, load defaults.
###############################################################################

try:
    with open('reactor_calibration.json', 'r', encoding='utf-8') as calibration_file:
        calibration = json.load(calibration_file)
except FileNotFoundError:
    calibration = {
        'pwm/analog'              : 1.2,
        'analog/uE'               : 1321.,
        'steps_x_to_first_well'   : 500,
        'steps_y_to_first_well'   : 500,
        'steps_x_well_separation' : 20,
        'steps_y_well_separation' : 20,
    }


###############################################################################
# Helper functions for change of units dependent on the calibration.
###############################################################################

def analog_read_to_PEC(analog):
    '''Map 0-1023 reading from photosensor to uE/m^2/s.'''
    return analog/calibration['analog/uE']

def PEC_to_PWM(pec):
    '''Map target uE/m^2/s to required PWM 0-255.'''
    return pec*calibration['analog/uE']*calibration['pwm/analog']
