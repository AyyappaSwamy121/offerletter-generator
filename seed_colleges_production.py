"""
Safe College Seeding & Certificate Backfill Script for Production.
Associates existing historical offer letter records with their respective College tenants.
Safe to run multiple times (idempotent). Does not delete or modify student details.
"""
import os
import sys

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
import django
django.setup()

from certificates.models import College, Certificate, CollegeAdminProfile
from django.contrib.auth.models import User

print("================================================================")
print("  OFFER LETTER GENERATION SYSTEM: COLLEGE SEED & BACKFILL TOOL")
print("================================================================")

# 1. Primary colleges with known aliases/variations
known_colleges = [
    {
        'name': 'Pragati Engineering College',
        'code': 'PRAGATI',
        'aliases': '\n'.join([
            'Dept of CSE , Pragati Engineering College (A), Surampalem',
            'Dept of ECE , Pragati Engineering College (A), Surampalem',
            'Dept of CSE( AI & ML) , Pragati Engineering College (A), Surampalem',
            'Dept of CSE(DS) , Pragati Engineering College (A), Surampalem',
            'Dept of CSE(AI) , Pragati Engineering College (A), Surampalem',
            'Dept of IT , Pragati Engineering College (A), Surampalem',
            'Dept of EEE , Pragati Engineering College (A), Surampalem',
            'Dept of CSE(CS) , Pragati Engineering College (A), Surampalem',
            'Dept of Civil , Pragati Engineering College (A), Surampalem',
            'Dept of Mech , Pragati Engineering College (A), Surampalem',
            'Pragati Engineering College (A), Surampalem',
            'Pragati Engineering College',
        ]),
        'address': 'Surampalem, Near Peddapuram, East Godavari District, Andhra Pradesh 533437',
    },
    {
        'name': 'Audisankara College of Engineering & Technology',
        'code': 'AUDISANKARA',
        'aliases': 'Audisankara College of Engineering & Technology(A)\nAudisankara College of Engineering and Technology',
        'address': 'Gudur, Tirupati District, Andhra Pradesh 524101',
    },
    {
        'name': 'Lakireddy Bali Reddy College of Engineering',
        'code': 'LBRCE',
        'aliases': 'Lakireddy Bali Reddy College of Engineering(A)\nLakireddy Bali Reddy College of Engineering (A)\nLAKIREDDY BALIREDDY COLLEGE OF ENGINEERING',
        'address': 'Mylavaram, Krishna District, Andhra Pradesh 521230',
    },
    {
        'name': 'Aditya University',
        'code': 'ADITYA',
        'aliases': '\n'.join([
            'School of Business, Aditya University',
            'Aditya Engineering College',
            'Aditya College of Engineering and Technology',
            'Aditya Institute of Technology and Management',
            'ADITYA COLLEGE OF ENGINEERING',
        ]),
        'address': 'Aditya Nagar, ADB Road, Surampalem, Andhra Pradesh 533437',
    },
    {
        'name': 'SRK Institute of Technology',
        'code': 'SRKIT',
        'aliases': 'SRK Institute of Technology(A)',
        'address': 'Enikepadu, Vijayawada, Andhra Pradesh 521108',
    },
    {
        'name': "Vignan's Institute of Information Technology",
        'code': 'VIIT',
        'aliases': "Vignan's Institute of Information Technology\nVIIT",
        'address': 'Beside VSEZ, Vadlapudi Post, Gajuwaka, Visakhapatnam, Andhra Pradesh 530049',
    },
    {
        'name': 'PSCMR College of Engineering and Technology',
        'code': 'PSCMR',
        'aliases': 'PSCMR College of Engineering and Technology (A)',
        'address': 'Kothapeta, Vijayawada, Andhra Pradesh 520001',
    },
    {
        'name': 'Gayatri Vidya Parishad College of Engineering',
        'code': 'GVP',
        'aliases': '\n'.join([
            'Gayatri Vidya Parishad College for Degree & PG courses (A)',
            'GAYATHRI VIDYA PARISHAD COLL OF ENGG FOR WOMEN',
            'Gayatri College',
        ]),
        'address': 'Madhurawada, Visakhapatnam, Andhra Pradesh 530048',
    },
    {
        'name': 'ANITS - Anil Neerukonda Institute of Technology & Sciences',
        'code': 'ANITS',
        'aliases': 'ANITS\nANITS College\nAnil Neerukonda Institute of Technology and Sciences',
        'address': 'Sangivalasa, Bheemunipatnam, Visakhapatnam, Andhra Pradesh 531162',
    },
    {
        'name': 'Swarnandhra College of Engineering and Technology',
        'code': 'SWARNANDHRA',
        'aliases': 'Swarnandhra College of Engineering and Technology(A)\nSWARNANDHRA COLL. OF ENGG AND TECHNOLOGY',
        'address': 'Seetharampuram, Narsapur, West Godavari, Andhra Pradesh 534280',
    },
    {
        'name': 'KKR & KSR Institute of Technology and Sciences',
        'code': 'KITS',
        'aliases': 'KKR AND KSR INST OF TECHNOLOGY AND SCI\nKKR & KSR Institute of Technology and Sciences',
        'address': 'Vinjanampadu, Vatticherukuru Mandal, Guntur, Andhra Pradesh 522017',
    },
    {
        'name': 'Santhiram Engineering College',
        'code': 'SREC',
        'aliases': 'Santhiram Engineering College(A)',
        'address': 'NH-40, Nandyal, Kurnool District, Andhra Pradesh 518501',
    },
    {
        'name': 'SRINIVASA INSTITUTE OF MANAGEMENT STUDIES',
        'code': 'SIMS',
        'aliases': 'SRINIVASA INSTITUTE OF MANAGEMANT STUDIES\nSRINIVASA INSTITUTE OF MANAGEMENT STUDIES',
        'address': 'Visakhapatnam, Andhra Pradesh',
    },
    {
        'name': 'N S Raju Institute of Engineering and Technology',
        'code': 'NSRIT',
        'aliases': 'N S Raju Institute of Engineering and Technology',
        'address': 'Sontyam, Anandapuram, Visakhapatnam, Andhra Pradesh 531173',
    },
    {
        'name': 'JNTU GV College of Engineering Vizianagaram',
        'code': 'JNTUGV',
        'aliases': 'JNTU GV College of Engineering Vizianagaram',
        'address': 'Vizianagaram, Andhra Pradesh 535003',
    },
    {
        'name': 'SRI VENKATESWARA ARTS COLLEGE (TTD)',
        'code': 'SVAC',
        'aliases': 'SRI VENKATESWARA ARTS COLLEGE (TTD)',
        'address': 'Tirupati, Andhra Pradesh 517502',
    },
    {
        'name': 'Dr. Jyothirmayi Degree College',
        'code': 'DJDC',
        'aliases': 'Dr. Jyothirmayi Degree College',
        'address': 'Adoni, Kurnool District, Andhra Pradesh 518301',
    },
    {
        'name': 'KSRM College of Engineering',
        'code': 'KSRMCE',
        'aliases': 'KSRM College of Engineering',
        'address': 'Kadapa, Andhra Pradesh 516003',
    },
    {
        'name': 'Sri Ramakrishna Degree College (Autonomous)',
        'code': 'SRDC',
        'aliases': 'Sri Ramakrishna Degree College (Autonomous)\nSri Ramakrishna Degree College (A) Nandyal',
        'address': 'Nandyal, Andhra Pradesh',
    },
    {
        'name': 'Gates Institute of Technology',
        'code': 'GATES',
        'aliases': 'GATES INSTITUTE OF TECHNOLOGY\nGates Institute of Technology(A)',
        'address': 'Gooty, Anantapur District, Andhra Pradesh 515401',
    },
]

