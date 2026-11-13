from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.db.models.functions import Lower
from django.conf import settings
import json
import logging
import os
from datetime import datetime

from .models import Certificate
from .forms import CertificateForm, CertificateSearchForm, ContactForm, OfferLetterForm
from .utils import process_certificate_request, save_offer_letter_to_database, send_certificate_email, is_virtual_offer_type, is_physical_offer_type, get_offer_type_choices

logger = logging.getLogger(__name__)

from decimal import Decimal
def clean_stipend_value(val):
    if val is None:
        return None
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except ImportError:
        pass
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ('nan', 'none', 'null', 'nat', ''):
        return None
    for char in ['₹', '$', ',', 'Rs', 'rs', 'RS']:
        val_str = val_str.replace(char, '')
    val_str = val_str.strip()
    try:
        f_val = float(val_str)
        nearest_int = round(f_val)
        if abs(f_val - nearest_int) < 0.10:
            return Decimal(str(nearest_int))
        rounded_val = round(f_val, 2)
        return Decimal(f"{rounded_val:.2f}")
    except (ValueError, TypeError):
        return None
   
from django.contrib.auth.decorators import login_required
@login_required
def home(request):
    """Home page view"""
    recent_certificates = Certificate.objects.filter(is_verified=True)[:6]
    stats = {
        'total_certificates': Certificate.objects.count(),
        'verified_certificates': Certificate.objects.filter(is_verified=True).count(),
        'emails_sent': Certificate.objects.filter(email_sent=True).count(),
    }
    
    from .models import SystemConfiguration
    system_config = SystemConfiguration.get_solo()
    
    context = {
        'recent_certificates': recent_certificates,
        'stats': stats,
        'system_config': system_config,
    }
    return render(request, 'certificates/home.html', context)



def generate_certificate(request):
    """Offer letter generation view - automatically uses student data from admin panel"""
    from .models import Certificate_student
    from datetime import datetime
    
    # Handle clearing old session data
    clear_session = request.GET.get('clear', None)
    if clear_session == 'true':
        if 'offer_letter_data' in request.session:
            del request.session['offer_letter_data']
        return redirect('generate_certificate')
    
    # Handle manual form submission (POST)
    if request.method == 'POST':
        form = OfferLetterForm(request.POST)
        if form.is_valid():
            try:
                # Convert form data to offer letter data format
                cleaned = form.cleaned_data.copy()
                
                # Handle optional dates
                start_date = form.cleaned_data.get('internship_start_date')
                end_date = form.cleaned_data.get('internship_end_date')

                # Calculate end date if start date is given but end date is not
                if start_date and not end_date:
                    duration_str = cleaned.get('internship_duration', '')
                    try:
                        months = int(duration_str.split()[0]) if 'Month' in duration_str else 2
                    except (ValueError, IndexError):
                        months = 2
                    
                    if months > 0:
                        from datetime import timedelta
                        # Approximate months to days for timedelta
                        # Using 30.44 days per month on average for more accuracy
                        end_date = start_date + timedelta(days=int(months * 30.44))
                stipend_val = cleaned.get('stipend')
                stipend_amount = clean_stipend_value(stipend_val)
                
                offer_letter_data = {
                    'candidate_name': cleaned.get('candidate_name', ''),
                    'roll_number': cleaned.get('roll_number', ''),
                    'course_name': cleaned.get('course_name', ''),
                    'institution_name': cleaned.get('institution_name', ''),
                    'institution_address': cleaned.get('institution_address', ''),
                    'institution_phone': cleaned.get('institution_phone', ''),
                    'candidate_mobile': cleaned.get('candidate_mobile', ''),
                    'candidate_email': cleaned.get('candidate_email', ''),
                    'internship_title': cleaned.get('internship_title', ''),
                    'internship_duration': cleaned.get('internship_duration', ''),
                    'issue_date': (
                        cleaned.get('issue_date').isoformat()
                        if cleaned.get('issue_date')
                        else datetime.now().strftime('%Y-%m-%d')
                    ),
                    'stipend_amount': stipend_amount,
                }

                if start_date:
                    offer_letter_data['internship_start_date'] = start_date.isoformat()
                if end_date:
                    offer_letter_data['internship_end_date'] = end_date.isoformat()
                
                # Save offer letter to database
                try:
                    from .utils import save_offer_letter_to_database, send_certificate_email
                    # Get offer_type from form - use it as the template name
                    offer_type = form.cleaned_data.get('offer_type', '')
                    selected_template = offer_type or form.cleaned_data.get('template')
                    certificate = save_offer_letter_to_database(offer_letter_data, template_name=selected_template)

                    # Save offer_type on the certificate record
                    if offer_type:
                        certificate.offer_type = offer_type
                        certificate.save(update_fields=['offer_type'])

                    # Virtual: send email automatically; Physical: skip email, provide download
                    if is_virtual_offer_type(offer_type):
                        try:
                            send_certificate_email(certificate)
                            logger.info(f"✅ Virtual offer letter generated and emailed for {offer_letter_data.get('candidate_name')} (Roll No: {offer_letter_data.get('roll_number')})")
                        except Exception as e:
                            logger.error(f"❌ Email sending failed for {offer_letter_data.get('candidate_name')}: {str(e)}")
                            messages.warning(request, f"Offer letter generated but email sending failed: {e}")
                    else:
                        logger.info(f"✅ Physical offer letter generated for {offer_letter_data.get('candidate_name')} (Roll No: {offer_letter_data.get('roll_number')}) - ready for download/print")
                except Exception as e:
                    logger.error(f"Error saving offer letter to database: {str(e)}")
                    messages.warning(
                        request,
                        f'Offer letter generated but database save failed: {str(e)}. You can still download the offer letter.'
                    )
                
                # Convert date objects to isoformat strings to allow JSON session serialization
                for date_field in ['internship_start_date', 'internship_end_date']:
                    value = cleaned.get(date_field)
                    if hasattr(value, 'isoformat'):
                        offer_letter_data[date_field] = value.isoformat()
                # Convert Decimal stipend to float for JSON session serialization
                if isinstance(offer_letter_data.get('stipend_amount'), Decimal):
                    offer_letter_data['stipend_amount'] = float(offer_letter_data['stipend_amount'])
                
                # Store in session for download
                request.session['offer_letter_data'] = offer_letter_data
                
                # Redirect to same page with preview option
                return redirect('generate_certificate')
            except Exception as e:
                logger.error(f"Error processing offer letter: {str(e)}")
                messages.error(
                    request, 
                    'An error occurred while processing your offer letter. Please try again.'
                )
        else:
            logger.error(f"Form validation errors: {form.errors}")
            messages.error(request, 'Please correct the errors below.')
            # form is already bound to POST data, no need to re-initialize
            # form = OfferLetterForm(request.POST)
    else:
        form = OfferLetterForm()
    
    # Handle student selection and offer letter generation (GET)
    student_id = request.GET.get('student_id', None)
    generate_action = request.GET.get('action', None)
    clear_session = request.GET.get('clear', None)
    
    # Clear old session data if requested
    if clear_session == 'true':
        if 'offer_letter_data' in request.session:
            del request.session['offer_letter_data']
        return redirect('generate_certificate')
    
    # Get all students from admin panel
    students = Certificate_student.objects.all().order_by('-created_at')
    
    # If student is selected, generate offer letter automatically
    if student_id and generate_action == 'generate':
        try:
            student = Certificate_student.objects.get(id=student_id)
            issue_date_param = request.GET.get('issue_date')
            if issue_date_param:
                try:
                    datetime.strptime(issue_date_param, '%Y-%m-%d')
                except ValueError:
                    issue_date_param = None
            
            # Calculate internship duration from dates if both exist
            start = student.start_date
            end = student.end_date
            
            # Determine internship duration
            # Priority: 1. Field from database, 2. Calculated from dates, 3. Default
            duration_text = student.internship_duration
            if not duration_text or duration_text.lower().strip() == 'nan':
                if start and end and start != end:
                    months = (end.year - start.year) * 12 + (end.month - start.month)
                    if months > 0:
                        duration_text = f"{months} Month{'s' if months != 1 else ''}"
                    else:
                        duration_text = "2 Months"
                else:
                    duration_text = "2 Months"
            
            # Map Certificate_student fields to offer letter data format
            offer_letter_data = {
                'candidate_name': student.full_name,
                'roll_number': student.roll_number,
                'course_name': student.course,  # Branch/Course name
                'institution_name': student.college_name,
                'institution_address': student.institution_address or '',
                'candidate_mobile': student.contact,
                'candidate_email': student.email,
                'internship_title': student.internship_title or student.course,
                'internship_duration': duration_text,
                'issue_date': issue_date_param or datetime.now().strftime('%Y-%m-%d'),
                'stipend_amount': clean_stipend_value(student.stipend_amount),
            }
            
            # Only add dates if they are provided and meaningful (not just same default)
            if start and end and start != end:
                 offer_letter_data['internship_start_date'] = start.isoformat()
                 offer_letter_data['internship_end_date'] = end.isoformat()
            elif start: # If only start is somehow there (shouldn't happen with current models but good for future)
                 offer_letter_data['internship_start_date'] = start.isoformat()
                 # Calculate end date if only start is present
                 try:
                     # Default to 2 months if we only have a start date
                     from datetime import timedelta
                     end = start + timedelta(days=61) # ~2 months
                     offer_letter_data['internship_end_date'] = end.isoformat()
                 except: pass
            
            # Save offer letter to database
            try:
                from .utils import save_offer_letter_to_database, send_certificate_email
                # Get offer_type from request (falls back to template param for backward compat)
                offer_type = request.GET.get('offer_type') or request.POST.get('offer_type', '')
                selected_template = offer_type or request.GET.get('template') or request.POST.get('template', 'OfferLetter')
                certificate = save_offer_letter_to_database(offer_letter_data, student=student, template_name=selected_template)

                # Save offer_type on the certificate record
                if offer_type:
                    certificate.offer_type = offer_type
                    certificate.save(update_fields=['offer_type'])

                # Virtual: send email; Physical: skip email, download/print
                if is_virtual_offer_type(offer_type):
                    try:
                        send_certificate_email(certificate)
                        messages.success(request, f'Virtual offer letter generated and emailed successfully to {student.email}!')
                    except Exception as e:
                        logger.error(f"Failed to send email: {e}")
                        messages.warning(request, f"Offer letter generated but email sending failed: {e}")
                else:
                    messages.success(request, f'Physical offer letter generated for {student.full_name} - ready for download/print.')
            except Exception as e:
                logger.error(f"Error saving offer letter to database: {str(e)}")
                messages.warning(
                    request,
                    f'Offer letter generated but database save failed: {str(e)}. You can still download the offer letter.'
                )
            
            # Store in session for download
            request.session['offer_letter_data'] = offer_letter_data
            request.session['last_certificate_id'] = certificate.id
            
            return redirect('generate_certificate')
            
        except Certificate_student.DoesNotExist:
            messages.error(request, 'Student not found.')
        except Exception as e:
            logger.error(f"Error generating offer letter: {str(e)}")
            messages.error(request, f'An error occurred: {str(e)}')
    
    # Get stored offer letter data for preview if available
    # Only show if we just generated it (has student_id in URL) or from POST
    # Clear it if just visiting the page normally
    offer_letter_data = None
    if student_id and generate_action == 'generate':
        # Just generated, get from session
        offer_letter_data = request.session.get('offer_letter_data', None)
    elif request.method == 'POST':
        # From form submission, get from session
        offer_letter_data = request.session.get('offer_letter_data', None)
    else:
        # Just visiting the page, clear old data
        if 'offer_letter_data' in request.session:
            del request.session['offer_letter_data']
        if 'last_certificate_id' in request.session:
            del request.session['last_certificate_id']
    
    # Get the real certificate object for URLs if we have data
    certificate_record = None
    if offer_letter_data:
        last_id = request.session.get('last_certificate_id')
        if last_id:
            try:
                certificate_record = Certificate.objects.get(id=last_id)
            except Certificate.DoesNotExist:
                pass
    
    # Format dates for display if offer_letter_data exists
    if offer_letter_data:
        try:
            if isinstance(offer_letter_data.get('internship_start_date'), str):
                start_date = datetime.strptime(offer_letter_data['internship_start_date'], '%Y-%m-%d')
                offer_letter_data['internship_start_date'] = start_date.strftime('%B %d, %Y')
        except (ValueError, TypeError):
            pass
        
        try:
            if isinstance(offer_letter_data.get('internship_end_date'), str):
                end_date = datetime.strptime(offer_letter_data['internship_end_date'], '%Y-%m-%d')
                offer_letter_data['internship_end_date'] = end_date.strftime('%B %d, %Y')
        except (ValueError, TypeError):
            pass

        # Format issue date for display (keep raw value for downloads/session)
        try:
            issue_date_raw = offer_letter_data.get('issue_date')
            if isinstance(issue_date_raw, str):
                try:
                    issue_date_dt = datetime.strptime(issue_date_raw, '%Y-%m-%d')
                except ValueError:
                    issue_date_dt = datetime.strptime(issue_date_raw, '%d-%m-%Y')
                offer_letter_data['issue_date_display'] = issue_date_dt.strftime('%B %d, %Y')
        except (ValueError, TypeError):
            pass
    
    # Initialize form for manual entry (optional) - check if already initialized
    if 'form' not in locals():
        form = OfferLetterForm()
    
    from .models import SystemConfiguration
    system_config = SystemConfiguration.get_solo()
    
    context = {
        'page_title': 'Generate Offer Letter',
        'students': students,
        'offer_letter_data': offer_letter_data,
        'certificate_record': certificate_record,
        'selected_student_id': student_id,
        'form': form,  # For manual entry option
        'system_config': system_config,
    }
    return render(request, 'certificates/generate.html', context)


