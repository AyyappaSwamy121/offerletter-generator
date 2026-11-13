# Offer Letter Generation System (CertGen)

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django Version](https://img.shields.io/badge/django-4.2%20LTS-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

A multi-tenant, SaaS-enabled web application developed for the **Council for Skills and Competencies (CSC India)** to generate, manage, personalize, verify, and distribute official internship offer letters for thousands of students across multiple colleges and universities.

---

## 🌟 Key Features

### 1. Multi-College Role-Based Access Control (RBAC) & Tenant Isolation
- **Dual User Roles**:
  - **Super Administrator**: Full system control, global statistics, cross-institution repository access, college administrator account creation, and audit trail management.
  - **College Administrator**: Secure, scoped access restricted exclusively to the administrator's assigned institution.
- **Strict Server-Side IDOR Defense**: College administrators can never view, download, or tamper with another college's documents by altering URLs, form payloads, API endpoints, or record IDs (enforced via Django ORM filtering and custom decorators).

### 2. College Administrator SaaS Dashboard (`/college/dashboard/`)
- **Institution Analytics**: Real-time metric cards displaying Total Offer Letters, Distinct Students, Letters Issued This Month, and Delivery Status.
- **Repository Search & Filtering**: Instant search across Student Name, Roll Number, and Offer Letter ID, with multi-criteria filtering by Course/Specialization, Email Delivery Status, and Date Range.
- **AJAX Details Modal**: Quick-view modal displaying complete student metadata, duration, stipend, issue dates, and public verification links.
- **Self-Service Security**: In-dashboard password updates with session re-authentication.

### 3. Bulk Operations & Data Exports
- **Single PDF Download**: Instant generation and delivery of personalized offer letters.
- **Selected Bulk ZIP Archive**: Checkbox-based multi-selection allowing administrators to package and download dozens of student offer letter PDFs in a single named `.zip` archive.
- **Filtered Bulk ZIP Archive**: Download all offer letters matching active search/filter criteria.
- **Excel Spreadsheet Export (`.xlsx`)**: Custom-styled OpenPyXL export featuring headers, borders, column auto-width, and verification links.
- **CSV Data Export**: UTF-8 BOM-encoded CSV compatible with Microsoft Excel and Google Sheets.

### 4. Automated Email Delivery with Embedded CID Logo
- **MIME Content-ID (CID) Inline Logo**: Uses `EmailMultiAlternatives` and `MIMEImage` with `<csc_logo>` Content-ID, ensuring the CSC India logo renders in student email clients (Gmail, Outlook, Yahoo) without triggering "external images blocked" warnings.
- **Email Delivery Tracking**: Automatically tracks delivery timestamps and email sent status in the database.

### 5. Super Admin College & Account Management (`/college-admins/`)
- Dynamic registration and assignment of institutional coordinators without hardcoded college lists.
- Instant active/inactive account toggling and modal-based administrator password resets.

### 6. Audit Trail & Security Logging (`/audit-logs/`)
- Comprehensive activity logging capturing logins, failed authentication attempts, single downloads, bulk ZIP generations, Excel/CSV exports, and administrative account changes with client IP addresses.

### 7. Public Verification Portal (`/verify/<certificate_id>/`)
- QR-code-backed public verification portal allowing employers and educational institutions to verify candidate offer letters in real time.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Backend Framework** | Django 4.2 LTS (Python 3.11+) |
| **Image & PDF Processing**| Pillow (PIL), ReportLab, qrcode[pil] |
| **Spreadsheets & Data** | OpenPyXL, XlsxWriter, Python CSV |
| **Database** | SQLite (Development) / PostgreSQL (Production) |
| **Frontend** | HTML5, CSS3, JavaScript (ES6+), Bootstrap 5, FontAwesome 6 |
| **WSGI / Web Server** | Gunicorn behind Nginx reverse proxy |
| **Email Service** | SMTP (ZeptoMail / Gmail / Custom SMTP) |
| **Cloud Backup** | Google Drive API v3 (Optional backup sync) |

---

## 📂 Project Structure

```text
├── certificate_project/          # Django Project Configuration
│   ├── settings.py               # Base settings & environment integration
│   ├── settings_production.py    # Production settings (PostgreSQL, SSL, HSTS)
│   ├── urls.py                   # Root URL configuration
│   └── wsgi.py                   # WSGI application entrypoint
├── certificates/                 # Main Application
│   ├── admin.py                  # Django admin registration & customizations
│   ├── admin_mgmt_views.py       # Super Admin: College Admin & Audit controllers
│   ├── college_views.py          # College Admin: Dashboard & Export controllers
│   ├── decorators.py             # Security & RBAC permission decorators
│   ├── forms.py                  # Form validation
│   ├── models.py                 # College, Profile, AuditLog, & Certificate models
│   ├── utils.py                  # PDF engine, QR generator, & MIME email engine
│   ├── views.py                  # Authentication, Home, & Single/Bulk generator views
│   ├── migrations/               # Database migrations (0001 through 0033)
│   └── tests.py                  # Automated test suite (Logo CID & RBAC tests)
├── media/                        # Static Branding & Media Assets
│   ├── CSC LOGO.png              # Official CSC India logo (used in emails & UI)
│   ├── CSC HEADER.png            # Official header banner
│   └── templates/                # Visual background templates for offer letters
├── static/                       # Static Assets (Fonts, sample Excel templates)
│   └── EXCEL_TEMPLATE_WITH_DATES.xlsx  # Sample student upload spreadsheet
├── templates/                    # Django HTML Templates
│   ├── base.html                 # Base layout, navbar, & footer
│   ├── login.html                # Responsive authentication page
│   └── certificates/             # Application templates
│       ├── college_dashboard.html   # College Admin SaaS portal
│       ├── college_admin_list.html  # Super Admin: Administrator listing
│       ├── college_admin_form.html  # Super Admin: Add/Edit admin form
│       ├── audit_log_list.html      # Super Admin: Audit trail table
│       └── home.html                # Super Admin overview dashboard
├── .env.example                  # Safe configuration template
├── .gitignore                    # Git exclusion rules
├── manage.py                     # Django management CLI
├── requirements.txt              # Python package dependencies
└── seed_colleges_production.py   # Idempotent college seeding & backfill script
```

---

## 🚀 Installation & Local Setup

### 1. Prerequisites
- Python 3.11 or higher
- Git
- Virtualenv (`python -m venv`)

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/offer-letter-system.git
cd offer-letter-system
```

### 3. Create & Activate a Virtual Environment
```bash
# On Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# On Windows (Command Prompt):
.\venv\Scripts\activate.bat
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy the example environment file and configure local values:
```bash
cp .env.example .env
```
*(On Windows: `copy .env.example .env`)*

Open `.env` and set:
```ini
SECRET_KEY=your-local-dev-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
```

### 6. Apply Database Migrations
```bash
python manage.py migrate
```

### 7. Seed Initial Colleges & Backfill Records (Optional)
To populate known colleges (Pragati, Aditya, LBRCE, VIIT, etc.):
```bash
python seed_colleges_production.py
```

### 8. Create a Super Administrator Account
```bash
python manage.py createsuperuser
```

### 9. Run the Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```
- **Login Portal:** [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)
- **Super Admin Dashboard:** [http://127.0.0.1:8000/home/](http://127.0.0.1:8000/home/)
- **College Management:** [http://127.0.0.1:8000/college-admins/](http://127.0.0.1:8000/college-admins/)
- **Audit Logs:** [http://127.0.0.1:8000/audit-logs/](http://127.0.0.1:8000/audit-logs/)

---

## 🧪 Running Automated Tests

The test suite covers email inline logo rendering, CID MIME structure, IDOR protection, bulk ZIP filtering, Excel data isolation, and authentication routing:

```bash
python -m unittest certificates.tests -v
```
*Expected Output:*
```text
test_bulk_email_all_receive_inline_logo (certificates.tests.CertificateEmailLogoTests) ... ok
test_get_csc_logo_info_metadata (certificates.tests.CertificateEmailLogoTests) ... ok
test_logo_file_exists_on_disk (certificates.tests.CertificateEmailLogoTests) ... ok
test_missing_logo_fallback_does_not_crash (certificates.tests.CertificateEmailLogoTests) ... ok
test_single_email_has_inline_logo_and_attachments (certificates.tests.CertificateEmailLogoTests) ... ok
test_bulk_zip_strips_foreign_ids (certificates.tests.MultiCollegeRBACTests) ... ok
test_college_admin_blocked_from_super_admin_views (certificates.tests.MultiCollegeRBACTests) ... ok
test_college_admin_login_and_redirect (certificates.tests.MultiCollegeRBACTests) ... ok
test_college_dashboard_data_isolation (certificates.tests.MultiCollegeRBACTests) ... ok
test_deactivated_college_admin_blocked (certificates.tests.MultiCollegeRBACTests) ... ok
test_export_data_isolation (certificates.tests.MultiCollegeRBACTests) ... ok
test_prevent_idor_detail_and_pdf (certificates.tests.MultiCollegeRBACTests) ... ok
test_super_admin_login (certificates.tests.MultiCollegeRBACTests) ... ok

Ran 13 tests in 4.8s: OK
```

---

## 🔐 Authentication & Roles Guide

| Role | Access URL | Permissions & Capabilities |
|---|---|---|
| **Super Admin** | `/home/` | Platform-wide analytics, all student records, create & manage college admin accounts, reset passwords, global export, system audit logs. |
| **College Admin** | `/college/dashboard/` | View and search only assigned college records, single PDF downloads, bulk ZIP downloads, filtered Excel/CSV exports, self-service password updates. |

### Creating a College Administrator Account:
1. Log in as Super Admin at `/login/`.
2. Navigate to **College Admins** (`/college-admins/`).
3. Click **Add College Admin** (`/college-admins/create/`).
4. Select the institution from the dynamic dropdown, enter the coordinator's name, email, and password.
5. The administrator can immediately log in using their email address at `/login/` and will be automatically routed to their institution's dashboard.

---

## 🌐 Production Deployment Overview

In production, the application runs behind **Nginx** reverse proxy and is served by **Gunicorn** on local port `127.0.0.1:8003`:

```text
[ Client HTTPS Request ]
           │
           ▼
[ Nginx Reverse Proxy (Port 443 / SSL) ]
           │
           ▼
[ Gunicorn WSGI Server (127.0.0.1:8003) ]
           │
           ▼
[ Django Application & Database ]
```

### Production Checklist:
1. Set `DEBUG=False` in `.env`.
2. Configure trusted domains in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.
3. Run migrations: `python manage.py migrate`.
4. Run static collection: `python manage.py collectstatic --noinput`.
5. Run college seed: `python seed_colleges_production.py`.
6. Start or reload Gunicorn: `sudo systemctl restart offerletters` or `kill -HUP <PID>`.

---

## 📄 License & Ownership

Proprietary software developed for the **Council for Skills and Competencies (CSC India)**.  
All rights reserved.
