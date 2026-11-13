import io
import csv
import zipfile
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse, FileResponse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Certificate, College, CollegeAdminProfile, AuditLog
from .decorators import college_admin_required
from .utils import generate_offer_letter_pdf


def _get_target_colleges(request, profile):
    """
    Determine the authorized colleges for the current request.
    If 'college_id' or 'college' is provided in GET parameters and belongs to the
    administrator's assigned colleges, return only that college (for filtering).
    Otherwise, return all active colleges assigned to the administrator.
    """
    assigned_colleges = profile.get_colleges()
    college_param = request.GET.get('college_id', '').strip() or request.GET.get('college', '').strip()

    if college_param:
        target = assigned_colleges.filter(pk=college_param)
        if target.exists():
            return target
    return assigned_colleges


def _get_filtered_college_queryset(request, profile, target_colleges=None):
    """
    Helper function to filter offer letters securely.
    Ensures that ONLY records belonging to the administrator's authorized assigned colleges
    can ever be returned, regardless of client-supplied parameters.
    """
    if target_colleges is None:
        target_colleges = _get_target_colleges(request, profile)

    qs = Certificate.objects.filter(
        college__in=target_colleges,
        is_deleted=False
    ).select_related('college').distinct().order_by('-created_at')

    # Search query
    search_query = request.GET.get('search', '').strip()
    if search_query:
        qs = qs.filter(
            Q(full_name__icontains=search_query) |
            Q(roll_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(certificate_id__icontains=search_query) |
            Q(course__icontains=search_query) |
            Q(internship_title__icontains=search_query) |
            Q(college_name__icontains=search_query) |
            Q(college__name__icontains=search_query)
        )

    # Course / Specialization filter
    course_filter = request.GET.get('course', '').strip()
    if course_filter:
        qs = qs.filter(Q(internship_title=course_filter) | Q(course=course_filter))

    # Email status filter
    email_status = request.GET.get('email_status', '').strip()
    if email_status == 'sent':
        qs = qs.filter(email_sent=True)
    elif email_status == 'not_sent':
        qs = qs.filter(email_sent=False)

    # Date range filters (supports start_date, end_date, or issue_date/created_at)
    date_from = request.GET.get('date_from', '').strip()
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(Q(issue_date__gte=d_from) | Q(created_at__date__gte=d_from))
        except ValueError:
            pass

    date_to = request.GET.get('date_to', '').strip()
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(Q(issue_date__lte=d_to) | Q(created_at__date__lte=d_to))
        except ValueError:
            pass

    return qs


@college_admin_required
def college_dashboard(request):
    """
    Dedicated SaaS dashboard for College Administrators.
    Strictly isolated: displays only the authenticated administrator's assigned colleges.
    Supports viewing all assigned colleges simultaneously or filtering by a specific assigned college.
    """
    profile = request.user.college_profile
    assigned_colleges = profile.get_colleges().order_by('name')

    # Selected specific college filter (if any)
    college_param = request.GET.get('college_id', '').strip() or request.GET.get('college', '').strip()
    selected_college = None
    if college_param:
        selected_college = assigned_colleges.filter(pk=college_param).first()

    target_colleges = assigned_colleges.filter(pk=selected_college.id) if selected_college else assigned_colleges

    # Base query for stats (all active certificates of the target colleges)
    base_qs = Certificate.objects.filter(college__in=target_colleges, is_deleted=False)
    now = timezone.now()

    # Real database statistics
    stats = {
        'total_offer_letters': base_qs.count(),
        'total_students': base_qs.values('roll_number').distinct().count(),
        'this_month': base_qs.filter(created_at__year=now.year, created_at__month=now.month).count(),
        'emails_sent': base_qs.filter(email_sent=True).count(),
    }

    # Available distinct courses for filter dropdown
    courses = list(
        base_qs.exclude(internship_title__isnull=True).exclude(internship_title='')
        .values_list('internship_title', flat=True).distinct().order_by('internship_title')
    )
    if not courses:
        courses = list(
            base_qs.exclude(course__isnull=True).exclude(course='')
            .values_list('course', flat=True).distinct().order_by('course')
        )

    # Filtered queryset for the table
    filtered_qs = _get_filtered_college_queryset(request, profile, target_colleges)
    filtered_count = filtered_qs.count()

    # Pagination: 25 items per page
    paginator = Paginator(filtered_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Page title
    if selected_college:
        page_title = f"{selected_college.name} - Offer Letter Dashboard"
    elif assigned_colleges.count() == 1:
        page_title = f"{assigned_colleges.first().name} - Offer Letter Dashboard"
    else:
        page_title = "Multi-College Offer Letter Dashboard"

    context = {
        'profile': profile,
        'assigned_colleges': assigned_colleges,
        'selected_college': selected_college,
        'selected_college_id': str(selected_college.id) if selected_college else '',
        'stats': stats,
        'courses': courses,
        'page_obj': page_obj,
        'filtered_count': filtered_count,
        # Preserve active filter parameters
        'search': request.GET.get('search', ''),
        'course': request.GET.get('course', ''),
        'email_status': request.GET.get('email_status', ''),
        'date_from': request.GET.get('date_from', ''),
        'date_to': request.GET.get('date_to', ''),
        'page_title': page_title,
    }
    return render(request, 'certificates/college_dashboard.html', context)


@college_admin_required
def college_offer_letter_detail_api(request, pk):
    """
    JSON endpoint for viewing details of a specific offer letter.
    Server-side enforced: returns 404 if the record does not belong to ANY of the user's assigned colleges.
    """
    assigned_colleges = request.user.college_profile.get_colleges()
    cert = get_object_or_404(Certificate, pk=pk, college__in=assigned_colleges, is_deleted=False)

    college = cert.college
    college_name = college.name if college else (cert.college_name or 'N/A')

    data = {
        'id': cert.id,
        'full_name': cert.full_name,
        'roll_number': cert.roll_number,
        'email': cert.email,
        'candidate_mobile': cert.candidate_mobile or 'N/A',
        'college_name': college_name,
        'course': cert.course or cert.internship_title or 'N/A',
        'internship_title': cert.internship_title or cert.course or 'N/A',
        'internship_duration': cert.internship_duration or '2 Months',
        'start_date': cert.start_date.strftime('%d %b %Y') if cert.start_date else 'N/A',
        'end_date': cert.end_date.strftime('%d %b %Y') if cert.end_date else 'N/A',
        'issue_date': cert.issue_date.strftime('%d %b %Y') if cert.issue_date else (cert.created_at.strftime('%d %b %Y') if cert.created_at else 'N/A'),
        'stipend_amount': f"₹{cert.stipend_amount}" if cert.stipend_amount is not None else "Unpaid",
        'certificate_id': cert.certificate_id or 'N/A',
        'verification_url': cert.get_verification_url() if cert.certificate_id else '',
        'email_sent': cert.email_sent,
        'email_sent_at': cert.email_sent_at.strftime('%d %b %Y %H:%M') if cert.email_sent_at else None,
        'has_pdf': bool(cert.certificate_pdf),
        'has_image': bool(cert.certificate_image),
        'download_pdf_url': f"/college/offer-letter/{cert.id}/download-pdf/",
    }
    return JsonResponse(data)


@college_admin_required
def college_download_pdf(request, pk):
    """
    Download individual offer letter PDF.
    Enforces strict ownership: college administrator can only download documents from their assigned colleges.
    """
    assigned_colleges = request.user.college_profile.get_colleges()
    cert = get_object_or_404(Certificate, pk=pk, college__in=assigned_colleges, is_deleted=False)
    college = cert.college

    pdf_bytes = None
    # 1. Try reading existing PDF file from disk
    if cert.certificate_pdf and hasattr(cert.certificate_pdf, 'path'):
        try:
            with open(cert.certificate_pdf.path, 'rb') as f:
                pdf_bytes = f.read()
        except Exception:
            pdf_bytes = None

    # 2. Dynamic generation fallback
    if not pdf_bytes:
        try:
            offer_letter_data = {
                'candidate_name': cert.full_name,
                'roll_number': cert.roll_number,
                'course_name': cert.course or cert.internship_title,
                'institution_name': cert.college_name or (college.name if college else ''),
                'institution_address': cert.institution_address or (getattr(college, 'address', '') if college else ''),
                'candidate_mobile': cert.candidate_mobile,
                'candidate_email': cert.email,
                'internship_title': cert.internship_title or cert.course,
                'internship_duration': cert.internship_duration,
                'issue_date': cert.issue_date.strftime('%Y-%m-%d') if cert.issue_date else cert.created_at.strftime('%Y-%m-%d'),
            }
            buf = generate_offer_letter_pdf(offer_letter_data)
            if buf:
                pdf_bytes = buf.getvalue()
        except Exception:
            pass

    if not pdf_bytes:
        raise Http404("Offer letter PDF could not be found or generated.")

    AuditLog.log(
        request,
        'DOWNLOAD_PDF',
        f"Downloaded offer letter PDF for student '{cert.full_name}' (Roll: {cert.roll_number})",
        college=college
    )

    clean_name = f"{cert.roll_number.replace(' ', '_')}_{cert.full_name.replace(' ', '_')}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{clean_name}"'
    return response


@college_admin_required
@require_POST
def college_download_selected_zip(request):
    """
    Download a ZIP archive containing PDFs for selected records (via checkboxes).
    Enforces strict ownership: filters out any IDs that do not belong to the user's assigned colleges.
    """
    assigned_colleges = request.user.college_profile.get_colleges()
    selected_ids = request.POST.getlist('selected_ids')

    if not selected_ids:
        messages.error(request, "No offer letters were selected for download.")
        return redirect('college_dashboard')

    # Security: Query only records that match selected_ids AND belong to THIS user's assigned colleges
    certs = Certificate.objects.filter(
        pk__in=selected_ids,
        college__in=assigned_colleges,
        is_deleted=False
    ).select_related('college')

    if not certs.exists():
        messages.error(request, "None of the selected offer letters were found or authorized.")
        return redirect('college_dashboard')

    # Build ZIP archive in memory
    zip_buffer = io.BytesIO()
    added_files = 0
    skipped_files = []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for cert in certs:
            pdf_bytes = None
            if cert.certificate_pdf and hasattr(cert.certificate_pdf, 'path'):
                try:
                    with open(cert.certificate_pdf.path, 'rb') as f:
                        pdf_bytes = f.read()
                except Exception:
                    pdf_bytes = None

            # Dynamic fallback generation if PDF file is missing
            if not pdf_bytes:
                try:
                    c_obj = cert.college
                    offer_letter_data = {
                        'candidate_name': cert.full_name,
                        'roll_number': cert.roll_number,
                        'course_name': cert.course or cert.internship_title,
                        'institution_name': cert.college_name or (c_obj.name if c_obj else ''),
                        'institution_address': cert.institution_address or (getattr(c_obj, 'address', '') if c_obj else ''),
                        'candidate_mobile': cert.candidate_mobile,
                        'candidate_email': cert.email,
                        'internship_title': cert.internship_title or cert.course,
                        'internship_duration': cert.internship_duration,
                        'issue_date': cert.issue_date.strftime('%Y-%m-%d') if cert.issue_date else cert.created_at.strftime('%Y-%m-%d'),
                    }
                    buf = generate_offer_letter_pdf(offer_letter_data)
                    if buf:
                        pdf_bytes = buf.getvalue()
                except Exception:
                    pass

            if pdf_bytes:
                clean_filename = f"{cert.roll_number.replace(' ', '_')}_{cert.full_name.replace(' ', '_')}.pdf"
                zf.writestr(clean_filename, pdf_bytes)
                added_files += 1
            else:
                skipped_files.append(f"{cert.roll_number} - {cert.full_name}")

        if skipped_files:
            summary = f"Skipped {len(skipped_files)} records due to missing PDF documents:\n" + "\n".join(skipped_files)
            zf.writestr("skipped_records_report.txt", summary)

    zip_buffer.seek(0)

    first_col = assigned_colleges.first()
    AuditLog.log(
        request,
        'BULK_DOWNLOAD_SELECTED',
        f"Downloaded selected ZIP with {added_files} offer letters across {assigned_colleges.count()} college(s)",
        college=first_col
    )

    clean_college = "Multi_College" if assigned_colleges.count() > 1 else (first_col.code or first_col.name.replace(' ', '_'))
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Selected_Offer_Letters_{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_download_filtered_zip(request):
    """
    Download a ZIP archive containing all offer letter PDFs matching the currently applied filters.
    Strictly constrained to the user's assigned colleges (and any active college filter).
    """
    profile = request.user.college_profile
    target_colleges = _get_target_colleges(request, profile)
    certs = _get_filtered_college_queryset(request, profile, target_colleges)
    total_count = certs.count()

    if total_count == 0:
        messages.warning(request, "No offer letters matched the applied filters.")
        return redirect('college_dashboard')

    # Build ZIP archive in memory
    zip_buffer = io.BytesIO()
    added_files = 0
    skipped_files = []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for cert in certs:
            pdf_bytes = None
            if cert.certificate_pdf and hasattr(cert.certificate_pdf, 'path'):
                try:
                    with open(cert.certificate_pdf.path, 'rb') as f:
                        pdf_bytes = f.read()
                except Exception:
                    pdf_bytes = None

            if not pdf_bytes:
                try:
                    c_obj = cert.college
                    offer_letter_data = {
                        'candidate_name': cert.full_name,
                        'roll_number': cert.roll_number,
                        'course_name': cert.course or cert.internship_title,
                        'institution_name': cert.college_name or (c_obj.name if c_obj else ''),
                        'institution_address': cert.institution_address or (getattr(c_obj, 'address', '') if c_obj else ''),
                        'candidate_mobile': cert.candidate_mobile,
                        'candidate_email': cert.email,
                        'internship_title': cert.internship_title or cert.course,
                        'internship_duration': cert.internship_duration,
                        'issue_date': cert.issue_date.strftime('%Y-%m-%d') if cert.issue_date else cert.created_at.strftime('%Y-%m-%d'),
                    }
                    buf = generate_offer_letter_pdf(offer_letter_data)
                    if buf:
                        pdf_bytes = buf.getvalue()
                except Exception:
                    pass

            if pdf_bytes:
                clean_filename = f"{cert.roll_number.replace(' ', '_')}_{cert.full_name.replace(' ', '_')}.pdf"
                zf.writestr(clean_filename, pdf_bytes)
                added_files += 1
            else:
                skipped_files.append(f"{cert.roll_number} - {cert.full_name}")

        if skipped_files:
            summary = f"Summary Report:\nTotal matching records: {total_count}\nAdded to ZIP: {added_files}\nSkipped: {len(skipped_files)}\n\nDetails:\n" + "\n".join(skipped_files)
            zf.writestr("export_summary.txt", summary)

    zip_buffer.seek(0)

    first_col = target_colleges.first()
    AuditLog.log(
        request,
        'BULK_DOWNLOAD_FILTERED',
        f"Downloaded filtered ZIP archive containing {added_files} offer letters across {target_colleges.count()} college(s)",
        college=first_col
    )

    if target_colleges.count() == 1:
        clean_college = first_col.code or first_col.name.replace(' ', '_')
    else:
        clean_college = "Multi_College"
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Filtered_Offer_Letters_{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_export_excel(request):
    """
    Export all offer letters matching the currently applied filters to an Excel (.xlsx) spreadsheet.
    Strictly isolated to the administrator's assigned colleges.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    profile = request.user.college_profile
    target_colleges = _get_target_colleges(request, profile)
    certs = _get_filtered_college_queryset(request, profile, target_colleges)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Offer Letters"

    # Header styling
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    border_thin = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB'),
    )

    headers = [
        "S.No",
        "Student Name",
        "Roll Number",
        "Email Address",
        "Mobile Number",
        "College / Institution",
        "Course / Specialization",
        "Internship Title",
        "Duration",
        "Start Date",
        "End Date",
        "Issue Date",
        "Stipend (₹)",
        "Offer Letter ID",
        "Email Delivered",
        "Verification URL",
    ]

    ws.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    # Populate rows
    for idx, cert in enumerate(certs, start=1):
        college_display = cert.college.name if cert.college else (cert.college_name or '')
        row = [
            idx,
            cert.full_name,
            cert.roll_number,
            cert.email,
            cert.candidate_mobile or '',
            college_display,
            cert.course or '',
            cert.internship_title or '',
            cert.internship_duration or '',
            cert.start_date.strftime('%d-%m-%Y') if cert.start_date else '',
            cert.end_date.strftime('%d-%m-%Y') if cert.end_date else '',
            cert.issue_date.strftime('%d-%m-%Y') if cert.issue_date else (cert.created_at.strftime('%d-%m-%Y') if cert.created_at else ''),
            float(cert.stipend_amount) if cert.stipend_amount is not None else 'Unpaid',
            cert.certificate_id or '',
            "Yes" if cert.email_sent else "No",
            cert.get_verification_url() if cert.certificate_id else '',
        ]
        ws.append(row)

        row_num = idx + 1
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.border = border_thin
            if col_num in [1, 3, 10, 11, 12, 13, 15]:
                cell.alignment = align_center
            else:
                cell.alignment = align_left

    # Auto-fit column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value or '')
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    ws.row_dimensions[1].height = 26

    first_col = target_colleges.first()
    AuditLog.log(
        request,
        'EXPORT_EXCEL',
        f"Exported {certs.count()} offer letters to Excel spreadsheet across {target_colleges.count()} college(s)",
        college=first_col
    )

    clean_college = first_col.code or first_col.name.replace(' ', '_') if target_colleges.count() == 1 else "Multi_College"
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Offer_Letters_{timestamp}.xlsx"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_export_csv(request):
    """
    Export all offer letters matching active filters to a CSV spreadsheet.
    Strictly isolated to the administrator's assigned colleges.
    """
    profile = request.user.college_profile
    target_colleges = _get_target_colleges(request, profile)
    certs = _get_filtered_college_queryset(request, profile, target_colleges)

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens with proper character encoding
    output.write('\ufeff')
    writer = csv.writer(output)

    headers = [
        "S.No",
        "Student Name",
        "Roll Number",
        "Email Address",
        "Mobile Number",
        "College / Institution",
        "Course / Specialization",
        "Internship Title",
        "Duration",
        "Start Date",
        "End Date",
        "Issue Date",
        "Stipend (INR)",
        "Offer Letter ID",
        "Email Delivered",
        "Verification URL",
    ]
    writer.writerow(headers)

    for idx, cert in enumerate(certs, start=1):
        college_display = cert.college.name if cert.college else (cert.college_name or '')
        writer.writerow([
            idx,
            cert.full_name,
            cert.roll_number,
            cert.email,
            cert.candidate_mobile or '',
            college_display,
            cert.course or '',
            cert.internship_title or '',
            cert.internship_duration or '',
            cert.start_date.strftime('%Y-%m-%d') if cert.start_date else '',
            cert.end_date.strftime('%Y-%m-%d') if cert.end_date else '',
            cert.issue_date.strftime('%Y-%m-%d') if cert.issue_date else (cert.created_at.strftime('%Y-%m-%d') if cert.created_at else ''),
            str(cert.stipend_amount) if cert.stipend_amount is not None else '',
            cert.certificate_id or '',
            "Yes" if cert.email_sent else "No",
            cert.get_verification_url() if cert.certificate_id else '',
        ])

    first_col = target_colleges.first()
    AuditLog.log(
        request,
        'EXPORT_CSV',
        f"Exported {certs.count()} offer letters to CSV spreadsheet across {target_colleges.count()} college(s)",
        college=first_col
    )

    clean_college = first_col.code or first_col.name.replace(' ', '_') if target_colleges.count() == 1 else "Multi_College"
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Offer_Letters_{timestamp}.csv"

    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_change_password(request):
    """
    Self-service password update for College Administrators.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('college_dashboard')

    current_password = request.POST.get('current_password', '')
    new_password = request.POST.get('new_password', '')
    confirm_password = request.POST.get('confirm_password', '')

    user = request.user
    if not user.check_password(current_password):
        messages.error(request, "Current password does not match.")
        return redirect('college_dashboard')

    if not new_password or len(new_password) < 6:
        messages.error(request, "New password must be at least 6 characters.")
        return redirect('college_dashboard')

    if new_password != confirm_password:
        messages.error(request, "New password confirmation does not match.")
        return redirect('college_dashboard')

    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user)

    profile = getattr(user, 'college_profile', None)
    AuditLog.log(
        request,
        'PASSWORD_CHANGE',
        f"College Administrator '{profile.full_name}' changed their account password",
        college=profile.primary_college if profile else None
    )

    messages.success(request, "Password updated successfully.")
    return redirect('college_dashboard')
