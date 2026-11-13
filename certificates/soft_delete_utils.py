import json
from django.core import serializers
from django.utils import timezone
from .models import DeletedDuplicateLog

def serialize_record(record):
    """
    Serializes a Django model instance into a JSON-compatible dict.
    """
    data = serializers.serialize("json", [record])
    struct = json.loads(data)[0]
    return struct

def soft_delete_record(record, deleted_by, reason, duplicate_reason=""):
    """
    Soft-deletes a Certificate or Certificate_student record by setting is_deleted=True
    and archives its data snapshot to DeletedDuplicateLog.
    """
    from .models import Certificate, Certificate_student
    snapshot_dict = serialize_record(record)
    
    # Determine the record type and clean attributes
    if isinstance(record, Certificate):
        record_type = 'Certificate'
        original_certificate_id = ""
        # Try to find another active certificate with the same roll number
        original = Certificate.objects.filter(roll_number__iexact=record.roll_number).first()
        if original:
            original_certificate_id = original.certificate_id or str(original.id)
            
        log = DeletedDuplicateLog.objects.create(
            original_certificate_id=original_certificate_id,
            deleted_certificate_id=record.certificate_id or str(record.id),
            full_name=record.full_name,
            roll_number=record.roll_number,
            course=record.course or '',
            college_name=record.college_name,
            internship_title=record.internship_title or '',
            internship_duration=record.internship_duration or '',
            issue_date=record.issue_date,
            start_date=record.start_date,
            end_date=record.end_date,
            email=record.email,
            candidate_mobile=record.candidate_mobile or '',
            offer_template=record.offer_type or '',
            deleted_by=deleted_by,
            snapshot=snapshot_dict,
            deletion_reason=reason,
            record_type=record_type,
            source_record_id=record.id,
            duplicate_detection_reason=duplicate_reason
        )
    else:
        record_type = 'Certificate_student'
        original_certificate_id = ""
        original_student = Certificate_student.objects.filter(roll_number__iexact=record.roll_number).first()
        if original_student:
            original_certificate_id = str(original_student.id)
            
        log = DeletedDuplicateLog.objects.create(
            original_certificate_id=original_certificate_id,
            deleted_certificate_id=str(record.id),
            full_name=record.full_name,
            roll_number=record.roll_number,
            course=record.course or '',
            college_name=record.college_name,
            internship_title=record.internship_title or '',
            internship_duration=record.internship_duration or '',
            issue_date=record.issue_date,
            start_date=record.start_date,
            end_date=record.end_date,
            email=record.email,
            candidate_mobile=record.contact or '',
            offer_template='',
            deleted_by=deleted_by,
            snapshot=snapshot_dict,
            deletion_reason=reason,
            record_type=record_type,
            source_record_id=record.id,
            duplicate_detection_reason=duplicate_reason
        )
        
    # Mark record as deleted
    record.is_deleted = True
    record.deleted_at = timezone.now()
    record.deleted_by = deleted_by
    record.deletion_reason = reason
    # Save the record bypassing validations to prevent unique constraint triggers
    if hasattr(record, 'save'):
        try:
            record.save(skip_validation=True)
        except TypeError:
            # Fallback if skip_validation is not supported
            record.save()
    else:
        record.save()
        
    return log

