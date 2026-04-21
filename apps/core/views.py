from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def welcome(request):
    """Post-signup interstitial — let the user choose what to do next."""
    # If user already has a creator profile, send them to edit
    if hasattr(request.user, "creator_profile"):
        return redirect("creators:edit")

    return render(request, "core/welcome.html")
