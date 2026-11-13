import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.utils import timezone
from datetime import datetime

from .models import College, CollegeAdminProfile, AuditLog, Certificate
from .decorators import super_admin_required


@super_admin_required
def college_admin_list(request):
    """Super Admin view: List and manage all College Administrator accounts."""
    search_query = request.GET.get('search', '').strip()
    college_filter = request.GET.get('college', '').strip()
    status_filter = request.GET.get('status', '').strip()

    profiles = CollegeAdminProfile.objects.select_related('user', 'college').all()

    if search_query:
        profiles = profiles.filter(
            Q(full_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(college__name__icontains=search_query)
        )

    if college_filter:
        profiles = profiles.filter(college_id=college_filter)

    if status_filter:
        if status_filter == 'active':
            profiles = profiles.filter(is_active=True, user__is_active=True)
        elif status_filter == 'inactive':
            profiles = profiles.filter(Q(is_active=False) | Q(user__is_active=False))

    colleges = College.objects.filter(is_active=True).order_by('name')

    stats = {
        'total_admins': CollegeAdminProfile.objects.count(),
        'active_admins': CollegeAdminProfile.objects.filter(is_active=True, user__is_active=True).count(),
        'inactive_admins': CollegeAdminProfile.objects.filter(Q(is_active=False) | Q(user__is_active=False)).count(),
        'total_colleges': College.objects.filter(is_active=True).count(),
    }

    context = {
        'profiles': profiles,
        'colleges': colleges,
        'search_query': search_query,
        'college_filter': college_filter,
        'status_filter': status_filter,
        'stats': stats,
        'page_title': 'College Admin Management',
    }
    return render(request, 'certificates/college_admin_list.html', context)


@super_admin_required
def college_admin_create(request):
    """Super Admin view: Create a new College Administrator account."""
    colleges = College.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        college_id = request.POST.get('college_id')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        phone = request.POST.get('phone', '').strip()
        status = request.POST.get('status', 'active')
        is_active = (status == 'active')

        # Form validations
        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email or '@' not in email:
            errors.append("A valid email address is required.")
        if not college_id:
            errors.append("Please select a college.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if password != confirm_password:
            errors.append("Password confirmation does not match.")

        # Check uniqueness of email and username
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            errors.append(f"An account with email or username '{email}' already exists.")

        selected_college = College.objects.filter(pk=college_id).first()
        if not selected_college:
            errors.append("Selected college does not exist.")

        if errors:
            for err in errors:
                messages.error(request, err)
            context = {
                'colleges': colleges,
                'form_data': request.POST,
                'page_title': 'Add College Administrator',
            }
            return render(request, 'certificates/college_admin_form.html', context)

        try:
            # Create User using email as username
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                is_staff=False,
                is_superuser=False,
                is_active=is_active
            )
            # Create CollegeAdminProfile
            profile = CollegeAdminProfile.objects.create(
                user=user,
                college=selected_college,
                full_name=full_name,
                phone=phone,
                is_active=is_active
            )

            AuditLog.log(
                request,
                'CREATE_COLLEGE_ADMIN',
                f"Created College Admin account '{full_name}' ({email}) for '{selected_college.name}'",
                college=selected_college
            )

            messages.success(request, f"College Administrator '{full_name}' created successfully for {selected_college.name}.")
            return redirect('college_admin_list')

        except Exception as e:
            messages.error(request, f"Error creating account: {str(e)}")

    context = {
        'colleges': colleges,
        'page_title': 'Add College Administrator',
    }
    return render(request, 'certificates/college_admin_form.html', context)


@super_admin_required
def college_admin_edit(request, pk):
    """Super Admin view: Edit an existing College Administrator account."""
    profile = get_object_or_404(CollegeAdminProfile, pk=pk)
    colleges = College.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        college_id = request.POST.get('college_id')
        phone = request.POST.get('phone', '').strip()
        status = request.POST.get('status', 'active')
        is_active = (status == 'active')

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email or '@' not in email:
            errors.append("Valid email is required.")
        if not college_id:
            errors.append("College selection is required.")

        selected_college = College.objects.filter(pk=college_id).first()
        if not selected_college:
            errors.append("Selected college does not exist.")

        # Check email uniqueness excluding current user
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exclude(pk=profile.user.pk).exists():
            errors.append(f"Email '{email}' is already used by another account.")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            profile.full_name = full_name
            profile.phone = phone
            profile.college = selected_college
            profile.is_active = is_active
            profile.save()

            # Update User record
            user = profile.user
            user.email = email
            user.username = email
            user.is_active = is_active
            user.save()

            AuditLog.log(
                request,
                'UPDATE_COLLEGE_ADMIN',
                f"Updated College Admin '{full_name}' ({email}) for college '{selected_college.name}'",
                college=selected_college
            )

            messages.success(request, f"Administrator '{full_name}' updated successfully.")
            return redirect('college_admin_list')

    context = {
        'profile': profile,
        'colleges': colleges,
        'is_edit': True,
        'page_title': f'Edit Administrator - {profile.full_name}',
    }
    return render(request, 'certificates/college_admin_form.html', context)


@super_admin_required
def college_admin_toggle_status(request, pk):
    """Super Admin view: Activate or Deactivate a College Administrator."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('college_admin_list')

    profile = get_object_or_404(CollegeAdminProfile, pk=pk)
    # Toggle status
    new_status = not profile.is_active
    profile.is_active = new_status
    profile.save()

    profile.user.is_active = new_status
    profile.user.save()

    action = 'ACTIVATE_COLLEGE_ADMIN' if new_status else 'DEACTIVATE_COLLEGE_ADMIN'
    action_text = 'activated' if new_status else 'deactivated'

    AuditLog.log(
        request,
        action,
        f"{action_text.capitalize()} College Admin account '{profile.full_name}' ({profile.user.email})",
        college=profile.college
    )

    messages.success(request, f"Administrator account for '{profile.full_name}' has been {action_text}.")
    return redirect('college_admin_list')


@super_admin_required
def college_admin_reset_password(request, pk):
    """Super Admin view: Reset a College Administrator's password."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('college_admin_list')

    profile = get_object_or_404(CollegeAdminProfile, pk=pk)
    new_password = request.POST.get('new_password', '').strip()
    confirm_password = request.POST.get('confirm_password', '').strip()

    if not new_password or len(new_password) < 6:
        messages.error(request, "Password must be at least 6 characters long.")
        return redirect('college_admin_list')

    if new_password != confirm_password:
        messages.error(request, "Passwords do not match.")
        return redirect('college_admin_list')

    profile.user.set_password(new_password)
    profile.user.save()

    AuditLog.log(
        request,
        'PASSWORD_RESET',
        f"Reset password for College Admin '{profile.full_name}' ({profile.user.email})",
        college=profile.college
    )

    messages.success(request, f"Password for '{profile.full_name}' has been reset successfully.")
    return redirect('college_admin_list')


@super_admin_required
def audit_log_list(request):
    """Super Admin view: Display audit logs with search and date filtering."""
    search_query = request.GET.get('search', '').strip()
    action_filter = request.GET.get('action', '').strip()
    from_date = request.GET.get('from_date', '').strip()
    to_date = request.GET.get('to_date', '').strip()

    logs = AuditLog.objects.select_related('user', 'college').all()

    if search_query:
        logs = logs.filter(
            Q(username__icontains=search_query) |
            Q(college_name__icontains=search_query) |
            Q(details__icontains=search_query) |
            Q(ip_address__icontains=search_query)
        )

    if action_filter:
        logs = logs.filter(action=action_filter)

    if from_date:
        try:
            dt_from = datetime.strptime(from_date, '%Y-%m-%d')
            logs = logs.filter(created_at__gte=dt_from)
        except ValueError:
            pass

    if to_date:
        try:
            dt_to = datetime.strptime(to_date, '%Y-%m-%d')
            # include the entire day
            dt_to = dt_to.replace(hour=23, minute=59, second=59)
            logs = logs.filter(created_at__lte=dt_to)
        except ValueError:
            pass

    # Pagination: 50 per page
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    actions = AuditLog.ACTION_CHOICES

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'action_filter': action_filter,
        'from_date': from_date,
        'to_date': to_date,
        'actions': actions,
        'total_logs': logs.count(),
        'page_title': 'Audit Logs & Activity Monitoring',
    }
    return render(request, 'certificates/audit_log_list.html', context)

