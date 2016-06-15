from sched import scheduler
from time import sleep

import numpy as np

from reactor import reactor
from database import db

s = scheduler()
current_experiment = None

class Event:
    pass

class StartExperiment(Event):
    def __init__(self, name, light, temp, strain, description):
        global current_experiment
        self.light = light
        self.temp = temp
        current_experiment = name
        self.strain = strain
        self.description = description

    def __call__(self):
        reactor.fill_with_media()
        reactor.set_light_input(self.light)
        with db:
            db.execute('''INSERT INTO experiments (name, description, strain_name)
                          VALUES (?, ?, ?)''',
                          (current_experiment, self.description, self.strain))
            light_in_data = reactor.light_input_array()
            db.execute('''INSERT INTO light_in__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, light_in_data))
        reactor.set_target_temp(self.temp)
        reactor.pause()

class MeasureTemp(Event):
    '''Periodically measure the temperature of the wells.'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        data = reactor.temp_array()
        with db:
            db.execute('''INSERT INTO temperature__C (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        print(type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class MeasureLightOut(Event):
    '''Periodically measure the light coming out of the wells.'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        data = reactor.light_out_array()
        with db:
            db.execute('''INSERT INTO light_out__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        print(type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class WaterFill(Event):
    '''Periodically fill up with water (for evaporative losses).'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        data = reactor.fill_with_water()
        with db:
            db.execute('''INSERT INTO water__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        print(type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class DrainFill(Event):
    '''Periodically drain and refill with media.'''
    def __init__(self, delay, drain_volume):
        self.delay = delay
        self.drain_volume = drain_volume

    def __call__(self):
        reactor.drain_well(self.drain_volume)
        drained_data = np.array([[self.drain_volume]*4]*5)
        media_data = reactor.fill_with_media_array()
        with db:
            db.execute('''INSERT INTO drained__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, drained_data))
            db.execute('''INSERT INTO media__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, media_data))
        print(type(self).__name__, 'drain', drained_data.mean(), 'media fill', media_data.mean())
        s.enter(self.delay*60,0,self)

class StopExperiment(Event):
    def __call__(self):
        print('Ending...')
        for event in s.queue:
            s.cancel(event)
        print('Ended')

events = [MeasureTemp, MeasureLightOut, WaterFill, DrainFill]