def restore_record_from_log(log_entry, restored_by, notes="", mode="full", force=False):
    """
    Restores a soft-deleted record from its DeletedDuplicateLog entry.
    Modes:
      - 'full': restores the original record to active state
      - 'new_record': restores as a completely new record (new ID/PK)
    """
    from .models import Certificate, Certificate_student
    
    snapshot = log_entry.snapshot
    if not snapshot:
        raise ValueError("No snapshot found in this log entry.")
        
    fields = snapshot.get('fields', {})
    model_name = log_entry.record_type
    roll_number = fields.get('roll_number')
    email = fields.get('email')
    certificate_id = fields.get('certificate_id')
    
    # Check if active record with this roll number, email, or certificate ID already exists
    if not force:
        conflicts = []
        if model_name == 'Certificate':
            if roll_number:
                roll_conflicts = Certificate.objects.filter(roll_number__iexact=roll_number)
                if roll_conflicts.exists():
                    conflicts.append(f"Roll Number '{roll_number}' (ID: {roll_conflicts.first().id})")
            if email:
                email_conflicts = Certificate.objects.filter(email__iexact=email)
                if email_conflicts.exists():
                    conflicts.append(f"Email '{email}' (ID: {email_conflicts.first().id})")
            if certificate_id:
                id_conflicts = Certificate.objects.filter(certificate_id=certificate_id)
                if id_conflicts.exists():
                    conflicts.append(f"Certificate ID '{certificate_id}' (ID: {id_conflicts.first().id})")
        else:
            if roll_number:
                roll_conflicts = Certificate_student.objects.filter(roll_number__iexact=roll_number)
                if roll_conflicts.exists():
                    conflicts.append(f"Roll Number '{roll_number}' (ID: {roll_conflicts.first().id})")
            if email:
                email_conflicts = Certificate_student.objects.filter(email__iexact=email)
                if email_conflicts.exists():
                    conflicts.append(f"Email '{email}' (ID: {email_conflicts.first().id})")
                    
        if conflicts:
            raise ValueError(f"Conflict: Active record(s) already exist with: {', '.join(conflicts)}")
            
    if model_name == 'Certificate':
        if mode == 'new_record':
            restored_record = Certificate()
        else:
            try:
                restored_record = Certificate.all_objects.get(id=log_entry.source_record_id)
            except Certificate.DoesNotExist:
                restored_record = Certificate()
                
        # Populate fields
        from django.db.models import DateField, DateTimeField
        from django.utils.dateparse import parse_date, parse_datetime
        for field, value in fields.items():
            if field not in ['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason', 'id']:
                try:
                    model_field = restored_record._meta.get_field(field)
                    if isinstance(model_field, DateTimeField) and isinstance(value, str):
                        value = parse_datetime(value)
                    elif isinstance(model_field, DateField) and isinstance(value, str):
                        value = parse_date(value)
                except Exception:
                    pass
                setattr(restored_record, field, value)
                
        restored_record.is_deleted = False
        restored_record.deleted_at = None
        restored_record.deleted_by = None
        restored_record.deletion_reason = None
        
        # Ensure certificate_id is present
        from .models import generate_certificate_id
        if not restored_record.certificate_id:
            restored_record.certificate_id = generate_certificate_id()
            
        # PDF/Image regeneration if missing
        from django.core.files.base import ContentFile
        from io import BytesIO
        from .utils import (
            generate_offer_letter_image, 
            generate_offer_letter_pdf, 
            generate_qr_code
        )
        import datetime
        
        # Reconstruct date strings/objects for generation
        def format_date(d):
            if not d:
                return ''
            if isinstance(d, (datetime.date, datetime.datetime)):
                return d.strftime('%Y-%m-%d')
            return str(d)
            
        issue_date_str = format_date(restored_record.issue_date)
        if not issue_date_str:
            issue_date_str = format_date(restored_record.created_at or datetime.datetime.now())
            
        offer_letter_data = {
            'candidate_name': restored_record.full_name,
            'roll_number': restored_record.roll_number,
            'course_name': restored_record.course,
            'institution_name': restored_record.college_name,
            'institution_address': restored_record.institution_address or '',
            'candidate_mobile': restored_record.candidate_mobile or 'N/A',
            'candidate_email': restored_record.email,
            'internship_title': restored_record.internship_title or restored_record.course or '',
            'internship_duration': restored_record.internship_duration or '2 Months',
            'issue_date': issue_date_str,
            'internship_start_date': format_date(restored_record.start_date),
            'internship_end_date': format_date(restored_record.end_date),
            'certificate_id': restored_record.certificate_id,
        }
        
        # Regenerate missing certificate image
        image_missing = not restored_record.certificate_image or not restored_record.certificate_image.storage.exists(restored_record.certificate_image.name)
        if image_missing:
            template_name = restored_record.offer_type or 'aicte-apsche offer letter-virtual'
            image_buffer = generate_offer_letter_image(offer_letter_data, template_name=template_name)
            image_buffer.seek(0)
            parts = []
            if restored_record.roll_number:
                parts.append(restored_record.roll_number.replace(' ', '_'))
            if restored_record.full_name:
                parts.append(restored_record.full_name.replace(' ', '_'))
            if restored_record.candidate_mobile:
                parts.append(restored_record.candidate_mobile.replace(' ', ''))
            filename = "_".join(parts) + ".png" if parts else "OfferLetter.png"
            restored_record.certificate_image.save(filename, ContentFile(image_buffer.read()), save=False)
            
        # Regenerate missing QR code
        qr_missing = not restored_record.qr_code_image or not restored_record.qr_code_image.storage.exists(restored_record.qr_code_image.name)
        if qr_missing:
            v_url = restored_record.get_verification_url()
            if v_url:
                qr_img = generate_qr_code(v_url, size=(300, 300))
                qr_io = BytesIO()
                qr_img.save(qr_io, format="PNG")
                qr_io.seek(0)
                qr_filename = f"qr_{restored_record.certificate_id}.png"
                restored_record.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=False)
                
        # Regenerate missing PDF
        pdf_missing = not restored_record.certificate_pdf or not restored_record.certificate_pdf.storage.exists(restored_record.certificate_pdf.name)
        if pdf_missing:
            pdf_buffer = generate_offer_letter_pdf(offer_letter_data)
            pdf_filename = f"Offer_Letter_{restored_record.full_name.replace(' ', '_')}.pdf"
            restored_record.certificate_pdf.save(pdf_filename, ContentFile(pdf_buffer.read()), save=False)
            
        restored_record.save(skip_validation=True)
        
    else: # Certificate_student
        if mode == 'new_record':
            restored_record = Certificate_student()
        else:
            try:
                restored_record = Certificate_student.all_objects.get(id=log_entry.source_record_id)
            except Certificate_student.DoesNotExist:
                restored_record = Certificate_student()
                
        from django.db.models import DateField, DateTimeField
        from django.utils.dateparse import parse_date, parse_datetime
        for field, value in fields.items():
            if field not in ['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason', 'id']:
                try:
                    model_field = restored_record._meta.get_field(field)
                    if isinstance(model_field, DateTimeField) and isinstance(value, str):
                        value = parse_datetime(value)
                    elif isinstance(model_field, DateField) and isinstance(value, str):
                        value = parse_date(value)
                except Exception:
                    pass
                setattr(restored_record, field, value)
                
        restored_record.is_deleted = False
        restored_record.deleted_at = None
        restored_record.deleted_by = None
        restored_record.deletion_reason = None
        restored_record.save()
        
    # Update log entry status
    log_entry.is_restored = True
    log_entry.restored_at = timezone.now()
    log_entry.restored_by = restored_by
    log_entry.restoration_notes = f"{notes} (Mode: {mode})"
    log_entry.save()
    
    return restored_record
