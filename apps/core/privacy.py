"""Explicit client identity boundary. Only an allowlisted proxy may supply X-Real-IP."""
import ipaddress
from django.conf import settings


def client_address(request):
    peer=request.META.get('REMOTE_ADDR','')
    try:
        peer=str(ipaddress.ip_address(peer))
    except ValueError:
        return 'unknown'
    if peer in settings.TRUSTED_PROXY_IPS:
        claimed=request.META.get('HTTP_X_REAL_IP','')
        try:
            return str(ipaddress.ip_address(claimed))
        except ValueError:
            pass
    return peer
