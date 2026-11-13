"""
Certificate generation utilities using PIL (Pillow)
"""

import os
import uuid
import qrcode
import openpyxl
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.utils import timezone
from io import BytesIO
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)


def get_default_font(size=24):
    """Get default font for certificate text"""
    try:
        # Try to use a system font
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/System/Library/Fonts/Arial.ttf',  # macOS
            'C:/Windows/Fonts/arial.ttf',  # Windows
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        
        # Fallback to default font
        return ImageFont.load_default()
    except Exception as e:
        logger.warning(f"Could not load font: {e}")
        return ImageFont.load_default()


def generate_qr_code(data, size=(100, 100)):
    """Generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.resize(size, Image.Resampling.LANCZOS)
    return qr_img


def get_text_size(text, font):
    """Get text size using PIL"""
    # Create a temporary image to measure text
    temp_img = Image.new('RGB', (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def get_available_certificate_templates():
    """
    Scans media/templates for files like original_certificate_*.jpg
    Also includes templates uploaded via the CertificateTemplate model.
    Returns a list of (value, label) tuples.
    DB templates are prefixed with 'db:' to distinguish from file-based ones.
    """
    template_dir = os.path.join(settings.MEDIA_ROOT, 'templates')
    choices = []
    
    # Static choices often used in the system (6 offer letter types)
    base_choices = [
        ('original_certificate_aicte-apscheofferletter-virtual.jpg', 'AICTE-APSCHE OFFER LETTER - Virtual'),
        ('original_certificate_onlyaicteofferletter-virtual.jpg', 'Only AICTE OFFER LETTER - Virtual'),
        ('original_certificate_onlyapscheofferletter-virtual.jpg', 'Only APSCHE OFFER LETTER - Virtual'),
        ('original_certificate_aicte-apscheofferletter-physical.jpg', 'AICTE-APSCHE OFFER LETTER - Physical'),
        ('original_certificate_onlyaicteofferletter-physical.jpg', 'Only AICTE OFFER LETTER - Physical'),
        ('original_certificate_onlyapscheofferletter-physical.jpg', 'Only APSCHE OFFER LETTER - Physical'),
    ]
    
    for val, label in base_choices:
        choices.append((val, label))
        
    if os.path.exists(template_dir):
        for filename in os.listdir(template_dir):
            if filename.startswith('original_certificate_') and filename.endswith('.jpg'):
                # Extract template name from filename
                name = filename.replace('original_certificate_', '').replace('.jpg', '')
                
                # Skip templates already covered by explicit base_choices above
                name_lower = name.lower()
                if (name_lower == 'offerletter' or
                    'aicte' in name_lower or
                    'apsche' in name_lower):
                    continue
                    
                choices.append((name, name.replace('_', ' ').title()))
    
    # Add templates from the database (CertificateTemplate model)
    try:
        from .models import CertificateTemplate
        db_templates = CertificateTemplate.objects.filter(is_active=True).order_by('-created_at')
        for tmpl in db_templates:
            choices.append((f'db:{tmpl.id}', f'{tmpl.name} (Custom)'))
    except Exception as e:
        logger.warning(f"Could not load database templates: {e}")
                    
    return choices


def get_offer_type_choices():
    """
    Return offer type choices grouped by Virtual/Physical for optgroup dropdown.
    Format: [(group_label, [(value, label), ...]), ...]
    """
    return [
        ('Virtual', [
            ('original_certificate_aicte-apscheofferletter-virtual.jpg', 'AICTE-APSCHE OFFER LETTER'),
            ('original_certificate_onlyaicteofferletter-virtual.jpg', 'Only AICTE OFFER LETTER'),
            ('original_certificate_onlyapscheofferletter-virtual.jpg', 'Only APSCHE OFFER LETTER'),
        ]),
        ('Physical', [
            ('original_certificate_aicte-apscheofferletter-physical.jpg', 'AICTE-APSCHE OFFER LETTER'),
            ('original_certificate_onlyaicteofferletter-physical.jpg', 'Only AICTE OFFER LETTER'),
            ('original_certificate_onlyapscheofferletter-physical.jpg', 'Only APSCHE OFFER LETTER'),
        ]),
    ]


def is_virtual_offer_type(offer_type):
    """Check if the offer type is Virtual (digital, email-based)."""
    if not offer_type:
        return True
    return offer_type.lower().endswith('-virtual')


def is_physical_offer_type(offer_type):
    """Check if the offer type is Physical (printable, address-based)."""
    if not offer_type:
        return False
    return offer_type.lower().endswith('-physical')

def wrap_text(text, font, max_width):
    """
    Helper to wrap text into multiple lines given a max width.
    """
    if not text:
        return []
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # Use font.getlength for accurate width measurement
        if font.getlength(test_line) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            
    if current_line:
        lines.append(' '.join(current_line))
        
    return lines


# DEPRECATED: This function has been replaced by the newer version below
# def save_offer_letter_to_database(data):
#     """
#     Creates or updates a Certificate object from offer letter data.
#     Then generates the image and returns the object.
#     """
#     from .models import Certificate
#     from datetime import datetime
# 
#     # Map the data to model fields
#     certificate, created = Certificate.objects.get_or_create(
#         roll_number=data.get('roll_number'),
#         defaults={
#             'full_name': data.get('candidate_name'),
#             'email': data.get('candidate_email'),
#             'candidate_mobile': data.get('candidate_mobile'),
#             'college_name': data.get('institution_name'),
#             'institution_address': data.get('institution_address'),
#             'course': data.get('course_name'),
#             'internship_title': data.get('internship_title'),
#             'internship_duration': data.get('internship_duration', ''),
#         }
#     )
# 
#     if not created:
#         # Update existing record
#         certificate.full_name = data.get('candidate_name')
#         certificate.email = data.get('candidate_email')
#         certificate.candidate_mobile = data.get('candidate_mobile')
#         certificate.college_name = data.get('institution_name')
#         certificate.institution_address = data.get('institution_address')
#         certificate.course = data.get('course_name')
#         certificate.internship_title = data.get('internship_title')
#         certificate.internship_duration = data.get('internship_duration', '')
# 
#     # Dates
#     if data.get('internship_start_date'):
#         try:
#             certificate.start_date = datetime.strptime(data['internship_start_date'], '%d-%m-%Y').date()
#         except (ValueError, TypeError):
#             pass
#             
#     if data.get('internship_end_date'):
#         try:
#             certificate.end_date = datetime.strptime(data['internship_end_date'], '%d-%m-%Y').date()
#         except (ValueError, TypeError):
#             pass
#             
#     if data.get('issue_date'):
#         try:
#             certificate.issue_date = datetime.strptime(data['issue_date'], '%d-%m-%Y').date()
#         except (ValueError, TypeError):
#             pass
# 
#     certificate.save()
# 
#     # Generate the image
#     generate_certificate_image(certificate, template_name='OfferLetter')
#     
#     return certificate


# def draw_centered_text(draw, text, x, y, font, fill="black"):
#     """Draw text centered at given coordinates"""
#     text_width, text_height = get_text_size(text, font)
#     draw.text((x - text_width // 2, y - text_height // 2), text, font=font, fill=fill)


# def generate_certificate(certificate_obj):
#     """
#     Generate certificate image with overlaid text and QR code
#     """
#     try:
#         # Load template image
#         template_path = settings.CERTIFICATE_TEMPLATE_PATH
#         if not os.path.exists(template_path):
#             raise FileNotFoundError(f"Certificate template not found: {template_path}")
        
#         # Open template image
#         template = Image.open(template_path)
#         template = template.convert("RGB")  # Ensure RGB mode
        
#         # Create drawing context
#         draw = ImageDraw.Draw(template)
        
#         # Define fonts
#         name_font = get_default_font(36)  # Larger font for name
#         regular_font = get_default_font(20)  # Regular font for other text
#         small_font = get_default_font(16)   # Small font for cert ID and date
        
#         # Get template dimensions
#         width, height = template.size
        
#         # Define text positions based on template analysis
#         # These coordinates are estimated based on the template layout
#         positions = {
#             'name': (width // 2, 320),          # Center, below "CERTIFICATE OF COMPLETION"
#             'course': (width // 2, 380),        # Center, below name
#             'college': (width // 2, 420),       # Center, below course
#             'roll_number': (width // 2, 460),   # Center, below college
#             'cert_id': (135, 515),              # Bottom left, where "Certificate No." is
#             'issue_date': (135, 541),           # Bottom left, where "Issue Date" is
#             'qr_code': (400, 505),              # Center bottom, where QR code should be
#         }
        
#         # Draw student name (prominent)
#         draw_centered_text(
#             draw, 
#             certificate_obj.full_name.upper(), 
#             positions['name'][0], 
#             positions['name'][1], 
#             name_font, 
#             fill="black"
#         )
        
#         # Draw course name
#         course_text = f"has successfully completed the course in {certificate_obj.course}"
#         draw_centered_text(
#             draw, 
#             course_text, 
#             positions['course'][0], 
#             positions['course'][1], 
#             regular_font, 
#             fill="black"
#         )
        
#         # Draw college name
#         college_text = f"from {certificate_obj.college_name}"
#         draw_centered_text(
#             draw, 
#             college_text, 
#             positions['college'][0], 
#             positions['college'][1], 
#             regular_font, 
#             fill="black"
#         )
        
#         # Draw roll number
#         roll_text = f"Roll Number: {certificate_obj.roll_number}"
#         draw_centered_text(
#             draw, 
#             roll_text, 
#             positions['roll_number'][0], 
#             positions['roll_number'][1], 
#             regular_font, 
#             fill="black"
#         )
        
#         # Draw certificate ID (replace existing text)
#         cert_id_text = f"A6A7A3C579Bb66"  # This will be replaced with actual cert ID
#         draw.text(
#             (positions['cert_id'][0] + 100, positions['cert_id'][1]), 
#             str(certificate_obj.certificate_id)[:16], 
#             font=small_font, 
#             fill="black"
#         )
        
#         # Draw issue date (replace existing text)
#         issue_date = certificate_obj.created_at.strftime("%d %B %Y")
#         draw.text(
#             (positions['issue_date'][0] + 80, positions['issue_date'][1]), 
#             issue_date, 
#             font=small_font, 
#             fill="black"
#         )
        
#         # Generate and add QR code
#         verification_url = certificate_obj.get_verification_url()
#         qr_img = generate_qr_code(verification_url, size=(80, 80))
        
#         # Paste QR code onto certificate (replace existing QR code)
#         qr_position = (positions['qr_code'][0] - 40, positions['qr_code'][1] - 40)
#         template.paste(qr_img, qr_position)
        
#         # Save certificate image
#         certificate_filename = certificate_obj.get_certificate_filename()
#         certificate_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, certificate_filename)
        
#         # Ensure output directory exists
#         os.makedirs(settings.CERTIFICATE_OUTPUT_PATH, exist_ok=True)
        
#         # Save the image
#         template.save(certificate_path, "PNG", quality=95)
        
#         # Save to model
#         with open(certificate_path, 'rb') as f:
#             certificate_obj.certificate_image.save(
#                 certificate_filename,
#                 ContentFile(f.read()),
#                 save=False
#             )
        
#         # Generate and save QR code separately
#         qr_filename = certificate_obj.get_qr_filename()
#         qr_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, qr_filename)
#         qr_img.save(qr_path, "PNG")
        
#         with open(qr_path, 'rb') as f:
#             certificate_obj.qr_code_image.save(
#                 qr_filename,
#                 ContentFile(f.read()),
#                 save=False
#             )
        
#         # Save the certificate object
#         certificate_obj.save()
        
#         logger.info(f"Certificate generated successfully for {certificate_obj.full_name}")
#         return certificate_path
        
#     except Exception as e:
#         logger.error(f"Error generating certificate: {str(e)}")
#         raise
from PIL import Image, ImageDraw
import os
from django.core.files.base import ContentFile
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
import os
from django.core.files.base import ContentFile
from django.conf import settings

