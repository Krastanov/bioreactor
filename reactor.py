import binascii
import glob
import logging
import os.path
import serial
import subprocess
import threading
import time

import numpy as np

from database import db

logger = logging.getLogger('arduino')


class ComProtocolError(Exception):
    pass


class SerialManager:
    def __init__(self, port):
        self.port = port
        self.serial = serial.Serial(port=self.port, baudrate=9600, timeout=4)
        time.sleep(2)
        self.lock = threading.Lock()
    def reset(self):
        self.serial.close()
        pwd = os.path.dirname(os.path.realpath(__file__))
        usbreset_file = os.path.join(pwd, 'usbreset')
        for line in subprocess.check_output(['lsusb']).split(b'\n'):
            if b'Arduino' in line:
                bus, dev = line.split(b':')[0].split(b' ')[1::2]
                bus = bus.decode('utf8')
                dev = dev.decode('utf8')
                break
        subprocess.check_output(['sudo', usbreset_file, '/dev/bus/usb/%s/%s'%(bus,dev)])
        self.serial = serial.Serial(port=self.port, baudrate=9600, timeout=4)
        time.sleep(2)
    def send(self, msg, debug=True):
        with self.lock:
            count = 0
            while count<5:
                buf = self.serial.read_all()
                if buf.endswith(b'\r\nready\r\n\x04'):
                    logger.info('The Arduino was reset.')
                    if debug:
                        print('reset has happened')
                elif buf:
                    raise ComProtocolError('Buffer not clean.')
                msg += ('#%X'%binascii.crc32(msg)).encode()
                self.serial.write(msg + b'\r')
                echo = self.serial.read_until(b'\x04') # ascii EOT
                ret =  self.serial.read_until(b'\x04') # ascii EOT
                expected = msg + b'\r\r\n' + msg + b'\r\n\x04'
                if debug:
                    print('out     : ',msg)
                    print('expected: ',expected)
                    print('echo    : ',echo)
                    print('return  : ',ret)
                if echo == expected:
                    break
                logger.info('The Arduino connection produced garbled echo. Resetting USB and retrying...')
                count += 1
                with db:
                    db.execute('''INSERT INTO communication_log
                                  (note ) VALUES (? )''',
                        ('reset %d on msg="%s" expected="%s" echo="%s" return="%s"'%(count, msg, expected, echo, ret),))
                self.reset()
            else:
                raise ComProtocolError('Repeated garbled echo!')
            if ret == b'\r\n-\r\n\x04':
                raise ComProtocolError('Arduino error!')
            ret, crc = ret[2:-3].split(b'#')
            if int(crc,16) != binascii.crc32(ret):
                raise ComProtocolError('Incorrect checksum!')
        return [float(_) if b'.' in _ else int(_) for _ in ret.split(b' ')]


class Reactor(SerialManager):
    '''`Reactor` does all the talking to the arduino hardware.'''
    def __init__(self, port):
        super().__init__(port)

    def move_head_steps(self, steps_x, steps_y):
        '''Move the head the given amount of steps.'''
        # XXX It divides the move in repeated small movements, because
        # movement is slow and it might timeout the serial connection.
        while steps_x > 0:
            self.send(b'moveStepper x +')
            steps_x -= 1
        while steps_x < 0:
            self.send(b'moveStepper x -')
            steps_x += 1
        while steps_y > 0:
            self.send(b'moveStepper y +')
            steps_y -= 1
        while steps_y < 0:
            self.send(b'moveStepper y -')
            steps_y += 1

    def move_head_to_origin(self):
        '''Move head to origin.

        First move in the x, then move in y.'''
        while self.send(b'checkOrigin')[0]:
            self.move_head_steps(-10, 0)

        while self.send(b'checkOrigin')[1]:
            self.move_head_steps(0, -10)

    def move_head_to_well(self, row, col, instrument_offset):
        '''Move the head to the given well, taking into account the instrument offset.'''
        ...

    def temps(self):
        '''Return the temperature for each of the temperature sensors.'''
        return self.send(b'getTemperatures')

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
        self.send(('setHeatFlow %d' %int(max_power*heat_flow)).encode())

    def set_target_temp(self, target_temp):
        '''Set the target temperature for the temperature control loop.'''
        self._target_temp = target_temp

    def stop_temperature_control(self):
        '''Stop the temperature control thread.'''
        if hasattr(self, '_temp_thread') and self._temp_thread.is_alive():
            self._stop_temperature_control.set()
            while self._temp_thread.is_alive():
                time.sleep(0.1)
            self.set_heat_flow(0)

    def start_temperature_control(self):
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
                with db:
                    db.execute('''INSERT INTO temperature_control_log
                                  (target_temp, error,
                                  proportional, integral)
                                  VALUES (?,?,?,?)''',
                                  (self._target_temp, error, P, I))
                print('\r',(self._target_temp, error, P, I, control), flush=True)
                time.sleep(10)
        self._temp_thread = threading.Thread(target=temp_control, name='TemperatureControl')
        self._temp_thread.start()

    def set_uv(self, mode):
        '''Turn the UV on (mode=1) or off (mode=0).'''
        ...

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
for serial_file in glob.glob('/dev/ttyACM*'):
    logger.info('Attempting Arduino connection on %s...'%serial_file)
    if True:
        reactor = Reactor(port=serial_file)
        logger.info('Connected to Arduino on %s.'%serial_file)
        break
else:
    logger.info('No Arduino detected! Set a mock reactor.')
    reactor = MockReactor()
