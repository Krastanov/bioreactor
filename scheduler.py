from sched import scheduler
from time import sleep

from reactor import reactor
from database import db

s = scheduler()

class Event:
    pass

class StartExperiment(Event):
    def __init__(self, experiment_name, light, temp):
        self.light = light
        self.temp = temp

    def __call__(self):
        reactor.fill_with_media()
        reactor.set_light_intensity(self.light)
        with db:
            light_in_data = ...
            db.execute('''INSERT INTO light_in_uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, light_in_data))
        reactor.set_target_temp(self.temp)
        reactor.pause()

class MeasureTemp(Event):
    '''Periodically measure the temperature of the wells.'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        temp_data = reactor.temp_by_well()
        with db:
            db.execute('''INSERT INTO temperature__C (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, temp_data))
        s.enter(...)

class MeasureLightOut(Event):
    '''Periodically measure the light coming out of the wells.'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        light_out_data = reactor.light_out_by_well()
        with db:
            db.execute('''INSERT INTO light_out__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, light_out_data))
        s.enter(...)

class WaterFill(Event):
    '''Periodically fill up with water (for evaporative losses).'''
    def __init__(self, delay):
        self.delay = delay

    def __call__(self):
        water_data = reactor.fill_with_water()
        with db:
            db.execute('''INSERT INTO water__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, water_data))
        s.enter(...)

class DrainFill(Event):
    '''Periodically drain and refill with media.'''
    def __init__(self, delay, drain_volume):
        self.delay = delay
        self.drain_volume = drain_volume

    def __call__(self):
        reactor.drain_well(self.drain_volume)
        drained_data = ...
        media_data = reactor.fill_with_media()
        with db:
            db.execute('''INSERT INTO drained__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, drained_data))
            db.execute('''INSERT INTO media__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (s.experiment, media_data))
        s.enter(...)


events = [MeasureTemp, MeasureLightOut, WaterFill, DrainFill]
