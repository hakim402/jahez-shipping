from celery import shared_task
@shared_task(name="jahez_shipping.foundation_ping")
def foundation_ping():
    """Non-mutating queue smoke check; no provider requests or domain writes."""
    return "pong"
