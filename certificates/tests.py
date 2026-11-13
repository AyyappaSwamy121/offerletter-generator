import os
import io
import zipfile
import django
from django.apps import apps

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
if not apps.ready:
    django.setup()

import unittest
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.core import mail
from django.test import Client
from django.contrib.auth.models import User
from certificates.models import Certificate, College, CollegeAdminProfile, AuditLog, SystemConfiguration
from certificates.utils import get_csc_logo_info, send_certificate_email


class CertificateEmailLogoTests(unittest.TestCase):
    created_dummy_files = []
    sample_cert = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = SystemConfiguration.get_solo()
        config.email_automation_enabled = True
        config.save()

        cls.sample_cert = Certificate.objects.exclude(certificate_image='').exclude(certificate_image__isnull=True).first()
        if cls.sample_cert:
            if cls.sample_cert.certificate_image:
                img_path = cls.sample_cert.certificate_image.path
                os.makedirs(os.path.dirname(img_path), exist_ok=True)
                if not os.path.isfile(img_path):
                    with open(img_path, 'wb') as f:
                        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82')
                    cls.created_dummy_files.append(img_path)
            if cls.sample_cert.certificate_pdf:
                pdf_path = cls.sample_cert.certificate_pdf.path
                os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                if not os.path.isfile(pdf_path):
                    with open(pdf_path, 'wb') as f:
                        f.write(b'%PDF-1.4 test')
                    cls.created_dummy_files.append(pdf_path)

    @classmethod
    def tearDownClass(cls):
        for fpath in cls.created_dummy_files:
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
            except Exception:
                pass
        super().tearDownClass()

    def setUp(self):
        config = SystemConfiguration.get_solo()
        config.email_automation_enabled = True
        config.save()

    def test_logo_file_exists_on_disk(self):
        """Verify the CSC India logo file exists on disk at settings.CSC_LOGO_PATH or media/CSC LOGO.png."""
        logo_path = getattr(settings, 'CSC_LOGO_PATH', os.path.join(settings.MEDIA_ROOT, 'CSC LOGO.png'))
        self.assertTrue(os.path.isfile(logo_path), f"CSC India logo does not exist at {logo_path}")
        self.assertGreater(os.path.getsize(logo_path), 0, "CSC India logo file is empty")

    def test_get_csc_logo_info_metadata(self):
        """Verify get_csc_logo_info returns valid metadata, CID, and binary data."""
        import certificates.utils as utils
        utils._CSC_LOGO_CACHE = None
        info = get_csc_logo_info()
        self.assertIsNotNone(info)
        self.assertEqual(info['cid'], 'csc_logo')
        self.assertEqual(info['subtype'], 'png')
        self.assertIn('CSC LOGO', info['filename'])
        self.assertGreater(len(info['data']), 0)

    def test_single_email_has_inline_logo_and_attachments(self):
        """Verify single email embeds the logo with CID and preserves existing attachments."""
        cert = self.sample_cert
        if not cert:
            self.skipTest("No certificate with certificate_image found in database")

        with mail.get_connection('django.core.mail.backends.locmem.EmailBackend') as connection:
            with patch('django.core.mail.EmailMultiAlternatives.get_connection', return_value=connection):
                mail.outbox = []
                cert.email = 'test_student@example.com'
                cert.save()

                send_certificate_email(cert)

                self.assertEqual(len(mail.outbox), 1)
                sent_email = mail.outbox[0]

                # Verify HTML references cid:csc_logo
                self.assertEqual(len(sent_email.alternatives), 1)
                html_body = sent_email.alternatives[0][0]
                self.assertIn('src="cid:csc_logo"', html_body)
                self.assertIn('alt="Council for Skills and Competencies (CSC India)"', html_body)

                # Inspect MIME parts
                mime_msg = sent_email.message()
                parts = mime_msg.get_payload()

                # Part 0 is multipart/alternative (plain text & HTML)
                self.assertEqual(parts[0].get_content_type(), 'multipart/alternative')

                # Part 1 is the inline logo image
                logo_part = parts[1]
                self.assertEqual(logo_part.get_content_type(), 'image/png')
                self.assertEqual(logo_part.get('Content-ID'), '<csc_logo>')
                self.assertIn('inline', logo_part.get('Content-Disposition'))

                # Subsequent parts are offer letter image and PDF attachments
                found_png_attachment = False
                found_pdf_attachment = False
                for part in parts[2:]:
                    disp = part.get('Content-Disposition', '')
                    c_type = part.get_content_type()
                    if 'attachment' in disp:
                        if c_type == 'image/png':
                            found_png_attachment = True
                        elif c_type == 'application/pdf':
                            found_pdf_attachment = True

                self.assertTrue(found_png_attachment, "Offer letter PNG image attachment missing")
                if cert.certificate_pdf:
                    self.assertTrue(found_pdf_attachment, "Offer letter PDF attachment missing")

    def test_bulk_email_all_receive_inline_logo(self):
        """Verify bulk email workflow provides each recipient with inline logo and attachments."""
        cert = self.sample_cert
        if not cert:
            self.skipTest("Need at least 1 certificate for bulk test")

        with mail.get_connection('django.core.mail.backends.locmem.EmailBackend') as connection:
            with patch('django.core.mail.EmailMultiAlternatives.get_connection', return_value=connection):
                mail.outbox = []
                for i in range(2):
                    cert.email = f"bulk_student_{i}@example.com"
                    cert.save()
                    send_certificate_email(cert)

                self.assertEqual(len(mail.outbox), 2)
                for email in mail.outbox:
                    html = email.alternatives[0][0]
                    self.assertIn('src="cid:csc_logo"', html)
                    mime_msg = email.message()
                    parts = mime_msg.get_payload()
                    logo_part = parts[1]
                    self.assertEqual(logo_part.get('Content-ID'), '<csc_logo>')
                    self.assertIn('inline', logo_part.get('Content-Disposition'))

    def test_missing_logo_fallback_does_not_crash(self):
        """Verify that when logo is missing, email falls back to public URL without crashing."""
        cert = self.sample_cert
        if not cert:
            self.skipTest("No certificate with certificate_image found")

        with mail.get_connection('django.core.mail.backends.locmem.EmailBackend') as connection:
            with patch('django.core.mail.EmailMultiAlternatives.get_connection', return_value=connection):
                mail.outbox = []
                with patch('certificates.utils.get_csc_logo_info', return_value=None):
                    send_certificate_email(cert)

                self.assertEqual(len(mail.outbox), 1)
                sent_email = mail.outbox[0]
                html_body = sent_email.alternatives[0][0]
                self.assertIn('/media/CSC%20LOGO.png', html_body)
                self.assertNotIn('cid:csc_logo', html_body)


class MultiCollegeRBACTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Client = Client
        cls.User = User
        cls.College = College
        cls.CollegeAdminProfile = CollegeAdminProfile
        cls.AuditLog = AuditLog

        # 1. Super Admin
        cls.super_user, _ = User.objects.get_or_create(
            username='test_super_admin_perm',
            defaults={'email': 'super_perm@test.com', 'is_staff': True, 'is_superuser': True}
        )
        cls.super_user.set_password('SuperPass123!')
        cls.super_user.is_staff = True
        cls.super_user.is_superuser = True
        cls.super_user.is_active = True
        cls.super_user.save()

        # 2. Colleges
        cls.college_pragati, _ = College.objects.get_or_create(
            name='Pragati Engineering College',
            defaults={'code': 'PRAGATI', 'is_active': True}
        )
        cls.college_pragati.is_active = True
        cls.college_pragati.save()

        cls.college_aditya, _ = College.objects.get_or_create(
            name='Aditya University',
            defaults={'code': 'ADITYA', 'is_active': True}
        )
        cls.college_aditya.is_active = True
        cls.college_aditya.save()

        cls.college_gayatri, _ = College.objects.get_or_create(
            name='Gayatri College of Engineering',
            defaults={'code': 'GAYATRI', 'is_active': True}
        )
        cls.college_gayatri.is_active = True
        cls.college_gayatri.save()

        # 3. Single-College Admin: Pragati
        cls.user_pragati, _ = User.objects.get_or_create(
            username='pragati_test_perm@test.com',
            defaults={'email': 'pragati_test_perm@test.com', 'is_staff': False, 'is_superuser': False}
        )
        cls.user_pragati.set_password('PragatiPass123!')
        cls.user_pragati.is_active = True
        cls.user_pragati.save()

        cls.pragati_profile, _ = CollegeAdminProfile.objects.get_or_create(
            user=cls.user_pragati,
            defaults={'full_name': 'Pragati Admin Incharge', 'is_active': True}
        )
        cls.pragati_profile.is_active = True
        cls.pragati_profile.college = cls.college_pragati
        cls.pragati_profile.save()
        cls.pragati_profile.colleges.set([cls.college_pragati])

        # 4. Single-College Admin: Aditya
        cls.user_aditya, _ = User.objects.get_or_create(
            username='aditya_test_perm@test.com',
            defaults={'email': 'aditya_test_perm@test.com', 'is_staff': False, 'is_superuser': False}
        )
        cls.user_aditya.set_password('AdityaPass123!')
        cls.user_aditya.is_active = True
        cls.user_aditya.save()

        cls.aditya_profile, _ = CollegeAdminProfile.objects.get_or_create(
            user=cls.user_aditya,
            defaults={'full_name': 'Aditya Admin Incharge', 'is_active': True}
        )
        cls.aditya_profile.is_active = True
        cls.aditya_profile.college = cls.college_aditya
        cls.aditya_profile.save()
        cls.aditya_profile.colleges.set([cls.college_aditya])

        # 5. Multi-College Admin: Avinash (Assigned Pragati + Aditya)
        cls.user_avinash, _ = User.objects.get_or_create(
            username='avinash@gmail.com',
            defaults={'email': 'avinash@gmail.com', 'is_staff': False, 'is_superuser': False}
        )
        cls.user_avinash.set_password('AvinashPass123!')
        cls.user_avinash.is_active = True
        cls.user_avinash.save()

        cls.avinash_profile, _ = CollegeAdminProfile.objects.get_or_create(
            user=cls.user_avinash,
            defaults={'full_name': 'Avinash Multi-Admin', 'is_active': True}
        )
        cls.avinash_profile.is_active = True
        cls.avinash_profile.college = cls.college_pragati
        cls.avinash_profile.save()
        cls.avinash_profile.colleges.set([cls.college_pragati, cls.college_aditya])

        # 6. Offer Letter Certificates for all 3 Colleges
        cls.pragati_cert, _ = Certificate.objects.get_or_create(
            roll_number="PRAG_PERM_001",
            defaults={
                'full_name': "Pragati Student Alpha",
                'college_name': "Pragati Engineering College",
                'college': cls.college_pragati,
                'email': "prag_alpha@example.com",
                'course': "Computer Science",
                'internship_title': "Web Development Intern"
            }
        )
        cls.pragati_cert.college = cls.college_pragati
        cls.pragati_cert.is_deleted = False
        cls.pragati_cert.save()

        cls.aditya_cert, _ = Certificate.objects.get_or_create(
            roll_number="ADIT_PERM_001",
            defaults={
                'full_name': "Aditya Student Beta",
                'college_name': "Aditya University",
                'college': cls.college_aditya,
                'email': "adit_beta@example.com",
                'course': "Artificial Intelligence",
                'internship_title': "AI Research Intern"
            }
        )
        cls.aditya_cert.college = cls.college_aditya
        cls.aditya_cert.is_deleted = False
        cls.aditya_cert.save()

        cls.gayatri_cert, _ = Certificate.objects.get_or_create(
            roll_number="GAYA_PERM_001",
            defaults={
                'full_name': "Gayatri Student Gamma",
                'college_name': "Gayatri College of Engineering",
                'college': cls.college_gayatri,
                'email': "gaya_gamma@example.com",
                'course': "Mechanical Engineering",
                'internship_title': "CAD Intern"
            }
        )
        cls.gayatri_cert.college = cls.college_gayatri
        cls.gayatri_cert.is_deleted = False
        cls.gayatri_cert.save()

    @classmethod
    def tearDownClass(cls):
        from django.contrib.auth.models import User
        User.objects.filter(username__in=[
            'test_super_admin_perm',
            'pragati_test_perm@test.com',
            'aditya_test_perm@test.com',
            'avinash@gmail.com',
            'new_temp_admin@test.com'
        ]).delete()
        super().tearDownClass()

    def assertContains(self, response, text, status_code=200):
        if status_code is not None:
            self.assertEqual(response.status_code, status_code)
        content = response.content.decode('utf-8', errors='replace')
        self.assertIn(text, content, f"Expected '{text}' to be found in response content.")

    # --- Authentication & Login Tests ---

    def test_super_admin_login(self):
        """Super Admin logs in and redirects to /home/."""
        c = self.Client()
        res = c.post('/login/', {'username': 'test_super_admin_perm', 'password': 'SuperPass123!'}, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/home/')

    def test_single_college_admin_login_and_redirect(self):
        """Single-college admin logs in with email and redirects to /college/dashboard/."""
        c = self.Client()
        res = c.post('/login/', {'username': 'pragati_test_perm@test.com', 'password': 'PragatiPass123!'}, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/college/dashboard/')

    def test_multi_college_admin_login_and_redirect(self):
        """Multi-college admin (Avinash) logs in with email and redirects to /college/dashboard/."""
        c = self.Client()
        res = c.post('/login/', {'username': 'avinash@gmail.com', 'password': 'AvinashPass123!'}, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/college/dashboard/')

    def test_deactivated_college_admin_blocked(self):
        """Deactivated college admin profile is blocked from logging in."""
        self.pragati_profile.is_active = False
        self.pragati_profile.save()

        c = self.Client()
        res = c.post('/login/', {'username': 'pragati_test_perm@test.com', 'password': 'PragatiPass123!'}, follow=True)
        self.assertContains(res, 'deactivated')

        self.pragati_profile.is_active = True
        self.pragati_profile.save()

    # --- Multi-College Combined Dashboard & Data Isolation Tests ---

    def test_multi_college_dashboard_combined_records(self):
        """Avinash's dashboard displays offer letters belonging to BOTH Pragati and Aditya, but NOT Gayatri."""
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get('/college/dashboard/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Should contain both assigned colleges' records
        self.assertIn(self.pragati_cert.full_name, content)
        self.assertIn(self.aditya_cert.full_name, content)

        # Must NEVER contain unassigned Gayatri records
        self.assertNotIn(self.gayatri_cert.full_name, content)

    def test_multi_college_filtering_pragati(self):
        """When Avinash filters by Pragati (?college_id=pragati), only Pragati records are shown."""
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get(f'/college/dashboard/?college_id={self.college_pragati.id}')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn(self.pragati_cert.full_name, content)
        self.assertNotIn(self.aditya_cert.full_name, content)
        self.assertNotIn(self.gayatri_cert.full_name, content)

    def test_multi_college_filtering_aditya(self):
        """When Avinash filters by Aditya (?college_id=aditya), only Aditya records are shown."""
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get(f'/college/dashboard/?college_id={self.college_aditya.id}')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn(self.aditya_cert.full_name, content)
        self.assertNotIn(self.pragati_cert.full_name, content)
        self.assertNotIn(self.gayatri_cert.full_name, content)

    def test_multi_college_filtering_unassigned_ignored(self):
        """When Avinash requests ?college_id=gayatri (unassigned), the filter is ignored and defaults to assigned colleges."""
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get(f'/college/dashboard/?college_id={self.college_gayatri.id}')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        # Shows assigned colleges' records
        self.assertIn(self.pragati_cert.full_name, content)
        self.assertIn(self.aditya_cert.full_name, content)
        # Gayatri remains inaccessible
        self.assertNotIn(self.gayatri_cert.full_name, content)

    def test_single_college_admin_dashboard_isolation(self):
        """Pragati Admin sees only Pragati records and cannot see Aditya or Gayatri records."""
        c = self.Client()
        c.force_login(self.user_pragati)

        res = c.get('/college/dashboard/')
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')

        self.assertIn(self.pragati_cert.full_name, content)
        self.assertNotIn(self.aditya_cert.full_name, content)
        self.assertNotIn(self.gayatri_cert.full_name, content)

    # --- Strict IDOR Defense Tests ---

    def test_prevent_idor_detail_and_pdf(self):
        """Avinash can access Pragati & Aditya records, but receives 404 when requesting Gayatri records."""
        c = self.Client()
        c.force_login(self.user_avinash)

        # Own Pragati record -> 200
        res_pragati_detail = c.get(f'/college/offer-letter/{self.pragati_cert.id}/detail/')
        self.assertEqual(res_pragati_detail.status_code, 200)

        # Own Aditya record -> 200
        res_aditya_detail = c.get(f'/college/offer-letter/{self.aditya_cert.id}/detail/')
        self.assertEqual(res_aditya_detail.status_code, 200)

        # Foreign Gayatri record -> 404 (IDOR blocked)
        res_gayatri_detail = c.get(f'/college/offer-letter/{self.gayatri_cert.id}/detail/')
        self.assertEqual(res_gayatri_detail.status_code, 404)

        # Foreign Gayatri PDF download -> 404 (IDOR blocked)
        res_gayatri_pdf = c.get(f'/college/offer-letter/{self.gayatri_cert.id}/download-pdf/')
        self.assertEqual(res_gayatri_pdf.status_code, 404)

    # --- Bulk Downloads & Exports Isolation Tests ---

    def test_bulk_zip_strips_foreign_ids(self):
        """Avinash submits Pragati, Aditya, and Gayatri IDs to bulk ZIP; Gayatri ID is stripped server-side."""
        c = self.Client()
        c.force_login(self.user_avinash)

        payload = {'selected_ids': [str(self.pragati_cert.id), str(self.aditya_cert.id), str(self.gayatri_cert.id)]}
        res = c.post('/college/offer-letters/download-selected-zip/', payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/zip')

        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        gayatri_roll = self.gayatri_cert.roll_number.replace(' ', '_')
        has_gayatri = any(gayatri_roll in n for n in names)
        self.assertFalse(has_gayatri, "Foreign unassigned college file found in bulk ZIP download!")

    def test_export_excel_multi_college_isolation(self):
        """Avinash's Excel export contains Pragati and Aditya records, and zero Gayatri records."""
        import openpyxl
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get('/college/offer-letters/export-excel/')
        self.assertEqual(res.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        ws = wb.active
        college_names = [row[5] for row in ws.iter_rows(min_row=2, values_only=True)]

        # Must contain Pragati and Aditya
        self.assertTrue(any('Pragati' in col for col in college_names))
        self.assertTrue(any('Aditya' in col for col in college_names))
        # Must NOT contain Gayatri
        self.assertFalse(any('Gayatri' in col for col in college_names))

    def test_export_csv_multi_college_isolation(self):
        """Avinash's CSV export contains Pragati and Aditya records, and zero Gayatri records."""
        import csv
        c = self.Client()
        c.force_login(self.user_avinash)

        res = c.get('/college/offer-letters/export-csv/')
        self.assertEqual(res.status_code, 200)
        lines = res.content.decode('utf-8').splitlines()
        reader = csv.reader(lines)
        rows = list(reader)
        college_names = [r[5] for r in rows[1:] if len(r) > 5]

        self.assertTrue(any('Pragati' in col for col in college_names))
        self.assertTrue(any('Aditya' in col for col in college_names))
        self.assertFalse(any('Gayatri' in col for col in college_names))

    # --- Super Admin Management Tests ---

    def test_super_admin_create_multi_college_admin(self):
        """Super Admin creates a new administrator assigned to multiple colleges."""
        c = self.Client()
        c.force_login(self.super_user)

        data = {
            'full_name': 'Test Temp Multi Admin',
            'email': 'new_temp_admin@test.com',
            'phone': '9876543210',
            'college_ids': [str(self.college_pragati.id), str(self.college_gayatri.id)],
            'password': 'TempAdminPass123!',
            'confirm_password': 'TempAdminPass123!',
            'is_active': 'on'
        }
        res = c.post('/college-admins/create/', data, follow=True)
        self.assertEqual(res.status_code, 200)

        # Verify created in DB
        created_user = User.objects.filter(username='new_temp_admin@test.com').first()
        self.assertIsNotNone(created_user)
        self.assertIsNotNone(created_user.college_profile)
        assigned_colleges = list(created_user.college_profile.colleges.values_list('name', flat=True))
        self.assertIn('Pragati Engineering College', assigned_colleges)
        self.assertIn('Gayatri College of Engineering', assigned_colleges)
        self.assertNotIn('Aditya University', assigned_colleges)

    def test_super_admin_create_validation_zero_colleges(self):
        """Creating an administrator without selecting at least one college is rejected with an error message."""
        c = self.Client()
        c.force_login(self.super_user)

        data = {
            'full_name': 'Invalid Admin No College',
            'email': 'invalid_no_col@test.com',
            'phone': '9876543210',
            'college_ids': [],  # No colleges selected!
            'password': 'TempAdminPass123!',
            'confirm_password': 'TempAdminPass123!',
            'is_active': 'on'
        }
        res = c.post('/college-admins/create/', data, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Please select at least one active institution')
        self.assertIsNone(User.objects.filter(username='invalid_no_col@test.com').first())

    def test_college_admin_blocked_from_super_admin_views(self):
        """College Admin is redirected away from Super Admin management pages."""
        c = self.Client()
        c.force_login(self.user_avinash)

        res1 = c.get('/college-admins/', follow=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn('/college/dashboard/', res1.url)

        res2 = c.get('/audit-logs/', follow=False)
        self.assertEqual(res2.status_code, 302)
        self.assertIn('/college/dashboard/', res2.url)


if __name__ == '__main__':
    unittest.main()
