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


def _get_filtered_college_queryset(request, college):
    """
    Helper function to filter the college's offer letters securely.
    Ensures that ONLY records belonging to this college can ever be returned.
    """
    qs = Certificate.objects.filter(college=college, is_deleted=False).order_by('-created_at')

    # Search query
    search_query = request.GET.get('search', '').strip()
    if search_query:
        qs = qs.filter(
            Q(full_name__icontains=search_query) |
            Q(roll_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(certificate_id__icontains=search_query) |
            Q(course__icontains=search_query) |
            Q(internship_title__icontains=search_query)
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
    Strictly isolated: displays only the authenticated administrator's college data.
    """
    profile = request.user.college_profile
    college = profile.college

    # Base query for stats (all active certificates of this college)
    base_qs = Certificate.objects.filter(college=college, is_deleted=False)
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
    filtered_qs = _get_filtered_college_queryset(request, college)
    filtered_count = filtered_qs.count()

    # Pagination: 25 items per page
    paginator = Paginator(filtered_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'profile': profile,
        'college': college,
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
        'page_title': f"{college.name} - Offer Letter Dashboard",
    }
    return render(request, 'certificates/college_dashboard.html', context)


@college_admin_required
def college_offer_letter_detail_api(request, pk):
    """
    JSON endpoint for viewing details of a specific offer letter.
    Server-side enforced: returns 404 if the record does not belong to the user's college.
    """
    college = request.user.college_profile.college
    cert = get_object_or_404(Certificate, pk=pk, college=college, is_deleted=False)

    data = {
        'id': cert.id,
        'full_name': cert.full_name,
        'roll_number': cert.roll_number,
        'email': cert.email,
        'candidate_mobile': cert.candidate_mobile or 'N/A',
        'college_name': cert.college_name,
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
    Enforces strict ownership: college administrator can only download their own college's documents.
    """
    college = request.user.college_profile.college
    cert = get_object_or_404(Certificate, pk=pk, college=college, is_deleted=False)

    pdf_bytes = None
    # 1. Try reading existing PDF file from disk
    if cert.certificate_pdf and hasattr(cert.certificate_pdf, 'path'):
        try:
            with open(cert.certificate_pdf.path, 'rb') as f:
                pdf_bytes = f.read()
        except Exception:
            pdf_bytes = None

    # 2. If missing on disk, generate PDF dynamically
    if not pdf_bytes:
        try:
            offer_letter_data = {
                'candidate_name': cert.full_name,
                'roll_number': cert.roll_number,
                'course_name': cert.course or cert.internship_title,
                'institution_name': cert.college_name,
                'institution_address': cert.institution_address or getattr(college, 'address', ''),
                'candidate_mobile': cert.candidate_mobile,
                'candidate_email': cert.email,
                'internship_title': cert.internship_title or cert.course,
                'internship_duration': cert.internship_duration,
                'issue_date': cert.issue_date.strftime('%Y-%m-%d') if cert.issue_date else cert.created_at.strftime('%Y-%m-%d'),
            }
            buf = generate_offer_letter_pdf(offer_letter_data)
            if buf:
                pdf_bytes = buf.getvalue()
        except Exception as e:
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
    Enforces strict ownership: filters out any IDs that do not belong to the user's college.
    """
    college = request.user.college_profile.college
    selected_ids = request.POST.getlist('selected_ids')

    if not selected_ids:
        messages.error(request, "No offer letters were selected for download.")
        return redirect('college_dashboard')

    # Security: Query only records that match selected_ids AND belong to THIS college
    certs = Certificate.objects.filter(
        pk__in=selected_ids,
        college=college,
        is_deleted=False
    )

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
                    offer_letter_data = {
                        'candidate_name': cert.full_name,
                        'roll_number': cert.roll_number,
                        'course_name': cert.course or cert.internship_title,
                        'institution_name': cert.college_name,
                        'institution_address': cert.institution_address or getattr(college, 'address', ''),
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

    AuditLog.log(
        request,
        'BULK_DOWNLOAD_SELECTED',
        f"Downloaded selected ZIP with {added_files} offer letters",
        college=college
    )

    clean_college = college.code or college.name.replace(' ', '_')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Selected_Offer_Letters_{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_download_filtered_zip(request):
    """
    Download a ZIP archive containing all offer letter PDFs matching the currently applied filters.
    Strictly constrained to the user's assigned college.
    """
    college = request.user.college_profile.college
    certs = _get_filtered_college_queryset(request, college)
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
                    offer_letter_data = {
                        'candidate_name': cert.full_name,
                        'roll_number': cert.roll_number,
                        'course_name': cert.course or cert.internship_title,
                        'institution_name': cert.college_name,
                        'institution_address': cert.institution_address or getattr(college, 'address', ''),
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

    AuditLog.log(
        request,
        'BULK_DOWNLOAD_FILTERED',
        f"Downloaded filtered ZIP archive containing {added_files} offer letters",
        college=college
    )

    clean_college = college.code or college.name.replace(' ', '_')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Filtered_Offer_Letters_{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_export_excel(request):
    """
    Export all offer letters matching the currently applied filters to an Excel (.xlsx) spreadsheet.
    Strictly isolated to the administrator's college.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    college = request.user.college_profile.college
    certs = _get_filtered_college_queryset(request, college)

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
        row = [
            idx,
            cert.full_name,
            cert.roll_number,
            cert.email,
            cert.candidate_mobile or '',
            college.name or cert.college_name or '',
            cert.course or '',
            cert.internship_title or '',
            cert.internship_duration or '',
            cert.start_date.strftime('%d-%m-%Y') if cert.start_date else '',
            cert.end_date.strftime('%d-%m-%Y') if cert.end_date else '',
            cert.issue_date.strftime('%d-%m-%Y') if cert.issue_date else (cert.created_at.strftime('%d-%m-%Y') if cert.created_at else ''),
            float(cert.stipend_amount) if cert.stipend_amount is not None else 0.0,
            cert.certificate_id or '',
            "Yes" if cert.email_sent else "No",
            cert.get_verification_url() if cert.certificate_id else '',
        ]
        ws.append(row)
        for col_num in range(1, len(headers) + 1):
            c = ws.cell(row=idx + 1, column=col_num)
            c.border = border_thin
            if col_num in [1, 3, 10, 11, 12, 13, 15]:
                c.alignment = align_center
            else:
                c.alignment = align_left

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    AuditLog.log(
        request,
        'EXPORT_EXCEL',
        f"Exported {certs.count()} offer letters to Excel",
        college=college
    )

    clean_college = college.code or college.name.replace(' ', '_')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Offer_Letters_{timestamp}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@college_admin_required
def college_export_csv(request):
    """
    Export all offer letters matching the currently applied filters to a CSV file.
    Strictly isolated to the administrator's college.
    """
    college = request.user.college_profile.college
    certs = _get_filtered_college_queryset(request, college)

    clean_college = college.code or college.name.replace(' ', '_')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{clean_college}_Offer_Letters_{timestamp}.csv"

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    # Write UTF-8 BOM so Excel opens special characters cleanly
    response.write('\ufeff'.encode('utf8'))

    writer = csv.writer(response)
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
        writer.writerow([
            idx,
            cert.full_name,
            cert.roll_number,
            cert.email,
            cert.candidate_mobile or '',
            college.name or cert.college_name or '',
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

    AuditLog.log(
        request,
        'EXPORT_CSV',
        f"Exported {certs.count()} offer letters to CSV",
        college=college
    )

    return response


@college_admin_required
def college_change_password(request):
    """
    Allow a College Administrator to update their account password.
    """
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect('college_dashboard')

        if not new_password or len(new_password) < 6:
            messages.error(request, "New password must be at least 6 characters long.")
            return redirect('college_dashboard')

        if new_password != confirm_password:
            messages.error(request, "New password confirmation does not match.")
            return redirect('college_dashboard')

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        AuditLog.log(
            request,
            'PASSWORD_CHANGE',
            f"College Admin '{request.user.college_profile.full_name}' changed their password",
            college=request.user.college_profile.college
        )

        messages.success(request, "Password updated successfully.")
        return redirect('college_dashboard')

    return redirect('college_dashboard')
