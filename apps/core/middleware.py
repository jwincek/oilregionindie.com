from django.contrib.auth import logout
from django.shortcuts import redirect


class SuspensionMiddleware:
    """
    Check if the current user is suspended. If so, log them out
    and redirect to a suspension notice page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and hasattr(request.user, "profile")
            and request.user.profile.is_suspended
        ):
            # Allow logout and static files
            if request.path not in ("/accounts/logout/", "/suspended/"):
                logout(request)
                return redirect("/suspended/")

        return self.get_response(request)
