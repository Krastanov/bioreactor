import logging
import sched
import threading
import time

import numpy as np

from reactor import reactor
from database import db

logger = logging.getLogger('scheduler')


###############################################################################
# Prepare scheduler.
###############################################################################

class ResolvedScheduler(sched.scheduler):
    '''Scheduler where new events can be added for execution at any time.'''
    def __init__(self, *args, resolution=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.resolution = resolution
    def run(self, blocking=True):
        if not blocking:
            return super().run(blocking=False)
        while True:
            super().run(blocking=False)
            self.delayfunc(self.resolution)
            if self.empty():
                break

s = ResolvedScheduler()
current_experiment = None

stop_thread = threading.Event()
def start_scheduler_thread():
    '''Start the scheduler in a dedicated thread. Return thread handler.'''
    def target():
        '''Continuously run the scheduler. If the queue is empty, wait a second and rerun.'''
        logger.info('Starting the scheduler...')
        while not stop_thread.is_set():
            s.run()
            time.sleep(1)
        logger.info('The scheduler has stopped.')
    t = threading.Thread(target=target,
                         name='Scheduler')
    t.start()
    return t

def stop_scheduler_thread():
    '''Stop the scheduler thread.'''
    logger.info('Stopping the scheduler...')
    stop_thread.set()


###############################################################################
# Experiment events that the scheduler can run.
###############################################################################

# XXX All `__init__` arguments are permitted to be strings!

class Event:
    pass

class StartExperiment(Event):
    def __init__(self, name, light, temp, strain, description,
                 **kw):
        global current_experiment
        current_experiment = name
        self.light = float(light)
        self.temp = float(temp)
        self.strain = strain
        self.description = description
        self.kw = kw

    def __call__(self):
        logger.info('Experiment %s starting...', current_experiment)
        reactor.fill_with_media()
        reactor.set_light_input(self.light)
        with db:
            to_record = [current_experiment, self.description, self.strain]+\
                        [self.kw[_] for _ in ['row1', 'row2', 'row3', 'row4', 'col1', 'col2', 'col3', 'col4', 'col5']]
            db.execute('''INSERT INTO experiments (name, description, strain_name, row1, row2, row3, row4, col1, col2, col3, col4, col5)
                          VALUES (?, ?, ?,  ?,?,?,?, ?,?,?,?,?)''',
                          to_record)
            light_in_data = reactor.light_input_array()
            db.execute('''INSERT INTO light_in__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, light_in_data))
        reactor.set_target_temp(self.temp)
        reactor.pause()

class MeasureTemp(Event):
    '''Periodically measure the temperature of the wells.'''
    def __init__(self, delay):
        self.delay = float(delay)

    def __call__(self):
        data = reactor.temp_array()
        with db:
            db.execute('''INSERT INTO temperature__C (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class MeasureLightOut(Event):
    '''Periodically measure the light coming out of the wells.'''
    def __init__(self, delay):
        self.delay = float(delay)

    def __call__(self):
        data = reactor.light_out_array()
        with db:
            db.execute('''INSERT INTO light_out__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class WaterFill(Event):
    '''Periodically fill up with water (for evaporative losses).'''
    def __init__(self, delay):
        self.delay = float(delay)

    def __call__(self):
        data = reactor.fill_with_water()
        with db:
            db.execute('''INSERT INTO water__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        s.enter(self.delay*60,0,self)

class DrainFill(Event):
    '''Periodically drain and refill with media.'''
    def __init__(self, delay, drain_volume):
        self.delay = float(delay)
        self.drain_volume = float(drain_volume)

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
        logger.info('%s: drain %s, media fill %s', type(self).__name__, 'drain', drained_data.mean(), 'media fill', media_data.mean())
        s.enter(self.delay*60,0,self)

class StopExperiment(Event):
    def __call__(self):
        logger.info('Experiment %s ending...', current_experiment)
        for event in s.queue:
            s.cancel(event)
        logger.info('Experiment %s ended.', current_experiment)

# Events that autopopulate the new experiment web page.
events = [MeasureTemp, MeasureLightOut, WaterFill, DrainFill]
