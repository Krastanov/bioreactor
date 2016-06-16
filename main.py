import logging
import logging.config
import time

from web import start_web_interface_thread, stop_web_interface_thread
from scheduler import start_scheduler_thread, stop_scheduler_thread


###############################################################################
# Configure loggers.
###############################################################################

LOG_CONF = {
    'version': 1,

    'formatters': {
        'standard': {
            'format': '\n%(asctime)s [%(levelname)s] %(threadName)s %(name)s:\n    %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level':'INFO',
            'class':'logging.StreamHandler',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'INFO'
        },
        'database': {
            'handlers': ['default'],
            'level': 'INFO' ,
            'propagate': False
        },
        'scheduler': {
            'handlers': ['default'],
            'level': 'INFO' ,
            'propagate': False
        },
        'scheduler': {
            'handlers': ['default'],
            'level': 'INFO' ,
            'propagate': False
        },
        'cherrypy.access': {
            'handlers': [],
            'level': 'INFO',
            'propagate': False
        },
        'cherrypy.error': {
            'handlers': ['default'],
            'level': 'INFO',
            'propagate': False
        },
    }
}

logging.config.dictConfig(LOG_CONF)
logger = logging.getLogger()


###############################################################################
# Starting all threads.
###############################################################################

def report(*threads):
    return '\n    '.join('%s: %s'%(t.name, t.is_alive()) for t in threads)

logger.info('Starting all threads.')
web_interface_thread = start_web_interface_thread()
scheduler_thread = start_scheduler_thread()
try:
    while True:
        logger.info(report(web_interface_thread,
                           scheduler_thread))
        time.sleep(5)
except KeyboardInterrupt:
    logger.info('Interrupted by user. Shutting down...')
logger.info('Stopping all threads.')
stop_web_interface_thread()
stop_scheduler_thread()
