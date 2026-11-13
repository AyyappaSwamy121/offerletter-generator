from django import forms
from django.core.validators import RegexValidator
from .models import Certificate
from datetime import date


def get_template_choices():
    """Dynamic template choices from media/templates (original_certificate_* files)."""
    from .utils import get_available_certificate_templates
    choices = get_available_certificate_templates()
    return choices if choices else [('', 'No templates found')]


def get_offer_type_choices():
    """Offer type choices grouped by Virtual/Physical for optgroup dropdown."""
    from .utils import get_offer_type_choices as _get_choices
    return _get_choices()


class CertificateForm(forms.Form):
    """Form for certificate generation"""
    
    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name',
            'required': True
        }),
        help_text='Enter your full name as it should appear on the certificate'
    )
    
    course = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter course name (optional)',
        }),
        required=False,
        help_text='Enter the course name (optional)'
    )
    
    college_name = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter college/institution name',
            'required': True
        }),
        help_text='Enter the name of your college or institution'
    )
    affiliated_name= forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter Affiliated University name',
            'required': True
        }),
        help_text='Enter the name of your Affiliated University'
    )
    
    roll_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your roll number',
            'required': True
        }),
        help_text='Enter your student roll number'
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'required': True
        }),
        help_text='Enter your email address to receive the certificate'
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',  # enables date picker in HTML5 browsers
            'required': True
        }),
        help_text='Select the start date of the course'
    )

    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'required': True
        }),
        help_text='Select the end date of the course'
    )
    
    template = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        help_text='Select the certificate template',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['template'].choices = get_template_choices()
        if self.fields['template'].choices and self.fields['template'].choices[0][0]:
            self.fields['template'].initial = self.fields['template'].choices[0][0]

    def clean_full_name(self):
        """Validate full name"""
        full_name = self.cleaned_data.get('full_name')
        if not full_name:
            raise forms.ValidationError('Full name is required')
        
        # Check for minimum length
        if len(full_name.strip()) < 2:
            raise forms.ValidationError('Full name must be at least 2 characters long')
        
        # Check for valid characters (letters, spaces, hyphens, apostrophes)
        if not all(c.isalpha() or c.isspace() or c in "'-." for c in full_name):
            raise forms.ValidationError('Full name can only contain letters, spaces, hyphens, apostrophes, and periods')
        
        return full_name.strip().title()
    
    def clean_course(self):
        """Validate course name"""
        course = self.cleaned_data.get('course')
        if not course:
            return ""
        
        if len(course.strip()) < 2:
            raise forms.ValidationError('Course name must be at least 2 characters long')
        
        return course.strip()
    
    def clean_college_name(self):
        """Validate college name"""
        college_name = self.cleaned_data.get('college_name')
        if not college_name:
            raise forms.ValidationError('College name is required')
        
        if len(college_name.strip()) < 2:
            raise forms.ValidationError('College name must be at least 2 characters long')
        
        return college_name.strip()
    
    def clean_roll_number(self):
        """Validate roll number"""
        roll_number = self.cleaned_data.get('roll_number')
        if not roll_number:
            raise forms.ValidationError('Roll number is required')
        
        roll_number = roll_number.strip().upper()
        
        # Check for minimum length
        if len(roll_number) < 3:
            raise forms.ValidationError('Roll number must be at least 3 characters long')
        
        return roll_number
    
    def clean_email(self):
        """Validate email and check for duplicates"""
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError('Email address is required')
        
        email = email.lower().strip()
        
        # Check if certificate already exists for this email and course combination
        # (Optional: You might want to allow multiple certificates per email)
        
        return email


class CertificateSearchForm(forms.Form):
    """Form for searching certificates"""
    
    search_query = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, email, roll number, or certificate ID',
        }),
        help_text='Enter search terms to find certificates'
    )
    
    course_filter = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by course name',
        }),
        help_text='Filter certificates by course name'
    )
    
    college_filter = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by college name',
        }),
        help_text='Filter certificates by college name'
    )


class ContactForm(forms.Form):
    """Contact form for support"""
    
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your name',
            'required': True
        })
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your email address',
            'required': True
        })
    )
    
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Subject (e.g., Offer Letter Generation Issue, Technical Support)',
            'required': True
        })
    )
    
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Please describe your issue or question in detail...',
            'rows': 5,
            'required': True
        })
    )

