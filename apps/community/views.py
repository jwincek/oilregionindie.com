from django.shortcuts import render


def index(request):
    """Community landing page — Phase 3."""
    return render(request, "community/index.html")