def get_default_font(size):
    """
    Returns a default PIL font with fallback to system or PIL default font.
    You can configure FONT_PATH in settings if needed.
    """
    try:
        font_path = getattr(settings, "CERTIFICATE_FONT_PATH", None)
        if font_path and os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        else:
            return ImageFont.load_default()
    except:
        return ImageFont.load_default()
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os

# Mock settings and utility functions for demonstration
class MockSettings:
    CERTIFICATE_TEMPLATE_PATH = '/home/ubuntu/upload/original_certificate.jpg'
    CERTIFICATE_OUTPUT_PATH = './output_certificates'

settings = MockSettings()

def get_default_font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except IOError:
        return ImageFont.load_default()

def draw_text_with_wrap(draw, text, x, y, font, max_width, fill):
    words = text.split(" ")
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        if font.getlength(test_line) <= max_width:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    lines.append(" ".join(current_line))

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.getbbox(line)[3] - font.getbbox(line)[1] + 5 # Line spacing

def generate_qr_code(data, size):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize(size, Image.LANCZOS)  # Ensure sharp resizing

class MockCertificateObj:
    def __init__(self):
        self.full_name = "John Doe"
        self.college_name = "University of Example"
        self.affiliated_name = "Example Affiliation"
        self.roll_number = "123456789"
        self.course = "Internship Program in Data Science"
        self.start_date = "01/01/2024"
        self.end_date = "31/03/2024"
        self.certificate_id = "A6A7A3C579Bb66"
        self.created_at = "2024-04-15"

    def get_verification_url(self):
        return "https://example.com/verify/" + self.certificate_id

    
    
    def get_certificate_filename(self):
        return f"{self.full_name.replace(' ', '_')}.png"


    def get_qr_filename(self):
        return f"qr_{self.full_name.replace(' ', '_')}.png"

from PIL import Image, ImageDraw, ImageFont
import os
from django.core.files.base import ContentFile
from django.conf import settings


# def get_default_font(size):
#     """
#     Returns a default PIL font with fallback to system or PIL default font.
#     You can configure CERTIFICATE_FONT_PATH in settings if needed.
#     """
#     try:
#         font_path = getattr(settings, "CERTIFICATE_FONT_PATH", None)
#         if font_path and os.path.exists(font_path):
#             return ImageFont.truetype(font_path, size)
#         else:
#             return ImageFont.load_default()
#     except:
#         return ImageFont.load_default()

from PIL import ImageFont
import os
from django.conf import settings

def get_default_font(size, bold=True):
    """
    Returns a PIL ImageFont object using the custom font from settings or falls back to default.
    Ensures minimum font size for visibility.
    """
    try:
        # Ensure minimum font size for visibility (reduced to allow professional 10pt-12pt)
        min_size = max(size, 12) 
        
        if bold:
            font_path = getattr(settings, "CERTIFICATE_FONT_PATH", None)
        else:
            font_path = getattr(settings, "CERTIFICATE_REGULAR_FONT_PATH", None)
            
        if font_path and os.path.exists(font_path):
            print(f"Font loaded from: {font_path} at size {min_size}")
            return ImageFont.truetype(str(font_path), min_size)  # ✅ Ensure it's a string
        
        else:
            # Try system fonts for better visibility (Windows, macOS, Linux)
            system_fonts = [
                'C:/Windows/Fonts/arial.ttf',  # Windows Arial
                'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
                'C:/Windows/Fonts/times.ttf',  # Windows Times
                '/System/Library/Fonts/Helvetica.ttc',  # macOS
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            ]
            
            for sys_font in system_fonts:
                if os.path.exists(sys_font):
                    print(f"Using system font: {sys_font} at size {min_size}")
                    return ImageFont.truetype(sys_font, min_size)
            
            print(f"Font path not found. Using default PIL font at size {min_size}.")
            # Try to get a larger default font
            try:
                return ImageFont.load_default()
            except:
                return ImageFont.load_default()
    except Exception as e:
        print(f"Font loading error: {e}, using default at size {min_size}")
        return ImageFont.load_default()
from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
import os
from django.conf import settings

# --- Helper functions ---
from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
import os
from django.conf import settings

# --- Helper functions ---

def draw_centered(draw, text, font, y, x_start, x_end, fill="black"):
    """Draw text centered between x_start and x_end."""
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    x = x_start + (x_end - x_start - text_width) / 2
    draw.text((x, y), text, font=font, fill=fill)

def draw_left(draw, text, font, x, y, fill="black"):
    """Draw left-aligned text with proper baseline alignment."""
    # Draw text at exact position (PIL uses top-left as reference)
    draw.text((x, y), text, font=font, fill=fill)

# --- Main function ---

# def generate_certificate(certificate_obj):
#     try:
#         # Load template image
#         template_path = settings.CERTIFICATE_TEMPLATE_PATH
#         if not os.path.exists(template_path):
#             raise FileNotFoundError(f"Certificate template not found: {template_path}")

#         template = Image.open(template_path).convert("RGB")
#         draw = ImageDraw.Draw(template)

#         # Fonts
#         base_size = settings.CERTIFICATE_FONT_SIZE
#         name_font = get_default_font(base_size * 5)
#         regular_font = get_default_font(base_size * 3.75)
#         small_font = get_default_font(base_size * 2.5)

#         # --- Draw Fields with Provided Coordinates ---
#         draw_centered(draw, certificate_obj.full_name, small_font, y=1065, x_start=1347, x_end=3077)
#         draw_centered(draw, certificate_obj.college_name, small_font, y=1180, x_start=632, x_end=3079)
#         draw_centered(draw, certificate_obj.affiliated_name, small_font, y=1310, x_start=842, x_end=1931)
#         draw_centered(draw, certificate_obj.roll_number, small_font, y=1310, x_start=2529, x_end=3065)
#         draw_centered(draw, certificate_obj.course, small_font, y=1446, x_start=2007, x_end=3093)
#         draw_centered(draw, certificate_obj.start_date.strftime("%d-%m-%Y"), small_font, y=1688, x_start=1333, x_end=2039)
#         draw_centered(draw, certificate_obj.end_date.strftime("%d-%m-%Y"), small_font, y=1681, x_start=2261, x_end=2954)
#         draw_left(draw, str(certificate_obj.certificate_id), small_font, x=844, y=1938)
#         draw_left(draw, certificate_obj.created_at.strftime("%d-%m-%Y"), small_font, x=661, y=2034)

#         # --- Generate QR Code ---
#         verification_url = certificate_obj.get_verification_url()
#         qr_img = generate_qr_code(verification_url, size=(450, 300))
#         template.paste(qr_img, (2718, 750))

#         # --- Save certificate image ---
#         os.makedirs(settings.CERTIFICATE_OUTPUT_PATH, exist_ok=True)
#         certificate_filename = f"{certificate_obj.full_name.replace(' ', '_')}.png"
#         certificate_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, certificate_filename)
#         template.save(certificate_path, "PNG", quality=95)

#         # --- Save image and QR code to model fields ---
#         from django.core.files.base import ContentFile

#         with open(certificate_path, 'rb') as f:
#             certificate_obj.certificate_image.save(certificate_filename, ContentFile(f.read()), save=False)

#         qr_filename = certificate_obj.get_qr_filename()
#         qr_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, qr_filename)
#         qr_img.save(qr_path, "PNG")
#         with open(qr_path, 'rb') as f:
#             certificate_obj.qr_code_image.save(qr_filename, ContentFile(f.read()), save=False)

#         certificate_obj.save()

#         print(f"✅ Certificate generated successfully for {certificate_obj.full_name} at {certificate_path}")
#         return certificate_path

#     except Exception as e:
#         print(f"❌ Error generating certificate: {str(e)}")
#         raise
from django.core.files.base import ContentFile
from io import BytesIO
import os
from django.conf import settings