print("1. Seeding and updating known Colleges...")
for item in known_colleges:
    col, created = College.objects.update_or_create(
        name=item['name'],
        defaults={
            'code': item.get('code'),
            'aliases': item.get('aliases', ''),
            'address': item.get('address', ''),
            'is_active': True,
        }
    )
    status = "Created" if created else "Exists"
    print(f"   [{status}] {col.name}")

# Also discover and register distinct raw college names in existing records
ignore_list = {'', '6/46/3', 'dvfgf', 'fdf', 'fdffg', 'ss', 'vvfrfd'}
raw_colleges = Certificate.objects.values_list('college_name', flat=True).distinct()

for raw_name in raw_colleges:
    raw_clean = (raw_name or '').strip()
    if not raw_clean or raw_clean.lower() in ignore_list:
        continue

    already_covered = False
    for c in College.objects.all():
        if c.name.lower() in raw_clean.lower():
            already_covered = True
            break
        if c.aliases:
            for alias in c.aliases.splitlines():
                if alias.strip().lower() == raw_clean.lower():
                    already_covered = True
                    break
        if already_covered:
            break

    if not already_covered:
        c, created = College.objects.get_or_create(
            name=raw_clean,
            defaults={'aliases': raw_clean, 'is_active': True}
        )
        if created:
            print(f"   [Discovered Institution] {c.name}")

# 2. Backfill Certificate.college relationships
print("\n2. Linking Certificates to College Foreign Keys...")
all_colleges = list(College.objects.all())
matched_count = 0
unmatched_count = 0

for cert in Certificate.all_objects.all():
    raw_name = (cert.college_name or '').strip()
    if not raw_name:
        cert.college = None
        cert.save(update_fields=['college'], skip_validation=True)
        unmatched_count += 1
        continue

    matched = None
    # 1. Exact name match
    for c in all_colleges:
        if c.name.lower() == raw_name.lower():
            matched = c
            break
        if c.aliases:
            aliases_list = [a.strip().lower() for a in c.aliases.splitlines() if a.strip()]
            if raw_name.lower() in aliases_list:
                matched = c
                break

    # 2. Substring match
    if not matched:
        for c in all_colleges:
            if c.name.lower() in raw_name.lower():
                matched = c
                break

    if matched:
        cert.college = matched
        cert.save(update_fields=['college'], skip_validation=True)
        matched_count += 1
    else:
        cert.college = None
        cert.save(update_fields=['college'], skip_validation=True)
        unmatched_count += 1

print(f"   Backfill Complete -> Matched & Linked: {matched_count}, Unmatched/Ambiguous: {unmatched_count}")

# 3. Associate legacy 'pragati' user if present
try:
    pragati_user = User.objects.filter(username='pragati').first()
    pragati_college = College.objects.filter(name='Pragati Engineering College').first()
    if pragati_user and pragati_college:
        profile, p_created = CollegeAdminProfile.objects.update_or_create(
            user=pragati_user,
            defaults={
                'college': pragati_college,
                'full_name': 'Pragati College Administrator',
                'is_active': True,
            }
        )
        print(f"\n3. Associated legacy user '{pragati_user.username}' with '{pragati_college.name}'.")
except Exception as e:
    print(f"\n3. Legacy user association skipped: {e}")

print("\n================================================================")
print("  SEED & BACKFILL FINISHED SUCCESSFULLY!")
print("================================================================")

