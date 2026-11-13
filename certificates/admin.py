from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.utils.safestring import mark_safe
import logging

logger = logging.getLogger(__name__)
from .models import Certificate, CertificateTemplate, DeletedDuplicateLog
import csv
from django.http import HttpResponse
import datetime
import zipfile
from io import BytesIO
from django.http import HttpResponse
import os
from django.shortcuts import render, redirect
import re
import datetime
from django.db.models import Count, Min,Q
from django.contrib import messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse


def get_duplicate_certificate_ids():
    """
    Return a set of Certificate IDs that have duplicates based on the unified 12-field key.
    """
    from .utils import get_certificate_duplicate_key
    groups = {}
    for cert in Certificate.objects.order_by('id'):
        key = get_certificate_duplicate_key(cert)
        if key[1]:  # Only group if roll number is present
            groups.setdefault(key, []).append(cert)

    duplicate_ids = set()
    for key, certs in groups.items():
        if len(certs) > 1:
            for c in certs[1:]:
                duplicate_ids.add(c.id)
    return duplicate_ids


class DuplicateStatusFilter(admin.SimpleListFilter):
    """Filter offer letters by duplicate status."""
    title = 'Duplicate Status'
    parameter_name = 'duplicate_status'

    def lookups(self, request, model_admin):
        return (
            ('duplicate', 'Duplicates (newer copy)'),
            ('original', 'Original (has duplicates/copies)'),
            ('unique', 'Unique (no duplicates)'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset

        from .utils import get_certificate_duplicate_key
        groups = {}
        for cert in Certificate.objects.order_by('id'):
            key = get_certificate_duplicate_key(cert)
            if key[1]:  # Only group if roll number is present
                groups.setdefault(key, []).append(cert)

        dup_ids = set()
        orig_ids = set()
        for key, certs in groups.items():
            if len(certs) > 1:
                orig_ids.add(certs[0].id)
                for c in certs[1:]:
                    dup_ids.add(c.id)

        if value == 'duplicate':
            return queryset.filter(id__in=dup_ids)
        elif value == 'original':
            return queryset.filter(id__in=orig_ids)
        elif value == 'unique':
            all_dup_ids = dup_ids | orig_ids
            return queryset.exclude(id__in=all_dup_ids)

        return queryset



class OfferTemplateFilter(admin.SimpleListFilter):
    """Filter certificates by offer letter template (parsed from offer_type)."""
    title = 'Offer Template'
    parameter_name = 'offer_template'

    def lookups(self, request, model_admin):
        from .utils import get_offer_type_choices
        choices = []
        for group_label, group_choices in get_offer_type_choices():
            for value, label in group_choices:
                display = f'{group_label} - {label}'
                choices.append((value, display))
        return choices

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(offer_type=value)
        return queryset
        
class StipendStatusFilter(admin.SimpleListFilter):
    """Filter offer letters by stipend presence/status."""
    title = 'Stipend Status'
    parameter_name = 'stipend_status'

    def lookups(self, request, model_admin):
        return (
            ('has_stipend', 'Has Stipend'),
            ('no_stipend', 'No Stipend'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'has_stipend':
            return queryset.filter(stipend_amount__isnull=False).exclude(stipend_amount=0)
        elif value == 'no_stipend':
            return queryset.filter(Q(stipend_amount__isnull=True) | Q(stipend_amount=0))
        return queryset


class StipendRangeFilter(admin.SimpleListFilter):
    """Filter offer letters by stipend range."""
    title = 'Stipend Range'
    parameter_name = 'stipend_range'
    template = 'admin/stipend_range_filter.html'

    def lookups(self, request, model_admin):
        return (
            ('0-1000', '₹0 - ₹1000'),
            ('1001-3000', '₹1001 - ₹3000'),
            ('3001-5000', '₹3001 - ₹5000'),
            ('5001-10000', '₹5001 - ₹10000'),
            ('10000+', '₹10000+'),
        )

    def queryset(self, request, queryset):
        # Handle custom min/max values from template form GET params
        min_stipend = request.GET.get('stipend_min')
        max_stipend = request.GET.get('stipend_max')
        
        if min_stipend or max_stipend:
            q_filter = Q()
            if min_stipend:
                try:
                    q_filter &= Q(stipend_amount__gte=float(min_stipend))
                except ValueError:
                    pass
            if max_stipend:
                try:
                    q_filter &= Q(stipend_amount__lte=float(max_stipend))
                except ValueError:
                    pass
            return queryset.filter(q_filter)

        value = self.value()
        if not value:
            return queryset

        if value == '0-1000':
            return queryset.filter(stipend_amount__gte=0, stipend_amount__lte=1000)
        elif value == '1001-3000':
            return queryset.filter(stipend_amount__gte=1001, stipend_amount__lte=3000)
        elif value == '3001-5000':
            return queryset.filter(stipend_amount__gte=3001, stipend_amount__lte=5000)
        elif value == '5001-10000':
            return queryset.filter(stipend_amount__gte=5001, stipend_amount__lte=10000)
        elif value == '10000+':
            return queryset.filter(stipend_amount__gt=10000)

        return queryset

@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """Admin interface for Offer Letter model"""
    
    list_display = [
        'full_name', 
        'course', 
        'college_name', 
        'roll_number',
        'stipend_display',
        'internship_title',
        'internship_duration',
        'issue_date',
        'start_date',
        'end_date',
        'email',
        'candidate_mobile',
        'offer_template',
        'offer_letter_link',
        'certificate_id',
        'is_verified',
        'email_sent',
        'drive_uploaded',
        'duplicate_status_col',
        'created_at',
    ]
    
    list_filter = [
        StipendStatusFilter,
        StipendRangeFilter,
        OfferTemplateFilter,
        DuplicateStatusFilter,
        'is_verified',
        'email_sent',
        'drive_uploaded',
        'created_at',
        'course',
        'college_name',
        'internship_title',
        'internship_duration',
        'start_date',
        'end_date'
    ]
    
    search_fields = [
        'full_name',
        'email',
        'candidate_mobile',
        'roll_number',
        'course',
        'college_name',
        'affiliated_name',
        'internship_title',
        'institution_phone',
        'certificate_id',
        'notes'
    ]
    
    readonly_fields = [
        'certificate_id',
        'verification_url',
        'created_at',
        'updated_at',
        'email_sent_at',
        'drive_uploaded_at',
        'certificate_preview',
        'qr_code_preview',
        'verification_link'
    ]
    
    fieldsets = (
        ('Candidate Information', {
            'fields': ('full_name', 'roll_number', 'email', 'candidate_mobile'),
            'description': 'Basic information about the candidate for the offer letter'
        }),
        ('Institution Details', {
            'fields': ('college_name', 'affiliated_name', 'institution_address', 'institution_phone'),
            'description': 'Institution information and contact details'
        }),
        ('Course Information', {
            'fields': ('course',),
            'description': 'Course name for the offer letter (Optional)'
        }),
        ('Internship Details', {
            'fields': ('internship_title', 'internship_duration', 'stipend_amount'),
            'description': 'Internship position, duration and optional stipend information'
        }),
        ('Internship/Program Period', {
            'fields': ('start_date', 'end_date', 'issue_date'),
            'description': 'Start and end dates for the internship or program, plus issue date for the offer letter'
        }),
        ('Offer Letter Details', {
            'fields': ('is_verified', 'notes'),
            'description': 'Offer letter identification and verification details'
        }),
        ('Document Files', {
            'fields': ('certificate_image', 'certificate_pdf', 'qr_code_image', 'certificate_preview', 'qr_code_preview'),
            'description': 'Generated offer letter documents and QR code'
        }),
        ('Email Delivery Status', {
            'fields': ('email_sent', 'email_sent_at'),
            'description': 'Track email delivery status to candidates'
        }),
        ('Google Drive Storage Status', {
            'fields': ('drive_uploaded', 'drive_file_id', 'drive_uploaded_at'),
            'description': 'Track Google Drive backup status'
        }),
        ('System Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Automatic timestamps for record tracking'
        }),
    )
    
    actions = [
        'remove_duplicates',
        'show_duplicate_info',
        'send_email_certificates',
        
        'regenerate_certificates',
        'regenerate_with_different_template',
        'mark_as_verified',
        'mark_as_not_verified',
        'export_certificates_csv',
        'export_certificates_excel',
        'export_certificates_zip',
    ]
    
    def delete_model(self, request, obj):
        from .soft_delete_utils import soft_delete_record
        username = request.user.username if request.user.is_authenticated else "Admin"
        soft_delete_record(obj, deleted_by=username, reason="Deleted manually via Django Admin detail view", duplicate_reason="Manual Admin action")

    def delete_queryset(self, request, queryset):
        from .soft_delete_utils import soft_delete_record
        username = request.user.username if request.user.is_authenticated else "Admin"
        deleted_count = 0
        for obj in queryset:
            soft_delete_record(obj, deleted_by=username, reason="Bulk deleted via Django Admin action", duplicate_reason="Manual Bulk Admin action")
            deleted_count += 1
        self.message_user(request, f"Successfully soft-deleted {deleted_count} record(s) and saved snapshots.", level=messages.SUCCESS)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/details/',
                self.admin_site.admin_view(self.detail_view),
                name='certificate-detail',
            ),
            path(
                'remove-duplicates-view/',
                self.admin_site.admin_view(self.remove_duplicates_view),
                name='remove-duplicates-view',
            ),
        ]
        return custom_urls + urls

    

    def remove_duplicates_view(self, request):
        """Custom admin view to display duplicate summary and perform cleanup."""
        from .utils import get_certificate_duplicate_key
        # Scan database for duplicates
        groups = {}
        for cert in Certificate.objects.order_by('id'):
            key = get_certificate_duplicate_key(cert)
            if key[1]:  # Only group if roll number is present
                groups.setdefault(key, []).append(cert)
        # Filter to only groups that have duplicates
        duplicate_groups = []
        for key, certs in groups.items():
            if len(certs) > 1:
                original = certs[0]
                duplicates = certs[1:]
                duplicate_groups.append({
                    'original': original,
                    'duplicates': duplicates,
                    'duplicate_ids': ", ".join(str(c.id) for c in duplicates),
                    'candidate_name': original.full_name,
                    'roll_number': original.roll_number,
                    'total_duplicates': len(duplicates),
                    'certs_list': certs
                })
        if request.method == 'POST':
            # Perform deletion
            deleted_count = 0
            username = request.user.username if request.user.is_authenticated else "Anonymous"
            
            for group in duplicate_groups:
                original = group['original']
                for duplicate in group['duplicates']:
                    # Soft-delete the duplicate record using the utility function
                    from .soft_delete_utils import soft_delete_record
                    soft_delete_record(
                        duplicate, 
                        deleted_by=username, 
                        reason="Duplicate Roll Number Cleanup (kept original ID: {})".format(original.certificate_id or original.id),
                        duplicate_reason="Roll Number appeared more than once"
                    )
                    deleted_count += 1
            
            self.message_user(
                request,
                f"Successfully deleted {deleted_count} duplicate offer letter(s). Originals were kept and logs generated.",
                level=messages.SUCCESS
            )
            return redirect('admin:certificates_certificate_changelist')
        context = dict(
            self.admin_site.each_context(request),
            duplicate_groups=duplicate_groups,
            total_cleanup_groups=len(duplicate_groups),
            total_cleanup_duplicates=sum(g['total_duplicates'] for g in duplicate_groups),
            opts=self.model._meta,
            app_label=self.model._meta.app_label,
            title="Remove Duplicate Offer Letters",
        )
        return render(request, 'admin/certificates/certificate/confirm_cleanup.html', context)

    def detail_view(self, request, object_id):
        certificate = self.get_object(request, object_id)
        context = dict(
            self.admin_site.each_context(request),
            certificate=certificate,
        )
        return render(request, 'admin/certificates/certificate/detail_view.html', context)
    def stipend_display(self, obj):
        if obj.stipend_amount is not None and obj.stipend_amount > 0:
            val = float(obj.stipend_amount)
            rounded = round(val)
            if abs(val - rounded) < 0.10:
                val = rounded
            if val == int(val):
                return f"₹{int(val)}"
            return f"₹{val:.2f}"
        return "—"
    stipend_display.short_description = "Stipend Amount (₹)"
    stipend_display.admin_order_field = 'stipend_amount'

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        search_term_clean = search_term.strip()
        if search_term_clean.isdigit() or (search_term_clean.replace('.', '', 1).isdigit() and search_term_clean.count('.') <= 1):
            try:
                stipend_val = float(search_term_clean)
                queryset |= self.model.objects.filter(stipend_amount=stipend_val)
            except ValueError:
                pass
        return queryset, use_distinct

    def duplicate_status_col(self, obj):
        """Highlight duplicate records with a colored badge in the list view."""
        dup_cache = getattr(self, '_dup_cache', None)
        if dup_cache is None:
            from .utils import get_certificate_duplicate_key
            dup_ids = set()
            orig_ids = set()

            groups = {}
            for cert in Certificate.objects.order_by('id'):
                key = get_certificate_duplicate_key(cert)
                if key[1]:  # Only group if roll number is present
                    groups.setdefault(key, []).append(cert)

            for key, certs in groups.items():
                if len(certs) > 1:
                    orig_ids.add(certs[0].id)
                    for c in certs[1:]:
                        dup_ids.add(c.id)

            self._dup_cache = {'dup_ids': dup_ids, 'orig_ids': orig_ids}
            dup_cache = self._dup_cache

        if obj.id in dup_cache['dup_ids']:
            return format_html(
                '<span style="background-color:#ff4d4d; color:#fff; '
                'padding:2px 8px; border-radius:3px; font-size:11px; '
                'font-weight:bold;">DUPLICATE</span>'
            )
        if obj.id in dup_cache['orig_ids']:
            return format_html(
                '<span style="background-color:#ffa500; color:#fff; '
                'padding:2px 8px; border-radius:3px; font-size:11px; '
                'font-weight:bold;">ORIGINAL</span>'
            )
        return format_html(
            '<span style="background-color:#4CAF50; color:#fff; '
            'padding:2px 8px; border-radius:3px; font-size:11px; '
            'font-weight:bold;">UNIQUE</span>'
        )
    duplicate_status_col.short_description = 'Status'
    
    @admin.action(description="✅ Mark as Verified")
    def mark_as_verified(self, request, queryset):
        """
        Bulk action: Mark selected offer letters as verified.
        Uses a single queryset.update() call for efficient bulk DB update.
        Requires 'change' permission on the Certificate model.
        """
        if not request.user.has_perm('certificates.change_certificate'):
            self.message_user(
                request,
                "You do not have permission to verify offer letters.",
                level=messages.ERROR,
            )
            return
        updated = queryset.update(is_verified=True)
        self.message_user(
            request,
            f"Successfully marked {updated} offer letter{'s' if updated != 1 else ''} as verified.",
            level=messages.SUCCESS,
        )
    @admin.action(description="❌ Mark as Not Verified")
    def mark_as_not_verified(self, request, queryset):
        """
        Bulk action: Mark selected offer letters as not verified.
        Uses a single queryset.update() call for efficient bulk DB update.
        Requires 'change' permission on the Certificate model.
        """
        if not request.user.has_perm('certificates.change_certificate'):
            self.message_user(
                request,
                "You do not have permission to unverify offer letters.",
                level=messages.ERROR,
            )
            return
        updated = queryset.update(is_verified=False)
        self.message_user(
            request,
            f"Successfully marked {updated} offer letter{'s' if updated != 1 else ''} as not verified.",
            level=messages.SUCCESS,
        )

    def remove_duplicates(self, request, queryset):
        """
        Bulk action: Delete duplicate offer letters, keeping the oldest record
        in each duplicate group (based on all 12 fields).
        """
        from .utils import get_certificate_duplicate_key
        deleted_count = 0
        kept_count = 0

        # Build groups in Python (handles NULLs correctly)
        source = queryset if queryset.count() > 0 else Certificate.objects
        groups = {}
        for cert in source.order_by('id'):
            key = get_certificate_duplicate_key(cert)
            if key[1]:  # Only group if roll number is present
                groups.setdefault(key, []).append(cert)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

        if not dup_groups:
            self.message_user(request, "No duplicate records found.", level=messages.WARNING)
            return

        username = request.user.username if request.user.is_authenticated else "Anonymous"
        for key, certs in dup_groups.items():
            original = certs[0]
            # Keep the first (oldest), soft-delete the rest
            from .soft_delete_utils import soft_delete_record
            for copy in certs[1:]:
                soft_delete_record(
                    copy, 
                    deleted_by=username, 
                    reason="Bulk Duplicate Roll Number Cleanup (kept original ID: {})".format(original.certificate_id or original.id),
                    duplicate_reason="Roll Number appeared more than once"
                )
                deleted_count += 1
            kept_count += 1

        self.message_user(
            request,
            f"Removed {deleted_count} duplicate(s). Kept {kept_count} original record(s). Logs generated.",
            level=messages.SUCCESS
        )
    remove_duplicates.short_description = "Remove duplicates (keep oldest)"

    def show_duplicate_info(self, request, queryset):
        """
        Bulk action: Display a summary of duplicate groups in the system.
        """
        from .utils import get_certificate_duplicate_key
        groups = {}
        for cert in Certificate.objects.order_by('id'):
            key = get_certificate_duplicate_key(cert)
            if key[1]:  # Only group if roll number is present
                groups.setdefault(key, []).append(cert)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

        if not dup_groups:
            self.message_user(request, "No duplicate records found in the system.", level=messages.INFO)
            return

        total_dup_groups = len(dup_groups)
        total_extra = sum(len(v) - 1 for v in dup_groups.values())

        lines = [f"Found {total_dup_groups} duplicate group(s) with {total_extra} extra record(s):"]
        for i, (key, certs) in enumerate(sorted(dup_groups.items(), key=lambda x: -len(x[1]))[:20], 1):
            name = certs[0].full_name
            roll = certs[0].roll_number
            email = certs[0].email
            internship = certs[0].internship_title or '-'
            start = certs[0].start_date or '-'
            end = certs[0].end_date or '-'
            cnt = len(certs)
            lines.append(
                f"  {i}. {name} | Roll: {roll} | Email: {email} | "
                f"Internship: {internship} | {start} to {end} | Copies: {cnt}"
            )

        if total_dup_groups > 20:
            lines.append(f"  ... and {total_dup_groups - 20} more group(s)")

        self.message_user(request, '\n'.join(lines), level=messages.INFO)
    show_duplicate_info.short_description = "Show duplicate summary"

    

    def offer_template(self, obj):
        """Display offer type as a user-friendly template name in admin list."""
        from .utils import get_template_display_name
        return get_template_display_name(obj.offer_type)
    offer_template.short_description = 'Offer Template'
    
    def offer_letter_link(self, obj):
        """Display a link to the offer letter image."""
        if obj.certificate_image:
            detail_url = f"/admin/certificates/certificate/{obj.pk}/details/"
            return format_html('<a href="{}">View Details</a>', detail_url)
        return "No image available"
    offer_letter_link.short_description = "Offer Letter"

    def certificate_preview(self, obj):
        """Display offer letter image preview"""
        if obj.certificate_image:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 200px; border: 1px solid #ddd; border-radius: 4px;" />',
                obj.certificate_image.url
            )
        return "No offer letter image available"
    certificate_preview.short_description = "Offer Letter Preview"
    
    def qr_code_preview(self, obj):
        """Display QR code preview for verification"""
        if obj.qr_code_image:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 100px; border: 1px solid #ddd; border-radius: 4px;" />',
                obj.qr_code_image.url
            )
        return "No QR code available"
    qr_code_preview.short_description = "Verification QR Code"
    
    def verification_link(self, obj):
        """Display clickable verification link"""
        if obj.verification_url:
            return format_html(
                '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: none;"><i class="fas fa-external-link-alt"></i> Verify Offer Letter</a>',
                obj.verification_url
            )
        return "No verification URL available"
    verification_link.short_description = "Verification Link"
    
    def send_email_certificates(self, request, queryset):
        """Admin action to send offer letters via email"""
        from .utils import send_certificate_email
        
        sent_count = 0
        for certificate in queryset:
            if not certificate.email_sent and certificate.certificate_image:
                try:
                    send_certificate_email(certificate)
                    sent_count += 1
                except Exception as e:
                    self.message_user(request, f"Failed to send email for {certificate.full_name}: {str(e)}", level='ERROR')
        
        if sent_count > 0:
            self.message_user(request, f"Successfully sent {sent_count} offer letter emails.")
    
    send_email_certificates.short_description = "Send offer letter emails"
    
    def upload_to_drive(self, request, queryset):
        """Admin action to upload offer letters to Google Drive"""
        from .utils import upload_to_google_drive
        
        uploaded_count = 0
        for certificate in queryset:
            if not certificate.drive_uploaded and certificate.certificate_image:
                try:
                    upload_to_google_drive(certificate)
                    uploaded_count += 1
                except Exception as e:
                    self.message_user(request, f"Failed to upload to Drive for {certificate.full_name}: {str(e)}", level='ERROR')
        
        if uploaded_count > 0:
            self.message_user(request, f"Successfully uploaded {uploaded_count} offer letters to Google Drive.")
    
    upload_to_drive.short_description = "Upload offer letters to Google Drive"
    
    def regenerate_certificates(self, request, queryset):
        """Admin action to regenerate offer letters"""
        from .utils import generate_offer_letter_image
        from datetime import datetime
        from django.core.files.base import ContentFile
        
        regenerated_count = 0
        for certificate in queryset:
            try:
                # Prepare offer letter data the same way as individual generation
                offer_letter_data = {
                    'candidate_name': certificate.full_name,
                    'roll_number': certificate.roll_number,
                    'course_name': certificate.course,
                    'institution_name': certificate.college_name,
                    'institution_address': getattr(certificate, 'institution_address', '') or '',
                    'candidate_mobile': getattr(certificate, 'candidate_mobile', '') or 'N/A',
                    'candidate_email': certificate.email,
                    'internship_title': getattr(certificate, 'internship_title', '') or certificate.course,
                    'internship_duration': certificate.internship_duration or '2 Months',
                    'issue_date': certificate.issue_date.strftime('%d-%m-%Y') if certificate.issue_date else certificate.created_at.strftime('%d-%m-%Y'),
                    'internship_start_date': certificate.start_date.strftime('%Y-%m-%d') if certificate.start_date else '',
                    'internship_end_date': certificate.end_date.strftime('%Y-%m-%d') if certificate.end_date else '',
                    'certificate_id': certificate.certificate_id,
                    'stipend_amount': certificate.stipend_amount,
                }
                
                # Use the same generate_offer_letter_image function as individual generation
                # offer_type may contain old-style values like 'AICTE-APSCHE OFFER LETTER-Virtual'
                # _resolve_template_image (called inside generate_offer_letter_image) handles
                # all such variations via dynamic directory scanning, so just pass it through.
                template_name = certificate.offer_type or 'original_certificate_aicte-apscheofferletter-virtual.jpg'
                image_buffer = generate_offer_letter_image(offer_letter_data, template_name=template_name)
                image_buffer.seek(0)
                
                # Save the generated image using ROLL NUMBER as filename
              # Build filename: RollNumber_Name_MobileNumber.png (skip missing fields)
                admin_parts = []
                if certificate.roll_number:
                    admin_parts.append(certificate.roll_number.replace(' ', '_'))
                if certificate.full_name:
                    admin_parts.append(certificate.full_name.replace(' ', '_'))
                if certificate.candidate_mobile:
                    admin_parts.append(certificate.candidate_mobile.replace(' ', ''))
                certificate_filename = "_".join(admin_parts) + ".png" if admin_parts else "OfferLetter.png"
                certificate.certificate_image.save(certificate_filename, ContentFile(image_buffer.read()), save=False)
                
                
                # Also regenerate the separate QR code field for admin preview
                try:
                    from .utils import generate_qr_code
                    v_url = certificate.get_verification_url()
                    if v_url:
                        qr_img = generate_qr_code(v_url, size=(300, 300))
                        qr_io = BytesIO()
                        qr_img.save(qr_io, format="PNG")
                        qr_io.seek(0)
                        certificate.qr_code_image.save(f"qr_{certificate_filename}", ContentFile(qr_io.read()), save=False)
                except Exception as qr_e:
                    logger.warning(f"QR field regeneration failed: {qr_e}")

                certificate.save()
                
                regenerated_count += 1
            except Exception as e:
                self.message_user(request, f"Failed to regenerate offer letter for {certificate.full_name}: {str(e)}", level='ERROR')
        
        if regenerated_count > 0:
            self.message_user(request, f"Successfully regenerated {regenerated_count} offer letters.")
    
    regenerate_certificates.short_description = "Regenerate offer letters"

    def regenerate_with_different_template(self, request, queryset):
        """Admin action to regenerate offer letters with a selected template"""
        from django.shortcuts import render
        from django.http import HttpResponseRedirect
        from django.conf import settings
        from django.core.files.base import ContentFile
        from .utils import generate_offer_letter_image, generate_qr_code
        import os
        from io import BytesIO
        
        # If the user has posted the form with a selected template
        if request.POST.get('post') == 'yes':
            selected_template = request.POST.get('selected_template')
            replace_existing = request.POST.get('replace_existing') == 'on'
            
            if not selected_template:
                self.message_user(request, "No template was selected. Action aborted.", level='ERROR')
                return HttpResponseRedirect(request.get_full_path())
                
            success_count = 0
            error_count = 0
            
            for cert in queryset:
                try:
                    # 1. Prepare offer letter data
                    offer_letter_data = {
                        'candidate_name': cert.full_name,
                        'roll_number': cert.roll_number,
                        'course_name': cert.course,
                        'institution_name': cert.college_name,
                        'institution_address': getattr(cert, 'institution_address', '') or '',
                        'candidate_mobile': getattr(cert, 'candidate_mobile', '') or 'N/A',
                        'candidate_email': cert.email,
                        'internship_title': getattr(cert, 'internship_title', '') or cert.course,
                        'internship_duration': cert.internship_duration or '2 Months',
                        'issue_date': cert.issue_date.strftime('%d-%m-%Y') if cert.issue_date else cert.created_at.strftime('%d-%m-%Y'),
                        'internship_start_date': cert.start_date.strftime('%Y-%m-%d') if cert.start_date else '',
                        'internship_end_date': cert.end_date.strftime('%Y-%m-%d') if cert.end_date else '',
                        'certificate_id': cert.certificate_id,
                        'stipend_amount': cert.stipend_amount,
                    }
                    
                    # 2. Generate new QR code
                    v_url = cert.get_verification_url()
                    qr_img = generate_qr_code(v_url, size=(300, 300))
                    qr_io = BytesIO()
                    qr_img.save(qr_io, format="PNG")
                    qr_io.seek(0)
                    
                    # 3. Generate new offer letter image
                    image_buffer = generate_offer_letter_image(offer_letter_data, template_name=selected_template)
                    image_buffer.seek(0)
                    
                    
                    
                    # 5. Build base filename parts
                    base_parts = []
                    if cert.roll_number:
                        base_parts.append(cert.roll_number.replace(' ', '_'))
                    if cert.full_name:
                        base_parts.append(cert.full_name.replace(' ', '_'))
                    if cert.candidate_mobile:
                        base_parts.append(cert.candidate_mobile.replace(' ', ''))
                    base_filename_stem = "_".join(base_parts) if base_parts else "OfferLetter"
                    
                    image_filename = f"{base_filename_stem}.png"
                    
                    qr_filename = f"qr_{base_filename_stem}.png"
                    
                    # 6. Apply versioning if not replacing
                    if not replace_existing:
                        def get_versioned_filename(field, base_filename):
                            storage = field.storage
                            filename_path = field.field.generate_filename(cert, base_filename)
                            if not storage.exists(filename_path):
                                return base_filename
                            name, ext = os.path.splitext(base_filename)
                            version = 2
                            while True:
                                candidate = f"{name}_v{version}{ext}"
                                candidate_path = field.field.generate_filename(cert, candidate)
                                if not storage.exists(candidate_path):
                                    return candidate
                                version += 1
                        
                        image_filename = get_versioned_filename(cert.certificate_image, image_filename)
                        
                        qr_filename = get_versioned_filename(cert.qr_code_image, qr_filename)
                    
                    # Save files
                    cert.certificate_image.save(image_filename, ContentFile(image_buffer.read()), save=False)
                    
                    cert.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=False)
                    
                    # Update fields
                    cert.template_used = selected_template
                    cert.offer_type = selected_template
                    cert.save()
                    
                    success_count += 1
                    logger.info(f"Successfully regenerated offer letter for {cert.full_name} using template {selected_template}")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error regenerating offer letter for {cert.full_name}: {str(e)}", exc_info=True)
                    self.message_user(request, f"Error for {cert.full_name}: {str(e)}", level='ERROR')
            
            if success_count > 0:
                from .utils import get_template_display_name
                friendly_name = get_template_display_name(selected_template)
                self.message_user(request, f"Successfully regenerated {success_count} offer letters using template '{friendly_name}'.")
            if error_count > 0:
                self.message_user(request, f"Failed to regenerate {error_count} offer letters. Check application logs.", level='WARNING')
                
            return HttpResponseRedirect(request.get_full_path())
            
        # Get templates from media/templates/
        templates = []
        templates_dir = os.path.join(settings.MEDIA_ROOT, 'templates')
        if os.path.exists(templates_dir):
            from .utils import get_template_display_name
            for file in sorted(os.listdir(templates_dir)):
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    templates.append({
                        'name': file,
                        'display_name': get_template_display_name(file),
                        'url': f"{settings.MEDIA_URL}templates/{file}"
                    })
                    
        context = {
            'queryset': queryset,
            'templates': templates,
            'opts': self.model._meta,
            'action_checkbox_name': '_selected_action',
        }
        
        return render(request, 'admin/certificates/certificate/regenerate_with_template.html', context)
        
    regenerate_with_different_template.short_description = "Regenerate offer letters with different template"

    def export_certificates_csv(modeladmin, request, queryset):
        """
        Admin bulk action: Export selected offer letters to CSV.
        Columns include Stipend, Certificate Status, Verification Status,
        Generated Date, Template Used, QR Code Status, Verification ID,
        Verification URL (production domain), and Offer Letter URL.
        """
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=offer_letters_{datetime.date.today()}.csv'

        writer = csv.writer(response)
        writer.writerow([
            'Full Name', 'Roll Number', 'Course', 'College Name', 'Affiliated Name',
            'Institution Address', 'Institution Phone', 'Email', 'Candidate Mobile',
            'Internship Title', 'Internship Duration', 'Start Date', 'End Date',
            'Stipend (INR)',
            'Offer Letter ID', 'Verification ID',
            'Verification URL',
            'Offer Letter URL',
            'Certificate Status',
            'Verification Status',
            'QR Code Status',
            'Email Sent', 'Drive Uploaded',
            'Generated Date',
            'Template Used',
            'Notes',
        ])

        for cert in queryset:
            # --- Verification URL (always production domain) ---
            verification_url = cert.get_verification_url() if cert.certificate_id else ''

            # --- Offer Letter URL (absolute URL to admin/frontend detail view) ---
            try:
                relative_url = reverse('certificate_detail_by_pk', kwargs={'pk': cert.pk})
                offer_letter_url = request.build_absolute_uri(relative_url)
            except Exception:
                offer_letter_url = ''

            # --- Certificate Status ---
            if cert.certificate_image or cert.certificate_pdf:
                cert_status = 'Generated'
            else:
                cert_status = 'Not Generated'

            # --- QR Code Status ---
            qr_status = 'Generated' if cert.qr_code_image else 'Not Generated'

            # --- Stipend ---
            if cert.stipend_amount:
                f_val = float(cert.stipend_amount)
                stipend_str = f'\u20b9{int(f_val)}' if f_val == int(f_val) else f'\u20b9{f_val:.2f}'
            else:
                stipend_str = 'No Stipend'

            writer.writerow([
                cert.full_name,
                cert.roll_number,
                cert.course or '',
                cert.college_name,
                cert.affiliated_name or '',
                cert.institution_address or '',
                cert.institution_phone or '',
                cert.email,
                cert.candidate_mobile or '',
                cert.internship_title or '',
                cert.internship_duration or '',
                cert.start_date.strftime('%Y-%m-%d') if cert.start_date else '',
                cert.end_date.strftime('%Y-%m-%d') if cert.end_date else '',
                stipend_str,
                cert.certificate_id or '',
                cert.certificate_id or '',   # Verification ID = same as Offer Letter ID
                verification_url,
                offer_letter_url,
                cert_status,
                'Verified' if cert.is_verified else 'Not Verified',
                qr_status,
                'Yes' if cert.email_sent else 'No',
                'Yes' if cert.drive_uploaded else 'No',
                cert.created_at.strftime('%Y-%m-%d %H:%M:%S') if cert.created_at else '',
                cert.template_used or '',
                cert.notes or '',
            ])

        return response
    export_certificates_csv.short_description = 'Export offer letters to CSV'

    def export_certificates_excel(self, request, queryset):
        """
        Admin bulk action: Export selected offer letters to Excel (.xlsx).
        Includes Stipend, Certificate Status, Verification Status, Generated Date,
        Template Used, QR Code Status, Verification ID, Verification URL
        (always production domain), and a clickable Offer Letter URL hyperlink.
        """
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from openpyxl.utils import get_column_letter
        import datetime

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Offer Letters"

        headers = [
            'Full Name', 'Roll Number', 'Course', 'College Name', 'Affiliated Name',
            'Institution Address', 'Institution Phone', 'Email', 'Candidate Mobile',
            'Internship Title', 'Internship Duration', 'Start Date', 'End Date',
            'Stipend (INR)',
            'Offer Letter ID', 'Verification ID',
            'Verification URL',
            'Offer Letter URL',
            'Certificate Status',
            'Verification Status',
            'QR Code Status',
            'Email Sent', 'Drive Uploaded',
            'Generated Date',
            'Template Used',
            'Notes',
        ]
        ws.append(headers)

        # Column indices (1-based)
        offer_url_col = headers.index('Offer Letter URL') + 1
        verif_url_col = headers.index('Verification URL') + 1

        # ---- Header styling ----
        header_font  = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        header_fill  = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
        header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        for col_num, _ in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font  = header_font
            cell.fill  = header_fill
            cell.alignment = header_align

        # Hyperlink / URL cell style
        link_font = Font(name='Arial', size=10, color='1F4E79', underline='single')
        url_font  = Font(name='Arial', size=10, color='0563C1', underline='single')

        for row_idx, cert in enumerate(queryset, start=2):
            # --- Verification URL (always production domain) ---
            verification_url = cert.get_verification_url() if cert.certificate_id else ''

            # --- Offer Letter URL (absolute URL to detail page) ---
            try:
                rel = reverse('certificate_detail_by_pk', kwargs={'pk': cert.pk})
                offer_letter_url = request.build_absolute_uri(rel)
            except Exception:
                offer_letter_url = ''

            # --- Certificate Status ---
            cert_status = 'Generated' if (cert.certificate_image or cert.certificate_pdf) else 'Not Generated'

            # --- QR Code Status ---
            qr_status = 'Generated' if cert.qr_code_image else 'Not Generated'

            # --- Stipend ---
            if cert.stipend_amount:
                f_val = float(cert.stipend_amount)
                stipend_str = f'\u20b9{int(f_val)}' if f_val == int(f_val) else f'\u20b9{f_val:.2f}'
            else:
                stipend_str = 'No Stipend'

            row_data = [
                cert.full_name,
                cert.roll_number,
                cert.course or '',
                cert.college_name,
                cert.affiliated_name or '',
                cert.institution_address or '',
                cert.institution_phone or '',
                cert.email,
                cert.candidate_mobile or '',
                cert.internship_title or '',
                cert.internship_duration or '',
                cert.start_date.strftime('%Y-%m-%d') if cert.start_date else '',
                cert.end_date.strftime('%Y-%m-%d') if cert.end_date else '',
                stipend_str,
                cert.certificate_id or '',
                cert.certificate_id or '',   # Verification ID
                verification_url,            # Verification URL plain text (hyperlinked below)
                'Open Offer Letter',         # Offer Letter URL display text (hyperlinked below)
                cert_status,
                'Verified' if cert.is_verified else 'Not Verified',
                qr_status,
                'Yes' if cert.email_sent else 'No',
                'Yes' if cert.drive_uploaded else 'No',
                cert.created_at.strftime('%Y-%m-%d %H:%M:%S') if cert.created_at else '',
                cert.template_used or '',
                cert.notes or '',
            ]
            ws.append(row_data)

            # Clickable hyperlink on 'Offer Letter URL' cell
            if offer_letter_url:
                c = ws.cell(row=row_idx, column=offer_url_col)
                c.hyperlink = offer_letter_url
                c.font = link_font

            # Clickable hyperlink on 'Verification URL' cell
            if verification_url:
                c = ws.cell(row=row_idx, column=verif_url_col)
                c.hyperlink = verification_url
                c.font = url_font

        # Auto-fit columns
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 14)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=offer_letters_{datetime.date.today()}.xlsx'
        wb.save(response)
        return response
    export_certificates_excel.short_description = 'Export offer letters to Excel'




    # def export_certificates_zip(self, request, queryset):
    #     """
    #     Export certificate image files as a ZIP for selected certificates (e.g., filtered by college).
    #     """
    #     buffer = BytesIO()
    #     zip_file = zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

    #     for certificate in queryset:
    #         if certificate.certificate_image:
    #             file_path = certificate.certificate_image.path
    #             file_name = os.path.basename(file_path)
    #             zip_file.write(file_path, arcname=file_name)

    #     zip_file.close()
    #     buffer.seek(0)

    #     response = HttpResponse(buffer, content_type='application/zip')
    #     response['Content-Disposition'] = 'attachment; filename=certificates.zip'
    #     return response

    def export_certificates_zip(self, request, queryset):
        """
        Export offer letter image files as a ZIP with the college name in the filename.
        """
        buffer = BytesIO()
        zip_file = zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

        for certificate in queryset:
            if certificate.certificate_image:
                file_path = certificate.certificate_image.path
                file_name = os.path.basename(file_path)
                zip_file.write(file_path, arcname=file_name)

        zip_file.close()
        buffer.seek(0)

        # Default to "offer_letters" if no valid data
        if queryset.exists():
            college_name = queryset.first().college_name or "institution"
        else:
            college_name = "institution"

        # Clean the college name to be safe for filenames
        safe_college_name = re.sub(r'\W+', '_', college_name.strip().lower())

        zip_filename = f"offer_letters_{safe_college_name}.zip"

        response = HttpResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename={zip_filename}'
        return response
    export_certificates_zip.short_description = "Export offer letters as ZIP"