def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources from the filesystem.
    """
    import os
    from django.conf import settings
    
    # Handle media URLs
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    # Handle static URLs
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    else:
        return uri

    # make sure that file exists
    if not os.path.isfile(path):
        raise Exception(
            'media URI must start with %s or %s' % (settings.MEDIA_URL, settings.STATIC_URL)
        )
    return path
def _resolve_template_image(template_name):
    """
    Resolve a template name to a PIL Image object.
    Supports both file-based templates and database templates (db:ID format).
    Returns (Image object, template_path_or_none).
    """
    from PIL import Image
    from django.conf import settings
    import os

    if not template_name:
        template_name = ""

    # Handle database templates (uploaded via frontend)
    if template_name.startswith('db:'):
        from .models import CertificateTemplate
        try:
            tmpl_id = int(template_name[3:])
            tmpl = CertificateTemplate.objects.get(id=tmpl_id, is_active=True)
            template_path = tmpl.template_image.path
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"DB template image file not found: {template_path}")
            logger.info(f"Using DB template: {tmpl.name} (ID: {tmpl_id})")
            return Image.open(template_path).convert("RGB"), template_path
        except CertificateTemplate.DoesNotExist:
            raise FileNotFoundError(f"Database template not found: {template_name}")
        except ValueError:
            raise ValueError(f"Invalid DB template identifier: {template_name}")

    # Check if the file exists directly in media/templates/
    direct_path = os.path.join(settings.MEDIA_ROOT, 'templates', template_name)
    if os.path.exists(direct_path):
        return Image.open(direct_path).convert("RGB"), direct_path

    # Clean the template name to resolve files robustly
    clean_name = template_name.strip()
    
    # Strip any known file extensions (case-insensitive)
    for ext in ['.jpg', '.jpeg', '.png']:
        if clean_name.lower().endswith(ext):
            clean_name = clean_name[:-len(ext)]
            break

    # Strip any leading 'original_certificate_' prefixes recursively
    while True:
        lower_name = clean_name.lower()
        if lower_name.startswith('original_certificate_'):
            clean_name = clean_name[len('original_certificate_'):]
        elif lower_name.startswith('original_certificate'):
            clean_name = clean_name[len('original_certificate'):]
        else:
            break

    # Normalize name for comparison with 6-types offer letters
    # NEW CODE — Paste this instead
    # Normalize name: remove spaces, dashes, underscores for fuzzy comparison
    norm_compare = clean_name.lower().replace(' ', '').replace('-', '').replace('_', '')

    # 1. Scan templates directory dynamically — matches regardless of dash/underscore/space
    template_filename = None
    template_dir = os.path.join(settings.MEDIA_ROOT, 'templates')

    search_dirs = [
        template_dir,
        os.path.join(settings.BASE_DIR, 'media', 'templates'),
        os.path.join('media', 'templates'),
    ]

    found_path = None
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            for filename in os.listdir(s_dir):
                fn_clean = filename.strip()
                for ext in ['.jpg', '.jpeg', '.png']:
                    if fn_clean.lower().endswith(ext):
                        fn_clean = fn_clean[:-len(ext)]
                        break
                while True:
                    fn_lower = fn_clean.lower()
                    if fn_lower.startswith('original_certificate_'):
                        fn_clean = fn_clean[len('original_certificate_'):]
                    elif fn_lower.startswith('original_certificate'):
                        fn_clean = fn_clean[len('original_certificate'):]
                    else:
                        break
                fn_norm = fn_clean.lower().replace(' ', '').replace('-', '').replace('_', '')
                if fn_norm == norm_compare:
                    found_path = os.path.join(s_dir, filename)
                    template_filename = filename
                    break
            if found_path:
                break

    # 2. Hardcoded fallback if dynamic scan fails
    if not found_path:
        if norm_compare == 'aicteapscheofferlettervirtual':
            template_filename = "original_certificate_aicte-apscheofferletter-virtual.jpg"
        elif norm_compare == 'onlyaicteofferlettervirtual':
            template_filename = "original_certificate_onlyaicteofferletter-virtual.jpg"
        elif norm_compare == 'onlyapscheofferlettervirtual':
            template_filename = "original_certificate_onlyapscheofferletter-virtual.jpg"
        elif norm_compare == 'aicteapscheofferletterphysical':
            template_filename = "original_certificate_aicte-apscheofferletter-physical.jpg"
        elif norm_compare == 'onlyaicteofferletterphysical':
            template_filename = "original_certificate_onlyaicteofferletter-physical.jpg"
        elif norm_compare == 'onlyapscheofferletterphysical':
            template_filename = "original_certificate_onlyapscheofferletter-physical.jpg"
        else:
            template_filename = f"original_certificate_{clean_name}.jpg"

        template_path = os.path.join(settings.MEDIA_ROOT, 'templates', template_filename)
        if not os.path.exists(template_path):
            for alt_path in [
                os.path.join(settings.BASE_DIR, 'media', 'templates', template_filename),
                os.path.join('media', 'templates', template_filename),
                os.path.join(settings.MEDIA_ROOT, 'templates', template_filename.lower()),
            ]:
                if os.path.exists(alt_path):
                    template_path = alt_path
                    break
        found_path = template_path

    if not os.path.exists(found_path):
        searched_paths = [
            os.path.join(settings.MEDIA_ROOT, 'templates', template_filename),
            os.path.join(settings.BASE_DIR, 'media', 'templates', template_filename),
            os.path.join('media', 'templates', template_filename),
            os.path.join(settings.MEDIA_ROOT, 'templates', template_filename.lower()),
        ]
        raise FileNotFoundError(
            f"Template not found: {template_filename}. Searched paths: {[p.replace(chr(92), '/') for p in searched_paths]}"
        )

    return Image.open(found_path).convert("RGB"), found_path
    
def get_template_display_name(template_name):
    """
    Get a user-friendly display name for a template filename.
    """
    if not template_name:
        return "—"
        
    # Standardize name by removing extensions and double prefixes
    clean = template_name.strip()
    for ext in ['.jpg', '.jpeg', '.png']:
        if clean.lower().endswith(ext):
            clean = clean[:-len(ext)]
            break
            
    while True:
        lower_name = clean.lower()
        if lower_name.startswith('original_certificate_'):
            clean = clean[len('original_certificate_'):]
        elif lower_name.startswith('original_certificate'):
            clean = clean[len('original_certificate'):]
        else:
            break
            
    # Normalize for comparison
    norm = clean.lower().replace(' ', '').replace('-', '').replace('_', '')
    
    mapping = {
        'aicteapscheofferlettervirtual': 'Virtual - AICTE-APSCHE',
        'aicteapscheofferletterphysical': 'Physical - AICTE-APSCHE',
        'onlyapscheofferlettervirtual': 'Virtual - APSCHE',
        'onlyapscheofferletterphysical': 'Physical - APSCHE',
        'onlyaicteofferlettervirtual': 'Virtual - AICTE',
        'onlyaicteofferletterphysical': 'Physical - AICTE',
    }
    
    if norm in mapping:
        return mapping[norm]
        
    # Handle DB templates (e.g. db:3 -> Custom Template Name)
    if template_name.startswith('db:'):
        from .models import CertificateTemplate
        try:
            tmpl_id = int(template_name[3:])
            tmpl = CertificateTemplate.objects.get(id=tmpl_id)
            return f"Custom - {tmpl.name}"
        except Exception:
            return f"Custom - DB {template_name[3:]}"
            
    # For any custom templates, return a cleaned and human-readable version
    cleaned = clean.replace('_', ' ').replace('-', ' ').title()
    return cleaned



def generate_certificate_image(certificate_obj, template_name='OfferLetter'):
    try:
        template, template_path = _resolve_template_image(template_name)
        draw = ImageDraw.Draw(template)
        
        # If it's an offer letter template, use offer letter specific layout
        offer_letter_templates = [
            
            'aicte-apsche offer letter-virtual', 'only aicte offer letter-virtual', 'only apsche offer letter-virtual',
            'aicte-apsche offer letter-physical', 'only aicte offer letter-physical', 'only apsche offer letter-physical',
        ]
        if template_name.lower() in offer_letter_templates:
            # Use specific layout for offer letters
            # Fonts - calibrated for 100 DPI to match 10-14pt
            regular_font = get_default_font(15, bold=False)  # ~11pt body
            name_font = get_default_font(18, bold=True)      # ~13.5pt highlight
            label_bold_font = get_default_font(16, bold=True) # ~12pt bold fields
            name_regular_font = get_default_font(18, bold=False)
            
            # To section unified coordinate logic
            to_x = 76
            to_y = 193
            line_gap = 22 # Thinner gap for 15px font
            
            # Issue Date (Right side) - Align with name block
            issue_date_str = certificate_obj.created_at.strftime('%B %d, %Y')
            draw_left(draw, issue_date_str, label_bold_font, 620, to_y, fill="black")
            
            # To: Information
            curr_y = to_y
            draw_left(draw, certificate_obj.full_name.upper(), name_regular_font, to_x, curr_y, fill="black")
            curr_y += line_gap
            
            # Combined Course and Roll Number
            combined_course_roll = f"{certificate_obj.course} | {certificate_obj.roll_number}"
            draw_left(draw, combined_course_roll, regular_font, to_x, curr_y, fill="black")
            curr_y += line_gap
                
            if certificate_obj.college_name:
                draw_left(draw, certificate_obj.college_name, regular_font, to_x, curr_y, fill="black")
                curr_y += line_gap
                
            # Address (optional)
            address = getattr(certificate_obj, 'institution_address', '')
            if address and address.strip().upper() != 'N/A':
                # Address (Optimized for two neat lines)
                addr_lines = wrap_text(address, regular_font, 400)
                for line in addr_lines:
                    draw_left(draw, line, regular_font, to_x, curr_y, fill="black")
                    curr_y += line_gap
            
            # Phone and Email (Values only, template has labels)
            curr_y += 4
            mobile = getattr(certificate_obj, 'candidate_mobile', '')
            if mobile and mobile.strip().upper() != 'N/A':
                draw_left(draw, mobile, regular_font, 139, 350, fill="black")
                curr_y += line_gap
                
            email = getattr(certificate_obj, 'email', '')
            if email and email.strip().upper() != 'N/A':
                # Aligned with "Email:" label at Y~332
                draw_left(draw, email, regular_font, 139, 378, fill="black")
            
           
            # Dear Section
            dear_y = 438
            draw_left(draw, certificate_obj.full_name, name_font, 129, dear_y, fill="black")
            
            # Bullet list (Title, Duration)
            course_display = certificate_obj.course or ""
            draw_left(draw, course_display, label_bold_font, 230, 846, fill="black")
            
            # Duration logic
            start = certificate_obj.start_date
            end = certificate_obj.end_date
            if start and end:
                months = (end.year - start.year) * 12 + (end.month - start.month)
                duration_text = f"{months} Month{'s' if months != 1 else ''}" if months > 0 else "2 Months"
                full_duration = f"{duration_text} (From {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')})"
                draw_left(draw, full_duration, label_bold_font, 260, 868, fill="black")
            
            # Footer / Acceptance
            acceptance_y = 1105
            draw_left(draw, certificate_obj.full_name, label_bold_font, 440, acceptance_y, fill="black")
            
            # QR Code Generation for Offer Letter
            verification_url = certificate_obj.get_verification_url()
            if verification_url:
                try:
                    qr_size = 150
                    qr_x, qr_y = 540, 930
                    
                    qr_img = generate_qr_code(verification_url, size=(qr_size, qr_size))
                    qr_img = qr_img.convert("RGB")
                    template.paste(qr_img, (qr_x, qr_y))
                    
                    # Add labels
                    small_f = get_default_font(13, bold=True)
                    draw.text((qr_x + 10, qr_y + qr_size + 5), "Scan to Verify", font=small_f, fill="black")
                    draw.text((qr_x + 10, qr_y + qr_size + 25), f"ID: {certificate_obj.certificate_id}", font=small_f, fill="black")
                    
                    logger.info(f"✅ Bulk QR code added at ({qr_x}, {qr_y})")
                except Exception as e:
                    logger.warning(f"QR code generation failed: {e}")

            # Save
            image_io = BytesIO()
            template.save(image_io, format="PNG", quality=95)
            image_io.seek(0)
            
            base_filename = certificate_obj.full_name.replace(' ', '_')
            certificate_filename = f"{base_filename}.png"
            certificate_obj.certificate_image.save(certificate_filename, ContentFile(image_io.read()), save=False)
            
            # Save QR to model (optional)
            if 'qr_img' in locals():
                try:
                    qr_io = BytesIO()
                    qr_img.save(qr_io, format="PNG")
                    qr_io.seek(0)
                    qr_filename = f"qr_{base_filename}.png"
                    certificate_obj.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=False)
                except Exception as e:
                    logger.warning(f"Failed to save QR code to model: {e}")

            certificate_obj.save()
            
            return certificate_obj.certificate_image.url

        # Fonts
        base_size = settings.CERTIFICATE_FONT_SIZE
        name_font = get_default_font(int(base_size * 1.4))
        small_font = get_default_font(int(base_size * 1.0))
        small_font2 = get_default_font(int(base_size * 0.8))

        # Draw Fields
        # draw_centered(draw, certificate_obj.full_name, small_font, y=375, x_start=460, x_end=1080)
        # draw_centered(draw, certificate_obj.college_name, small_font, y=415, x_start=245, x_end=1065)
        # # draw_centered(draw, certificate_obj.college_name, small_font, y=415, x_start=215, x_end=1065)
        # draw_centered(draw, certificate_obj.affiliated_name, small_font, y=462, x_start=290, x_end=670)
        # draw_centered(draw, certificate_obj.roll_number, small_font, y=458, x_start=915, x_end=1080)
        # # draw_centered(draw, certificate_obj.roll_number, small_font, y=458, x_start=880, x_end=1080)
        # draw_centered(draw, certificate_obj.course, small_font, y=512, x_start=690, x_end=1130)

        # draw_centered(draw, certificate_obj.start_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=600, x_end=830)
        # draw_centered(draw, certificate_obj.end_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=910, x_end=1130)
        # draw_left(draw, str(certificate_obj.certificate_id), small_font2, x=292, y=660)
        # draw_left(draw, certificate_obj.created_at.strftime("%d-%m-%Y"), small_font2, x=292, y=700)
        # draw_centered(draw, "Verify at https://verify.cscindia.org.in/", small_font2, 805, 292, 1080)
        draw_centered(draw, certificate_obj.full_name, small_font, y=375, x_start=460, x_end=1080)
        draw_centered(draw, certificate_obj.college_name, small_font, y=415, x_start=245, x_end=1065)
        draw_centered(draw, certificate_obj.affiliated_name, small_font, y=462, x_start=290, x_end=670)
        draw_centered(draw, certificate_obj.roll_number, small_font, y=458, x_start=915, x_end=1080)
        draw_centered(draw, certificate_obj.course, small_font, y=512, x_start=690, x_end=1130)
        draw_centered(draw, certificate_obj.start_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=600, x_end=830)
        draw_centered(draw, certificate_obj.end_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=910, x_end=1130)
        draw_left(draw, str(certificate_obj.certificate_id), small_font2, x=296, y=665)
        draw_left(draw, certificate_obj.created_at.strftime("%d-%m-%Y"), small_font2, x=229, y=700)
        draw_centered(draw, "Verify at https://offerletters.cscindia.org.in/", small_font2, 805, 292, 1080)

        # QR Code
        verification_url = certificate_obj.get_verification_url()
        if not verification_url:
            # Fallback if get_verification_url returns empty (e.g. missing id)
            domain = getattr(settings, 'SITE_DOMAIN', 'offerletters.cscindia.org.in')
            if 'localhost' in domain: domain = 'offerletters.cscindia.org.in'
            verification_url = f"https://{domain}/verify/{certificate_obj.certificate_id}/"

        logger.info(f"QR Code Debug - Generated verification URL: {verification_url}")
        qr_img = generate_qr_code(verification_url, size=(110, 80))
        template.paste(qr_img, (963, 278))

        # Convert template image to memory
        image_io = BytesIO()
        template.save(image_io, format="PNG", quality=95)
        image_io.seek(0)

        # Use only the student's name for the filename, spaces replaced by underscores
        base_filename = certificate_obj.full_name.replace(' ', '_')
        certificate_filename = f"{base_filename}.png"
        certificate_obj.certificate_image.save(certificate_filename, ContentFile(image_io.read()), save=False)

        # Save QR to model (optional)
        qr_io = BytesIO()
        qr_img.save(qr_io, format="PNG")
        qr_io.seek(0)
        qr_filename = f"qr_{base_filename}.png"
        certificate_obj.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=False)

        certificate_obj.save()

        print(f"✅ Saved via Django model: {certificate_filename}")
        return certificate_obj.certificate_image.url

    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Error generating certificate: {str(e)}")
        raise
# def generate_certificate_image(certificate_obj):
#     try:
#         # Load certificate template
#         template_path = settings.CERTIFICATE_TEMPLATE_PATH
#         if not os.path.exists(template_path):
#             raise FileNotFoundError(f"Template not found: {template_path}")

#         template = Image.open(template_path).convert("RGB")
#         draw = ImageDraw.Draw(template)

#         # Fonts
#         base_size = settings.CERTIFICATE_FONT_SIZE
#         name_font = get_default_font(int(base_size * 1.8))
#         small_font = get_default_font(int(base_size * 1.0))

#         # Draw Fields
#         draw_centered(draw, certificate_obj.full_name, small_font, y=375, x_start=460, x_end=1080)
#         draw_centered(draw, certificate_obj.college_name, small_font, y=415, x_start=215, x_end=1065)
#         draw_centered(draw, certificate_obj.affiliated_name, small_font, y=462, x_start=290, x_end=670)
#         draw_centered(draw, certificate_obj.roll_number, small_font, y=458, x_start=880, x_end=1080)
#         draw_centered(draw, certificate_obj.course, small_font, y=512, x_start=700, x_end=1080)
#         draw_centered(draw, certificate_obj.start_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=600, x_end=830)
#         draw_centered(draw, certificate_obj.end_date.strftime("%d-%m-%Y"), small_font, y=605, x_start=910, x_end=1130)
#         draw_left(draw, str(certificate_obj.certificate_id), small_font, x=298, y=682)
#         draw_left(draw, certificate_obj.created_at.strftime("%d-%m-%Y"), small_font, x=298, y=725)

#         # QR Code
#         verification_url = certificate_obj.get_verification_url()
#         qr_img = generate_qr_code(verification_url, size=(110, 80))
#         template.paste(qr_img, (963, 278))

#         # Convert template image to memory
#         image_io = BytesIO()
#         template.save(image_io, format="PNG", quality=95)
#         image_io.seek(0)

#         certificate_filename = f"{certificate_obj.full_name.replace(' ', '_')}_{certificate_obj.certificate_id}.png"
#         certificate_obj.certificate_image.save(certificate_filename, ContentFile(image_io.read()), save=False)

#         # Save QR to model (optional)
#         qr_io = BytesIO()
#         qr_img.save(qr_io, format="PNG")
#         qr_io.seek(0)
#         qr_filename = certificate_obj.get_qr_filename()
#         certificate_obj.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=False)

#         certificate_obj.save()

#         print(f"✅ Saved via Django model: {certificate_filename}")
#         return certificate_obj.certificate_image.url

#     except Exception as e:
#         print(f"❌ Error: {e}")
#         raise





# Example usage (for testing)
if __name__ == "__main__":
    mock_cert = MockCertificateObj()
    generate_certificate_image(mock_cert)









# def generate_certificate_pdf(certificate_obj):
#     """
#     Generate PDF version of the certificate (optional enhancement)
#     """
#     try:
#         from reportlab.pdfgen import canvas
#         from reportlab.lib.pagesizes import A4, landscape
#         from reportlab.lib.utils import ImageReader
        
