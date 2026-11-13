from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
import uuid
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
import os
from datetime import date
import random
import string

INTERNSHIP_DURATION_CHOICES = [
    ('1 Month', '1 Month'),
    ('2 Months', '2 Months'),
    ('3 Months', '3 Months'),
    ('4 Months', '4 Months'),
    ('5 Months', '5 Months'),
    ('6 Months', '6 Months'),
    ('7 Months', '7 Months'),
    ('8 Months', '8 Months'),
    ('9 Months', '9 Months'),
    ('10 Months', '10 Months'),
    ('11 Months', '11 Months'),
    ('1 Year', '1 Year'),
]
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class College(models.Model):
    """Multi-tenant College / Institution Entity"""
    name = models.CharField(
        max_length=300, 
        unique=True, 
        db_index=True,
        help_text="Official college name"
    )
    code = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True,
        help_text="Short college code or abbreviation"
    )
    aliases = models.TextField(
        blank=True, 
        help_text="Newline-separated department names or raw strings matching this college"
    )
    contact_email = models.EmailField(blank=True, null=True, help_text="College primary contact email")
    contact_phone = models.CharField(max_length=30, blank=True, null=True, help_text="College phone number")
    address = models.CharField(max_length=500, blank=True, null=True, help_text="Campus address")
    is_active = models.BooleanField(default=True, help_text="Whether this college tenant is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "College"
        verbose_name_plural = "Colleges"

    def __str__(self):
        return self.name

    def get_certificates_queryset(self):
        """Return all active offer letters for this college."""
        q = models.Q(college=self)
        if self.aliases:
            for alias in self.aliases.splitlines():
                alias_clean = alias.strip()
                if alias_clean:
                    q |= models.Q(college_name__iexact=alias_clean)
        q |= models.Q(college_name__iexact=self.name)
        return Certificate.objects.filter(q, is_deleted=False)


class Certificate(models.Model):
    """Model to store certificate information"""
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.CharField(max_length=150, blank=True, null=True)
    deletion_reason = models.TextField(blank=True, null=True)
    
    objects = ActiveManager()
    all_objects = models.Manager()
    
    # Unique certificate ID
    # certificate_id = models.UUIDField(
    #     default=uuid.uuid4, 
    #     unique=True, 
    #     editable=False,
    #     help_text="Unique identifier for the certificate"
    # )
    certificate_id = models.CharField(
        max_length=18,
        unique=True,
        blank=True,
        null=True,
        editable=False,
        help_text="Unique identifier for the certificate (not used for offer letters)"
    )
    
    # Student Information
    full_name = models.CharField(
        max_length=200,
        help_text="Full name of the student"
    )

    roll_number = models.CharField(
        max_length=50,
        help_text="Student roll number"
    )

    college_name = models.CharField(
        max_length=300,
        help_text="Name of the college/institution"
    )

    college = models.ForeignKey(
        'College',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates',
        help_text="Associated college entity for multi-tenant RBAC"
    )

    affiliated_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="Name of the Affiliated University"
    )
    
    course = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Course name"
    )
    
    # Institution Details
    institution_address = models.CharField(
        max_length=500,
        blank=True,
        help_text="Complete address of the institution"
    )
    
    institution_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Institution phone number"
    )
    
    # Candidate Contact Information
    email = models.EmailField(
        help_text="Candidate email address"
    )
    
    candidate_mobile = models.CharField(
        max_length=15,
        blank=True,
        help_text="Candidate mobile number"
    )
    
    # Internship Details
    internship_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Internship position title (e.g., Software Development Intern)"
    )
    
    internship_duration = models.CharField(
        max_length=50,
        choices=INTERNSHIP_DURATION_CHOICES,
        blank=True,
        default='2 Months',
        help_text="Duration of the internship"
    )
    
    start_date = models.DateField(null=True, blank=True, default=date.today)
    end_date = models.DateField(null=True, blank=True, default=date.today)
    
    # Issue Date for Offer Letter
    issue_date = models.DateField(
        null=True,
        blank=True,
        help_text="Issue date for the offer letter (overrides default creation date)"
    )
    
    # Certificate Files
    certificate_image = models.ImageField(
        upload_to='certificates/',
        blank=True,
        null=True,
        help_text="Generated certificate image"
    )
    
    certificate_pdf = models.FileField(
        upload_to='certificates/pdf/',
        blank=True,
        null=True,
        help_text="Generated certificate PDF (optional)"
    )
    
    # QR Code
    qr_code_image = models.ImageField(
        upload_to='qr_codes/',
        blank=True,
        null=True,
        help_text="QR code image for verification"
    )
    
    # Verification URL
    verification_url = models.URLField(
        blank=True,
        help_text="URL for certificate verification"
    )
    
    # Status and Timestamps
    is_verified = models.BooleanField(
        default=True,
        help_text="Whether the certificate is verified"
    )
    
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="Certificate creation timestamp"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp"
    )
    
    # Email and Drive Status
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether email has been sent"
    )
    
    email_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Email sent timestamp"
    )
    
    drive_uploaded = models.BooleanField(
        default=False,
        help_text="Whether uploaded to Google Drive"
    )
    
    drive_file_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Google Drive file ID"
    )
    
    drive_uploaded_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Drive upload timestamp"
    )
    
    # Additional metadata
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or comments"
    )
    
    # Offer Letter Type (Virtual / Physical)
    offer_type = models.CharField(
        max_length=60,
        blank=True,
        default='',
        help_text="Offer letter type: Virtual (digital/email) or Physical (printable)"
    )
    # Optional Stipend Amount
    stipend_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Stipend Amount (₹)",
        help_text="Optional stipend amount (leave blank if no stipend)"
    )
    template_used = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Template name or file used for generation"
    )
    
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Offer Letter"
        verbose_name_plural = "Offer Letters"
        constraints = [
            models.UniqueConstraint(
                fields=['roll_number'],
                name='unique_certificate_roll_number',
                condition=models.Q(is_deleted=False) & ~models.Q(roll_number=''),
                violation_error_message='An offer letter with the same roll number already exists.'
            ),
        ]
    
    def __str__(self):
        return f"Offer Letter for {self.full_name} - {self.internship_title or self.course}"
    
    def get_verification_url(self):
        """Generate verification URL for the certificate (only if certificate_id exists)"""
        if not self.certificate_id:
            return ""
        from django.conf import settings
        
        # Priority:
        # 1. BASE_URL setting (if not localhost)
        # 2. SITE_DOMAIN and SITE_PROTOCOL settings (if domain not localhost)
        # 3. Hardcoded production default
        
        base_url = getattr(settings, 'BASE_URL', None)
        if base_url and 'localhost' not in base_url and '127.0.0.1' not in base_url:
            base_url = base_url.rstrip('/')
            return f"{base_url}/verify/{self.certificate_id}/"
        
        domain = getattr(settings, 'SITE_DOMAIN', 'offerletters.cscindia.org.in')
        protocol = getattr(settings, 'SITE_PROTOCOL', 'https')
        
        # If domain is still localhost, use the production default
        if 'localhost' in domain or '127.0.0.1' in domain:
            domain = 'offerletters.cscindia.org.in'
            protocol = 'https'
            
        return f"{protocol}://{domain}/verify/{self.certificate_id}/"
    
    

    def get_certificate_filename(self):
        """Generate filename for certificate image"""
        return f"certificate_{self.certificate_id}.png"
    
    def get_qr_filename(self):
        """Generate filename for QR code image"""
        return f"qr_{self.certificate_id}.png"
    
    # def save(self, *args, **kwargs):
    #     """Override save to set verification URL"""
    #     if not self.verification_url:
    #         self.verification_url = self.get_verification_url()
    #     super().save(*args, **kwargs)

    def clean(self):
        """Validate model data for integrity and consistency"""
        from django.core.exceptions import ValidationError
        
        # Validate that end_date is after start_date
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({
                    'end_date': 'End date must be after or equal to the start date.'
                })

        # Prevent duplicate insertion at the validation layer based on Roll Number
        if self.roll_number:
            potential_matches = Certificate.objects.filter(roll_number__iexact=self.roll_number.strip())
            if self.pk:
                potential_matches = potential_matches.exclude(pk=self.pk)
            if potential_matches.exists():
                raise ValidationError(
                    f"An offer letter with this Roll Number ({self.roll_number}) already exists."
                )
    
    def save(self, *args, **kwargs):
        """Override save - Offer letters do not require certificate_id"""
        
        if self.stipend_amount is not None:
            try:
                f_val = float(self.stipend_amount)
                nearest_int = round(f_val)
                if abs(f_val - nearest_int) < 0.10:
                    self.stipend_amount = Decimal(str(nearest_int))
            except (ValueError, TypeError):
                pass
        # Skip validation if updating from migrations or bulk operations
        skip_validation = kwargs.pop('skip_validation', False)
        if not skip_validation:
            try:
                self.full_clean(exclude=None, validate_unique=False)
            except ValidationError:
                # Validation errors will be handled by admin forms
                pass
        
        # Generate certificate_id if missing (now required for offer letters too)
        if not self.certificate_id:
            self.certificate_id = generate_certificate_id()

        # Auto-associate college if missing
        if not self.college_id and self.college_name:
            try:
                matched_col = College.objects.filter(
                    models.Q(name__iexact=self.college_name.strip()) |
                    models.Q(aliases__icontains=self.college_name.strip())
                ).first()
                if not matched_col:
                    raw_lower = self.college_name.lower()
                    for c in College.objects.filter(is_active=True):
                        if c.name.lower() in raw_lower:
                            matched_col = c
                            break
                if matched_col:
                    self.college = matched_col
            except Exception:
                pass

        if not self.verification_url and self.certificate_id:
            self.verification_url = self.get_verification_url()
        super().save(*args, **kwargs)