from django import forms
from .models import CertificateExcelUpload

class CertificateExcelForm(forms.ModelForm):
    issue_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': 'Select issue date'
        }),
        help_text='Select issue date for all offer letters in this upload (optional)'
    )
    common_stipend_amount = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 5000 (leave blank if no stipend)',
            'step': '0.01',
        }),
        help_text='Common stipend amount applied to all candidates in this upload (optional). Leave blank if no stipend.'
    )
    
    
    class Meta:
        model = CertificateExcelUpload
        fields = ['excel_file', 'issue_date']
        widgets = {
            'excel_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class OfferLetterForm(forms.Form):
    """Form for internship offer letter generation"""
    
    offer_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'class': 'form-control',
            'required': True,
        }),
        required=True,
        label='Select Offer Letter Type',
        help_text='Select the offer letter type (Virtual for digital/email, Physical for printable)'
    )
    
    candidate_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter candidate full name',
            'required': True
        }),
        help_text='Enter the candidate\'s full name as it should appear on the offer letter'
    )
    
    roll_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter roll number',
            'required': True
        }),
        help_text='Enter the candidate\'s roll number'
    )
    
    course_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter course name (optional)',
        }),
        required=False,
        label='Course Name (optional)',
        help_text='Enter the candidate\'s course name (optional)'
    )
    
    institution_name = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter institution name',
            'required': True
        }),
        help_text='Enter the name of the institution'
    )
    
    institution_address = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Enter institution address (optional)',
            'rows': 3,
            'required': False
        }),
        required=False,
        help_text='Enter the complete institution address (optional)'
    )
    
    institution_phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter institution phone number',
        }),
        required=False,
        help_text='Enter the institution phone number'
    )

    issue_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'required': True
        }),
        initial=date.today,
        help_text='Select the issue date that should appear on the offer letter'
    )
    
    candidate_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter candidate email address',
            'required': True
        }),
        help_text='Enter the candidate\'s email address to receive the offer letter'
    )
    
    candidate_mobile = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter candidate mobile number (optional)',
        }),
        required=False,
        label='Candidate Mobile Number (optional)',
        help_text='Enter the candidate\'s mobile number (optional)'
    )
    
    internship_title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter internship title (e.g., Software Development Intern)',
            'required': True
        }),
        help_text='Enter the internship position title'
    )
    
    internship_duration = forms.ChoiceField(
        choices=[],  # populated from model in __init__
        widget=forms.Select(attrs={
            'class': 'form-control',
            'required': True
        }),
        help_text='Select the internship duration',
        initial='2 Months'
    )
    
    template = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False,
        help_text='Select the offer letter template',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['offer_type'].choices = get_offer_type_choices()
        if self.fields['offer_type'].choices:
            first_group = self.fields['offer_type'].choices[0]
            if isinstance(first_group, tuple) and len(first_group) == 2 and isinstance(first_group[1], list):
                self.fields['offer_type'].initial = first_group[1][0][0]
        self.fields['template'].choices = get_template_choices()
        if self.fields['template'].choices and self.fields['template'].choices[0][0]:
            self.fields['template'].initial = self.fields['template'].choices[0][0]
        from .models import INTERNSHIP_DURATION_CHOICES
        self.fields['internship_duration'].choices = INTERNSHIP_DURATION_CHOICES

    internship_start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        required=False,
        help_text='Select the internship start date (optional)'
    )

    internship_end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        required=False,
        help_text='Select the internship end date (optional)'
    )
    
    stipend = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 5000 (leave blank if no stipend)',
            'step': '0.01',
            'id': 'id_stipend',
        }),
        label='Stipend Amount (Optional)',
        help_text='Enter stipend amount per month (optional). Leave blank if no stipend is offered.'
    )
    
    def clean_candidate_name(self):
        """Validate candidate name"""
        candidate_name = self.cleaned_data.get('candidate_name')
        if not candidate_name:
            raise forms.ValidationError('Candidate name is required')
        
        if len(candidate_name.strip()) < 2:
            raise forms.ValidationError('Candidate name must be at least 2 characters long')
        
        if not all(c.isalpha() or c.isspace() or c in "'-." for c in candidate_name):
            raise forms.ValidationError('Candidate name can only contain letters, spaces, hyphens, apostrophes, and periods')
        
        return candidate_name.strip().title()
    
    def clean_roll_number(self):
        """Validate roll number"""
        roll_number = self.cleaned_data.get('roll_number')
        if not roll_number:
            raise forms.ValidationError('Roll number is required')
        
        roll_number = roll_number.strip().upper()
        
        if len(roll_number) < 3:
            raise forms.ValidationError('Roll number must be at least 3 characters long')
        
        return roll_number
    
    def clean_course_name(self):
        """Validate course name"""
        course_name = self.cleaned_data.get('course_name')
        if not course_name:
            return "" # Optional field
        
        if len(course_name.strip()) < 2:
            raise forms.ValidationError('Course name must be at least 2 characters long')
        
        return course_name.strip()
    
    def clean_institution_name(self):
        """Validate institution name"""
        institution_name = self.cleaned_data.get('institution_name')
        if not institution_name:
            raise forms.ValidationError('Institution name is required')
        
        if len(institution_name.strip()) < 2:
            raise forms.ValidationError('Institution name must be at least 2 characters long')
        
        return institution_name.strip()
    
    def clean_institution_address(self):
        """Validate institution address"""
        institution_address = self.cleaned_data.get('institution_address')
        if not institution_address:
            return ''
        
        if len(institution_address.strip()) < 5:
            raise forms.ValidationError('Institution address must be at least 5 characters long')
        
        return institution_address.strip()
    
    def clean_institution_phone(self):
        """Validate institution phone"""
        institution_phone = self.cleaned_data.get('institution_phone')
        if not institution_phone:
            return ''
        
        # Basic phone validation
        if len(institution_phone.strip()) < 10:
            raise forms.ValidationError('Please enter a valid phone number')
        
        return institution_phone.strip()
    
    def clean_candidate_email(self):
        """Validate candidate email"""
        email = self.cleaned_data.get('candidate_email')
        if not email:
            raise forms.ValidationError('Email address is required')
        
        return email.lower().strip()
    
    def clean_candidate_mobile(self):
        """Validate candidate mobile (optional)"""
        mobile = self.cleaned_data.get('candidate_mobile')
        if not mobile:
            return "" # Optional field
        
        # Basic mobile validation
        mobile_stripped = mobile.strip()
        if mobile_stripped and len(mobile_stripped) < 10:
            raise forms.ValidationError('Please enter a valid mobile number')
        
        return mobile_stripped
    
    def clean_internship_title(self):
        """Validate internship title"""
        internship_title = self.cleaned_data.get('internship_title')
        if not internship_title:
            raise forms.ValidationError('Internship title is required')
        
        if len(internship_title.strip()) < 2:
            raise forms.ValidationError('Internship title must be at least 2 characters long')
        
        return internship_title.strip()
    
    def clean_internship_duration(self):
        """Validate internship duration"""
        duration = self.cleaned_data.get('internship_duration')
        if not duration:
            raise forms.ValidationError('Internship duration is required')
        
        # ChoiceField already validates against choices, just return the value
        return duration


class CertificateTemplateUploadForm(forms.Form):
    """Form for uploading a new certificate template from the frontend UI"""

    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter template name (e.g., CSC India Offer Letter)',
            'required': True
        }),
        help_text='A unique name for this template'
    )

    template_image = forms.ImageField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/png,image/jpeg,image/jpg',
        }),
        help_text='Upload a template image (PNG or JPG, recommended: high-resolution offer letter background)',
        required=True
    )

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise forms.ValidationError('Template name is required')
        name = name.strip()
        if len(name) < 2:
            raise forms.ValidationError('Template name must be at least 2 characters long')
        # Check for duplicate names
        from .models import CertificateTemplate
        if CertificateTemplate.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(f'A template with the name "{name}" already exists. Please choose a different name.')
        return name

    def clean_template_image(self):
        image = self.cleaned_data.get('template_image')
        if not image:
            raise forms.ValidationError('Template image is required')
        # Validate file size (max 10MB)
        if image.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Image file size must be under 10MB')
        # Validate file extension
        import os
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png']:
            raise forms.ValidationError('Only JPG and PNG image files are allowed')
        return image
