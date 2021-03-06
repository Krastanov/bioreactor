import heapq
import logging
import sched
import threading
import time

import pytimeparse

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
        self.current = None
    def run(self, blocking=True):
        # Based on the python3.5 source code.
        lock = self._lock
        q = self._queue
        delayfunc = self.delayfunc
        timefunc = self.timefunc
        pop = heapq.heappop
        while True:
            with lock:
                if not q:
                    break
                time, priority, action, argument, kwargs = current = q[0]
                now = timefunc()
                if time > now:
                    delay = True
                else:
                    delay = False
                    pop(q)
            if delay:
                if not blocking:
                    return time - now
                delayfunc(self.resolution)
                continue
            else:
                self.current = current
                action(*argument, **kwargs)
                self.current = None
                delayfunc(0)

reactor_scheduler = ResolvedScheduler()
current_experiment = None

stop_thread = threading.Event()
def start_scheduler_thread():
    '''Start the scheduler in a dedicated thread. Return thread handler.'''
    def target():
        '''Continuously run the scheduler. If the queue is empty, wait a second and rerun.'''
        logger.info('Starting the scheduler...')
        while not stop_thread.is_set():
            reactor_scheduler.run()
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

class RepeatedEvent(Event):
    def __init__(self, delay='1min'):
        try:
            secs = float(delay)*60
        except ValueError:
            secs = pytimeparse.parse(delay)
        if secs is None:
            raise ValueError('Could not convert string "%s" to time.'%delay)
        self.delay = secs

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
        reactor.set_target_temp(self.temp)
        with db:
            reactor.set_light_input(self.light)
            light_in_data = reactor.light_input_array()
            db.execute('''INSERT INTO light_in__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, light_in_data))
        reactor.pause()

class MeasureTemp(RepeatedEvent):
    '''Periodically measure the temperature of the wells.'''
    def __call__(self):
        data = reactor.temp_array()
        with db:
            db.execute('''INSERT INTO temperature__C (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        reactor_scheduler.enter(self.delay,0,self)

class MeasureLightOut(RepeatedEvent):
    '''Periodically measure the light coming out of the wells.'''
    def __call__(self):
        data = reactor.light_out_array()
        with db:
            db.execute('''INSERT INTO light_out__uEm2s (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        reactor_scheduler.enter(self.delay,0,self)

class WaterFill(RepeatedEvent):
    '''Periodically fill up with water (for evaporative losses).'''
    def __call__(self):
        data = reactor.fill_with_water()
        with db:
            db.execute('''INSERT INTO water__ml (experiment_name, data)
                          VALUES (?, ?)''',
                         (current_experiment, data))
        logger.info('%s %s', type(self).__name__, data.mean())
        reactor_scheduler.enter(self.delay,0,self)

class DrainFill(RepeatedEvent):
    '''Periodically drain and refill with media.'''
    def __init__(self, delay="1min", drain_volume="1"):
        super().__init__(delay)
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
        reactor_scheduler.enter(self.delay,0,self)

class StopExperiment(Event):
    def __call__(self):
        global current_experiment
        logger.info('Experiment %s ending...', current_experiment)
        # TODO Not thread safe!
        for event in s.queue:
            s.cancel(event)
        current_experiment = None
        logger.info('Experiment %s ended.', current_experiment)

# Events that autopopulate the new experiment web page.
events = [MeasureTemp, MeasureLightOut, WaterFill, DrainFill]
