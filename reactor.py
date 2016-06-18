import numpy as np

class Reactor:
    def __getattr__(self, name):
        def mock_function(*args):
            import time
            time.sleep(10)
            return np.random.random((4,5))*2-1
        return mock_function

reactor = Reactor()