#         if not certificate_obj.certificate_image:
#             raise ValueError("Certificate image must be generated first")
        
#         # Create PDF
#         pdf_filename = f"certificate_{certificate_obj.certificate_id}.pdf"
#         pdf_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, 'pdf', pdf_filename)
        
#         # Ensure PDF directory exists
#         os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        
#         # Create PDF with certificate image
#         c = canvas.Canvas(pdf_path, pagesize=landscape(A4))
        
#         # Add certificate image to PDF
#         img = ImageReader(certificate_obj.certificate_image.path)
#         c.drawImage(img, 0, 0, width=landscape(A4)[0], height=landscape(A4)[1])
        
#         c.save()
        
#         # Save to model
#         with open(pdf_path, 'rb') as f:
#             certificate_obj.certificate_pdf.save(
#                 pdf_filename,
#                 ContentFile(f.read()),
#                 save=False
#             )
        
#         certificate_obj.save()
        
#         logger.info(f"Certificate PDF generated successfully for {certificate_obj.full_name}")
#         return pdf_path
        
#     except ImportError:
#         logger.warning("ReportLab not installed, PDF generation skipped")
#         return None
#     except Exception as e:
#         logger.error(f"Error generating certificate PDF: {str(e)}")
#         raise
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.conf import settings
from django.core.files.base import ContentFile
import os


def generate_certificate_pdf(certificate_obj):
    context = {
        'full_name': certificate_obj.full_name.upper(),
        'college_name': certificate_obj.college_name,
        'roll_number': certificate_obj.roll_number,
        'course': certificate_obj.course,
        'certificate_id': str(certificate_obj.certificate_id)[:12],
        'issue_date': certificate_obj.created_at.strftime("%d-%m-%Y"),
        'qr_code_url': certificate_obj.qr_code_image.url  # Must be full/static URL
    }

    html = render_to_string("certificate_template.html", context)
    cert_filename = certificate_obj.get_certificate_filename().replace('.png', '.pdf')
    cert_path = os.path.join(settings.CERTIFICATE_OUTPUT_PATH, cert_filename)
    os.makedirs(settings.CERTIFICATE_OUTPUT_PATH, exist_ok=True)

    with open(cert_path, "wb") as out_file:
        pisa_status = pisa.CreatePDF(html, dest=out_file, link_callback=link_callback)

    if pisa_status.err:
        raise Exception("Error creating PDF")

    with open(cert_path, 'rb') as f:
        certificate_obj.certificate_pdf.save(cert_filename, ContentFile(f.read()), save=False)

    certificate_obj.save()
    return cert_path