def generate_certificate_id():
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"CscIndia-{random_part}"

def generate_custom_certificate_id():
        prefix = "CSCIndia-"
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return prefix + suffix


class CollegeAdminProfile(models.Model):
    """Profile associating a Django User with a single College"""
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='college_profile',
        help_text="Django user account"
    )
    college = models.ForeignKey(
        College, 
        on_delete=models.CASCADE, 
        related_name='administrators',
        help_text="Assigned college institution"
    )
    full_name = models.CharField(max_length=200, help_text="Administrator full name")
    phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    is_active = models.BooleanField(default=True, help_text="Whether this administrator account is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = "College Administrator Profile"
        verbose_name_plural = "College Administrator Profiles"

    def __str__(self):
        return f"{self.full_name} ({self.college.name})"


class AuditLog(models.Model):
    """Audit log tracking administrative actions, logins, downloads, and exports"""
    ACTION_CHOICES = [
        ('LOGIN', 'User Login'),
        ('LOGIN_FAILED', 'Failed Login Attempt'),
        ('LOGOUT', 'User Logout'),
        ('DOWNLOAD_PDF', 'Download Offer Letter PDF'),
        ('BULK_DOWNLOAD_SELECTED', 'Bulk Download Selected (ZIP)'),
        ('BULK_DOWNLOAD_FILTERED', 'Bulk Download Filtered (ZIP)'),
        ('EXPORT_EXCEL', 'Export Excel'),
        ('EXPORT_CSV', 'Export CSV'),
        ('CREATE_COLLEGE_ADMIN', 'Create College Admin'),
        ('UPDATE_COLLEGE_ADMIN', 'Update College Admin'),
        ('ACTIVATE_COLLEGE_ADMIN', 'Activate College Admin'),
        ('DEACTIVATE_COLLEGE_ADMIN', 'Deactivate College Admin'),
        ('PASSWORD_RESET', 'Reset Password'),
        ('PASSWORD_CHANGE', 'Change Password'),
    ]

    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='audit_logs'
    )
    username = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=50, default='Super Admin')
    college = models.ForeignKey(
        College, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='audit_logs'
    )
    college_name = models.CharField(max_length=300, blank=True)
    action = models.CharField(max_length=100, choices=ACTION_CHOICES, db_index=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.action} by {self.username} at {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"

    @classmethod
    def log(cls, request, action, details="", college=None):
        """Helper method to easily record audit log entries"""
        try:
            user = getattr(request, 'user', None)
            user_obj = user if user and user.is_authenticated else None
            username = user.username if user_obj else 'Anonymous'
            
            # Determine role and college
            role = 'Super Admin'
            col = college
            if user_obj:
                if hasattr(user_obj, 'college_profile'):
                    role = 'College Admin'
                    col = col or user_obj.college_profile.college
                elif user_obj.is_superuser:
                    role = 'Super Admin'
                elif user_obj.is_staff:
                    role = 'Super Admin'
                else:
                    role = 'User'

            ip = cls.get_client_ip(request)

            return cls.objects.create(
                user=user_obj,
                username=username,
                role=role,
                college=col,
                college_name=col.name if col else '',
                action=action,
                details=details,
                ip_address=ip
            )
        except Exception:
            pass

    @staticmethod
    def get_client_ip(request):
        if not request:
            return None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CertificateTemplate(models.Model):
    """Model to store certificate template configurations"""
    
    name = models.CharField(
        max_length=100,
        help_text="Template name"
    )
    
    template_image = models.ImageField(
        upload_to='templates/',
        help_text="Template image file"
    )
    
    # Text positioning coordinates
    name_x = models.IntegerField(default=400, help_text="X coordinate for name")
    name_y = models.IntegerField(default=300, help_text="Y coordinate for name")
    
    course_x = models.IntegerField(default=400, help_text="X coordinate for course")
    course_y = models.IntegerField(default=350, help_text="Y coordinate for course")
    
    college_x = models.IntegerField(default=400, help_text="X coordinate for college")
    college_y = models.IntegerField(default=400, help_text="Y coordinate for college")
    
    roll_x = models.IntegerField(default=200, help_text="X coordinate for roll number")
    roll_y = models.IntegerField(default=500, help_text="Y coordinate for roll number")
    
    cert_id_x = models.IntegerField(default=100, help_text="X coordinate for certificate ID")
    cert_id_y = models.IntegerField(default=515, help_text="Y coordinate for certificate ID")
    
    date_x = models.IntegerField(default=100, help_text="X coordinate for date")
    date_y = models.IntegerField(default=541, help_text="Y coordinate for date")
    
    qr_x = models.IntegerField(default=360, help_text="X coordinate for QR code")
    qr_y = models.IntegerField(default=465, help_text="Y coordinate for QR code")
    
    # Font settings
    font_size = models.IntegerField(default=24, help_text="Font size for text")
    font_color = models.CharField(
        max_length=7, 
        default="#000000", 
        help_text="Font color in hex format"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this template is active"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Offer Letter Template"
        verbose_name_plural = "Offer Letter Templates"
    
    def __str__(self):
        return f"Template: {self.name}"


from django.db import models
from datetime import date
class Certificate_student(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.CharField(max_length=150, blank=True, null=True)
    deletion_reason = models.TextField(blank=True, null=True)
    
    objects = ActiveManager()
    all_objects = models.Manager()

    full_name = models.CharField(max_length=100)
    course = models.CharField(max_length=100, blank=True, null=True)
    roll_number = models.CharField(max_length=50)
    college_name = models.CharField(max_length=200)
    affiliated_name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    issue_date = models.DateField(
        null=True,
        blank=True,
        help_text="Issue date for the offer letter (from bulk upload form)"
    )
    email = models.EmailField()
    contact = models.CharField(max_length=20)
    gender = models.CharField(max_length=10)
    internship_title = models.CharField(max_length=200, blank=True, null=True)
    internship_duration = models.CharField(max_length=50, choices=INTERNSHIP_DURATION_CHOICES, blank=True, null=True, default='2 Months')
    institution_address = models.CharField(max_length=500, blank=True, null=True)
    stipend_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name="Stipend Amount (₹)",
        help_text="Optional stipend amount (leave blank if no stipend)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['roll_number'],
                name='unique_student_roll_number',
                condition=models.Q(is_deleted=False) & ~models.Q(roll_number=''),
                violation_error_message='A student with the same roll number already exists.'
            )
        ]

    def __str__(self):
        return self.full_name
    def save(self, *args, **kwargs):
        # Ensure stipend_amount is rounded to nearest integer if within 0.10
        if self.stipend_amount is not None:
            try:
                f_val = float(self.stipend_amount)
                nearest_int = round(f_val)
                if abs(f_val - nearest_int) < 0.10:
                    self.stipend_amount = Decimal(str(nearest_int))
            except (ValueError, TypeError):
                pass
        super().save(*args, **kwargs)



class CertificateExcelUpload(models.Model):
    excel_file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    issue_date = models.DateField(
        null=True,
        blank=True,
        help_text="Issue date for all offer letters in this upload (overrides default creation date)"
    )


class SystemConfiguration(models.Model):
    """
    Singleton model to store global system settings.
    """
    email_automation_enabled = models.BooleanField(
        default=True, 
        help_text="If disabled, the system will not send any automated emails (Offer Letters, Certificates, etc.)"
    )


    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SystemConfiguration.objects.exists():
            # If you try to save a new instance, set the PK to the existing one to overwrite it
            self.pk = SystemConfiguration.objects.first().pk
        super(SystemConfiguration, self).save(*args, **kwargs)

    def __str__(self):
        return "System Configuration"

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class DeletedDuplicateLog(models.Model):
    """Model to log deleted duplicate offer letters for audit tracking"""
    original_certificate_id = models.CharField(max_length=50, help_text="ID of the kept original certificate")
    deleted_certificate_id = models.CharField(max_length=50, help_text="ID of the deleted duplicate certificate")
    full_name = models.CharField(max_length=200)
    roll_number = models.CharField(max_length=50)
    course = models.CharField(max_length=200, blank=True, null=True)
    college_name = models.CharField(max_length=300)
    internship_title = models.CharField(max_length=200, blank=True)
    internship_duration = models.CharField(max_length=50, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    email = models.EmailField()
    candidate_mobile = models.CharField(max_length=15, blank=True)
    offer_template = models.CharField(max_length=100, blank=True)
    deleted_at = models.DateTimeField(auto_now_add=True)
    deleted_by = models.CharField(max_length=150, blank=True, null=True, help_text="User who performed the deletion")
    snapshot = models.JSONField(blank=True, null=True)
    is_restored = models.BooleanField(default=False)
    restored_at = models.DateTimeField(blank=True, null=True)
    restored_by = models.CharField(max_length=150, blank=True, null=True)
    restoration_notes = models.TextField(blank=True, null=True)
    deletion_reason = models.TextField(blank=True, null=True)
    record_type = models.CharField(
        max_length=50, 
        choices=[('Certificate', 'Offer Letter / Certificate'), ('Certificate_student', 'Student Staging')], 
        default='Certificate'
    )
    source_record_id = models.IntegerField(blank=True, null=True)
    duplicate_detection_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = "Deleted Duplicate Log"
        verbose_name_plural = "Deleted Duplicate Logs"

    def __str__(self):
        return f"Deleted Duplicate of {self.full_name} - Roll: {self.roll_number}"

