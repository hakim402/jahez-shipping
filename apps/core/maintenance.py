from django.conf import settings


def active():
    # Fail closed if the data directory cannot be inspected.
    try:
        return (settings.DATA_DIR/'maintenance.lock').exists()
    except OSError:
        return True
