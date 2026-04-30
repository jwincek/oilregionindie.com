from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import CommunityPostForm, ReplyForm
from .models import CommunityPost, Tag


@require_GET
def index(request):
    """Community post listing with filtering."""
    posts = CommunityPost.objects.filter(parent__isnull=True).select_related(
        "author"
    ).prefetch_related("tags", "replies")

    post_type = request.GET.get("type")
    if post_type:
        posts = posts.filter(post_type=post_type)

    tag_slug = request.GET.get("tag")
    if tag_slug:
        posts = posts.filter(tags__slug=tag_slug)

    query = request.GET.get("q")
    if query:
        from django.db.models import Q
        posts = posts.filter(Q(title__icontains=query) | Q(body__icontains=query))

    tags = Tag.objects.all()

    template = "community/_post_list.html" if request.htmx else "community/index.html"

    return render(request, template, {
        "posts": posts,
        "tags": tags,
        "post_types": CommunityPost.PostType.choices,
        "current_type": post_type,
        "current_tag": tag_slug,
        "query": query or "",
    })


@require_GET
def detail(request, pk):
    """Post detail with replies."""
    post = get_object_or_404(
        CommunityPost.objects.select_related("author").prefetch_related(
            "tags", "replies__author"
        ),
        pk=pk,
        parent__isnull=True,
    )
    reply_form = ReplyForm() if request.user.is_authenticated else None

    return render(request, "community/detail.html", {
        "post": post,
        "reply_form": reply_form,
    })


@login_required
def create(request):
    """Create a new community post."""
    if request.method == "POST":
        form = CommunityPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()
            messages.success(request, "Post published.")
            return redirect("community:detail", pk=post.pk)
    else:
        form = CommunityPostForm()

    return render(request, "community/post_form.html", {"form": form})


@login_required
def edit(request, pk):
    """Edit an existing post (author only)."""
    post = get_object_or_404(CommunityPost, pk=pk, parent__isnull=True)

    if post.author != request.user:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = CommunityPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Post updated.")
            return redirect("community:detail", pk=post.pk)
    else:
        form = CommunityPostForm(instance=post)

    return render(request, "community/post_form.html", {"form": form, "post": post})


@login_required
@require_POST
def delete(request, pk):
    """Delete a post (author only)."""
    post = get_object_or_404(CommunityPost, pk=pk)

    if post.author != request.user:
        return HttpResponseForbidden()

    post.delete()
    messages.info(request, "Post deleted.")

    # If it was a reply, go back to the parent; otherwise go to index
    if post.parent:
        return redirect("community:detail", pk=post.parent.pk)
    return redirect("community:index")


@login_required
@require_POST
def reply(request, pk):
    """Add a reply to a post."""
    parent = get_object_or_404(CommunityPost, pk=pk, parent__isnull=True)

    form = ReplyForm(request.POST)
    if form.is_valid():
        reply_post = form.save(commit=False)
        reply_post.author = request.user
        reply_post.parent = parent
        reply_post.post_type = parent.post_type
        reply_post.save()

    return redirect("community:detail", pk=parent.pk)
