import time

import requests

from . import control
from .exceptions import Fatal
from .logging_setup import note

PROBE_URL = "https://web.whatsapp.com"


def internet_up(url=PROBE_URL, timeout=5):
    try:
        requests.head(url, timeout=timeout)
        return True
    except requests.RequestException:
        return False


def wait_for_internet(max_wait):
    start = time.time()
    while not internet_up():
        control.check()
        if time.time() - start > max_wait:
            raise Fatal("Internet on this machine was down too long")
        note("Internet is down on this machine, waiting...")
        control.nap(10)
