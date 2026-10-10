from celery import shared_task
from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from . import adapter
from .adapter import ProviderError
from .models import IntegrationJob
from .payloads import normalize, PayloadError
from .services import claim_job, process_receipt, apply_response, record_error, recover_pending, schedule_reconciliation


@shared_task(name="jahez_shipping.tracking.process_job", ignore_result=True)
def process_job(job_id):
    job = claim_job(job_id)
    if not job:
        return
    try:
        if job.kind == "receipt":
            if not (job.receipt.is_demo and settings.DEBUG) and adapter.configuration() != "ready":
                raise ProviderError("integration_disabled", True, 300)
            process_receipt(job)
            return
        leg = job.leg
        if leg.shipment.archived_at or leg.shipment.is_demo or leg.shipment.tracking_mode == "manual":
            raise ProviderError("reference_no_longer_eligible")
        data = adapter.request("register" if job.kind == "register" else "gettrackinfo", [{"number": leg.tracking_number, "carrier": leg.carrier_identifier}])
        outcome = adapter.outcome(data, leg.tracking_number, leg.carrier_identifier, registering=job.kind == "register")
        normalized = normalize(outcome.payload) if outcome.accepted and job.kind == "refresh" else None
        apply_response(job, outcome, normalized)
    except ProviderError as exc:
        record_error(job, exc)
    except (PayloadError, ValueError, TypeError, KeyError):
        record_error(job, ProviderError("invalid_provider_payload"))
    except SoftTimeLimitExceeded:
        record_error(job, ProviderError("processing_timeout", True))
    except Exception:
        # Do not let Celery log confidential provider exceptions/payloads.
        record_error(job, ProviderError("processing_unavailable", True))


@shared_task(name="jahez_shipping.tracking.reconcile", ignore_result=True)
def reconcile():
    from apps.core.maintenance import active
    if active():return
    from apps.shipments.deletion import clean_file_removals
    clean_file_removals()
    recover_pending()
    schedule_reconciliation()
