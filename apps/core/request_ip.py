"""
Client IP resolution for proxied deployments.

In production gunicorn sits behind two proxies (Coolify's proxy →
nginx), so REMOTE_ADDR is always the internal address of the last hop.
The real client is the *final* entry of X-Forwarded-For: our own edge
proxy appends it, and any entries to its left arrived from the client
and are spoofable. Referenced by AXES_CLIENT_IP_CALLABLE in settings.
"""


def client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.rsplit(",", 1)[-1].strip()
    return request.META.get("REMOTE_ADDR", "")
