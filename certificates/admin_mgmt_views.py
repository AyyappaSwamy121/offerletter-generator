import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import OperationalError
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

    # Graceful handling if migration 0034 has not been applied yet
    m2m_available = True
    try:
        profiles = CollegeAdminProfile.objects.select_related('user', 'college').prefetch_related('colleges').all()
        # Evaluate to check if intermediate table exists
        list(profiles[:1])
    except OperationalError:
        m2m_available = False
        profiles = CollegeAdminProfile.objects.select_related('user', 'college').all()
        messages.warning(
            request,
            "Database migration pending: The multi-college table is not created yet. "
            "Please run 'python manage.py migrate' in your server terminal to apply migration 0034."
        )

    if search_query:
        if m2m_available:
            profiles = profiles.filter(
                Q(full_name__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(colleges__name__icontains=search_query) |
                Q(college__name__icontains=search_query)
            ).distinct()
        else:
            profiles = profiles.filter(
                Q(full_name__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(college__name__icontains=search_query)
            ).distinct()

    if college_filter:
        if m2m_available:
            profiles = profiles.filter(Q(colleges__id=college_filter) | Q(college_id=college_filter)).distinct()
        else:
            profiles = profiles.filter(college_id=college_filter).distinct()

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
    """Super Admin view: Create a new College Administrator account with multiple colleges."""
    colleges = College.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        college_ids = request.POST.getlist('college_ids')
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
        if not college_ids:
            errors.append("Please select at least one active institution.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters long.")
        if password != confirm_password:
            errors.append("Password confirmation does not match.")

        # Check uniqueness of email and username
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            errors.append(f"An account with email or username '{email}' already exists.")

        selected_colleges = College.objects.filter(pk__in=college_ids, is_active=True)
        if not selected_colleges.exists():
            errors.append("Please select at least one active, valid institution.")

        if errors:
            for err in errors:
                messages.error(request, err)
            context = {
                'colleges': colleges,
                'form_data': request.POST,
                'assigned_college_ids': [int(cid) for cid in college_ids if cid.isdigit()],
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
            first_college = selected_colleges.first()
            profile = CollegeAdminProfile.objects.create(
                user=user,
                college=first_college,
                full_name=full_name,
                phone=phone,
                is_active=is_active
            )
            # Set Many-to-Many relationships
            profile.colleges.set(selected_colleges)

            col_names = ", ".join(selected_colleges.values_list('name', flat=True))
            AuditLog.log(
                request,
                'CREATE_COLLEGE_ADMIN',
                f"Created College Admin account '{full_name}' ({email}) assigned to: {col_names}",
                college=first_college
            )

            messages.success(request, f"College Administrator '{full_name}' created successfully with {selected_colleges.count()} assigned institution(s).")
            return redirect('college_admin_list')

        except Exception as e:
            messages.error(request, f"Error creating account: {str(e)}")

    context = {
        'colleges': colleges,
        'assigned_college_ids': [],
        'page_title': 'Add College Administrator',
    }
    return render(request, 'certificates/college_admin_form.html', context)


@super_admin_required
def college_admin_edit(request, pk):
    """Super Admin view: Edit an existing College Administrator account with multiple colleges."""
    profile = get_object_or_404(CollegeAdminProfile, pk=pk)
    colleges = College.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        college_ids = request.POST.getlist('college_ids')
        phone = request.POST.get('phone', '').strip()
        status = request.POST.get('status', 'active')
        is_active = (status == 'active')

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email or '@' not in email:
            errors.append("Valid email is required.")
        if not college_ids:
            errors.append("Please select at least one active institution.")

        selected_colleges = College.objects.filter(pk__in=college_ids, is_active=True)
        if not selected_colleges.exists():
            errors.append("Please select at least one active, valid institution.")

        # Check email uniqueness excluding current user
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exclude(pk=profile.user.pk).exists():
            errors.append(f"Email '{email}' is already used by another account.")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            first_college = selected_colleges.first()
            profile.full_name = full_name
            profile.phone = phone
            profile.college = first_college
            profile.is_active = is_active
            profile.colleges.set(selected_colleges)
            profile.save()

            # Update User record
            user = profile.user
            user.email = email
            user.username = email
            user.is_active = is_active
            user.save()

            col_names = ", ".join(selected_colleges.values_list('name', flat=True))
            AuditLog.log(
                request,
                'UPDATE_COLLEGE_ADMIN',
                f"Updated College Admin '{full_name}' ({email}) assigned to: {col_names}",
                college=first_college
            )

            messages.success(request, f"Administrator '{full_name}' updated successfully ({selected_colleges.count()} college(s) assigned).")
            return redirect('college_admin_list')

    # On GET or error, preselect assigned college IDs
    current_ids = list(profile.colleges.values_list('id', flat=True))
    if not current_ids and profile.college_id:
        current_ids = [profile.college_id]

    context = {
        'profile': profile,
        'colleges': colleges,
        'assigned_college_ids': current_ids,
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
        f"Super Admin {action_text} account '{profile.full_name}' ({profile.user.email})",
        college=profile.primary_college
    )

    messages.success(request, f"Administrator account for '{profile.full_name}' has been {action_text}.")
    return redirect('college_admin_list')


@super_admin_required
def college_admin_reset_password(request, pk):
    """Super Admin view: Reset password for a College Administrator."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('college_admin_list')

    profile = get_object_or_404(CollegeAdminProfile, pk=pk)
    new_password = request.POST.get('new_password', '').strip()
    confirm_password = request.POST.get('confirm_password', '').strip()

    if not new_password or len(new_password) < 6:
        messages.error(request, "New password must be at least 6 characters long.")
        return redirect('college_admin_list')

    if new_password != confirm_password:
        messages.error(request, "New password confirmation does not match.")
        return redirect('college_admin_list')

    profile.user.set_password(new_password)
    profile.user.save()

    AuditLog.log(
        request,
        'PASSWORD_RESET',
        f"Super Admin reset password for College Admin '{profile.full_name}' ({profile.user.email})",
        college=profile.primary_college
    )

    messages.success(request, f"Password for '{profile.full_name}' has been reset successfully.")
    return redirect('college_admin_list')


@super_admin_required
def audit_log_list(request):
    """Super Admin view: Search and filter the complete system audit trail."""
    action_filter = request.GET.get('action', '').strip()
    role_filter = request.GET.get('role', '').strip()
    search_query = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    logs = AuditLog.objects.select_related('college').all().order_by('-created_at')

    if action_filter:
        logs = logs.filter(action=action_filter)

    if role_filter:
        logs = logs.filter(role=role_filter)

    if search_query:
        logs = logs.filter(
            Q(username__icontains=search_query) |
            Q(college_name__icontains=search_query) |
            Q(details__icontains=search_query) |
            Q(ip_address__icontains=search_query)
        )

    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            logs = logs.filter(created_at__date__gte=d_from)
        except ValueError:
            pass

    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            logs = logs.filter(created_at__date__lte=d_to)
        except ValueError:
            pass

    # Pagination: 50 items per page
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    actions = AuditLog.ACTION_CHOICES

    context = {
        'page_obj': page_obj,
        'actions': actions,
        'action_filter': action_filter,
        'role_filter': role_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'total_logs': logs.count(),
        'page_title': 'Audit Logs',
    }
    return render(request, 'certificates/audit_log_list.html', context)