def generate_offer_letter_image(offer_letter_data, template_name='aicte-apscheofferletter.jpg'):
    """
    Generate offer letter image by overlaying text on the template image.
    Template: original_certificate_offerletter.jpg
    
    Places the following dynamic fields:
    - Name of candidate
    - Roll number
    - Branch/Course name
    - Institution name
    - Institution address
    - Mobile number
    - Email id
    - Internship title
    - Internship duration
    - Issue date
    """
    try:
        from datetime import datetime
        
        # Load offer letter template - support multiple templates with prefix 'original_certificate_'
        # Remove .jpg extension if already present to avoid double extension
        if template_name.upper() == 'AICTE-APSCHE OFFER LETTER':
            template_filename = "original_certificate_aicte-apscheofferletter.jpg"

        elif template_name.upper() == 'ONLY AICTE OFFER LETTER':
            template_filename = "original_certificate_onlyaicteofferletter.jpg"

        elif template_name.upper() == 'ONLY APSCHE OFFER LETTER':
            template_filename = "original_certificate_onlyapscheofferletter.jpg"

        else:
    # Use the filename directly if it already comes from the database/admin
            template_filename = os.path.basename(template_name)

    # Add extension only if missing
            if not template_filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                template_filename += '.jpg'
        template_path = os.path.join(settings.MEDIA_ROOT,'templates',template_filename)
        
        # Debug: Log the path being searched
        logger.info(f"Looking for template at: {template_path}")
        logger.info(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        logger.info(f"BASE_DIR: {settings.BASE_DIR}")
        
        # Try to find template if not found at expected path
        if not os.path.exists(template_path):
            # Try alternative paths
            alternative_paths = [
                os.path.join(settings.BASE_DIR, 'media', 'templates', template_filename),
                os.path.join('media', 'templates', template_filename),
                os.path.join(settings.MEDIA_ROOT, 'templates', template_filename.lower()),
            ]
            
            for alt_path in alternative_paths:
                logger.info(f"Trying alternative path: {alt_path}")
                if os.path.exists(alt_path):
                    template_path = alt_path
                    logger.info(f"Found template at: {template_path}")
                    break
            
            # If still not found, raise error with all attempted paths
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Template not found: {template_filename}. Searched paths: {[template_path] + alternative_paths}")
            
        template = Image.open(template_path).convert("RGB")
        draw = ImageDraw.Draw(template)
        
        # Get template dimensions
        width, height = template.size
        logger.info(f"Template image size: {width}x{height} pixels")
        
        # Fonts - calibrated for 100 DPI to match 10-14pt
        regular_font = get_default_font(15, bold=False)  # ~11pt body
        small_font = get_default_font(13, bold=False)    # ~9pt supplementary
        name_font = get_default_font(18, bold=True)      # ~13.5pt highlight
        label_bold_font = get_default_font(16, bold=True) # ~12pt bold fields
        
        # Extract data
        # Helper to clean nan values from data and format mobile numbers
        def _clear_nan(val, is_mobile=False):
            if val is None: return ""
            s = str(val).strip()
            if s.lower() == 'nan': return ""
            if is_mobile and s:
                try:
                    # Handle .0 or scientific notation from Excel/Pandas
                    return str(int(float(s)))
                except (ValueError, TypeError):
                    return s
            return s

        candidate_name = _clear_nan(offer_letter_data.get('candidate_name', ''))
        roll_number = _clear_nan(offer_letter_data.get('roll_number', ''))
        course_name = _clear_nan(offer_letter_data.get('course_name', ''))  # Branch/Course name
        institution_name = _clear_nan(offer_letter_data.get('institution_name', ''))
        institution_address = _clear_nan(offer_letter_data.get('institution_address', ''))
        candidate_mobile = _clear_nan(offer_letter_data.get('candidate_mobile', ''), is_mobile=True)
        candidate_email = _clear_nan(offer_letter_data.get('candidate_email', ''))
        internship_title = _clear_nan(offer_letter_data.get('internship_title', ''))
        internship_duration = _clear_nan(offer_letter_data.get('internship_duration', ''))
        
        # Format issue date
        issue_date_str = offer_letter_data.get('issue_date', '')
        if not issue_date_str:
            issue_date_str = datetime.now().strftime('%B %d, %Y')
        elif isinstance(issue_date_str, str):
            try:
                # Support both YYYY-MM-DD and DD-MM-YYYY
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        date_obj = datetime.strptime(issue_date_str, fmt)
                        issue_date_str = date_obj.strftime('%B %d, %Y')
                        break
                    except ValueError:
                        continue
            except:
                pass
        
        # Helper function to wrap text with width constraint
        def wrap_text(text, font, max_width):
            """Wrap text to fit within max_width pixels"""
            words = text.split()
            lines = []
            current_line = []
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = font.getbbox(test_line)
                test_width = bbox[2] - bbox[0]
                
                if test_width <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            return lines if lines else [text]
        
        # Helper function to truncate text if too long
        def truncate_text(text, font, max_width):
            """Truncate text to fit within max_width pixels"""
            if not text:
                return ''
            
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                return text
            
            # Truncate character by character until it fits
            truncated = text
            while truncated and text_width > max_width:
                truncated = truncated[:-1]
                if truncated:
                    test_text = truncated + '...'
                    bbox = font.getbbox(test_text)
                    text_width = bbox[2] - bbox[0]
                else:
                    break
            
            return truncated + '...' if truncated else text[:10] + '...'
        
        # --- TO section layout ---
        to_x_left = 76
        to_y_start = 193
        line_gap = 22  # Optimized for ~11pt (15px) font
        max_to_width = 700

        # Issue Date – keep aligned with Name block horizontally
        date_text = truncate_text(issue_date_str, label_bold_font, 260)
        draw_left(draw, date_text, label_bold_font, 623,175, fill="#000000")

        # 1) Candidate name in CAPITAL letters - bold
        name_text = candidate_name.upper()
        draw_left(draw, name_text, name_font, to_x_left, to_y_start, fill="#000000")

        # 2) Second line: Course Name and Roll Number on the same line
        second_line_y = to_y_start + line_gap
        course_display = course_name or ""
        # Add comma only if both roll number and course exist
        if roll_number and course_display:
            combined_text = f"{roll_number}, {course_display}"
        else:
            combined_text = roll_number or course_display
        combined_text = truncate_text(combined_text, regular_font, 700)
        draw_left(draw, combined_text, regular_font, to_x_left, second_line_y, fill="#000000")

        # 3) Third line: Institution name
        third_line_y = second_line_y + line_gap
        inst_name_text = truncate_text(institution_name, regular_font, 700)
        draw_left(draw, inst_name_text, regular_font, to_x_left, third_line_y, fill="#000000")

        # 4) Fourth line: Institution address (Optimized for two neat lines)
        fourth_line_y = third_line_y + line_gap
        address_lines = wrap_text(institution_address, regular_font, 400)
        for i, line in enumerate(address_lines):
            draw_left(draw, line, regular_font, to_x_left, fourth_line_y + (i * line_gap), fill="#000000")
        
        # 5) Contact block (Values only, template has labels)
        contact_y = fourth_line_y + (len(address_lines) * line_gap) - 2
        
        mobile_raw = candidate_mobile if candidate_mobile else ''
        mobile_value = '' if mobile_raw.strip().upper() == 'N/A' else mobile_raw.strip()
        if mobile_value:
            # Shift right if drawing after a label, or use fixed X
            draw_left(draw, mobile_value, regular_font, 139, 330, fill="#000000")
            contact_y += line_gap
        
        email_raw = candidate_email if candidate_email else ''
        email_value = '' if email_raw.strip().upper() == 'N/A' else email_raw.strip()
        if email_value:
            # The template likely has "Email:" label at Y~335
            draw_left(draw, email_value, regular_font, 139, 348, fill="#000000")
        
        # Candidate name after "Dear " - NO TRUNCATION
        greeting_name = candidate_name + ","
        draw_left(draw, greeting_name, name_font, 129, 425, fill="#000000")

        
        # Internship title - aligned with bullet point on template
        title_text = truncate_text(internship_title, label_bold_font, 500)
        draw_left(draw, title_text, label_bold_font, 247, 638, fill="#000000")
        
        # Internship duration - aligned with bullet point on template
        curr_x = 290
        curr_y = 659
        
        # 1. Duration prefix (e.g., "3 Months") - BOLD
        duration_prefix = internship_duration
        draw_left(draw, duration_prefix, label_bold_font, curr_x, curr_y, fill="#000000")
        curr_x += label_bold_font.getlength(duration_prefix)
        
        # 2. Add dates if available
        start_date_raw = offer_letter_data.get('internship_start_date')
        end_date_raw = offer_letter_data.get('internship_end_date')
        if start_date_raw and end_date_raw:
            try:
                def format_date_str(d):
                    if isinstance(d, str):
                        try:
                            d = datetime.strptime(d, '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            return d
                    if hasattr(d, 'strftime'):
                        return d.strftime('%d %b %Y')
                    return str(d)

                start_fmt = format_date_str(start_date_raw)
                end_fmt = format_date_str(end_date_raw)
                
                # " (From " - REGULAR
                from_text = " (From "
                draw_left(draw, from_text, regular_font, curr_x, curr_y, fill="#000000")
                curr_x += regular_font.getlength(from_text)
                
                # start_fmt - BOLD
                draw_left(draw, start_fmt, label_bold_font, curr_x, curr_y, fill="#000000")
                curr_x += label_bold_font.getlength(start_fmt)
                
                # " to " - REGULAR
                to_word = " to "
                draw_left(draw, to_word, regular_font, curr_x, curr_y, fill="#000000")
                curr_x += regular_font.getlength(to_word)
                
                # end_fmt - BOLD
                draw_left(draw, end_fmt, label_bold_font, curr_x, curr_y, fill="#000000")
                curr_x += label_bold_font.getlength(end_fmt)
                
                # ")" - REGULAR
                closing_brace = ")"
                draw_left(draw, closing_brace, regular_font, curr_x, curr_y, fill="#000000")
            except Exception as e:
                logger.warning(f"Error formatting dates for duration: {e}")
                
        # Draw stipend if provided
        stipend_val = offer_letter_data.get('stipend_amount')
        if stipend_val:
            try:
                # Failsafe: round to nearest integer if within 0.10
                f_val = float(stipend_val)
                rounded_val = round(f_val)
                if abs(f_val - rounded_val) < 0.10:
                    stipend_val = rounded_val
            except (ValueError, TypeError):
                pass
            stipend_str = str(stipend_val).strip()
            is_numeric = False
            try:
                float(stipend_str)
                is_numeric = True
            except ValueError:
                pass
            
            if is_numeric:
                try:
                    val = float(stipend_str)
                    if val == int(val):
                        formatted_stipend = f"₹{int(val)} per month"
                    else:
                        formatted_stipend = f"₹{val:.2f} per month"
                except:
                    formatted_stipend = f"₹{stipend_str} per month"
            else:
                formatted_stipend = stipend_str
                
            # If it doesn't already start with "stipend" or similar, prefix it
            if not any(prefix in formatted_stipend.lower() for prefix in ['stipend', 'rs', '₹']):
                formatted_stipend = f"₹{formatted_stipend} per month"
                
            bullet_x = 87
            bullet_y = 615
            bullet_font = get_default_font(24, bold=True)
            draw_left(draw, "•", bullet_font, bullet_x, bullet_y - 3, fill="#000000")
            dot_width = bullet_font.getlength("•")
            label_x = bullet_x + dot_width + 4
            draw_left(draw, " Stipend: ", label_bold_font, label_x, bullet_y, fill="#000000")
            val_x = label_x + label_bold_font.getlength(" Stipend: ")
            label_regular_font = get_default_font(16, bold=False)
            draw_left(draw, formatted_stipend, label_regular_font, val_x, bullet_y, fill="#000000")
            
        # Name of the candidate under signature - aligned with "Name:" field on template
        acceptance_name = candidate_name
        draw_left(draw, acceptance_name, label_bold_font, 368, 1155, fill="#000000")
        
        # Date: line is fixed on template, we don't need to draw it
        
        # --- QR Code Generation ---
        
        certificate_id = offer_letter_data.get('certificate_id', '')
        if certificate_id:
            # Use the production domain as absolute fallback
            domain = getattr(settings, 'SITE_DOMAIN', 'offerletters.cscindia.org.in')
            if 'localhost' in domain: domain = 'offerletters.cscindia.org.in'
            protocol = getattr(settings, 'SITE_PROTOCOL', 'https')
            if 'http' == protocol and domain == 'offerletters.cscindia.org.in': protocol = 'https'
            
            verification_url = f"{protocol}://{domain}/verify/{certificate_id}/"
            try:
                qr_size = 120
                qr_x, qr_y = 630, 205
                
                qr_image = generate_qr_code(verification_url, size=(qr_size, qr_size))
                qr_image = qr_image.convert("RGB")
                template.paste(qr_image, (qr_x, qr_y))
                
                # Add labels - positioned immediately below QR code
                small_f = get_default_font(13, bold=True)
                draw.text((qr_x + 2, qr_y + qr_size + 2), f"ID: {certificate_id}", font=small_f, fill="black")
                
                logger.info(f"✅ Manual QR code added at ({qr_x}, {qr_y})")
            except Exception as qr_error:
                logger.warning(f"QR code generation failed: {qr_error}")
        
        # Convert template image to memory
        image_io = BytesIO()
        template.save(image_io, format="PNG", quality=95)
        image_io.seek(0)
        
        return image_io
        
    except Exception as e:
        logger.error(f"Error generating offer letter image: {str(e)}")
        raise
def normalize_field_string(val):
    if val is None:
        return ""
    s = str(val).strip().lower()
    if "@gamil.com" in s:
        s = s.replace("@gamil.com", "@gmail.com")
    return s

def normalize_mobile_digits(val):
    if val is None:
        return ""
    import re
    # Remove non-digits
    digits = re.sub(r'\D', '', str(val))
    # If 12-digit Indian number starting with 91, strip prefix
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    # If 11-digit number starting with 0, strip prefix
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits

def normalize_date_val(val):
    if not val:
        return ""
    # If already a datetime or date object
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    # Try parsing string
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ('none', 'nan', 'nat', 'null', ''):
        return ""
    from datetime import datetime
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d %b %Y', '%d %B %Y'):
        try:
            return datetime.strptime(val_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    try:
        import pandas as pd
        t = pd.to_datetime(val_str)
        if not pd.isna(t):
            return t.strftime('%Y-%m-%d')
    except:
        pass
    return val_str

def get_certificate_duplicate_key(cert_or_dict):
    """
    Returns a normalized tuple key representing a unique offer letter.
    To treat any Roll Number appearing more than once as a duplicate,
    this key uses only the roll number (at index 1) and sets other fields to empty string.
    Supports Certificate objects, Certificate_student objects, or dicts.
    """
    if isinstance(cert_or_dict, dict):
        roll_number = cert_or_dict.get('roll_number')
    else:
        roll_number = getattr(cert_or_dict, 'roll_number', '')

    norm_roll = normalize_field_string(roll_number)
    return ("", norm_roll, "", "", "", "", "", "", "", "", "", "")




def save_offer_letter_to_database(offer_letter_data, student=None, template_name=None):
    """
    Save offer letter to database (Certificate model) after generation.
    Creates a Certificate record with all the offer letter data and generated image.
    Offer letters do not require a certificate_id.
    """
    try:
        from .models import Certificate
        from datetime import datetime
        from django.core.files.base import ContentFile
        
        # Parse dates (support both YYYY-MM-DD and DD-MM-YYYY)
        def parse_date_any(value):
            if not value:
                return None
            if hasattr(value, 'date') and hasattr(value, 'strftime') and not isinstance(value, str):
                # datetime -> date, date -> date
                try:
                    return value.date()
                except Exception:
                    return value
            if isinstance(value, str):
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
            return None

        issue_date_raw = offer_letter_data.get('issue_date', '')
        issue_date = parse_date_any(issue_date_raw) or datetime.now().date()
        logger.info(f"Using issue_date: {issue_date} (raw: {issue_date_raw})")
        
        # Get start and end dates from student if available, or from offer_letter_data
        if student:
            start_date = student.start_date
            end_date = student.end_date
        else:
            # Try to get from offer_letter_data
            start_date_str = offer_letter_data.get('internship_start_date', '')
            end_date_str = offer_letter_data.get('internship_end_date', '')
            if start_date_str:
                try:
                    parsed = parse_date_any(start_date_str)
                    if parsed:
                        start_date = parsed
                        logger.info(f"Successfully parsed start_date: '{start_date_str}' -> {start_date}")
                    else:
                        start_date = None
                except Exception as e:
                    logger.error(f"Failed to parse start_date '{start_date_str}': {str(e)}")
                    start_date = None
            else:
                start_date = None
            
            if end_date_str:
                try:
                    parsed = parse_date_any(end_date_str)
                    if parsed:
                        end_date = parsed
                        logger.info(f"Successfully parsed end_date: '{end_date_str}' -> {end_date}")
                    else:
                        end_date = None
                except Exception as e:
                    logger.error(f"Failed to parse end_date '{end_date_str}': {str(e)}")
                    end_date = None
            else:
                end_date = None
        
        # Use internship duration directly from Excel without overriding
        duration = offer_letter_data.get('internship_duration', '').strip()
        if duration:
            duration_choice = duration  # Use Excel value directly
            logger.info(f"Using internship duration from Excel: '{duration}'")
        else:
            duration_choice = ''
            logger.info("No internship duration provided, using empty value")
        
        # Check if certificate already exists for this combination
        # Matches the 12-field duplicate matching logic
        roll_number = offer_letter_data.get('roll_number', '')
        candidate_email = offer_letter_data.get('candidate_email', '').strip()
        candidate_name = offer_letter_data.get('candidate_name', '').strip()
        
        target_key = get_certificate_duplicate_key({
            'candidate_name': candidate_name,
            'roll_number': roll_number,
            'candidate_email': candidate_email,
            'candidate_mobile': offer_letter_data.get('candidate_mobile', ''),
            'course_name': offer_letter_data.get('course_name', ''),
            'institution_name': offer_letter_data.get('institution_name', ''),
            'internship_title': offer_letter_data.get('internship_title', ''),
            'internship_duration': duration_choice,
            'issue_date': issue_date,
            'internship_start_date': start_date,
            'internship_end_date': end_date,
            'offer_type': template_name or '',
        })
        
        # Search the database for any potential matches based on Roll Number
        existing_certificate = None
        if roll_number:
            potential_matches = Certificate.objects.filter(roll_number__iexact=roll_number.strip())
            for cert in potential_matches.order_by('id'):
                if get_certificate_duplicate_key(cert) == target_key:
                    existing_certificate = cert
                    break
        
        # Generate or get certificate_id BEFORE image generation (needed for QR code)
        from .models import generate_certificate_id
        if existing_certificate:
            cert_id = existing_certificate.certificate_id or generate_certificate_id()
        else:
            cert_id = generate_certificate_id()
        
        # Add certificate_id to offer_letter_data for QR code generation
        offer_letter_data['certificate_id'] = cert_id
        
        # Generate offer letter image (now includes QR code with certificate_id)
        # Use default template if template_name is None
        actual_template_name = template_name if template_name else 'AICTE-APSCHE OFFER LETTER'
        image_buffer = generate_offer_letter_image(offer_letter_data, template_name=actual_template_name)
        image_buffer.seek(0)
        
        # Create or update certificate record
        if existing_certificate:
            certificate = existing_certificate
            # Update fields
            certificate.full_name = offer_letter_data.get('candidate_name', '')
            certificate.roll_number = roll_number
            certificate.course = offer_letter_data.get('course_name', '')
            certificate.college_name = offer_letter_data.get('institution_name', '')
            certificate.institution_address = offer_letter_data.get('institution_address', '')
            certificate.email = offer_letter_data.get('candidate_email', '')
            certificate.candidate_mobile = offer_letter_data.get('candidate_mobile', '')
            certificate.internship_title = offer_letter_data.get('internship_title', '')
            certificate.internship_duration = duration_choice
            certificate.start_date = start_date
            certificate.end_date = end_date
            certificate.issue_date = issue_date  # Save issue date
            certificate.certificate_id = cert_id  # Ensure certificate_id is set
            certificate.offer_type = template_name or ''  # Save offer type
            certificate.stipend_amount = offer_letter_data.get('stipend_amount')  # Save stipend
        else:
            certificate = Certificate(
                certificate_id=cert_id,
                full_name=offer_letter_data.get('candidate_name', ''),
                roll_number=roll_number,
                course=offer_letter_data.get('course_name', ''),
                college_name=offer_letter_data.get('institution_name', ''),
                affiliated_name=student.affiliated_name if student else '',
                institution_address=offer_letter_data.get('institution_address', ''),
                email=offer_letter_data.get('candidate_email', ''),
                candidate_mobile=offer_letter_data.get('candidate_mobile', ''),
                internship_title=offer_letter_data.get('internship_title', ''),
                internship_duration=duration_choice,
                start_date=start_date,
                end_date=end_date,
                issue_date=issue_date,  # Save issue date
                offer_type=template_name or '',  # Save offer type
                stipend_amount=offer_letter_data.get('stipend_amount'),
                is_verified=True,
            )
        
        # Build filename: RollNumber_Name_MobileNumber.png (skip missing fields)
        parts = []
        roll_number = offer_letter_data.get('roll_number', '').strip()
        name = offer_letter_data.get('candidate_name', '').strip()
        mobile = offer_letter_data.get('candidate_mobile', '').strip()
        if roll_number:
            parts.append(roll_number.replace(' ', '_'))
        if name:
            parts.append(name.replace(' ', '_'))
        if mobile:
            parts.append(mobile.replace(' ', ''))
        certificate_filename = "_".join(parts) + ".png" if parts else "OfferLetter.png"
        certificate.certificate_image.save(certificate_filename, ContentFile(image_buffer.read()), save=False)
        
        # Save certificate to database
        try:
            certificate.save()
        except ValidationError as ve:
            logger.error(f"Validation error saving certificate: {str(ve)}")
            try:
                certificate.save(skip_validation=True)
                logger.info(f"✅ Offer letter saved to database (skip validation) for {certificate.full_name}")
            except Exception as e2:
                logger.error(f"Failed to save certificate even with skip_validation: {str(e2)}")
                raise
        except IntegrityError as ie:
            # DB-level unique constraint violation — duplicate already exists
            logger.warning(f"Duplicate offer letter blocked by DB constraint for {offer_letter_data.get('candidate_name', '')} ({offer_letter_data.get('roll_number', '')}): {str(ie)}")
            # Return the existing record instead
            if not existing_certificate:
                dup_filter = {
                    'roll_number__iexact': roll_number.strip(),
                }
                existing_certificate = Certificate.objects.filter(**dup_filter).first()
            if existing_certificate:
                logger.info(f"Returning existing offer letter record for {existing_certificate.full_name} (ID: {existing_certificate.certificate_id})")
                return existing_certificate
            raise
        except Exception as e:
            logger.error(f"Error saving offer letter to database: {str(e)}")
            raise

        # Save QR image to model field for preview in admin
        try:
            verification_url = certificate.get_verification_url()
            qr_img = generate_qr_code(verification_url, size=(300, 300))
            qr_io = BytesIO()
            qr_img.save(qr_io, format="PNG")
            qr_io.seek(0)
            qr_filename = f"qr_{certificate.certificate_id}.png"
            certificate.qr_code_image.save(qr_filename, ContentFile(qr_io.read()), save=True)
            logger.info(f"✅ QR model field updated for {certificate.full_name}")
        except Exception as qr_err:
            logger.warning(f"QR field update failed: {qr_err}")

        logger.info(f"✅ Offer letter saved to database for {certificate.full_name} (ID: {certificate.certificate_id})")
        
        return certificate
        
    except Exception as e:
        logger.error(f"Error saving offer letter to database: {str(e)}")
        raise





def generate_offer_letter_pdf(offer_letter_data):
    """
    Generate PDF version of the offer letter
    """
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    from io import BytesIO
    from datetime import datetime
    
    # Format dates for display
    formatted_data = offer_letter_data.copy()
    
    # Add QR code URL from matching Certificate object if possible
    cert_id = offer_letter_data.get('certificate_id')
    if cert_id:
        try:
            from .models import Certificate
            cert = Certificate.objects.get(certificate_id=cert_id)
            if cert.qr_code_image:
                formatted_data['qr_code_url'] = cert.qr_code_image.url
        except:
            pass
    try:
        if isinstance(formatted_data.get('internship_start_date'), str):
            start_date = datetime.strptime(formatted_data['internship_start_date'], '%Y-%m-%d')
            formatted_data['formatted_start_date'] = start_date.strftime('%B %d, %Y')
        else:
            formatted_data['formatted_start_date'] = str(formatted_data.get('internship_start_date', ''))
    except (ValueError, TypeError):
        formatted_data['formatted_start_date'] = str(formatted_data.get('internship_start_date', ''))
    
    try:
        if isinstance(formatted_data.get('internship_end_date'), str):
            end_date = datetime.strptime(formatted_data['internship_end_date'], '%Y-%m-%d')
            formatted_data['formatted_end_date'] = end_date.strftime('%B %d, %Y')
        else:
            formatted_data['formatted_end_date'] = str(formatted_data.get('internship_end_date', ''))
    except (ValueError, TypeError):
        formatted_data['formatted_end_date'] = str(formatted_data.get('internship_end_date', ''))
    
    # Prefer issue_date if provided, otherwise use current date
    issue_date_raw = formatted_data.get('issue_date')
    issue_date_display = None
    if issue_date_raw:
        try:
            if isinstance(issue_date_raw, str):
                try:
                    issue_dt = datetime.strptime(issue_date_raw, '%Y-%m-%d')
                except ValueError:
                    issue_dt = datetime.strptime(issue_date_raw, '%d-%m-%Y')
                issue_date_display = issue_dt.strftime('%B %d, %Y')
        except (ValueError, TypeError):
            issue_date_display = None

    formatted_data['issue_date_display'] = issue_date_display
    formatted_data['current_date'] = issue_date_display or datetime.now().strftime('%B %d, %Y')
    
    # Normalize stipend_amount for template rendering
    raw_stipend = formatted_data.get('stipend_amount')
    if raw_stipend is not None:
        try:
            f_val = float(raw_stipend)
            # Failsafe: round to nearest integer if within 0.05
            rounded_val = round(f_val)
            if abs(f_val - rounded_val) < 0.10:
                stipend_float = float(rounded_val)
            else:
                stipend_float = f_val
            # Display without trailing .00 if it's a whole number
            if stipend_float == int(stipend_float):
                formatted_data['stipend_amount'] = str(int(stipend_float))
            else:
                formatted_data['stipend_amount'] = f"{stipend_float:.2f}"
        except (ValueError, TypeError):
            formatted_data['stipend_amount'] = None
    else:
        formatted_data['stipend_amount'] = None

    
    # Render HTML template
    html = render_to_string("certificates/offer_letter_template.html", formatted_data)
    
    # Create PDF in memory
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer, link_callback=link_callback)
    
    if pisa_status.err:
        raise Exception("Error creating PDF")
    
    pdf_buffer.seek(0)
    return pdf_buffer


# from datetime import datetime
# def create_certificate_from_form_data(form_data):
#     """
#     Create certificate from form data and generate all files
#     """
#     from .models import Certificate
    
#     # Create certificate object
#     certificate = Certificate.objects.create(
#         full_name=form_data['full_name'],
#         roll_number=form_data['roll_number'],
#         course=form_data['course'],
#         college_name=form_data['college_name'],
#         affiliated_name=form_data['affiliated_name'],
#         email=form_data['email'],
#         start_date=form_data['start_date'],
#         end_date=form_data['end_date'],
#     )
    
#     # Generate certificate image and QR code
#     generate_certificate_image(certificate)
    
#     # Generate PDF (optional)
#     try:
#         generate_certificate_pdf(certificate)

#     except Exception as e:
#         logger.warning(f"PDF generation failed: {e}")
    
#     return certificate


from datetime import datetime
def create_certificate_from_form_data(form_data):
    """
    Create certificate from form data and generate all files
    """
    from .models import Certificate
    
    # Create certificate object
    certificate = Certificate.objects.create(
        full_name=form_data['full_name'],
        roll_number=form_data['roll_number'],
        course=form_data['course'],
        college_name=form_data['college_name'],
        affiliated_name=form_data['affiliated_name'],
        email=form_data['email'],
        start_date=form_data['start_date'],
        end_date=form_data['end_date'],
    )
    
    # Generate certificate image and QR code
    template_name = form_data.get('template', 'Pragna')
    generate_certificate_image(certificate, template_name=template_name)

    # Generate PDF (optional)
    try:
        if template_name.lower() == 'offerletter':
            offer_letter_data = {
                'candidate_name': certificate.full_name,
                'roll_number': certificate.roll_number,
                'course_name': certificate.course,
                'institution_name': certificate.college_name,
                'institution_address': certificate.institution_address,
                'candidate_mobile': certificate.candidate_mobile,
                'candidate_email': certificate.email,
                'internship_title': certificate.internship_title,
                'internship_duration': certificate.internship_duration,
                'issue_date': certificate.created_at.strftime('%Y-%m-%d'),
            }
            pdf_buffer = generate_offer_letter_pdf(offer_letter_data)
            certificate.certificate_pdf.save(f"{certificate.full_name}.pdf", ContentFile(pdf_buffer.read()), save=False)
        else:
            generate_certificate_pdf(certificate)

    except Exception as e:
        logger.warning(f"PDF generation failed: {e}")
    
    return certificate


_CSC_LOGO_CACHE = None


def get_csc_logo_info():
    """
    Retrieve and cache CSC India logo metadata and file content for email embedding.
    Returns:
        dict with keys 'data', 'subtype', 'filename', 'cid', 'path'
        or None if no valid logo file exists.
    """
    global _CSC_LOGO_CACHE
    if _CSC_LOGO_CACHE is not None:
        return _CSC_LOGO_CACHE

    from django.conf import settings
    import logging
    import os

    logger = logging.getLogger(__name__)

    candidates = []

    # 1. Explicit setting from settings / environment
    if hasattr(settings, 'CSC_LOGO_PATH') and settings.CSC_LOGO_PATH:
        candidates.append(str(settings.CSC_LOGO_PATH))

    # 2. MEDIA_ROOT locations
    media_root = getattr(settings, 'MEDIA_ROOT', '')
    if media_root:
        candidates.append(os.path.join(str(media_root), 'CSC LOGO.png'))
        candidates.append(os.path.join(str(media_root), 'CSC_LOGO.png'))
        candidates.append(os.path.join(str(media_root), 'csc_logo.png'))

    # 3. BASE_DIR / media / static locations
    base_dir = getattr(settings, 'BASE_DIR', '')
    if base_dir:
        candidates.append(os.path.join(str(base_dir), 'media', 'CSC LOGO.png'))
        candidates.append(os.path.join(str(base_dir), 'static', 'images', 'logo.png'))
        candidates.append(os.path.join(str(base_dir), 'static', 'images', 'CSC LOGO.png'))

    logo_path = None
    for cand in candidates:
        if cand and os.path.isfile(cand):
            logo_path = cand
            break

    if not logo_path:
        logger.warning(
            "⚠️ CSC India logo file could not be found at any configured location. Checked: %s",
            candidates
        )
        return None

    try:
        with open(logo_path, 'rb') as f:
            data = f.read()

        filename = os.path.basename(logo_path)
        ext = os.path.splitext(filename)[1].lower().lstrip('.')
        if ext == 'jpg':
            ext = 'jpeg'
        subtype = ext if ext in ['png', 'jpeg', 'gif', 'webp'] else 'png'
        cid = 'csc_logo'

        _CSC_LOGO_CACHE = {
            'data': data,
            'subtype': subtype,
            'filename': filename,
            'cid': cid,
            'path': logo_path,
        }
        logger.info(f"Loaded and cached CSC India logo from {logo_path} ({len(data)} bytes, {subtype})")
        return _CSC_LOGO_CACHE
    except Exception as e:
        logger.warning(f"⚠️ Error reading CSC India logo from {logo_path}: {e}")
        return None


def send_certificate_email(certificate_obj):
    """
    Send internship offer letter via email with provided template.
    """
    try:
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        from django.utils import timezone
        import logging
        import os

        logger = logging.getLogger(__name__)

        # Check global automation setting
        from .models import SystemConfiguration
        config = SystemConfiguration.get_solo()
        if not config.email_automation_enabled:
            logger.warning(f"⚠️ Email sending skipped for {certificate_obj.email}: Automation is disabled.")
            return

        if not certificate_obj.certificate_image:
            raise ValueError("Certificate image must be generated first")

        subject = "Internship Offer Letter - Council for Skills and Competencies (CSC India)"
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = [certificate_obj.email]
        
        # Calculate duration or use what's in the object
        duration = getattr(certificate_obj, 'internship_duration', '')
        if not duration and certificate_obj.start_date and certificate_obj.end_date:
            months = (certificate_obj.end_date.year - certificate_obj.start_date.year) * 12 + (certificate_obj.end_date.month - certificate_obj.start_date.month)
            if months > 0:
                duration = f"{months} Months"
            else:
                 duration = "2 Months" # Fallback

        internship_title = certificate_obj.internship_title or certificate_obj.course

        # Format duration with dates if available
        display_duration = duration
        if certificate_obj.start_date and certificate_obj.end_date:
            start_fmt = certificate_obj.start_date.strftime('%d %b %Y')
            end_fmt = certificate_obj.end_date.strftime('%d %b %Y')
            display_duration = f"{duration} (From {start_fmt} to {end_fmt})"

        # Plain text fallback
        text_content = f"""
Subject: Internship Offer – Council for Skills and Competencies (CSC India)

Dear {certificate_obj.full_name},

Greetings from the Council for Skills and Competencies (CSC India)!

We are pleased to inform you that you have been selected for the Internship offered by the Council for Skills and Competencies (CSC India).

The details of your internship are as follows:

* Internship Title: {internship_title}
* Internship Duration: {display_duration}


During this internship, you will gain exposure to industry-relevant tools, practical knowledge, and hands-on experience, guided by expert mentors and structured learning modules. You will be expected to actively participate in all assigned tasks, training sessions, and project activities throughout the internship period.

Further details regarding onboarding, communication channels, and your mentor assignment will be shared with you shortly.

We believe this internship will be a valuable learning experience and will contribute meaningfully to your career development.

To confirm your acceptance, please sign this letter and send a scanned copy to us by within 2 Days.

For any queries, feel free to contact us at {settings.DEFAULT_FROM_EMAIL}.

We look forward to having you onboard.

Warm regards,
Certificate Management Team  
Council for Skills and Competencies (CSC India)  
Visakhapatnam, Andhra Pradesh, India

WhatsApp: 9666500222  
Email: rammohan@cscindia.org.in  
Website: https://cscindia.org.in
"""

        # Determine logo configuration for email
        logo_info = get_csc_logo_info()
        if logo_info:
            logo_cid = logo_info['cid']
            logo_src = f"cid:{logo_cid}"
            has_inline_logo = True
        else:
            base_url = getattr(settings, 'BASE_URL', 'https://offerletters.cscindia.org.in')
            logo_src = f"{str(base_url).rstrip('/')}/media/CSC%20LOGO.png"
            has_inline_logo = False

        # HTML version
        html_content = f"""
<html>
<head>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            color: #333;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 700px;
            margin: auto;
            background: #fff;
            padding: 30px;
            border: 1px solid #eee;
            border-radius: 8px;
        }}
        p {{
            margin-bottom: 15px;
        }}
        ul {{
            list-style-type: none;
            padding: 0;
        }}
        li {{
            margin-bottom: 8px;
        }}
        .signature {{
            margin-top: 30px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div style="text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
            <img src="{logo_src}" alt="Council for Skills and Competencies (CSC India)" width="200" style="max-width: 200px; width: 100%; height: auto; display: block; margin: 0 auto; border: 0; outline: none; text-decoration: none;" />
        </div>

        <p>Dear {certificate_obj.full_name},</p>

        <p>Greetings from the <strong>Council for Skills and Competencies (CSC India)</strong>!</p>

        <p>We are pleased to inform you that <strong>you have been selected</strong> for the <strong> Internship</strong> offered by the <strong>Council for Skills and Competencies (CSC India).</strong></p>

        <p>The details of your internship are as follows:</p>

        <ul>
            <li><strong>Internship Title:</strong> {internship_title}</li>
            <li><strong>Internship Duration:</strong> {display_duration}</li>
            <li><strong>Under Initiative:</strong> Council for Skills and Competencies (CSC India)</li>
        </ul>

        

        <p>During this internship, you will gain exposure to industry-relevant tools, practical knowledge, and hands-on experience, guided by expert mentors and structured learning modules. You will be expected to actively participate in all assigned tasks, training sessions, and project activities throughout the internship period.</p>

        <p>Further details regarding onboarding, communication channels, and your mentor assignment will be shared with you shortly.</p>

        <p>We believe this internship will be a valuable learning experience and will contribute meaningfully to your career development.</p>

        <p>To confirm your acceptance, please sign this letter and send a scanned copy to us by within 2 Days.</p>

        <p>For any queries, feel free to contact us at <a href="mailto:{settings.DEFAULT_FROM_EMAIL}">{settings.DEFAULT_FROM_EMAIL}</a>.</p>

        <p>We look forward to having you onboard.</p>

        <div class="signature">
            <p>Warm regards,</p>
            <strong>Learning Management Team</strong><br>
            Council for Skills and Competencies (CSC India)<br>
            Visakhapatnam, Andhra Pradesh, India<br><br>
            <b>WhatsApp/Phone Number:</b> <b>9666500222, 7901500222</b><br>
            <b>Email:</b> <b><a href="mailto:rammohan@cscindia.org.in">rammohan@cscindia.org.in</a></b><br>
            <b>LMS:</b> <a href="https://learn.cscindia.org.in/" target="_blank">learn.cscindia.org.in</a><br>
            <b>Website:</b> <a href="https://cscindia.org.in" target="_blank">cscindia.org.in</a><br>
            <b>Offer Letters:</b> <a href="https://offerletters.cscindia.org.in" target="_blank">offerletters.cscindia.org.in</a>
        </div>
    </div>
</body>
</html>
"""

        # Compose and attach email contents
        # Note: Gmail will use the authenticated account (EMAIL_HOST_USER) as the sender
        # But we can set Reply-To to support@cscindia.org.in
        email = EmailMultiAlternatives(subject, text_content, from_email, to_email)
        email.attach_alternative(html_content, "text/html")
        # Set Reply-To header to support@cscindia.org.in
        email.reply_to = ['support@cscindia.org.in']

        # Attach inline logo with Content-ID if available
        if has_inline_logo and logo_info:
            try:
                from email.mime.image import MIMEImage
                logo_part = MIMEImage(logo_info['data'], _subtype=logo_info['subtype'])
                logo_part.add_header('Content-ID', f"<{logo_info['cid']}>")
                logo_part.add_header('Content-Disposition', 'inline', filename=logo_info['filename'])
                email.attach(logo_part)
            except Exception as logo_err:
                logger.warning(f"⚠️ Failed to attach inline logo: {logo_err}. Proceeding with email delivery.")

        # Build email attachment filename: RollNumber_Name_MobileNumber.png
        email_parts = []
        if certificate_obj.roll_number:
            email_parts.append(certificate_obj.roll_number.replace(' ', '_'))
        if certificate_obj.full_name:
            email_parts.append(certificate_obj.full_name.replace(' ', '_'))
        if certificate_obj.candidate_mobile:
            email_parts.append(certificate_obj.candidate_mobile.replace(' ', ''))
        image_filename = "_".join(email_parts) + ".png" if email_parts else "OfferLetter.png"
        with open(certificate_obj.certificate_image.path, 'rb') as f:
            email.attach(image_filename, f.read(), 'image/png')
        
        # Attach PDF if available using ROLL NUMBER
        if certificate_obj.certificate_pdf:
            pdf_filename = f"{certificate_obj.roll_number.replace(' ', '_')}.pdf"
            with open(certificate_obj.certificate_pdf.path, 'rb') as f:
                email.attach(pdf_filename, f.read(), 'application/pdf')

        # Send email
        email.send()

        # Update certificate status
        certificate_obj.email_sent = True
        certificate_obj.email_sent_at = timezone.now()
        certificate_obj.save()

        logger.info(f"✅ Certificate email sent successfully to {certificate_obj.email}")

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Error sending certificate email: {str(e)}")
        raise


def upload_to_google_drive(certificate_obj):
    """
    Upload certificate to Google Drive with student name as filename.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
        from googleapiclient.http import MediaFileUpload
        from django.conf import settings
        from django.utils import timezone
        import os
        import logging

        logger = logging.getLogger(__name__)

        if not certificate_obj.certificate_image:
            raise ValueError("Certificate image must be generated first")

        credentials_file = settings.GOOGLE_DRIVE_CREDENTIALS_FILE
        if not credentials_file or not os.path.exists(credentials_file):
            raise FileNotFoundError("Google Drive credentials file not found")

        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        credentials = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        service = build('drive', 'v3', credentials=credentials)

        # File name is just student's name
        file_name = f"{certificate_obj.full_name.replace(' ', '_')}.png"
        file_metadata = {
            'name': file_name,
            'parents': [settings.GOOGLE_DRIVE_FOLDER_ID] if settings.GOOGLE_DRIVE_FOLDER_ID else []
        }

        media = MediaFileUpload(
            certificate_obj.certificate_image.path,
            mimetype='image/png'
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        # Save file ID and update status
        certificate_obj.drive_uploaded = True
        certificate_obj.drive_file_id = file.get('id')
        certificate_obj.drive_uploaded_at = timezone.now()
        certificate_obj.save()

        logger.info(f"Certificate uploaded to Google Drive: {file.get('id')}")
        return file.get('id')

    except Exception as e:
        logger.error(f"Error uploading to Google Drive: {str(e)}")
        raise


# def upload_to_google_drive(certificate_obj):
#     """
#     Upload certificate to Google Drive
#     """
#     from django.conf import settings
#     import os
#     import logging

#     logger = logging.getLogger(__name__)

#     logger.info("📁 Checking Google Drive credentials file:")
#     logger.info(f"Path: {settings.GOOGLE_DRIVE_CREDENTIALS_FILE}")
#     logger.info(f"Exists: {os.path.exists(settings.GOOGLE_DRIVE_CREDENTIALS_FILE)}")

#     try:
#         from googleapiclient.discovery import build
#         from google.oauth2.service_account import Credentials
#         from googleapiclient.http import MediaFileUpload
#         from django.utils import timezone

#         if not certificate_obj.certificate_image:
#             raise ValueError("Certificate image must be generated first")

#         # Check if credentials file exists
#         credentials_file = settings.GOOGLE_DRIVE_CREDENTIALS_FILE
#         if not credentials_file or not os.path.exists(credentials_file):
#             raise FileNotFoundError("Google Drive credentials file not found")

#         # Set up credentials and service
#         SCOPES = ['https://www.googleapis.com/auth/drive.file']
#         credentials = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
#         service = build('drive', 'v3', credentials=credentials, cache_discovery=False)

#         # Prepare file metadata
#         file_name = f"certificate_{certificate_obj.full_name.replace(' ', '_')}_{certificate_obj.certificate_id}.png"
#         file_metadata = {
#             'name': file_name,
#             'parents': [settings.GOOGLE_DRIVE_FOLDER_ID] if settings.GOOGLE_DRIVE_FOLDER_ID else []
#         }

#         # Upload file
#         media = MediaFileUpload(
#             certificate_obj.certificate_image.path,
#             mimetype='image/png'
#         )

#         file = service.files().create(
#             body=file_metadata,
#             media_body=media,
#             fields='id'
#         ).execute()

#         # Update certificate status
#         certificate_obj.drive_uploaded = True
#         certificate_obj.drive_file_id = file.get('id')
#         certificate_obj.drive_uploaded_at = timezone.now()
#         certificate_obj.save()

#         logger.info(f"✅ Certificate uploaded to Google Drive: {file.get('id')}")
#         return file.get('id')

#     except Exception as e:
#         logger.error(f"❌ Error uploading to Google Drive: {str(e)}")
#         raise

def process_excel_file(excel_file):
    """
    Process an Excel file to bulk-generate offer letters.
    """
    try:
        workbook = openpyxl.load_workbook(excel_file)
        sheet = workbook.active

        # Get header row
        header = [cell.value for cell in sheet[1]]

        # Find student_id column
        if 'student_id' not in header:
            raise ValueError("student_id column not found in Excel file")

        student_id_index = header.index('student_id')

        # Process each row
        for row in sheet.iter_rows(min_row=2, values_only=True):
            student_id = row[student_id_index]
            
            # Create offer_letter_data from row
            offer_letter_data = {header[i]: row[i] for i in range(len(header))}
            
            # Save offer letter to database
            save_offer_letter_to_db(offer_letter_data, student_id)

    except Exception as e:
        logger.error(f"Error processing Excel file: {str(e)}")
        raise
    
def process_excel_chunked(file_path, file_extension, issue_date, chunk_size=1000):
    """
    Process Excel/CSV file in chunks to avoid memory issues with large files.
    Uses bulk_create for efficient database inserts with duplicate detection.
    
    Returns: (success_count, failure_count, duplicate_count, total_rows)
    """
    import pandas as pd
    from .models import Certificate_student
    from datetime import datetime
    from dateutil.parser import parse as dateutil_parse
    
    logger.info(f"Starting chunked processing of file: {file_path}")
    
    # Read file based on its extension
    if file_extension == 'csv':
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding='latin-1')
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding='cp1252')
    elif file_extension in ['xlsx', 'xls']:
        # For Excel, read in chunks
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")
    
    df.columns = df.columns.str.strip()
    total_rows = len(df)
    logger.info(f"Total rows in file: {total_rows}")
    
    # Create case-insensitive column mapping
    column_map = {col.lower(): col for col in df.columns}
    
    # Helper functions
    def _get_column_value(row, variants):
        """Get value from row trying multiple column name variants"""
        for variant in variants:
            if variant.lower() in column_map:
                actual_col = column_map[variant.lower()]
                val = row.get(actual_col)
                if pd.notna(val) and str(val).strip() != '':
                    return val
        return None
    
    def _clean_nan(val):
        if pd.isna(val) or str(val).lower().strip() == 'nan':
            return ''
        return str(val).strip()
    
    def _normalize_date(val):
        if pd.isna(val):
            return None
        if hasattr(val, 'strftime'):
            return val.strftime('%d-%m-%Y')
        try:
            parsed = dateutil_parse(str(val))
            if parsed:
                return parsed.strftime('%d-%m-%Y')
        except Exception:
            pass
        return None
    
    # Column name variants
    name_variants = ['Name', 'Full Name', 'Full Name', 'Candidate Name', 'Student Name']
    roll_variants = ['Roll No', 'Roll Number', 'Roll Number']
    course_variants = ['Course', 'Course Name']
    college_variants = ['College Name', 'Institution Name']
    address_variants = ['Institution Address', 'College Address']
    mobile_variants = ['Candidate Mobile', 'Mobile', 'Contact']
    email_variants = ['Candidate Email', 'Email', 'e-mail']
    title_variants = ['Internship Title', 'Title', 'Subject']
    duration_variants = ['Internship Duration', 'Duration', 'Months']
    start_date_variants = ['Start Date', 'Start_Date', 'StartDate', 'start_date', 'Start', 'startdate']
    end_date_variants = ['End Date', 'End_Date', 'EndDate', 'end_date', 'End', 'enddate']
    
    success_count = 0
    failure_count = 0
    duplicate_count = 0
    students_to_create = []
    processed_combinations = set()  # Track combinations within current upload
    
    # Process in chunks
    for i in range(0, total_rows, chunk_size):
        chunk = df.iloc[i:i + chunk_size]
        logger.info(f"Processing chunk {i//chunk_size + 1}: rows {i+1} to {min(i+chunk_size, total_rows)}")
        
        for _, row in chunk.iterrows():
            try:
                candidate_name = _get_column_value(row, name_variants) or ''
                roll_number = _get_column_value(row, roll_variants) or ''
                course_name = _get_column_value(row, course_variants) or ''
                institution_name = _get_column_value(row, college_variants) or ''
                institution_address = _get_column_value(row, address_variants) or ''
                candidate_mobile = _get_column_value(row, mobile_variants) or ''
                candidate_email = _get_column_value(row, email_variants) or ''
                internship_title = _get_column_value(row, title_variants) or ''
                internship_duration = _get_column_value(row, duration_variants) or ''
                
                # Clean mobile number
                if candidate_mobile:
                    try:
                        candidate_mobile = str(int(float(candidate_mobile)))
                    except (ValueError, TypeError):
                        candidate_mobile = str(candidate_mobile).strip()
                
                # Normalize dates
                start_date_val = _get_column_value(row, start_date_variants)
                end_date_val = _get_column_value(row, end_date_variants)
                internship_start_date = _normalize_date(start_date_val)
                internship_end_date = _normalize_date(end_date_val)
                
                # Parse dates for database
                start_date_obj = None
                end_date_obj = None
                if internship_start_date:
                    try:
                        start_date_obj = datetime.strptime(internship_start_date, '%d-%m-%Y').date()
                    except ValueError:
                        pass
                if internship_end_date:
                    try:
                        end_date_obj = datetime.strptime(internship_end_date, '%d-%m-%Y').date()
                    except ValueError:
                        pass
                
                # Create duplicate key for checking
                # Use tuple of (roll_number, email, full_name, internship_title, start_date, end_date)
                # IMPORTANT: Use raw date strings when parsing fails so different dates
                # don't collapse to the same None key and get falsely skipped as duplicates
                start_key = start_date_obj.isoformat() if start_date_obj else (str(start_date_val).strip() if start_date_val is not None and not pd.isna(start_date_val) else '')
                end_key = end_date_obj.isoformat() if end_date_obj else (str(end_date_val).strip() if end_date_val is not None and not pd.isna(end_date_val) else '')
                
                duplicate_key = _clean_nan(roll_number).strip().lower()
                
                # Check if this combination already exists in current upload (only for non-empty roll numbers)
                if duplicate_key and duplicate_key in processed_combinations:
                    logger.info(f"Skipping duplicate within current upload: {candidate_name} ({roll_number})")
                    duplicate_count += 1
                    continue
                
                # Check if this combination already exists in database (only for non-empty roll numbers)
                if duplicate_key:
                    existing = Certificate_student.objects.filter(
                        roll_number__iexact=_clean_nan(roll_number).strip()
                    ).first()
                    
                    if existing:
                        logger.info(f"Skipping existing database record: {candidate_name} ({roll_number})")
                        duplicate_count += 1
                        processed_combinations.add(duplicate_key)
                        continue
                
                # Add to processed combinations (only for non-empty roll numbers)
                if duplicate_key:
                    processed_combinations.add(duplicate_key)
                
                # Create student object (without saving yet)
                student = Certificate_student(
                    full_name=_clean_nan(candidate_name),
                    roll_number=_clean_nan(roll_number),
                    course=_clean_nan(course_name),
                    college_name=_clean_nan(institution_name),
                    affiliated_name='',
                    start_date=start_date_obj,
                    end_date=end_date_obj,
                    issue_date=issue_date,
                    email=_clean_nan(candidate_email),
                    contact=_clean_nan(candidate_mobile),
                    gender='',
                    internship_title=_clean_nan(internship_title),
                    internship_duration=_clean_nan(internship_duration),
                    institution_address=_clean_nan(institution_address),
                )
                students_to_create.append(student)
                
            except Exception as e:
                failure_count += 1
                logger.error(f"Error processing row: {str(e)}")
        
        # Bulk create this chunk
        if students_to_create:
            try:
                Certificate_student.objects.bulk_create(students_to_create, batch_size=500, ignore_conflicts=True)
                logger.info(f"Bulk created {len(students_to_create)} records")
                success_count += len(students_to_create)
                students_to_create = []  # Clear for next chunk
            except Exception as e:
                logger.error(f"Bulk create failed: {str(e)}")
                # Fallback to individual saves
                for student in students_to_create:
                    try:
                        student.save()
                        success_count += 1
                    except Exception as save_error:
                        logger.error(f"Individual save failed: {str(save_error)}")
                        failure_count += 1
                students_to_create = []
    
    # Create any remaining records
    if students_to_create:
        try:
            Certificate_student.objects.bulk_create(students_to_create, batch_size=500, ignore_conflicts=True)
            logger.info(f"Bulk created final {len(students_to_create)} records")
            success_count += len(students_to_create)
        except Exception as e:
            logger.error(f"Final bulk create failed: {str(e)}")
    
    logger.info(f"Chunked processing complete: {success_count} created, {failure_count} failures, {duplicate_count} duplicates skipped")
    return success_count, failure_count, duplicate_count, total_rows








def process_certificate_request(form_data):
    """
    Complete certificate processing workflow:
    1. Create certificate
    2. Generate image and QR code
    3. Send email
    4. Upload to Google Drive
    """
    try:
        # Create and generate certificate
        certificate = create_certificate_from_form_data(form_data)
        
        # Send email (if configured)
        
        # try:
        #     send_certificate_email(certificate)
        # except Exception as e:
        #     logger.warning(f"Email sending failed: {e}")
        
        # # Upload to Google Drive (if configured)
        # try:
        #     upload_to_google_drive(certificate)
        # except Exception as e:
        #     logger.warning(f"Google Drive upload failed: {e}")
        
        return certificate
        
    except Exception as e:
        logger.error(f"Error processing certificate request: {str(e)}")
        raise
    




