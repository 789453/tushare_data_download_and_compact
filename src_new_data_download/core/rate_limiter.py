import time
import threading
from collections import defaultdict

class GlobalRateLimiter:
    def __init__(self):
        self._locks = defaultdict(threading.Lock)
        self._last_call = defaultdict(float)
        self._intervals = defaultdict(lambda: 1.0) # Default 1 second interval

    def set_rate(self, api_name: str, rpm: int):
        if rpm > 0:
            self._intervals[api_name] = 60.0 / rpm
        else:
            self._intervals[api_name] = 0.0

    def wait(self, api_name: str):
        interval = self._intervals[api_name]
        if interval <= 0:
            return

        with self._locks[api_name]:
            elapsed = time.time() - self._last_call[api_name]
            wait_time = interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_call[api_name] = time.time()