@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    """Admin interface for Offer Letter Template model"""
    
    list_display = [
        'name',
        'is_active',
        'font_size',
        'font_color',
        'created_at'
    ]
    
    list_filter = [
        'is_active',
        'created_at'
    ]
    
    search_fields = [
        'name'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'template_preview'
    ]
    
    fieldsets = (
        ('Template Information', {
            'fields': ('name', 'template_image', 'is_active', 'template_preview')
        }),
        ('Text Positioning', {
            'fields': (
                ('name_x', 'name_y'),
                ('course_x', 'course_y'),
                ('college_x', 'college_y'),
                ('roll_x', 'roll_y'),
                ('cert_id_x', 'cert_id_y'),
                ('date_x', 'date_y'),
                ('qr_x', 'qr_y')
            )
        }),
        ('Font Settings', {
            'fields': ('font_size', 'font_color')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def template_preview(self, obj):
        """Display template image preview"""
        if obj.template_image:
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px;" />',
                obj.template_image.url
            )
        return "No template image"
    template_preview.short_description = "Template Preview"


from .models import Certificate_student, CertificateExcelUpload
import pandas as pd
from django.utils.dateparse import parse_date

@admin.register(Certificate_student)
class CertificateStudentAdmin(admin.ModelAdmin):
    """Admin interface for Student data used in offer letter generation"""
    
    list_display = [
        'full_name', 
        'course', 
        'roll_number',
        'college_name',
        'stipend_display',
        'affiliated_name',
        'internship_title',
        'internship_duration',
        'start_date',
        'end_date', 
        'email',
        'contact',
        'gender',
        'is_deleted',
        'created_at'
    ]
    
    list_filter = [
        'is_deleted',
        StipendStatusFilter,
        StipendRangeFilter,
        'course',
        'college_name',
        'internship_duration',
        'gender',
        'created_at',
        'start_date',
        'end_date'
    ]
    def get_queryset(self, request):
        # Return all objects (including soft-deleted/processed records)
        return self.model.all_objects.get_queryset()
    
    search_fields = [
        'full_name',
        'email',
        'roll_number',
        'course',
        'college_name',
        'affiliated_name',
        'contact'
    ]
    
    fieldsets = (
        ('Candidate Information', {
            'fields': ('full_name', 'roll_number', 'email', 'contact', 'gender')
        }),
        ('Institution & Course Details', {
            'fields': ('course', 'college_name', 'affiliated_name')
        }),
        ('Internship Details', {
            'fields': ('internship_title', 'internship_duration', 'stipend_amount')
        }),
        ('Program Period', {
            'fields': ('start_date', 'end_date')
        }),
        ('System Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']

    def delete_model(self, request, obj):
        from .soft_delete_utils import soft_delete_record
        username = request.user.username if request.user.is_authenticated else "Admin"
        soft_delete_record(obj, deleted_by=username, reason="Deleted manually via Django Admin detail view", duplicate_reason="Manual Admin action")

    def delete_queryset(self, request, queryset):
        from .soft_delete_utils import soft_delete_record
        username = request.user.username if request.user.is_authenticated else "Admin"
        deleted_count = 0
        for obj in queryset:
            soft_delete_record(obj, deleted_by=username, reason="Bulk deleted via Django Admin action", duplicate_reason="Manual Bulk Admin action")
            deleted_count += 1
        self.message_user(request, f"Successfully soft-deleted {deleted_count} staging record(s) and saved snapshots.", level=messages.SUCCESS)

    def stipend_display(self, obj):
        if obj.stipend_amount is not None and obj.stipend_amount > 0:
            val = float(obj.stipend_amount)
            rounded = round(val)
            if abs(val - rounded) < 0.10:
                val = rounded
            if val == int(val):
                return f"₹{int(val)}"
            return f"₹{val:.2f}"
        return "—"
    stipend_display.short_description = "Stipend Amount (₹)"
    stipend_display.admin_order_field = 'stipend_amount'

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        search_term_clean = search_term.strip()
        if search_term_clean.isdigit() or (search_term_clean.replace('.', '', 1).isdigit() and search_term_clean.count('.') <= 1):
            try:
                stipend_val = float(search_term_clean)
                queryset |= self.model.objects.filter(stipend_amount=stipend_val)
            except ValueError:
                pass
        return queryset, use_distinct




@admin.register(CertificateExcelUpload)
class CertificateExcelUploadAdmin(admin.ModelAdmin):
    """Admin interface for Excel file uploads for bulk offer letter generation"""
    
    list_display = ['excel_file', 'uploaded_at', 'file_size_display']
    list_filter = ['uploaded_at']
    readonly_fields = ['uploaded_at']
    actions = ['process_excel_file']

    def file_size_display(self, obj):
        """Display file size in a human-readable format"""
        if obj.excel_file:
            try:
                # Check if file exists before accessing size
                if obj.excel_file.storage.exists(obj.excel_file.name):
                    size = obj.excel_file.size
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if size < 1024.0:
                            return f"{size:.2f} {unit}"
                        size /= 1024.0
                    return f"{size:.2f} TB"
                else:
                    return "File not found"
            except (FileNotFoundError, OSError, AttributeError):
                return "File unavailable"
        return "N/A"
    file_size_display.short_description = "File Size"

    def process_excel_file(self, request, queryset):
        """Process Excel files and import student data for offer letter generation"""
        for upload in queryset:
            try:
                # Check if file exists before processing
                if not upload.excel_file or not upload.excel_file.storage.exists(upload.excel_file.name):
                    self.message_user(
                        request,
                        f"Error: Excel file for upload record (ID: {upload.id}) not found. The file may have been deleted.",
                        level='ERROR'
                    )
                    continue
                
                df = pd.read_excel(upload.excel_file.path)

                imported_count = 0
                for _, row in df.iterrows():
                    # Handle optional dates for parsing
                    def safe_parse_date(val):
                        if pd.isna(val) or str(val).lower() in ['nan', 'none', '']:
                            return None
                        try:
                            return parse_date(str(val))
                        except:
                            return None

                    obj, created = Certificate_student.objects.get_or_create(
                        full_name=row['Name'],
                        course=row['Course'],
                        roll_number=row['Roll No'],
                        college_name=row['College Name'],
                        affiliated_name=row['Affiliated Name'],
                        start_date=safe_parse_date(row.get('Start Date')),
                        end_date=safe_parse_date(row.get('End Date')),
                        email=row['Email'],
                        contact=str(row['Contact']),
                        gender=row['Gender']
                    )
                    if created:
                        imported_count += 1
                
                self.message_user(
                    request, 
                    f"Successfully processed Excel file. {imported_count} new student records imported for offer letter generation."
                )
            except FileNotFoundError:
                self.message_user(
                    request,
                    f"Error: Excel file for upload record (ID: {upload.id}) not found. The file may have been deleted.",
                    level='ERROR'
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Error processing Excel file (ID: {upload.id}): {str(e)}",
                    level='ERROR'
                )
    process_excel_file.short_description = "Process and import student data for offer letters"

from .models import SystemConfiguration

@admin.register(SystemConfiguration)
class SystemConfigurationAdmin(admin.ModelAdmin):
    """
    Admin for globally configuring system settings.
    Prevent adding or deleting more instances to assume singleton behavior.
    """
    list_display = ['__str__', 'email_automation_enabled']
    list_editable = ['email_automation_enabled']

    def has_add_permission(self, request):
        return not SystemConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
        
@admin.register(DeletedDuplicateLog)
class DeletedDuplicateLogAdmin(admin.ModelAdmin):
    change_list_template = 'admin/certificates/deletedduplicatelog/change_list.html'
    
    list_display = [
        'source_record_id',
        'full_name',
        'roll_number',
        'email',
        'candidate_mobile',
        'college_name',
        'internship_title',
        'deleted_certificate_id',
        'deleted_by',
        'deleted_at',
        'deletion_reason',
        'original_certificate_id',
        'restore_status',
        'actions_col',
        'created_date_col'
    ]
    
    list_filter = [
        'is_restored',
        'record_type',
        'deleted_at',
        'deleted_by',
        'offer_template',
        'college_name',
        'internship_title'
    ]
    
    search_fields = [
        'full_name',
        'roll_number',
        'email',
        'original_certificate_id',
        'deleted_certificate_id',
        'deleted_by'
    ]
    
    actions = [
        'bulk_restore_selected',
        'bulk_permanently_delete',
        'export_selected_xlsx'
    ]
    
    fieldsets = (
        ('Overview', {
            'fields': ('record_type', 'source_record_id', 'restore_status', 'deletion_reason', 'duplicate_detection_reason')
        }),
        ('Student Information', {
            'fields': ('student_info_display',),
        }),
        ('Academic & Internship Details', {
            'fields': ('academic_info_display', 'internship_info_display'),
        }),
        ('Document Details & Preview', {
            'fields': ('offer_letter_info_display', 'pdf_preview_display'),
        }),
        ('Audit Log & Restoration Details', {
            'fields': ('system_info_display', 'audit_timeline_display'),
        }),
    )
    
    readonly_fields = [
        'record_type',
        'source_record_id',
        'restore_status',
        'deletion_reason',
        'duplicate_detection_reason',
        'student_info_display',
        'academic_info_display',
        'internship_info_display',
        'offer_letter_info_display',
        'system_info_display',
        'pdf_preview_display',
        'audit_timeline_display',
    ]

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser if request.user else False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser if request.user else False

    def has_add_permission(self, request):
        return False

    def restore_status(self, obj):
        if obj.is_restored:
            return format_html('<span style="background-color:#38a169; color:white; padding:2px 8px; border-radius:3px; font-weight:bold; font-size:11px;">RESTORED</span>')
        return format_html('<span style="background-color:#dd6b20; color:white; padding:2px 8px; border-radius:3px; font-weight:bold; font-size:11px;">PENDING</span>')
    restore_status.short_description = 'Restore Status'

    def created_date_col(self, obj):
        if obj.snapshot and 'fields' in obj.snapshot:
            created_at = obj.snapshot['fields'].get('created_at')
            if created_at:
                return created_at[:10]
        return '-'
    created_date_col.short_description = 'Created Date'

    def actions_col(self, obj):
        if obj.is_restored:
            return format_html('<span style="color:#718096; font-size:11px;">Restored by {}</span>', obj.restored_by or 'Admin')
        restore_url = f"/admin/certificates/deletedduplicatelog/{obj.pk}/restore/"
        return format_html(
            '<a class="button" href="{}" style="background-color:#38a169; color:white; padding:3px 8px; border-radius:4px; text-decoration:none; font-weight:bold; font-size:11px;">Restore</a>',
            restore_url
        )
    actions_col.short_description = 'Actions'

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        from django.utils import timezone
        
        # Calculate dashboard metrics
        total = DeletedDuplicateLog.objects.count()
        today = DeletedDuplicateLog.objects.filter(deleted_at__date=timezone.now().date()).count()
        restored = DeletedDuplicateLog.objects.filter(is_restored=True).count()
        pending = DeletedDuplicateLog.objects.filter(is_restored=False).count()
        
        from django.db.models import Count
        reasons_qs = DeletedDuplicateLog.objects.values('deletion_reason').annotate(c=Count('id')).order_by('-c')[:3]
        common_reasons = ", ".join([f"'{r['deletion_reason']}' ({r['c']})" for r in reasons_qs if r['deletion_reason']])
        
        extra_context['stats'] = {
            'total': total,
            'today': today,
            'restored': restored,
            'pending': pending,
            'common_reasons': common_reasons or "None",
        }
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'restore-dashboard/',
                self.admin_site.admin_view(self.restore_dashboard_view),
                name='restore-dashboard',
            ),
            path(
                '<path:object_id>/restore/',
                self.admin_site.admin_view(self.restore_view),
                name='restore-log-record',
            ),
            path(
                '<path:object_id>/restore-new/',
                self.admin_site.admin_view(self.restore_new_view),
                name='restore-log-record-new',
            ),
        ]
        return custom_urls + urls

    def restore_dashboard_view(self, request):
        from django.utils import timezone
        from .models import DeletedDuplicateLog, Certificate, Certificate_student
        from django.db.models import Q
        
        if not request.user.is_superuser:
            self.message_user(request, "Only Super Admins can access the Restore Dashboard.", level=messages.ERROR)
            return redirect('admin:index')
            
        # Handle POST actions
        if request.method == 'POST':
            action = request.POST.get('action')
            selected_ids = request.POST.getlist('selected_ids')
            if not selected_ids:
                self.message_user(request, "No records selected.", level=messages.WARNING)
            elif action == 'bulk_restore':
                from .soft_delete_utils import restore_record_from_log
                restored_cnt = 0
                error_cnt = 0
                username = request.user.username if request.user.is_authenticated else "Admin"
                for lid in selected_ids:
                    try:
                        log_entry = DeletedDuplicateLog.objects.get(pk=lid)
                        if not log_entry.is_restored:
                            restore_record_from_log(log_entry, restored_by=username, notes="Bulk Restored via Restore Dashboard", mode="full", force=True)
                            restored_cnt += 1
                    except Exception as e:
                        error_cnt += 1
                self.message_user(request, f"Successfully restored {restored_cnt} record(s). Failures: {error_cnt}", level=messages.SUCCESS)
            elif action == 'bulk_delete':
                deleted_cnt = 0
                for lid in selected_ids:
                    try:
                        log_entry = DeletedDuplicateLog.objects.get(pk=lid)
                        log_entry.delete()
                        deleted_cnt += 1
                    except Exception as e:
                        pass
                self.message_user(request, f"Successfully permanently deleted {deleted_cnt} log record(s).", level=messages.SUCCESS)
            return redirect(request.get_full_path())

        # Get query parameters
        search_query = request.GET.get('q', '').strip()
        record_type = request.GET.get('record_type', '').strip()
        restore_status = request.GET.get('status', '').strip()
        
        # Base queryset
        queryset = DeletedDuplicateLog.objects.all()
        
        # Apply filters
        if record_type:
            queryset = queryset.filter(record_type=record_type)
            
        if restore_status == 'restored':
            queryset = queryset.filter(is_restored=True)
        elif restore_status == 'pending':
            queryset = queryset.filter(is_restored=False)
            
        if search_query:
            queryset = queryset.filter(
                Q(full_name__icontains=search_query) |
                Q(roll_number__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(deleted_certificate_id__icontains=search_query) |
                Q(original_certificate_id__icontains=search_query) |
                Q(deleted_by__icontains=search_query)
            )
            
        logs = queryset.order_by('-deleted_at')
        
        # Calculate stats
        stats = {
            'total': DeletedDuplicateLog.objects.count(),
            'restored': DeletedDuplicateLog.objects.filter(is_restored=True).count(),
            'pending': DeletedDuplicateLog.objects.filter(is_restored=False).count(),
            'deleted_today': DeletedDuplicateLog.objects.filter(deleted_at__date=timezone.now().date()).count(),
            'restored_today': DeletedDuplicateLog.objects.filter(restored_at__date=timezone.now().date()).count(),
        }
        
        # Pre-process logs for active conflicts
        logs_with_conflicts = []
        for log in logs:
            has_conflict = False
            conflict_details = []
            
            if not log.is_restored:
                fields = log.snapshot.get('fields', {}) if log.snapshot else {}
                roll = fields.get('roll_number')
                email = fields.get('email')
                cert_id = fields.get('certificate_id')
                
                if log.record_type == 'Certificate':
                    if roll:
                        c_roll = Certificate.objects.filter(roll_number__iexact=roll).first()
                        if c_roll:
                            has_conflict = True
                            conflict_details.append(f"Roll: {roll}")
                    if email:
                        c_email = Certificate.objects.filter(email__iexact=email).first()
                        if c_email:
                            has_conflict = True
                            conflict_details.append(f"Email: {email}")
                    if cert_id:
                        c_id = Certificate.objects.filter(certificate_id=cert_id).first()
                        if c_id:
                            has_conflict = True
                            conflict_details.append(f"ID: {cert_id}")
                else:
                    if roll:
                        c_roll = Certificate_student.objects.filter(roll_number__iexact=roll).first()
                        if c_roll:
                            has_conflict = True
                            conflict_details.append(f"Roll: {roll}")
                    if email:
                        c_email = Certificate_student.objects.filter(email__iexact=email).first()
                        if c_email:
                            has_conflict = True
                            conflict_details.append(f"Email: {email}")
                            
            logs_with_conflicts.append({
                'log': log,
                'has_conflict': has_conflict,
                'conflict_details': ", ".join(conflict_details),
                'fields': log.snapshot.get('fields', {}) if log.snapshot else {}
            })
            
        context = dict(
            self.admin_site.each_context(request),
            stats=stats,
            logs=logs_with_conflicts,
            search_query=search_query,
            record_type=record_type,
            restore_status=restore_status,
            opts=self.model._meta,
            title="Restore Management Dashboard",
        )
        return render(request, 'admin/certificates/deletedduplicatelog/restore_dashboard.html', context)

    def restore_view(self, request, object_id):
        log_entry = get_object_or_404(DeletedDuplicateLog, pk=object_id)
        from .soft_delete_utils import restore_record_from_log
        username = request.user.username if request.user.is_authenticated else "Admin"
        
        from .models import Certificate, Certificate_student
        fields = log_entry.snapshot.get('fields', {}) if log_entry.snapshot else {}
        roll_number = fields.get('roll_number')
        conflict = False
        
        if roll_number:
            if log_entry.record_type == 'Certificate':
                conflict = Certificate.objects.filter(roll_number__iexact=roll_number).exists()
            else:
                conflict = Certificate_student.objects.filter(roll_number__iexact=roll_number).exists()
                
        if conflict and not request.GET.get('force') == 'true':
            context = dict(
                self.admin_site.each_context(request),
                log_entry=log_entry,
                roll_number=roll_number,
                opts=self.model._meta,
                title="Restoration Conflict Detected",
            )
            return render(request, 'admin/certificates/deletedduplicatelog/restore_conflict.html', context)
            
        try:
            restore_record_from_log(log_entry, restored_by=username, notes="Restored via Admin UI", mode="full", force=True)
            self.message_user(request, "Record restored successfully to active status.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Restoration failed: {str(e)}", level=messages.ERROR)
            
        return redirect('admin:certificates_deletedduplicatelog_changelist')

    def restore_new_view(self, request, object_id):
        log_entry = get_object_or_404(DeletedDuplicateLog, pk=object_id)
        from .soft_delete_utils import restore_record_from_log
        username = request.user.username if request.user.is_authenticated else "Admin"
        try:
            restore_record_from_log(log_entry, restored_by=username, notes="Restored as new active record", mode="new_record", force=True)
            self.message_user(request, "Record restored as a new active record successfully.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Restoration failed: {str(e)}", level=messages.ERROR)
            
        return redirect('admin:certificates_deletedduplicatelog_changelist')

    def bulk_restore_selected(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only Super Admins can restore records.", level=messages.ERROR)
            return
            
        from .soft_delete_utils import restore_record_from_log
        restored_count = 0
        error_count = 0
        username = request.user.username if request.user.is_authenticated else "Admin"
        
        for log_entry in queryset.filter(is_restored=False):
            try:
                restore_record_from_log(log_entry, restored_by=username, notes="Bulk Restored", mode="full", force=True)
                restored_count += 1
            except Exception as e:
                error_count += 1
                
        self.message_user(request, f"Successfully restored {restored_count} record(s). Failures: {error_count}", level=messages.SUCCESS)
    bulk_restore_selected.short_description = "Restore selected records (Force)"

    def bulk_permanently_delete(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "Only Super Admins can permanently delete logs.", level=messages.ERROR)
            return
            
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Permanently deleted {count} archived log record(s).", level=messages.SUCCESS)
    bulk_permanently_delete.short_description = "Permanently delete selected logs"

    def export_selected_xlsx(self, request, queryset):
        import pandas as pd
        from django.http import HttpResponse
        
        data = []
        for obj in queryset:
            data.append({
                'Record ID': obj.source_record_id or obj.id,
                'Full Name': obj.full_name,
                'Roll Number': obj.roll_number,
                'Email': obj.email,
                'Mobile': obj.candidate_mobile,
                'College': obj.college_name,
                'Internship': obj.internship_title,
                'Deleted By': obj.deleted_by,
                'Deleted At': obj.deleted_at.strftime('%Y-%m-%d %H:%M') if obj.deleted_at else '',
                'Reason': obj.deletion_reason,
                'Restore Status': 'Restored' if obj.is_restored else 'Pending'
            })
            
        df = pd.DataFrame(data)
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="Deleted_Duplicates_Export.xlsx"'
        
        with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Deleted Logs')
            
        return response
    export_selected_xlsx.short_description = "Export selected logs to Excel"

    def student_info_display(self, obj):
        if not obj.snapshot: return "No snapshot data available."
        fields = obj.snapshot.get('fields', {})
        from .utils import get_template_display_name
        friendly_template = get_template_display_name(fields.get('offer_type', ''))
        html = f"""
        <table style="width:100%; border-collapse:collapse; background:#fdfdfd; border:1px solid #e2e8f0; font-size:13px; border-radius:4px; overflow:hidden;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; width:200px; color:#4a5568; background:#f7fafc;">Full Name:</td><td style="padding:10px; color:#2d3748;">{fields.get('full_name', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Roll Number:</td><td style="padding:10px; color:#2d3748;">{fields.get('roll_number', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Email:</td><td style="padding:10px; color:#2d3748;">{fields.get('email', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Mobile Number:</td><td style="padding:10px; color:#2d3748;">{fields.get('candidate_mobile', fields.get('contact', '-'))}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Gender:</td><td style="padding:10px; color:#2d3748;">{fields.get('gender', '-')}</td></tr>
            <tr><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Date of Birth:</td><td style="padding:10px; color:#2d3748;">{fields.get('dob', '-')}</td></tr>
        </table>
        """
        return mark_safe(html)
    student_info_display.short_description = "Student Information"

    def academic_info_display(self, obj):
        if not obj.snapshot: return "No snapshot data available."
        fields = obj.snapshot.get('fields', {})
        html = f"""
        <table style="width:100%; border-collapse:collapse; background:#fdfdfd; border:1px solid #e2e8f0; font-size:13px; border-radius:4px; overflow:hidden;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; width:200px; color:#4a5568; background:#f7fafc;">College Name:</td><td style="padding:10px; color:#2d3748;">{fields.get('college_name', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Branch/Course:</td><td style="padding:10px; color:#2d3748;">{fields.get('course', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">University:</td><td style="padding:10px; color:#2d3748;">{fields.get('affiliated_name', '-')}</td></tr>
        </table>
        """
        return mark_safe(html)
    academic_info_display.short_description = "Academic Details"

    def internship_info_display(self, obj):
        if not obj.snapshot: return "No snapshot data available."
        fields = obj.snapshot.get('fields', {})
        html = f"""
        <table style="width:100%; border-collapse:collapse; background:#fdfdfd; border:1px solid #e2e8f0; font-size:13px; border-radius:4px; overflow:hidden;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; width:200px; color:#4a5568; background:#f7fafc;">Internship Title:</td><td style="padding:10px; color:#2d3748;">{fields.get('internship_title', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Duration:</td><td style="padding:10px; color:#2d3748;">{fields.get('internship_duration', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Start Date:</td><td style="padding:10px; color:#2d3748;">{fields.get('start_date', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">End Date:</td><td style="padding:10px; color:#2d3748;">{fields.get('end_date', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Issue Date:</td><td style="padding:10px; color:#2d3748;">{fields.get('issue_date', '-')}</td></tr>
        </table>
        """
        return mark_safe(html)
    internship_info_display.short_description = "Internship Details"

    def offer_letter_info_display(self, obj):
        if not obj.snapshot: return "No snapshot data available."
        fields = obj.snapshot.get('fields', {})
        html = f"""
        <table style="width:100%; border-collapse:collapse; background:#fdfdfd; border:1px solid #e2e8f0; font-size:13px; border-radius:4px; overflow:hidden;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; width:200px; color:#4a5568; background:#f7fafc;">Offer Letter / Certificate ID:</td><td style="padding:10px; color:#2d3748;">{fields.get('certificate_id', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Offer Template:</td><td style="padding:10px; color:#2d3748;">{friendly_template}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Email Sent Status:</td><td style="padding:10px; color:#2d3748;">{'Sent' if fields.get('email_sent') else 'Pending'}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Email Sent Date:</td><td style="padding:10px; color:#2d3748;">{fields.get('email_sent_at', '-')}</td></tr>
        </table>
        """
        return mark_safe(html)
    offer_letter_info_display.short_description = "Document Status Summary"

    def system_info_display(self, obj):
        if not obj.snapshot: return "No snapshot data available."
        fields = obj.snapshot.get('fields', {})
        html = f"""
        <table style="width:100%; border-collapse:collapse; background:#fdfdfd; border:1px solid #e2e8f0; font-size:13px; border-radius:4px; overflow:hidden;">
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; width:200px; color:#4a5568; background:#f7fafc;">Created At:</td><td style="padding:10px; color:#2d3748;">{fields.get('created_at', '-')}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Deleted By:</td><td style="padding:10px; color:#2d3748;">{obj.deleted_by or '-'}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Deleted At:</td><td style="padding:10px; color:#2d3748;">{obj.deleted_at.strftime('%Y-%m-%d %H:%M') if obj.deleted_at else '-'}</td></tr>
            <tr style="border-bottom: 1px solid #edf2f7;"><td style="padding:10px; font-weight:bold; color:#4a5568; background:#f7fafc;">Deletion Reason:</td><td style="padding:10px; color:#2d3748;">{obj.deletion_reason or '-'}</td></tr>
        </table>
        """
        return mark_safe(html)
    system_info_display.short_description = "Deletion Metadata Summary"

    def pdf_preview_display(self, obj):
        if not obj.snapshot: return "No snapshot files available."
        fields = obj.snapshot.get('fields', {})
        pdf_field = fields.get('certificate_pdf') or fields.get('certificate_image')
        pdf_url = ""
        
        if pdf_field:
            from django.conf import settings
            pdf_url = settings.MEDIA_URL + pdf_field
            
        if pdf_url:
            html = f"""
            <div style="margin-bottom:15px; display:flex; gap:10px;">
                <a class="button" href="{pdf_url}" target="_blank" style="background-color:#3182ce; color:white; padding:8px 16px; border-radius:5px; text-decoration:none; font-weight:bold; font-size:12px;">Open in New Tab</a>
                <a class="button" href="{pdf_url}" download style="background-color:#4a5568; color:white; padding:8px 16px; border-radius:5px; text-decoration:none; font-weight:bold; font-size:12px;">Download Document</a>
            </div>
            <div style="border:1px solid #e2e8f0; border-radius:6px; overflow:hidden; background:#f7fafc;">
                <iframe src="{pdf_url}" style="width:100%; height:550px; border:none;"></iframe>
            </div>
            """
            return mark_safe(html)
        return "No PDF / Image file is linked in the snapshot or the document was not generated."
    pdf_preview_display.short_description = "Archived Document Preview"

    def audit_timeline_display(self, obj):
        html = f"""
        <div style="font-size:13px; line-height:1.6; font-family:-apple-system, BlinkMacSystemFont, sans-serif; padding:15px; background:#fff; border:1px solid #e2e8f0; border-radius:6px;">
            <div style="margin-bottom:15px; padding-left:15px; border-left:4px solid #e53e3e;">
                <strong style="color:#e53e3e; font-size:14px;">Deleted</strong><br/>
                <span>Timestamp: {obj.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if obj.deleted_at else 'Unknown'}</span><br/>
                <span>Performed By: <strong>{obj.deleted_by or 'System'}</strong></span><br/>
                <span style="color:#718096;">Reason: {obj.deletion_reason or 'No reason specified.'}</span>
            </div>
        """
        if obj.is_restored:
            html += f"""
            <div style="padding-left:15px; border-left:4px solid #38a169; margin-top:15px;">
                <strong style="color:#38a169; font-size:14px;">Restored</strong><br/>
                <span>Timestamp: {obj.restored_at.strftime('%Y-%m-%d %H:%M:%S') if obj.restored_at else ''}</span><br/>
                <span>Performed By: <strong>{obj.restored_by or 'Admin'}</strong></span><br/>
                <span style="color:#718096;">Notes: {obj.restoration_notes or 'Restored successfully.'}</span>
            </div>
            """
        html += "</div>"
        return mark_safe(html)
    audit_timeline_display.short_description = "Timeline Audit History"


from .models import College, CollegeAdminProfile, AuditLog

@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'total_certificates_display', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'aliases', 'address')
    readonly_fields = ('created_at', 'updated_at')

    def total_certificates_display(self, obj):
        return obj.certificates.filter(is_deleted=False).count()
    total_certificates_display.short_description = "Active Offer Letters"


@admin.register(CollegeAdminProfile)
class CollegeAdminProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user_email_display', 'college', 'is_active', 'created_at')
    list_filter = ('is_active', 'college')
    search_fields = ('full_name', 'user__email', 'user__username', 'college__name')
    readonly_fields = ('created_at', 'updated_at')

    def user_email_display(self, obj):
        return obj.user.email or obj.user.username
    user_email_display.short_description = "Email / Username"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'username', 'role', 'college_name', 'action', 'ip_address')
    list_filter = ('action', 'role')
    search_fields = ('username', 'college_name', 'details', 'ip_address')
    readonly_fields = ('user', 'username', 'role', 'college', 'college_name', 'action', 'details', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


