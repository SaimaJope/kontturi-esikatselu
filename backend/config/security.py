import ipaddress

from django.http import HttpResponse


def client_ip(request):
    """Never accept a client-supplied X-Forwarded-For as the rate-limit identity."""
    try:
        return str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return None


def locked_out(request, credentials=None, *args, **kwargs):
    response = HttpResponse(
        "Liian monta kirjautumisyritystä. Yritä uudelleen 15 minuutin kuluttua.",
        status=429, content_type="text/plain; charset=utf-8",
    )
    response["Retry-After"] = "900"
    response["Cache-Control"] = "no-store"
    return response
