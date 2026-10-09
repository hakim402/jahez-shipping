from celery import shared_task
from .services import process, recover


@shared_task(name='jahez_shipping.ai.process', ignore_result=True)
def process_draft(pk):
    try:
        process(pk)
    except Exception:
        # Durable lease expiry recovers interrupted work. Never emit confidential tracebacks.
        return None


@shared_task(name='jahez_shipping.ai.recover', ignore_result=True)
def recover_drafts():
    try:
        recover()
    except Exception:
        return None


@shared_task(name='jahez_shipping.ai.explain',ignore_result=True)
def explain_run(pk):
    from .assistant import process
    try:
        process(pk)
    except Exception:
        return None


@shared_task(name='jahez_shipping.ai.recover_assistant',ignore_result=True)
def recover_assistant():
    from .assistant import recover
    try:
        recover()
    except Exception:
        return None