def download_offer_letter_pdf(request):
    """Download offer letter as PDF"""
    offer_letter_data = request.session.get('offer_letter_data', None)
    
    if not offer_letter_data:
        messages.error(request, 'No offer letter data found. Please fill in the form first.')
        return redirect('generate_certificate')
    
    try:
        from .utils import generate_offer_letter_pdf
        
        # Generate PDF
        pdf_buffer = generate_offer_letter_pdf(offer_letter_data)
        
        # Create response
        candidate_name = offer_letter_data.get('candidate_name', 'OfferLetter').replace(' ', '_')
        filename = f"Offer_Letter_{candidate_name}.pdf"
        
        response = HttpResponse(pdf_buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating offer letter PDF: {str(e)}")
        messages.error(request, 'An error occurred while generating the PDF. Please try again.')
        return redirect('generate_certificate')


def download_offer_letter_image(request):
    """Download offer letter as PNG image"""
    offer_letter_data = request.session.get('offer_letter_data', None)
    
    if not offer_letter_data:
        messages.error(request, 'No offer letter data found. Please fill in the form first.')
        return redirect('generate_certificate')
    
    try:
        from .utils import generate_offer_letter_image
        from datetime import datetime
        
        # Add issue date if not present
        if 'issue_date' not in offer_letter_data:
            offer_letter_data['issue_date'] = datetime.now().strftime('%Y-%m-%d')
        
        # Generate image
        image_buffer = generate_offer_letter_image(offer_letter_data)
        
        # Build filename: RollNumber_Name_MobileNumber.png (skip missing fields)
        gen_parts = []
        roll_number = offer_letter_data.get('roll_number', '').strip()
        name = offer_letter_data.get('candidate_name', '').strip()
        mobile = offer_letter_data.get('candidate_mobile', '').strip()
        if roll_number:
            gen_parts.append(roll_number.replace(' ', '_'))
        if name:
            gen_parts.append(name.replace(' ', '_'))
        if mobile:
            gen_parts.append(mobile.replace(' ', ''))
        filename = f"Offer_Letter_{'_'.join(gen_parts)}.png" if gen_parts else "Offer_Letter.png"
        
        response = HttpResponse(image_buffer.read(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating offer letter image: {str(e)}")
        messages.error(request, 'An error occurred while generating the image. Please try again.')
        return redirect('generate_certificate')


@login_required
def generate_offer_letter(request):
    """Offer letter generation form view - supports Solo and Bulk modes"""
    from .forms import CertificateExcelForm

    if request.method == 'POST':
        mode = request.POST.get('mode', 'solo')

        if mode == 'bulk':
            # Handle bulk upload
            form = OfferLetterForm()
            bulk_form = CertificateExcelForm(request.POST, request.FILES)
            if bulk_form.is_valid():
                instance = bulk_form.save()
                file_path = instance.excel_file.path
                file_extension = file_path.split('.')[-1].lower()

                import pandas as pd
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
                    df = pd.read_excel(file_path)
                else:
                    messages.error(request, f"Unsupported file format: {file_extension}. Please upload CSV or Excel files.")
                    from .models import SystemConfiguration
                    system_config = SystemConfiguration.get_solo()
                    return render(request, 'certificates/generate_offer_letter.html', {
                        'form': form, 'bulk_form': bulk_form,
                        'page_title': 'Generate Offer Letter', 'system_config': system_config,
                    })

                df.columns = df.columns.str.strip()
                success_count = 0
                failure_count = 0
                duplicate_count = 0
                processed_combinations = set()

                from .models import Certificate_student
                for _, row in df.iterrows():
                    try:
                        candidate_name = row.get('Name') or row.get('Full Name') or row.get('Candidate Name')
                        roll_number = row.get('Roll No') or row.get('Roll Number')
                        course_name = row.get('Course') or row.get('Course Name')
                        institution_name = row.get('College Name') or row.get('Institution Name')
                        institution_address = row.get('Institution Address') or row.get('College Address') or ''
                        candidate_mobile = row.get('Candidate Mobile') or row.get('Mobile') or row.get('Contact') or ''
                        if pd.notna(candidate_mobile):
                            try:
                                candidate_mobile = str(int(float(candidate_mobile)))
                            except (ValueError, TypeError):
                                candidate_mobile = str(candidate_mobile).strip()
                        else:
                            candidate_mobile = ''
                        candidate_email = row.get('Candidate Email') or row.get('Email') or ''
                        internship_title = row.get('Internship Title') or row.get('Title') or row.get('Subject') or ''
                        raw_internship_duration = row.get('Internship Duration') or row.get('Duration') or row.get('Months') or ''
                        internship_duration = str(raw_internship_duration).strip()
                        
                        # --- Stipend from Excel or common field ---
                        raw_stipend = (row.get('Stipend') or row.get('Stipend Amount') or
                                       row.get('stipend') or row.get('stipend_amount'))
                        # Get common stipend fallback from form
                        common_stipend = bulk_form.cleaned_data.get('common_stipend_amount')
                        stipend_amount_row = clean_stipend_value(raw_stipend)
                        if stipend_amount_row is None and common_stipend is not None:
                            stipend_amount_row = clean_stipend_value(common_stipend)


                        start_date_val = row.get('Start Date')
                        end_date_val = row.get('End Date')

                        start_date_variants = ['Start Date', 'Start_Date', 'StartDate', 'start_date', 'Start']
                        end_date_variants = ['End Date', 'End_Date', 'EndDate', 'end_date', 'End']

                        found_start = None
                        found_end = None
                        for variant in start_date_variants:
                            if variant in df.columns:
                                found_start = row.get(variant)
                                break
                        for variant in end_date_variants:
                            if variant in df.columns:
                                found_end = row.get(variant)
                                break

                        if found_start is not None:
                            start_date_val = found_start
                        if found_end is not None:
                            end_date_val = found_end

                        def _normalize_date(val):
                            if pd.isna(val):
                                return ''
                            if hasattr(val, 'strftime'):
                                return val.strftime('%d-%m-%Y')
                            try:
                                from dateutil.parser import parse as dateutil_parse
                                parsed = dateutil_parse(str(val))
                                if parsed:
                                    return parsed.strftime('%d-%m-%Y')
                            except Exception:
                                try:
                                    if '-' in str(val):
                                        parts = str(val).split('-')
                                        if len(parts) == 3 and len(parts[0]) == 4:
                                            year, month, day = parts
                                            return f"{day}-{month}-{year}"
                                        elif len(parts) == 3 and len(parts[0]) <= 2:
                                            return str(val)
                                except Exception:
                                    pass
                        def _clean_nan(val):
                            if pd.isna(val) or str(val).lower().strip() == 'nan':
                                return ''
                            return str(val).strip()

                        internship_start_date = _normalize_date(start_date_val)
                        internship_end_date = _normalize_date(end_date_val)

                        # Dates are optional - proceed even if missing
                        start_date_obj = datetime.strptime(internship_start_date, '%d-%m-%Y').date() if internship_start_date else None
                        end_date_obj = datetime.strptime(internship_end_date, '%d-%m-%Y').date() if internship_end_date else None

                        upload_issue_date = instance.issue_date
                        if upload_issue_date:
                            issue_date_str = upload_issue_date.strftime('%d-%m-%Y')
                        else:
                            issue_date_str = datetime.now().strftime('%d-%m-%Y')

                        # --- Duplicate detection ---
                        from .utils import get_certificate_duplicate_key
                        row_key = get_certificate_duplicate_key({
                            'candidate_name': _clean_nan(candidate_name),
                            'roll_number': _clean_nan(roll_number),
                            'candidate_email': _clean_nan(candidate_email),
                            'candidate_mobile': _clean_nan(candidate_mobile),
                            'course_name': _clean_nan(course_name),
                            'institution_name': _clean_nan(institution_name),
                            'internship_title': _clean_nan(internship_title),
                            'internship_duration': _clean_nan(internship_duration),
                            'issue_date': upload_issue_date,
                            'internship_start_date': start_date_obj,
                            'internship_end_date': end_date_obj,
                            'offer_type': '',
                        })

                        row_11_key = row_key[:11]

                        # Check if this combination already exists in current upload
                        if row_11_key[1] and row_11_key in processed_combinations:
                            logger.info(f"Skipping duplicate within current upload: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                            duplicate_count += 1
                            continue

                        # Check if this combination already exists in database staging (Certificate_student)
                        existing_student = False
                        if roll_number:
                            for s in Certificate_student.objects.filter(roll_number__iexact=_clean_nan(roll_number).strip()):
                                if get_certificate_duplicate_key(s)[:11] == row_11_key:
                                    existing_student = True
                                    break
                        if existing_student:
                            logger.info(f"Skipping existing student database record: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                            duplicate_count += 1
                            if row_11_key[1]:
                                processed_combinations.add(row_11_key)
                            continue

                        # Also check Certificate (Offer Letter) table to prevent duplicates there
                        existing_cert = False
                        if roll_number:
                            for c in Certificate.objects.filter(roll_number__iexact=_clean_nan(roll_number).strip()):
                                if get_certificate_duplicate_key(c)[:11] == row_11_key:
                                    existing_cert = True
                                    break
                        if existing_cert:
                            logger.info(f"Skipping existing offer letter record: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                            duplicate_count += 1
                            if row_11_key[1]:
                                processed_combinations.add(row_11_key)
                            continue

                        if row_11_key[1]:
                            processed_combinations.add(row_11_key)

                        Certificate_student.objects.create(
                            full_name=_clean_nan(candidate_name),
                            roll_number=_clean_nan(roll_number),
                            course=_clean_nan(course_name),
                            college_name=_clean_nan(institution_name),
                            affiliated_name='',
                            start_date=start_date_obj,
                            end_date=end_date_obj,
                            issue_date=upload_issue_date,
                            email=_clean_nan(candidate_email),
                            contact=_clean_nan(candidate_mobile),
                            gender='',
                            internship_title=_clean_nan(internship_title),
                            internship_duration=_clean_nan(internship_duration),
                            institution_address=_clean_nan(institution_address),
                            stipend_amount=stipend_amount_row,
                        )
                        success_count += 1
                    except Exception as e:
                        failure_count += 1
                        logger.error(f"Failed to process row in bulk upload: {str(e)}")

                if success_count > 0:
                    messages.success(request, f"{success_count} student records were successfully uploaded and saved for offer letter generation.")
                if duplicate_count > 0:
                    messages.info(request, f"{duplicate_count} duplicate records were skipped.")
                if failure_count > 0:
                    messages.error(request, f"{failure_count} records failed to upload. Please check the data.")

                return redirect('generate_certificates_from_db')
            else:
                messages.error(request, 'Please correct the errors in the upload form.')
        else:
            # Handle solo form
            form = OfferLetterForm(request.POST)
            bulk_form = CertificateExcelForm()
            if form.is_valid():
                try:
                    messages.success(
                        request,
                        f'Offer letter generated successfully for {form.cleaned_data.get("candidate_name")}!'
                    )
                    return redirect('home')
                except Exception as e:
                    logger.error(f"Error generating offer letter: {str(e)}")
                    messages.error(
                        request,
                        'An error occurred while generating your offer letter. Please try again.'
                    )
            else:
                messages.error(request, 'Please correct the errors below.')
    else:
        form = OfferLetterForm()
        bulk_form = CertificateExcelForm()

    from .models import SystemConfiguration
    system_config = SystemConfiguration.get_solo()
    context = {
        'form': form,
        'bulk_form': bulk_form,
        'page_title': 'Generate Offer Letter',
        'system_config': system_config,
    }
    return render(request, 'certificates/generate_offer_letter.html', context)




def certificate_detail_by_pk(request, pk):
    """Certificate detail view using primary key."""
    try:
        certificate = get_object_or_404(Certificate, pk=pk)
        
        # Reuse the same context logic as the original detail view
        offer_letter = {
            'candidate_name': certificate.full_name,
            'roll_number': certificate.roll_number,
            'course_name': certificate.course,
            'institution_name': certificate.college_name,
            'institution_address': getattr(certificate, 'institution_address', None) or '',
            'institution_phone': getattr(certificate, 'institution_phone', None) or '',
            'candidate_email': certificate.email,
            'candidate_mobile': getattr(certificate, 'candidate_mobile', None) or '',
            'internship_title': certificate.internship_title,
            'internship_duration': getattr(certificate, 'internship_duration', f"{certificate.start_date} - {certificate.end_date}"),
            'internship_start_date': certificate.start_date,
            'internship_end_date': certificate.end_date,
        }
        
        context = {
            'certificate': certificate,
            'offer_letter': offer_letter,
            'page_title': f'Offer Letter - {certificate.full_name}',
        }
        return render(request, 'certificates/detail.html', context)
        
    except Exception as e:
        logger.error(f"Error loading certificate detail by pk: {str(e)}")
        raise Http404("Certificate not found")


def certificate_detail(request, certificate_id):
    """Backward-compatible detail view used by older URLs with certificate_id.

    Newer code should prefer certificate_detail_by_pk/verify_certificate, but
    this ensures existing URLs in certificates/urls.py still resolve.
    """
    try:
        if not certificate_id or certificate_id == 'None':
            raise Http404("Certificate not found")

        certificate = get_object_or_404(Certificate, certificate_id=certificate_id)

        offer_letter = {
            'candidate_name': certificate.full_name,
            'roll_number': certificate.roll_number,
            'course_name': certificate.course,
            'institution_name': certificate.college_name,
            'institution_address': getattr(certificate, 'institution_address', None) or '',
            'institution_phone': getattr(certificate, 'institution_phone', None) or '',
            'candidate_email': certificate.email,
            'candidate_mobile': getattr(certificate, 'candidate_mobile', None) or '',
            'internship_title': certificate.internship_title,
            'internship_duration': getattr(certificate, 'internship_duration', f"{certificate.start_date} - {certificate.end_date}"),
            'internship_start_date': certificate.start_date,
            'internship_end_date': certificate.end_date,
        }

        context = {
            'certificate': certificate,
            'offer_letter': offer_letter,
            'page_title': f'Offer Letter - {certificate.full_name}',
        }
        return render(request, 'certificates/detail.html', context)

    except Exception as e:
        logger.error(f"Error loading certificate detail: {str(e)}")
        raise Http404("Certificate not found")

def verify_certificate(request, certificate_id=None):
    """Public verification view supporting multiple lookup methods (ID, email, roll number, mobile)."""
    method = request.GET.get('method')
    value = request.GET.get('value', '').strip()

    verification_attempted = bool(method and value)
    certificate = None
    matching_certificates = None
    is_verified = False
    error_message = None

    # Prioritize form submission over URL parameters
    if verification_attempted:
        try:
            qs = Certificate.objects.all()

            if method == 'certificate_id':
                qs = qs.filter(certificate_id=value)
            elif method == 'email':
                qs = qs.filter(email__iexact=value)
            elif method == 'roll_number':
                qs = qs.filter(roll_number__iexact=value)
            elif method == 'mobile':
                qs = qs.filter(candidate_mobile__iexact=value)
            else:
                qs = Certificate.objects.none()

            count = qs.count()
            if count == 0:
                error_message = "No offer letter found for the provided details."
            elif count == 1:
                certificate = qs.first()
                is_verified = certificate.is_verified
            else:
                matching_certificates = qs.order_by('-created_at')
        except Exception as e:
            logger.error(f"Error verifying certificate via method {method}: {str(e)}")
            error_message = "An error occurred during verification."

    # If no form submission, check for a certificate_id in the URL
    elif certificate_id and certificate_id != 'None':
        try:
            certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
            is_verified = certificate.is_verified
            verification_attempted = True # We want to show the result
        except Http404:
            error_message = "Certificate not found or invalid."
            verification_attempted = True
        except Exception as e:
            logger.error(f"Error loading certificate by URL: {str(e)}")
            error_message = "An error occurred."
            verification_attempted = True

    context = {
        'certificate': certificate,
        'is_verified': is_verified,
        'verification_attempted': verification_attempted,
        'matching_certificates': matching_certificates,
        'error_message': error_message,
        'page_title': 'Certificate Verification',
    }

    return render(request, 'certificates/verify_student.html', context)

# views.py
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Q, Count
from django.db.models.functions import Lower
import pandas as pd
from .models import Certificate
from .forms import CertificateSearchForm
from django.core.paginator import Paginator


def certificate_list(request):
    form = CertificateSearchForm(request.GET or None)
    # Always fetch fresh data from database, don't use any cached values
    certificates = Certificate.objects.filter(is_verified=True).order_by('-created_at').select_for_update()

    courses = Certificate.objects.filter(is_verified=True).exclude(internship_title__isnull=True).exclude(internship_title='').values_list('internship_title', flat=True).distinct().order_by('internship_title')
    colleges = Certificate.objects.filter(is_verified=True).exclude(college_name__isnull=True).exclude(college_name='').values_list('college_name', flat=True).distinct().order_by('college_name')

    search_query = request.GET.get('search_query', '')
    course_filter = request.GET.get('course_filter', '')
    college_filter = request.GET.get('college_filter', '')

    if search_query:
        certificates = certificates.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(roll_number__icontains=search_query) |
            Q(certificate_id__icontains=search_query) |
            Q(course__icontains=search_query) |
            Q(internship_title__icontains=search_query)
        )

    if course_filter:
        certificates = certificates.filter(internship_title__icontains=course_filter)

    if college_filter:
        certificates = certificates.filter(college_name__icontains=college_filter)

    # Pagination with configurable items per page
    items_per_page = request.GET.get('items_per_page', '25')
    try:
        items_per_page = int(items_per_page)
        if items_per_page not in [10, 25, 50, 100]:
            items_per_page = 25
    except:
        items_per_page = 25
    
    paginator = Paginator(certificates, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Calculate statistics from fresh data
    total_certificates = paginator.count
    verified_certificates = total_certificates  # All are filtered by is_verified=True
    emails_sent = Certificate.objects.filter(is_verified=True, email_sent=True).count()
    drive_uploads = Certificate.objects.filter(is_verified=True, drive_uploaded=True).count()

    context = {
        'form': form,
        'page_obj': page_obj,
        'certificates': page_obj,
        'courses': courses,
        'colleges': colleges,
        'search_query': search_query,
        'course_filter': course_filter,
        'college_filter': college_filter,
        'items_per_page': items_per_page,
        'is_paginated': page_obj.has_other_pages(),
        'total_certificates': total_certificates,
        'verified_certificates': verified_certificates,
        'emails_sent': emails_sent,
        'drive_uploads': drive_uploads,
    }
    
    response = render(request, 'certificates/list.html', context)
    
    # Add cache control headers to prevent browser caching
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

from django.contrib import messages
def export_certificates(request):
    """
    Frontend export: exports filtered offer letters to Excel (.xlsx).
    Includes: Stipend, Certificate Status, Verification Status, QR Code Status,
    Generated Date, Template Used, Verification ID, Verification URL (production
    domain), and a clickable Offer Letter URL hyperlink.
    URL is built with request.build_absolute_uri so it works in both dev and production.
    """
    from django.urls import reverse as url_reverse
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    import datetime as dt

    search_query = request.GET.get('search_query', '')
    course_filter = request.GET.get('course_filter', '')
    college_filter = request.GET.get('college_filter', '')

    certificates = Certificate.objects.filter(is_verified=True)

    if search_query:
        certificates = certificates.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(roll_number__icontains=search_query) |
            Q(certificate_id__icontains=search_query) |
            Q(course__icontains=search_query) |
            Q(internship_title__icontains=search_query)
        )

    if course_filter:
        certificates = certificates.filter(internship_title__icontains=course_filter)

    if college_filter:
        certificates = certificates.filter(college_name__icontains=college_filter)

    if not certificates.exists():
        messages.warning(request, "No certificate data found for the selected filters.")
        return redirect('certificate_list')

    # ---- Build workbook ----
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Certificates"

    headers = [
        'Full Name', 'Email', 'Roll Number', 'College', 'Course',
        'Internship Title', 'Internship Duration', 'Start Date', 'End Date',
        'Stipend (INR)',
        'Certificate ID', 'Verification ID',
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

    # Hyperlink / URL cell styles
    link_font = Font(name='Arial', size=10, color='1F4E79', underline='single')
    url_font  = Font(name='Arial', size=10, color='0563C1', underline='single')

    for row_idx, cert in enumerate(certificates, start=2):
        # --- Verification URL (always production domain) ---
        verification_url = cert.get_verification_url() if cert.certificate_id else ''

        # --- Offer Letter URL (absolute URL to detail page) ---
        try:
            rel = url_reverse('certificate_detail_by_pk', kwargs={'pk': cert.pk})
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

        issued_date = cert.created_at.strftime('%Y-%m-%d %H:%M:%S') if cert.created_at else ''
        row_data = [
            cert.full_name,
            cert.email,
            cert.roll_number,
            cert.college_name,
            cert.course or '',
            cert.internship_title or '',
            cert.internship_duration or '',
            cert.start_date.strftime('%Y-%m-%d') if cert.start_date else '',
            cert.end_date.strftime('%Y-%m-%d') if cert.end_date else '',
            stipend_str,
            cert.certificate_id or '',
            cert.certificate_id or '',       # Verification ID
            verification_url,                # Verification URL (hyperlinked below)
            'Open Offer Letter',             # Offer Letter URL display text (hyperlinked below)
            cert_status,
            'Verified' if cert.is_verified else 'Not Verified',
            qr_status,
            'Yes' if cert.email_sent else 'No',
            'Yes' if cert.drive_uploaded else 'No',
            issued_date,
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

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max((len(str(cell.value)) for cell in col if cell.value is not None), default=10)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 14)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=Filtered_Certificates_{dt.date.today()}.xlsx'
    wb.save(response)
    return response





def download_certificate(request, pk):
    """Download certificate image"""
    try:
        certificate = get_object_or_404(Certificate, pk=pk)
        
        if not certificate.certificate_image:
            raise Http404("Certificate image not found")
        
        # Serve the file
        response = HttpResponse(
            certificate.certificate_image.read(),
            content_type='image/png'
        )
        # Build filename: RollNumber_Name_MobileNumber.png
        dl_parts = []
        if certificate.roll_number:
            dl_parts.append(certificate.roll_number.replace(' ', '_'))
        if certificate.full_name:
            dl_parts.append(certificate.full_name.replace(' ', '_'))
        if certificate.candidate_mobile:
            dl_parts.append(certificate.candidate_mobile.replace(' ', ''))
        dl_filename = "_".join(dl_parts) + ".png" if dl_parts else "OfferLetter.png"
        response['Content-Disposition'] = f'attachment; filename="{dl_filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading certificate: {str(e)}")
        raise Http404("Certificate not found")


def download_certificate_pdf(request, pk):
    """Download certificate PDF"""
    try:
        certificate = get_object_or_404(Certificate, pk=pk)
        
        if not certificate.certificate_pdf:
            raise Http404("Certificate PDF not found")
        
        # Serve the file
        response = HttpResponse(
            certificate.certificate_pdf.read(),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="{certificate.full_name.replace(" ", "_")}.pdf"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading certificate PDF: {str(e)}")
        raise Http404("Certificate PDF not found")


def download_offer_letter_image_by_id(request, pk):
    """Download offer letter image using primary key (works even when certificate_id is null)."""
    try:
        certificate = get_object_or_404(Certificate, pk=pk)

        if not certificate.certificate_image:
            raise Http404("Offer letter image not found")

        response = HttpResponse(
            certificate.certificate_image.read(),
            content_type='image/png'
        )
        # Build filename: RollNumber_Name_MobileNumber.png
        view_parts = []
        if certificate.roll_number:
            view_parts.append(certificate.roll_number.replace(' ', '_'))
        if certificate.full_name:
            view_parts.append(certificate.full_name.replace(' ', '_'))
        if certificate.candidate_mobile:
            view_parts.append(certificate.candidate_mobile.replace(' ', ''))
        view_filename = "_".join(view_parts) + ".png" if view_parts else "OfferLetter.png"
        response['Content-Disposition'] = f'inline; filename="{view_filename}"'
        return response

    except Exception as e:
        logger.error(f"Error downloading offer letter image by id: {str(e)}")
        raise Http404("Offer letter image not found")


@require_http_methods(["GET", "POST"])
def contact(request):
    """Contact form view"""
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            try:
                # Here you would typically send an email or save to database
                # For now, just show a success message
                messages.success(
                    request,
                    'Thank you for your message! We will get back to you soon.'
                )
                return redirect('contact')
            except Exception as e:
                logger.error(f"Error processing contact form: {str(e)}")
                messages.error(
                    request,
                    'An error occurred while sending your message. Please try again.'
                )
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ContactForm()
    
    context = {
        'form': form,
        'page_title': 'Contact Us',
    }
    return render(request, 'certificates/contact.html', context)


def about(request):
    """About page view"""
    context = {
        'page_title': 'About Us',
    }
    return render(request, 'certificates/about.html', context)


@csrf_exempt
def api_verify_certificate(request, certificate_id):
    """API endpoint for certificate verification"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        certificate = Certificate.objects.get(certificate_id=certificate_id)
        
        data = {
            'verified': certificate.is_verified,
            'certificate_id': str(certificate.certificate_id),
            'full_name': certificate.full_name,
            'course': certificate.course,
            'college_name': certificate.college_name,
            'roll_number': certificate.roll_number,
            'issue_date': certificate.created_at.strftime('%d %B %Y'),
            'verification_url': certificate.verification_url,
        }
        
        return JsonResponse(data)
        
    except Certificate.DoesNotExist:
        return JsonResponse({
            'verified': False,
            'error': 'Certificate not found'
        }, status=404)
    except Exception as e:
        logger.error(f"API verification error: {str(e)}")
        return JsonResponse({
            'verified': False,
            'error': 'Verification failed'
        }, status=500)


def stats(request):
    """Statistics page"""
    stats_data = {
        'total_certificates': Certificate.objects.count(),
        'verified_certificates': Certificate.objects.filter(is_verified=True).count(),
        'pending_certificates': Certificate.objects.filter(is_verified=False).count(),
        'emails_sent': Certificate.objects.filter(email_sent=True).count(),
        'drive_uploads': Certificate.objects.filter(drive_uploaded=True).count(),
        'recent_certificates': Certificate.objects.filter(is_verified=True).order_by('-created_at')[:10],
        'top_courses': Certificate.objects.exclude(internship_title__isnull=True).exclude(internship_title='').values('internship_title').annotate(count=Count('internship_title')).order_by('-count', Lower('internship_title')),
        'top_colleges': Certificate.objects.order_by(Lower('college_name')).values_list('college_name', flat=True).distinct(),
    }

    context = {
        'stats': stats_data,
        'page_title': 'Offer Letter Statistics',
    }
    return render(request, 'certificates/stats.html', context)


from django.shortcuts import render, redirect
from .forms import CertificateExcelForm
from .models import Certificate_student
import pandas as pd
from django.contrib import messages
from django.utils.dateparse import parse_date
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import CertificateExcelForm
from .models import Certificate_student
from django.utils.dateparse import parse_date
import pandas as pd

def upload_excel(request):
    if request.method == 'POST':
        form = CertificateExcelForm(request.POST, request.FILES)
        if form.is_valid():
            instance = form.save()
            file_path = instance.excel_file.path
            file_extension = file_path.split('.')[-1].lower()
            
            # Read file based on its extension
            if file_extension == 'csv':
                try:
                    # Try UTF-8 first
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        # Try Latin-1 (ISO-8859-1) which handles byte 0xa0
                        df = pd.read_csv(file_path, encoding='latin-1')
                    except UnicodeDecodeError:
                        # Try cp1252 (Windows-1252) as fallback
                        df = pd.read_csv(file_path, encoding='cp1252')
            elif file_extension in ['xlsx', 'xls']:
                df = pd.read_excel(file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}. Please upload CSV or Excel files.")
            
            df.columns = df.columns.str.strip()

            success_count = 0
            failure_count = 0
            duplicate_count = 0
            processed_combinations = set()  # Track duplicate combinations within current upload
            # Check if required columns exist (flexible matching)
            name_column = None
            email_column = None
            
            # Look for name column variations
            name_variations = ['name', 'full name', 'fullname', 'student name', 'full_name']
            for col in df.columns:
                if any(variation in col.lower() for variation in name_variations):
                    Name = col
                    break
            
            # Look for email column variations  
            email_variations = ['email', 'e-mail', 'email address', 'e_mail', 'mail']
            for col in df.columns:
                if any(variation in col.lower() for variation in email_variations):
                    email = col

            for _, row in df.iterrows():
                try:
                    # Flexible column resolution so template header variants still work
                    candidate_name = (
                        row.get('Name')
                        or row.get('Full Name')
                        or row.get('Candidate Name')
                    )
                    roll_number = row.get('Roll No') or row.get('Roll Number')
                    course_name = row.get('Course') or row.get('Course Name')
                    institution_name = row.get('College Name') or row.get('Institution Name')
                    institution_address = (
                        row.get('Institution Address')
                        or row.get('College Address')
                        or ''
                    )
                    candidate_mobile = (
                        row.get('Candidate Mobile')
                        or row.get('Mobile')
                        or row.get('Contact')
                        or ''
                    )
                    # Force candidate_mobile to be an integer string if it's a number
                    if pd.notna(candidate_mobile):
                        try:
                            # Convert to float first to handle scientific notation/decimals, 
                            # then to int, then to str
                            candidate_mobile = str(int(float(candidate_mobile)))
                        except (ValueError, TypeError):
                            candidate_mobile = str(candidate_mobile).strip()
                    else:
                        candidate_mobile = ''
                    candidate_email = (
                        row.get('Candidate Email')
                        or row.get('Email')
                        or ''
                    )
                    internship_title = (
                        row.get('Internship Title') 
                        or row.get('Title') 
                        or row.get('Subject')
                        or ''
                    )
                    raw_internship_duration = (
                        row.get('Internship Duration') 
                        or row.get('Duration')
                        or row.get('Months')
                        or ''
                    )
                    internship_duration = str(raw_internship_duration).strip()
                    
                    # Log the raw duration for debugging
                    if raw_internship_duration:
                        logger.info(f"Raw internship duration from Excel: '{raw_internship_duration}' -> '{internship_duration}'")
                    else:
                        logger.warning(f"No internship duration found in Excel for row: {row.get('Name', 'Unknown')}")

                    # Normalize dates to ISO strings if possible so save_offer_letter_to_database
                    # can parse them consistently.
                    # Log raw date values for debugging
                    logger.info(f"Processing row: {row.get('Name', 'Unknown')}")
                    logger.info(f"Available columns: {list(df.columns)}")
                    
                    # Check for various possible column names (case-insensitive)
                    start_date_variants = ['Start Date', 'Start_Date', 'StartDate', 'start_date', 'Start', 'start', 'startdate', 'START DATE']
                    end_date_variants = ['End Date', 'End_Date', 'EndDate', 'end_date', 'End', 'end', 'enddate', 'END DATE']
                    
                    found_start = None
                    found_end = None
                    start_date_val = None
                    end_date_val = None
                    
                    # Create a case-insensitive mapping of column names
                    column_map = {col.lower(): col for col in df.columns}
                    
                    for variant in start_date_variants:
                        if variant.lower() in column_map:
                            actual_col = column_map[variant.lower()]
                            found_start = row.get(actual_col)
                            logger.info(f"Found Start Date column: '{actual_col}' = '{found_start}'")
                            break
                    
                    for variant in end_date_variants:
                        if variant.lower() in column_map:
                            actual_col = column_map[variant.lower()]
                            found_end = row.get(actual_col)
                            logger.info(f"Found End Date column: '{actual_col}' = '{found_end}'")
                            break
                    
                    if found_start is not None:
                        start_date_val = found_start
                        logger.info(f"Start Date found: '{found_start}' (type: {type(found_start)})")
                    else:
                        logger.warning(f"No Start Date column found in Excel for row: {row.get('Name', 'Unknown')}")
                    if found_end is not None:
                        end_date_val = found_end
                        logger.info(f"End Date found: '{found_end}' (type: {type(found_end)})")
                    else:
                        logger.warning(f"No End Date column found in Excel for row: {row.get('Name', 'Unknown')}")

                    def _normalize_date(val):
                        if pd.isna(val):
                            logger.info(f"Date is NaN: {val}")
                            return ''
                        # pandas Timestamp or datetime/date
                        if hasattr(val, 'strftime'):
                            result = val.strftime('%d-%m-%Y')
                            logger.info(f"Date object formatted: {val} -> {result}")
                            return result
                        # Fallback: try multiple date formats
                        try:
                            # Try DD-MM-YYYY first
                            from dateutil.parser import parse as dateutil_parse
                            parsed = dateutil_parse(str(val))
                            if parsed:
                                result = parsed.strftime('%d-%m-%Y')
                                logger.info(f"Date parsed successfully with dateutil: '{val}' -> {result}")
                                return result
                        except Exception as e:
                            logger.warning(f"dateutil failed to parse date '{val}': {str(e)}")
                            try:
                                # Try YYYY-MM-DD as fallback
                                if '-' in str(val):
                                    parts = str(val).split('-')
                                    if len(parts) == 3 and len(parts[0]) == 4:
                                        # YYYY-MM-DD format
                                        year, month, day = parts
                                        result = f"{day}-{month}-{year}"
                                        logger.info(f"Date converted from YYYY-MM-DD: '{val}' -> {result}")
                                        return result
                                    elif len(parts) == 3 and len(parts[0]) <= 2:
                                        # DD-MM-YYYY format
                                        result = str(val)
                                        logger.info(f"Date already in DD-MM-YYYY: '{val}' -> {result}")
                                        return result
                            except Exception as e:
                                logger.error(f"Date conversion failed for '{val}': {str(e)}")
                                pass
                        return ''

                    # Helper to handle NaN/nan strings from Pandas
                    def _clean_nan(val):
                        if pd.isna(val) or str(val).lower().strip() == 'nan':
                            return ''
                        return str(val).strip()

                    # Helper to validate if a date string is actually valid
                    def _is_valid_date(date_str):
                        if not date_str or str(date_str).strip() == '':
                            return False
                        try:
                            datetime.strptime(date_str, '%d-%m-%Y')
                            return True
                        except ValueError:
                            return False

                    internship_start_date = _normalize_date(start_date_val)
                    internship_end_date = _normalize_date(end_date_val)
                    
                    # Debug: Log the results of date normalization
                    logger.info(f"Date normalization results for {row.get('Name', 'Unknown')}:")
                    logger.info(f"  start_date_val: '{start_date_val}' -> internship_start_date: '{internship_start_date}'")
                    logger.info(f"  end_date_val: '{end_date_val}' -> internship_end_date: '{internship_end_date}'")
                    
                    # Dates are optional - only warn if provided but invalid
                    if internship_start_date and not _is_valid_date(internship_start_date):
                        messages.warning(request, f"Invalid Start Date for row: {row.get('Name', 'Unknown')}. Value: '{internship_start_date}'. Expected DD-MM-YYYY format.")
                    if internship_end_date and not _is_valid_date(internship_end_date):
                        messages.warning(request, f"Invalid End Date for row: {row.get('Name', 'Unknown')}. Value: '{internship_end_date}'. Expected DD-MM-YYYY format.")

                    # Use issue_date from upload form if provided, otherwise use current date
                    upload_issue_date = instance.issue_date
                    if upload_issue_date:
                        issue_date_str = upload_issue_date.strftime('%d-%m-%Y')
                    else:
                        issue_date_str = datetime.now().strftime('%d-%m-%Y')

                    offer_letter_data = {
                        'candidate_name': _clean_nan(candidate_name),
                        'roll_number': _clean_nan(roll_number),
                        'course_name': _clean_nan(course_name),
                        'institution_name': _clean_nan(institution_name),
                        'institution_address': _clean_nan(institution_address),
                        'candidate_mobile': _clean_nan(candidate_mobile),
                        'candidate_email': _clean_nan(candidate_email),
                        'internship_title': _clean_nan(internship_title),
                        'internship_duration': _clean_nan(internship_duration),
                        'issue_date': issue_date_str,
                        'internship_start_date': internship_start_date,
                        'internship_end_date': internship_end_date,
                    }

                    # Parse dates for duplicate checking
                    start_date_obj = datetime.strptime(internship_start_date, '%d-%m-%Y').date() if internship_start_date else None
                    end_date_obj = datetime.strptime(internship_end_date, '%d-%m-%Y').date() if internship_end_date else None

                    # --- Duplicate detection ---
                    from .utils import get_certificate_duplicate_key
                    row_key = get_certificate_duplicate_key({
                        'candidate_name': _clean_nan(candidate_name),
                        'roll_number': _clean_nan(roll_number),
                        'candidate_email': _clean_nan(candidate_email),
                        'candidate_mobile': _clean_nan(candidate_mobile),
                        'course_name': _clean_nan(course_name),
                        'institution_name': _clean_nan(institution_name),
                        'internship_title': _clean_nan(internship_title),
                        'internship_duration': _clean_nan(internship_duration),
                        'issue_date': upload_issue_date,
                        'internship_start_date': start_date_obj,
                        'internship_end_date': end_date_obj,
                        'offer_type': '',
                    })

                    row_11_key = row_key[:11]

                    # Check if this combination already exists in current upload
                    if row_11_key[1] and row_11_key in processed_combinations:
                        logger.info(f"Skipping duplicate within current upload: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                        duplicate_count += 1
                        continue

                    # Check if this combination already exists in database staging (Certificate_student)
                    existing_student = False
                    if roll_number:
                        for s in Certificate_student.objects.filter(roll_number__iexact=_clean_nan(roll_number).strip()):
                            if get_certificate_duplicate_key(s)[:11] == row_11_key:
                                existing_student = True
                                break
                    if existing_student:
                        logger.info(f"Skipping existing student database record: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                        duplicate_count += 1
                        if row_11_key[1]:
                            processed_combinations.add(row_11_key)
                        continue

                    # Also check Certificate (Offer Letter) table to prevent duplicates there
                    existing_cert = False
                    if roll_number:
                        for c in Certificate.objects.filter(roll_number__iexact=_clean_nan(roll_number).strip()):
                            if get_certificate_duplicate_key(c)[:11] == row_11_key:
                                existing_cert = True
                                break
                    if existing_cert:
                        logger.info(f"Skipping existing offer letter record: {_clean_nan(candidate_name)} ({_clean_nan(roll_number)})")
                        duplicate_count += 1
                        if row_11_key[1]:
                            processed_combinations.add(row_11_key)
                        continue

                    if row_11_key[1]:
                        processed_combinations.add(row_11_key)
                    
                    # --- Stipend from Excel ---
                    raw_stipend = (row.get('Stipend') or row.get('Stipend Amount') or
                                   row.get('stipend') or row.get('stipend_amount'))
                    stipend_amount_row = clean_stipend_value(raw_stipend)

                    # Save to Certificate_student model for later generation
                    
                    student = Certificate_student.objects.create(
                        full_name=_clean_nan(candidate_name),
                        roll_number=_clean_nan(roll_number),
                        course=_clean_nan(course_name),
                        college_name=_clean_nan(institution_name),
                        affiliated_name='',  # Can be added to Excel if needed
                        start_date=start_date_obj,
                        end_date=end_date_obj,
                        issue_date=upload_issue_date,  # Save issue date from upload form
                        email=_clean_nan(candidate_email),
                        contact=_clean_nan(candidate_mobile),
                        gender='',  # Can be added to Excel if needed
                        internship_title=_clean_nan(internship_title),
                        internship_duration=_clean_nan(internship_duration),
                        institution_address=_clean_nan(institution_address),
                        stipend_amount=stipend_amount_row,
                    )
                    success_count += 1
                    logger.info(f"✅ Successfully saved student data for {row.get('Name') or row.get('Full Name')} (Roll No: {row.get('Roll No')})")
                except Exception as e:
                    failure_count += 1
                    student_name = row.get('Name') or row.get('Full Name') or 'Unknown'
                    roll_number = row.get('Roll No') or 'Unknown'
                    logger.error(f"❌ Failed to generate offer letter for {student_name} (Roll No: {roll_number}): {str(e)}")
                    logger.error(f"❌ Error type: {type(e).__name__}")
                    logger.error(f"❌ Error details: {str(e)}")
                    import traceback
                    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                    logger.error(f"❌ Offer letter data: {offer_letter_data}")

            if success_count > 0:
                messages.success(request, f"{success_count} student records were successfully uploaded and saved for offer letter generation.")
            if duplicate_count > 0:
                messages.info(request, f"{duplicate_count} duplicate records were skipped (same roll number, email, name, internship, and dates).")
            if failure_count > 0:
                messages.error(request, f"{failure_count} records failed to upload. Please check the logs.")

            # Redirect to generation page for smooth workflow
            return redirect('generate_certificates_from_db')
    else:
        form = CertificateExcelForm()

    return render(request, 'certificates/upload_excel.html', {'form': form})

from django.http import FileResponse
from .models import CertificateExcelUpload
def download_excel_template(request):
    """Download Excel template with required Start Date and End Date columns"""
    try:
        # Use the template from media/templates directory
        template_path = os.path.join(settings.MEDIA_ROOT, 'templates', 'Offer letter excel template.xlsx')
        if os.path.exists(template_path):
            response = FileResponse(open(template_path, 'rb'), as_attachment=True, filename='Offer_letter_excel_template.xlsx')
            response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            return response
        else:
            # Fallback to creating template dynamically if file doesn't exist
            import pandas as pd
            from django.http import HttpResponse
            
            # Create template with required columns
            template_data = {
                'Name': ['Sample Student 1', 'Sample Student 2'],
                'Email': ['student1@example.com', 'student2@example.com'],
                'Roll No': ['R001', 'R002'],
                'Course': ['Computer Science', 'Information Technology'],
                'College Name': ['ABC Engineering College', 'XYZ University'],
                'Institution Address': ['123 College Street, Hyderabad', '456 University Avenue, Bangalore'],
                'Candidate Mobile': ['9000000001', '9000000002'],
                'Candidate Email': ['student1@example.com', 'student2@example.com'],
                'Internship Title': ['Web Development Intern', 'Data Science Intern'],
                'Internship Duration': ['6 Months', '3 Months'],
                'Start Date': ['19-01-2026', '01-02-2026'],
                'End Date': ['19-07-2026', '01-08-2026'],
                'Stipend': ['5000', ''],  # Optional: per-candidate stipend amount (leave blank for none)
            }
            
            df = pd.DataFrame(template_data)
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename=EXCEL_TEMPLATE_WITH_DATES.xlsx'
            df.to_excel(response, index=False, engine='openpyxl')
            return response
            
    except Exception as e:
        logger.error(f"Error downloading Excel template: {str(e)}")
        from django.contrib import messages
        messages.error(request, 'Error downloading template. Please try again.')
        return redirect('upload_excel')
    except CertificateExcelUpload.DoesNotExist:
        raise Http404("No Excel template found.")

# from django.shortcuts import render, redirect
# from django.contrib import messages
# from .models import Certificate_student
# from .utils import process_certificate_request, send_certificate_email, upload_to_google_drive
# import logging

# logger = logging.getLogger(__name__)

# def generate_certificates_from_db(request):
#     """
#     Generate certificates for all students from Certificate_student model.
#     """
#     if request.method == 'POST':
#         students = Certificate_student.objects.all()
#         success_count = 0
#         failed_count = 0

#         for student in students:
#             data = {
#                 'full_name': student.full_name,
#                 'course': student.course,
#                 'roll_number': student.roll_number,
#                 'college_name': student.college_name,
#                 'start_date': student.start_date,
#                 'end_date': student.end_date,
#                 'email': student.email,
#                 'contact': student.contact,
#                 'gender': student.gender,
#             }

#             try:
#                 certificate = process_certificate_request(data)

#                 # Upload to Google Drive
#                 upload_to_google_drive(certificate)

#                 # Send certificate via email
#                 send_certificate_email(certificate)

#                 success_count += 1
#             except Exception as e:
#                 logger.error(f"Failed for {student.full_name}: {str(e)}")
#                 failed_count += 1

#         messages.success(request, f'{success_count} certificate(s) generated, emailed, and uploaded to Drive.')
#         if failed_count > 0:
#             messages.warning(request, f'{failed_count} certificate(s) failed.')

#         # return redirect('generate_certificates_report')  # Optional: redirect to a report or log page

#     context = {
#         'page_title': 'Generate All Certificates'
#     }
#     return render(request, 'certificates/generate_from_db.html', context)



from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Certificate_student
from .utils import process_certificate_request, send_certificate_email, upload_to_google_drive, get_available_certificate_templates
import logging

logger = logging.getLogger(__name__)

def generate_certificates_from_db(request):
    """
    Bulk generate offer letters from Certificate_student model.
    Successfully processed rows will be deleted from the database.
    """
    if request.method == 'POST':
        students = Certificate_student.objects.all()
        success_count = 0
        fail_count = 0
        duplicate_count = 0  # Track duplicates
        if not students.exists():
            messages.warning(request, "⚠️ No data found. Please insert student details before generating offer letters.")
            return redirect('generate_certificates_from_db')

        offer_type = request.POST.get('offer_type', '')
        selected_template = offer_type or request.POST.get('template') or 'original_certificate_aicte-apscheofferletter-virtual.jpg'
        for student in students:
            try:
                # Helper to clean nan values and format phone numbers
                def _clean_nan_bulk(val, is_mobile=False):
                    if val is None: return ""
                    s = str(val).strip()
                    if s.lower() == 'nan': return ""
                    if is_mobile and s:
                        try:
                            # Convert to float first to handle .0 or scientific notation
                            return str(int(float(s)))
                        except (ValueError, TypeError):
                            return s
                    return s

                # Check for duplicate using unified 12-field key matching
                from .utils import get_certificate_duplicate_key
                target_key = get_certificate_duplicate_key({
                    'candidate_name': _clean_nan_bulk(student.full_name),
                    'roll_number': _clean_nan_bulk(student.roll_number),
                    'candidate_email': _clean_nan_bulk(student.email),
                    'candidate_mobile': _clean_nan_bulk(student.contact, is_mobile=True),
                    'course_name': _clean_nan_bulk(student.course),
                    'institution_name': _clean_nan_bulk(student.college_name),
                    'internship_title': _clean_nan_bulk(student.internship_title or student.course),
                    'internship_duration': _clean_nan_bulk(student.internship_duration),
                    'issue_date': student.issue_date or datetime.now().date(),
                    'internship_start_date': student.start_date,
                    'internship_end_date': student.end_date,
                    'offer_type': selected_template,
                })

                # Check if this exact duplicate key already exists in the database
                existing_cert_exists = False
                student_roll = _clean_nan_bulk(student.roll_number).strip()
                if student_roll:
                    for cert in Certificate.objects.filter(roll_number__iexact=student_roll):
                        if get_certificate_duplicate_key(cert) == target_key:
                            existing_cert_exists = True
                            break

                if existing_cert_exists:
                    logger.info(f"Certificate already exists with key: {target_key}. Skipping.")
                    duplicate_count += 1
                    continue

                # Map Certificate_student data to offer letter format
                offer_letter_data = {
                    'candidate_name': _clean_nan_bulk(student.full_name),
                    'roll_number': _clean_nan_bulk(student.roll_number),
                    'course_name': _clean_nan_bulk(student.course),
                    'institution_name': _clean_nan_bulk(student.college_name),
                    'institution_address': _clean_nan_bulk(student.institution_address or ''),
                    'candidate_mobile': _clean_nan_bulk(student.contact, is_mobile=True),
                    'candidate_email': _clean_nan_bulk(student.email),
                    'internship_title': _clean_nan_bulk(student.internship_title or student.course),
                    'internship_duration': _clean_nan_bulk(student.internship_duration),
                    'issue_date': student.issue_date.strftime('%d-%m-%Y') if student.issue_date else datetime.now().strftime('%d-%m-%Y'),
                    'stipend_amount': student.stipend_amount,
                }

                # Add dates if available
                if student.start_date:
                    offer_letter_data['internship_start_date'] = student.start_date.strftime('%d-%m-%Y')
                if student.end_date:
                    offer_letter_data['internship_end_date'] = student.end_date.strftime('%d-%m-%Y')

                # Generate the offer letter
                certificate = save_offer_letter_to_database(offer_letter_data, template_name=selected_template)

                # Save offer_type on the certificate record
                if offer_type:
                    certificate.offer_type = offer_type
                    certificate.save(update_fields=['offer_type'])

                # Virtual: send email automatically; Physical: skip email
                if is_virtual_offer_type(offer_type):
                    try:
                        send_certificate_email(certificate)
                    except Exception as e:
                        logger.error(f"Failed to send email for {student.roll_number}: {str(e)}")

                # If successful, delete the student entry
                from .soft_delete_utils import soft_delete_record
                username = request.user.username if request.user.is_authenticated else "System/Bulk Generator"
                soft_delete_record(student, deleted_by=username, reason="Offer letter successfully generated", duplicate_reason="Cleanup after bulk generation")

                success_count += 1

            except Exception as e:
                logger.error(f"Error for {student.full_name}: {str(e)}")
                fail_count += 1

        type_label = "Virtual" if is_virtual_offer_type(offer_type) else "Physical"
        messages.success(
            request,
            f"✅ {success_count} {type_label} offer letters generated. ❌ {fail_count} failed and were retained. 🚫 {duplicate_count} skipped due to duplicate email + internship title."
        )
        return redirect('generate_certificates_from_db')

    return render(request, 'certificates/generate_from_db.html', {
        'page_title': 'Generate Offer Letters from Uploaded Data',
        'offer_type_choices': get_offer_type_choices(),
    })



import pandas as pd
from django.http import HttpResponse
from .models import Certificate_student

def export_certificates_to_excel(request):
    # Get all data from the database
    data = Certificate_student.objects.all().values(
        'full_name', 'course', 'roll_number', 'college_name',
        'affiliated_name', 'start_date', 'end_date', 'email',
        'contact', 'gender', 'stipend_amount' 
    )

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Create Excel response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="certificates_export.xlsx"'

    # Write DataFrame to Excel
    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Certificates', index=False)

    return response


from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login,logout
from django.contrib import messages

def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'college_profile'):
            return redirect('college_dashboard')
        elif request.user.is_superuser or request.user.is_staff:
            return redirect('home')

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me') == 'on'

        if not identifier or not password:
            messages.error(request, 'Please provide both email/username and password.')
            return render(request, 'login.html')

        from django.contrib.auth.models import User
        from django.db.models import Q
        from .models import AuditLog

        # Find user by username or email
        user_candidate = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()

        username_to_auth = user_candidate.username if user_candidate else identifier
        user = authenticate(request, username=username_to_auth, password=password)

        if user is not None:
            if not user.is_active:
                AuditLog.log(request, 'LOGIN_FAILED', f"Deactivated user '{identifier}' attempted login")
                messages.error(request, 'Your account is deactivated. Please contact the administrator.')
                return render(request, 'login.html')

            # Check if user is a college administrator
            if hasattr(user, 'college_profile'):
                profile = user.college_profile
                primary_col = profile.primary_college

                if not profile.is_active:
                    AuditLog.log(request, 'LOGIN_FAILED', f"Deactivated college admin '{identifier}' attempted login", college=primary_col)
                    messages.error(request, 'Your college administrator account has been deactivated. Please contact the Super Admin.')
                    return render(request, 'login.html')

                active_colleges = profile.get_colleges()
                if not active_colleges.exists():
                    AuditLog.log(request, 'LOGIN_FAILED', f"College admin '{identifier}' attempted login with no active assigned colleges", college=primary_col)
                    messages.error(request, 'Your assigned institutions are currently suspended or none are assigned. Please contact the Super Admin.')
                    return render(request, 'login.html')

                login(request, user)
                if remember_me:
                    request.session.set_expiry(1209600)  # 2 weeks
                else:
                    request.session.set_expiry(0)

                col_names = ", ".join(active_colleges.values_list('name', flat=True)[:2])
                if active_colleges.count() > 2:
                    col_names += f" (+{active_colleges.count() - 2} more)"

                AuditLog.log(request, 'LOGIN', f"College Admin '{profile.full_name}' logged in successfully ({col_names})", college=active_colleges.first())
                messages.success(request, f"Welcome back, {profile.full_name} ({col_names})")
                return redirect('college_dashboard')

            # Super Admin / Staff user
            if user.is_superuser or user.is_staff:
                login(request, user)
                if remember_me:
                    request.session.set_expiry(1209600)
                else:
                    request.session.set_expiry(0)

                AuditLog.log(request, 'LOGIN', f"Super Admin '{user.username}' logged in successfully")
                messages.success(request, f"Welcome, {user.first_name or user.username}!")
                next_url = request.GET.get('next') or request.POST.get('next') or 'home'
                return redirect(next_url)

            # Standard user without college profile
            login(request, user)
            return redirect('home')

        else:
            from .models import AuditLog
            AuditLog.log(request, 'LOGIN_FAILED', f"Invalid credentials attempt for identifier '{identifier}'")
            messages.error(request, 'Invalid email/username or password.')

    return render(request, 'login.html')

def logout_view(request):
    from .models import AuditLog
    if request.user.is_authenticated:
        col = getattr(request.user, 'college_profile', None)
        AuditLog.log(request, 'LOGOUT', f"User '{request.user.username}' logged out", college=col.college if col else None)
    logout(request)
    messages.info(request, "You have been logged out securely.")
    return redirect('login')


# views.py
from django.shortcuts import render
from .models import Certificate
from django.db.models.functions import Lower
from django.db.models import Q, Count
from django.db.models.functions import Lower


def certificate_list_view(request):
    certificates = Certificate.objects.all()

    # Get filter values from GET request
    course_filter = request.GET.get('course')
    college_filter = request.GET.get('college_name')
    is_verified_filter = request.GET.get('is_verified')
    email_filter = request.GET.get('email_sent')
    name_filter = request.GET.get('full_name')

    # Apply filters
    if course_filter:
        certificates = certificates.filter(course__iexact=course_filter)
    if college_filter:
        certificates = certificates.filter(college_name__iexact=college_filter)
    if is_verified_filter in ['True', 'False']:
        certificates = certificates.filter(is_verified=(is_verified_filter == 'True'))
    if email_filter in ['True', 'False']:
        certificates = certificates.filter(email_sent=(email_filter == 'True'))
    if name_filter:
        certificates = certificates.filter(full_name__icontains=name_filter)

    context = {
        'certificates': certificates,
        'course_filter': course_filter,
        'college_filter': college_filter,
        'is_verified_filter': is_verified_filter,
        'email_filter': email_filter,
        'name_filter': name_filter,
        'available_courses': Certificate.objects.order_by(Lower('course')).values_list('course', flat=True).distinct(),
        'available_colleges': Certificate.objects.order_by(Lower('college_name')).values_list('college_name', flat=True).distinct(),
    }
    return render(request, 'certificates/filter.html', context)


from django.shortcuts import render
from django.db.models import Q, Count
from django.db.models.functions import Lower
from .models import Certificate  # Make sure this import is correct

def verify_student(request):
    """
    Public certificate verification page supporting multiple methods.
    Accepts GET params: method (certificate_id, phone, email, roll_number), value (user input).
    Renders result in certificates/verify_student.html.
    """
    method = request.GET.get('method', 'certificate_id')
    value = request.GET.get('value', '').strip()
    certificate = None
    is_verified = False
    error_message = ''
    verification_attempted = False  # NEW FLAG

    if value:
        verification_attempted = True  # Mark that verification was attempted
        query = Q()
        
        if method == 'certificate_id':
            query = Q(certificate_id__iexact=value)
        elif method == 'phone':
            query = Q(phone__icontains=value)  # Assumes a phone field exists
        elif method == 'email':
            query = Q(email__iexact=value)
        elif method == 'roll_number':
            query = Q(roll_number__iexact=value)
        else:
            error_message = 'Invalid verification method.'

        if not error_message:
            try:
                certificate = Certificate.objects.filter(query, is_verified=True).first()
                if certificate:
                    is_verified = True
                else:
                    error_message = 'No certificate found for the provided information.'
            except Exception as e:
                error_message = 'An error occurred during verification.'

    context = {
        'certificate': certificate,
        'is_verified': is_verified,
        'error_message': error_message,
        'method': method,
        'value': value,
        'verification_attempted': verification_attempted,  # PASS TO TEMPLATE
    }

    return render(request, 'certificates/verify_student.html', context)


def verify_certificate(request, certificate_id=None):
    """Public verification view supporting multiple lookup methods (ID, email, roll number, mobile)."""
    method = request.GET.get('method')
    value = request.GET.get('value', '').strip()

    verification_attempted = bool(method and value)
    certificate = None
    matching_certificates = None
    is_verified = False
    error_message = None

    # Prioritize form submission over URL parameters
    if verification_attempted:
        try:
            qs = Certificate.objects.all()

            if method == 'certificate_id':
                qs = qs.filter(certificate_id=value)
            elif method == 'email':
                qs = qs.filter(email__iexact=value)
            elif method == 'roll_number':
                qs = qs.filter(roll_number__iexact=value)
            elif method == 'mobile':
                qs = qs.filter(candidate_mobile__iexact=value)
            else:
                qs = Certificate.objects.none()

            count = qs.count()
            if count == 0:
                error_message = "No offer letter found for the provided details."
            elif count == 1:
                certificate = qs.first()
                is_verified = certificate.is_verified
            else:
                matching_certificates = qs.order_by('-created_at')
        except Exception as e:
            logger.error(f"Error verifying certificate via method {method}: {str(e)}")
            error_message = "An error occurred during verification."

    # If no form submission, check for a certificate_id in the URL
    elif certificate_id and certificate_id != 'None':
        try:
            certificate = get_object_or_404(Certificate, certificate_id=certificate_id)
            is_verified = certificate.is_verified
            verification_attempted = True # We want to show the result
        except Http404:
            error_message = "Certificate not found or invalid."
            verification_attempted = True
        except Exception as e:
            logger.error(f"Error loading certificate by URL: {str(e)}")
            error_message = "An error occurred."
            verification_attempted = True

    context = {
        'certificate': certificate,
        'is_verified': is_verified,
        'verification_attempted': verification_attempted,
        'matching_certificates': matching_certificates,
        'error_message': error_message,
        'page_title': 'Certificate Verification',
    }

    return render(request, 'certificates/verify_student.html', context)


@login_required
@require_http_methods(["POST"])
def toggle_email_automation(request):
    """View to toggle email automation settings"""
    from .models import SystemConfiguration
    
    # Just to be safe, check if user is superuser or staff
    if not request.user.is_staff:
         return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)

    try:
        data = json.loads(request.body)
        enabled = data.get("enabled", False)
        
        config = SystemConfiguration.get_solo()
        config.email_automation_enabled = enabled
        config.save()
        
        status_msg = "enabled" if enabled else "disabled"
        return JsonResponse({
            "status": "success", 
            "message": f"Email automation {status_msg}",
            "enabled": config.email_automation_enabled
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
def manage_templates(request):
    """View for managing certificate templates - upload new, list existing, toggle active status"""
    from .models import CertificateTemplate
    from .forms import CertificateTemplateUploadForm
    from .utils import get_available_certificate_templates

    if request.method == 'POST':
        form = CertificateTemplateUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                template = CertificateTemplate.objects.create(
                    name=form.cleaned_data['name'],
                    template_image=form.cleaned_data['template_image'],
                    is_active=True,
                )
                messages.success(
                    request,
                    f'Template "{template.name}" uploaded successfully! It is now available for offer letter generation.'
                )
                return redirect('manage_templates')
            except Exception as e:
                logger.error(f"Error uploading template: {str(e)}")
                messages.error(request, f'Error uploading template: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CertificateTemplateUploadForm()

    # Get all templates (both DB and file-based) for display
    db_templates = CertificateTemplate.objects.all().order_by('-created_at')
    file_templates = get_available_certificate_templates()

    from .models import SystemConfiguration
    system_config = SystemConfiguration.get_solo()

    context = {
        'form': form,
        'db_templates': db_templates,
        'file_templates': file_templates,
        'page_title': 'Manage Offer Letter Templates',
        'system_config': system_config,
    }
    return render(request, 'certificates/manage_templates.html', context)


@login_required
@require_http_methods(["POST"])
def toggle_template(request, pk):
    """Toggle the is_active status of a database template"""
    from .models import CertificateTemplate
    try:
        template = CertificateTemplate.objects.get(pk=pk)
        template.is_active = not template.is_active
        template.save()
        status = "activated" if template.is_active else "deactivated"
        messages.success(request, f'Template "{template.name}" {status} successfully.')
    except CertificateTemplate.DoesNotExist:
        messages.error(request, 'Template not found.')
    except Exception as e:
        logger.error(f"Error toggling template: {str(e)}")
        messages.error(request, f'Error updating template: {str(e)}')
    return redirect('manage_templates')


@login_required
@require_http_methods(["POST"])
def delete_template(request, pk):
    """Delete a database template (only custom uploaded templates, not default ones)"""
    from .models import CertificateTemplate
    try:
        template = CertificateTemplate.objects.get(pk=pk)
        name = template.name
        template.delete()
        messages.success(request, f'Template "{name}" deleted successfully.')
    except CertificateTemplate.DoesNotExist:
        messages.error(request, 'Template not found.')
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        messages.error(request, f'Error deleting template: {str(e)}')
    return redirect('manage_templates')

