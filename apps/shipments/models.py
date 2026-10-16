"""Migration-only app shell. No active business models."""
import secrets

def public_reference():
    """Historical 0001 default only; not an active lookup or publication service."""
    return "JHZ-" + secrets.token_hex(20).upper()
