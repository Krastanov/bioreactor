import logging
import os.path
import time

from nanpy import ArduinoApi,  SerialManager, Stepper, DallasTemperature
from nanpy.arduinotree import ArduinoTree
import numpy as np

from database import db

logger = logging.getLogger('arduino')


class Reactor:
    '''`Reactor` does all the talking to the arduino hardware.'''
    def __init__(self, connection):
        self.arduino = ArduinoApi(connection=connection)
        self.arduinotree = ArduinoTree(connection=connection)

        # Movement
        self.stepper_x = Stepper(4096, 23, 25, pin3=27, pin4=29,
                                 speed=2, connection=connection)
        self.stepper_y = Stepper(4096, 28, 26, pin3=24, pin4=22,
                                 speed=2, connection=connection)
        self.pin_x_origin = self.arduinotree.pin.get('D53')
        self.pin_y_origin = self.arduinotree.pin.get('D52')
        self.pin_x_origin.mode = 0
        self.pin_x_origin.write_pullup(1)
        self.pin_y_origin.mode = 0
        self.pin_y_origin.write_pullup(1)

        # Temperature sensing
        self.temp_sensor = DallasTemperature(33, connection)
        temp_ads = [
         '28.2D.6D.55.07.00.00.3C',
         '28.28.B8.56.07.00.00.D3',
         '28.38.B2.55.07.00.00.BD',
         '28.F1.AD.56.07.00.00.2F',
         '28.C8.C8.55.07.00.00.1F',
         '28.DB.FA.55.07.00.00.1A']
        #convert addresses from base 16 to base 10
        self.dec_temp_ads = [[int(_,16) for _ in a.split('.')] for a in temp_ads]

        # Temperature control
        # TODO current nanpy version has a bug and does not support the object oriented interface on all pins
        #self.pin_A_cool = self.arduinotree.pin.get('D2')
        #self.pin_A_heat = self.arduinotree.pin.get('D3')
        #self.pin_B_heat = self.arduinotree.pin.get('D4')
        #self.pin_B_cool = self.arduinotree.pin.get('D5')
        #self.pin_A_cool.pwm.write_value(0)
        #self.pin_A_heat.pwm.write_value(0)
        #self.pin_B_heat.pwm.write_value(0)
        #self.pin_B_cool.pwm.write_value(0)
        self.pin_A_cool = 2
        self.pin_A_heat = 3
        self.pin_B_heat = 4
        self.pin_B_cool = 5
        self.arduino.analogWrite(self.pin_A_cool, 0)
        self.arduino.analogWrite(self.pin_A_heat, 0)
        self.arduino.analogWrite(self.pin_B_heat, 0)
        self.arduino.analogWrite(self.pin_B_cool, 0)

        # UV light
        self.pin_uv = self.arduinotree.pin.get('D7')
        self.pin_uv.mode = 0
        self.pin_uv.digital_value = 0

        # Light sensing
        self.pin_light_in = self.arduinotree.pin.get('A7')
        self.pin_light_in.mode = 1

    def move_head_steps(self, steps_x, steps_y):
        '''Move the head the given amount of steps.'''
        # XXX It divides the move in repeated small movements, because
        # movement is slow and it might timeout the serial connection.
        if steps_x:
            steps = abs(steps_x)
            d = steps_x//steps
            while steps>10:
                self.stepper_x.step(d*10)
                steps -= 10
            self.stepper_x.step(d*steps)
        if steps_y:
            steps = abs(steps_y)
            d = steps_y//steps
            while steps>10:
                self.stepper_y.step(d*10)
                steps -= 10
            self.stepper_y.step(d*steps)

    def move_head_to_origin(self):
        '''Move head to origin.

        First move in the x, then move in y.'''
        while self.pin_x_origin.digital_value:
            self.move_head_steps(-10, 0)

        while self.pin_y_origin.digital_value:
            self.move_head_steps(0, -10)

    def move_head_to_well(self, row, col, instrument_offset):
        '''Move the head to the given well, taking into account the instrument offset.'''
        ...

    def temps(self):
        '''Return the temperature for each of the temperature sensors.'''
        self.temp_sensor.requestTemperatures()
        [self.temp_sensor.getTempC(_) for _ in self.dec_temp_ads] # XXX repeat due to timer issues
        return [self.temp_sensor.getTempC(_) for _ in self.dec_temp_ads]

    def mean_temp(self):
        '''Return the average temperature across the sensors.'''
        return sum(self.temps())/6

    def row_temps(self):
        '''Calculate the temperature in each of the rows of wells (assuming linear gradient).'''
        temps = self.temps()
        meanA = sum(temps[0:2])/2
        meanB = sum(temps[2:4])/2
        meanC = sum(temps[4:6])/2

        row1 = meanA - (meanB-meanA)/2
        row2 = (meanA + meanB)/2
        row3 = (meanB + meanC)/2
        row4 = meanC + (meanC-meanB)/2

        return [row1, row2, row3, row4]

    def set_heat_flow(self, heat_flow):
        '''Set signed normalized TEC power.

        Positive means heating.'''
        assert -1 <= heat_flow <= +1, 'Heat flow is out of range.'
        max_power = 30 # XXX max pwm power supported by the H-bridge we have
        if heat_flow>=0:
            self.arduino.analogWrite(self.pin_A_cool, 0)
            self.arduino.analogWrite(self.pin_B_cool, 0)
            self.arduino.analogWrite(self.pin_A_heat, int(max_power*heat_flow))
            self.arduino.analogWrite(self.pin_B_heat, int(max_power*heat_flow))
        elif heat_flow<0:
            self.arduino.analogWrite(self.pin_A_heat, 0)
            self.arduino.analogWrite(self.pin_B_heat, 0)
            self.arduino.analogWrite(self.pin_A_cool, int(-max_power*heat_flow))
            self.arduino.analogWrite(self.pin_B_cool, int(-max_power*heat_flow))

    def set_target_temp(self, target_temp):
        '''Set the target temperature for the temperature control loop.'''
        self._target_temp = target_temp

    def stop_temperature_control(self):
        '''Stop the temperature control thread.'''
        if hasattr(self, '_temp_thread') and self._temp_thread.is_alive():
            self._stop_temperature_control.set()
            while self._temp_thread.is_alive():
                time.sleep(0.1)

    def start_temperature_control(self, target_temp):
        '''A PI loop for temperature control. Starts its own thread.'''
        if hasattr(self, '_temp_thread') and self._temp_thread.is_alive():
            raise ValueError('A temperature control thread is already active')
        self._stop_temperature_control = threading.Event()
        def temp_control():
            I = 0
            while not self._stop_temperature_control.is_set():
                error = self.mean_temp()-self._target_temp
                P = -error
                control = P
                if -1 < control < 1: # XXX simplistic windup protection
                    I += P
                else:
                    I = 0
                control += I/10
                control = min(+1., control)
                control = max(-1., control)
                self.set_heat_flow(control)
                print(('%.2f '*3)%(P, I, control))
                with db:
                    db.execute('''INSERT INTO temperature_control_log
                                  (target_temp, error,
                                  proportional, integral)
                                  VALUES (?,?,?,?)''',
                                  (self._target_temp, error, P, I))
                time.sleep(10)
        self._temp_thread = threading.Thread(target=temp_control, name='TemperatureControl')

    def set_uv(self, mode):
        '''Turn the UV on (mode=1) or off (mode=0).'''
        assert mode in [0,1], 'UV supports only on or off modes.'
        self.pin_uv.digital_value = mode

    def set_light_intensity(self, intensity):
        '''Set illumination for LEDs.'''
        ...

    def measure_optical_density(self):
        ...


class MockReactor:
    '''A mock reactor class for dev and testing.'''
    def __getattr__(self, name):
        def mock_function(*args):
            import time
            time.sleep(3)
            return np.random.random((4,5))*2-1
        return mock_function


# Try to connect to the Arduino. If it is not available start a mock reactor.
for serial_file in ['/dev/ttyACM0','/dev/ttyACM1']:
    logger.info('Attempting Arduino connection on %s...'%serial_file)
    if os.path.isfile(serial_file):
        connection = SerialManager(device=serial_file)
        reactor = Reactor(connection=connection)
        logger.info('Connected to Arduino on %s.'%serial_file)
        break
else:
    logger.info('No Arduino detected! Set a mock reactor.')
    reactor = MockReactor()
