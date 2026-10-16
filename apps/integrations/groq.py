"""Configuration/client construction only. No extraction, navigation or automatic requests."""
from django.conf import settings
from groq import Groq


class ProviderUnavailable(ValueError):
    pass


def configuration(vision=False):
    if not settings.GROQ_ENABLED:
        return "disabled"
    if not settings.GROQ_API_KEY.strip() or settings.GROQ_API_KEY.startswith(("REPLACE_", "YOUR_")):
        return "missing_key"
    model = settings.GROQ_VISION_MODEL if vision else settings.GROQ_TEXT_MODEL
    mode = settings.GROQ_VISION_OUTPUT_MODE if vision else settings.GROQ_TEXT_OUTPUT_MODE
    if not model.strip():
        return "missing_model"
    return "ready" if mode in ("schema", "json") else "invalid_mode"


def create_client(*, vision=False, transport=None):
    if configuration(vision) != "ready":
        raise ProviderUnavailable("Groq is not configured for this operation.")
    import httpx
    # Construction performs no network request; later callers must explicitly close the client.
    return Groq(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com",
                timeout=httpx.Timeout(30, connect=5), max_retries=0,
                http_client=httpx.Client(transport=transport, follow_redirects=False, trust_env=False))
