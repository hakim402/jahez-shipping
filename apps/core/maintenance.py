from django.conf import settings


def active():
    # Fail closed if the data directory cannot be inspected.
    try:
        return (settings.DATA_DIR/'maintenance.lock').exists()
    except OSError:
        return True


def pause_claim(function):
    from functools import wraps
    @wraps(function)
    def guarded(*args,**kwargs):
        if active():return None
        return function(*args,**kwargs)
    return guarded
