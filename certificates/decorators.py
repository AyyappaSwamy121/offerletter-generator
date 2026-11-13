from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden


def is_super_admin(user):
    """Check if the user has Super Admin privileges."""
    if not user.is_authenticated:
        return False
    # Superuser, or staff who is not a restricted college admin
    return user.is_superuser or (user.is_staff and not hasattr(user, 'college_profile'))


def is_college_admin(user):
    """Check if the user is an active College Administrator."""
    if not user.is_authenticated:
        return False
    if not hasattr(user, 'college_profile'):
        return False
    profile = user.college_profile
    return (
        profile.is_active and 
        user.is_active and 
        profile.get_colleges().exists()
    )


def super_admin_required(view_func):
    """Decorator ensuring only Super Admins can access the view."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if hasattr(request.user, 'college_profile'):
            messages.error(request, "Access restricted. You do not have Super Admin privileges.")
            return redirect('college_dashboard')
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "Access denied. Administrator privileges required.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def college_admin_required(view_func):
    """Decorator ensuring only active College Administrators can access the view."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # If user is a super admin, allow them to view or redirect appropriately
        if is_super_admin(request.user):
            messages.info(request, "You are logged in as Super Admin. Redirected to Super Admin Home.")
            return redirect('home')

        if not hasattr(request.user, 'college_profile'):
            messages.error(request, "Your account is not associated with any college.")
            return redirect('login')

        profile = request.user.college_profile
        if not profile.is_active or not request.user.is_active:
            messages.error(request, "Your college administrator account has been deactivated. Please contact the Super Admin.")
            return redirect('login')

        # Check if the administrator has at least one active assigned college
        active_colleges = profile.colleges.filter(is_active=True)
        if not active_colleges.exists():
            messages.error(request, "Your assigned institutions are currently suspended or none are assigned. Please contact the Super Admin.")
            return redirect('login')

        return view_func(request, *args, **kwargs)
    return _wrapped_view
    return _wrapped_view


def admin_or_college_required(view_func):
    """Decorator allowing either Super Admin or College Admin."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if is_super_admin(request.user) or is_college_admin(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Access denied.")
        return redirect('login')
    return _wrapped_view

