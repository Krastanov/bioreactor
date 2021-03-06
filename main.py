import logging
import logging.config


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
        'webinterface': {
            'handlers': ['default'],
            'level': 'INFO' ,
            'propagate': False
        },
        'arduino': {
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
import time
import webbrowser

from web import start_web_interface_thread, stop_web_interface_thread
from scheduler import start_scheduler_thread, stop_scheduler_thread


def report(*threads):
    return '\n    '.join('%s: %s'%(t.name, t.is_alive()) for t in threads)

logger.info('Starting scheduler and web threads...')
scheduler_thread = start_scheduler_thread()
web_interface_thread = start_web_interface_thread()
webbrowser.open('http://localhost:8080', new=1, autoraise=True)
try:
    while True:
        logger.info(report(web_interface_thread,
                           scheduler_thread))
        time.sleep(5)
except KeyboardInterrupt:
    logger.info('Interrupted by user. Shutting down...')
logger.info('Stopping scheduler and web threads...')
stop_scheduler_thread()
stop_web_interface_thread()
