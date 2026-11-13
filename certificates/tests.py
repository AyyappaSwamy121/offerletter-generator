import os
import django
from django.apps import apps

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
if not apps.ready:
    django.setup()

import unittest
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.core import mail
from certificates.models import Certificate, SystemConfiguration
from certificates.utils import get_csc_logo_info, send_certificate_email


class CertificateEmailLogoTests(unittest.TestCase):

    def setUp(self):
        # Ensure email automation is enabled in configuration
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
        cert = Certificate.objects.filter(certificate_image__isnull=False).first()
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
        certs = list(Certificate.objects.filter(certificate_image__isnull=False)[:3])
        if len(certs) < 2:
            self.skipTest("Need at least 2 certificates for bulk test")

        with mail.get_connection('django.core.mail.backends.locmem.EmailBackend') as connection:
            with patch('django.core.mail.EmailMultiAlternatives.get_connection', return_value=connection):
                mail.outbox = []
                for i, c in enumerate(certs):
                    c.email = f"bulk_student_{i}@example.com"
                    c.save()
                    send_certificate_email(c)

                self.assertEqual(len(mail.outbox), len(certs))
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
        cert = Certificate.objects.filter(certificate_image__isnull=False).first()
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


if __name__ == '__main__':
    unittest.main()


class MultiCollegeRBACTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.test import Client
        from certificates.models import College, CollegeAdminProfile, AuditLog
        from django.contrib.auth.models import User

        cls.Client = Client
        cls.User = User
        cls.College = College
        cls.CollegeAdminProfile = CollegeAdminProfile
        cls.AuditLog = AuditLog

        # Super Admin
        cls.super_user, _ = User.objects.get_or_create(
            username='test_super_admin_perm',
            defaults={'email': 'super_perm@test.com', 'is_staff': True, 'is_superuser': True}
        )
        cls.super_user.set_password('SuperPass123!')
        cls.super_user.is_staff = True
        cls.super_user.is_superuser = True
        cls.super_user.is_active = True
        cls.super_user.save()

        # Pragati College
        cls.college_pragati, _ = College.objects.get_or_create(
            name='Pragati Engineering College',
            defaults={'code': 'PRAGATI', 'is_active': True}
        )
        cls.college_pragati.is_active = True
        cls.college_pragati.save()

        # Aditya College
        cls.college_aditya, _ = College.objects.get_or_create(
            name='Aditya University',
            defaults={'code': 'ADITYA', 'is_active': True}
        )
        cls.college_aditya.is_active = True
        cls.college_aditya.save()

        # Pragati Admin
        cls.user_pragati, _ = User.objects.get_or_create(
            username='pragati_test_perm@test.com',
            defaults={'email': 'pragati_test_perm@test.com', 'is_staff': False, 'is_superuser': False}
        )
        cls.user_pragati.set_password('PragatiPass123!')
        cls.user_pragati.is_active = True
        cls.user_pragati.save()

        cls.pragati_profile, _ = CollegeAdminProfile.objects.get_or_create(
            user=cls.user_pragati,
            defaults={'college': cls.college_pragati, 'full_name': 'Pragati Admin Incharge', 'is_active': True}
        )
        cls.pragati_profile.is_active = True
        cls.pragati_profile.college = cls.college_pragati
        cls.pragati_profile.save()

        # Aditya Admin
        cls.user_aditya, _ = User.objects.get_or_create(
            username='aditya_test_perm@test.com',
            defaults={'email': 'aditya_test_perm@test.com', 'is_staff': False, 'is_superuser': False}
        )
        cls.user_aditya.set_password('AdityaPass123!')
        cls.user_aditya.is_active = True
        cls.user_aditya.save()

        cls.aditya_profile, _ = CollegeAdminProfile.objects.get_or_create(
            user=cls.user_aditya,
            defaults={'college': cls.college_aditya, 'full_name': 'Aditya Admin Incharge', 'is_active': True}
        )
        cls.aditya_profile.is_active = True
        cls.aditya_profile.college = cls.college_aditya
        cls.aditya_profile.save()

        # Certificates
        cls.pragati_cert = Certificate.objects.filter(college=cls.college_pragati, is_deleted=False).first()
        if not cls.pragati_cert:
            cls.pragati_cert = Certificate.objects.create(
                full_name="Pragati Student Perm A",
                roll_number="PRAG_PERM_001",
                college_name="Pragati Engineering College",
                college=cls.college_pragati,
                email="prag_perm_student@example.com"
            )

        cls.aditya_cert = Certificate.objects.filter(college=cls.college_aditya, is_deleted=False).first()
        if not cls.aditya_cert:
            cls.aditya_cert = Certificate.objects.create(
                full_name="Aditya Student Perm B",
                roll_number="ADIT_PERM_001",
                college_name="Aditya University",
                college=cls.college_aditya,
                email="adit_perm_student@example.com"
            )

    @classmethod
    def tearDownClass(cls):
        from django.contrib.auth.models import User
        User.objects.filter(username__in=[
            'test_super_admin_perm',
            'pragati_test_perm@test.com',
            'aditya_test_perm@test.com'
        ]).delete()
        super().tearDownClass()

    def assertContains(self, response, text, status_code=200):
        if status_code is not None:
            self.assertEqual(response.status_code, status_code)
        content = response.content.decode('utf-8', errors='replace')
        self.assertIn(text, content, f"Expected '{text}' to be found in response content.")

    def test_super_admin_login(self):
        """Super Admin logs in and redirects to /home/."""
        c = self.Client()
        res = c.post('/login/', {'username': 'test_super_admin_perm', 'password': 'SuperPass123!'}, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, '/home/')

    def test_college_admin_login_and_redirect(self):
        """College Admin logs in with email and redirects to /college/dashboard/."""
        c = self.Client()
        res = c.post('/login/', {'username': 'pragati_test_perm@test.com', 'password': 'PragatiPass123!'}, follow=False)
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

    def test_college_dashboard_data_isolation(self):
        """Pragati Admin sees only Pragati records and cannot see Aditya records."""
        c = self.Client()
        c.force_login(self.user_pragati)

        res = c.get('/college/dashboard/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Pragati Engineering College')
        content = res.content.decode('utf-8')
        self.assertIn(self.pragati_cert.full_name, content)
        self.assertNotIn(self.aditya_cert.full_name, content)

    def test_prevent_idor_detail_and_pdf(self):
        """Pragati Admin receives 404 when accessing Aditya records (IDOR prevention)."""
        c = self.Client()
        c.force_login(self.user_pragati)

        # Own Pragati record -> 200
        res_own = c.get(f'/college/offer-letter/{self.pragati_cert.id}/detail/')
        self.assertEqual(res_own.status_code, 200)

        # Foreign Aditya record -> 404
        res_foreign_detail = c.get(f'/college/offer-letter/{self.aditya_cert.id}/detail/')
        self.assertEqual(res_foreign_detail.status_code, 404)

        res_foreign_pdf = c.get(f'/college/offer-letter/{self.aditya_cert.id}/download-pdf/')
        self.assertEqual(res_foreign_pdf.status_code, 404)

    def test_bulk_zip_strips_foreign_ids(self):
        """Client-submitted foreign IDs are stripped from bulk ZIP download."""
        import zipfile
        import io
        c = self.Client()
        c.force_login(self.user_pragati)

        payload = {'selected_ids': [str(self.pragati_cert.id), str(self.aditya_cert.id)]}
        res = c.post('/college/offer-letters/download-selected-zip/', payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/zip')

        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        aditya_roll = self.aditya_cert.roll_number.replace(' ', '_')
        has_aditya = any(aditya_roll in n for n in names)
        self.assertFalse(has_aditya, "Foreign college file found in bulk ZIP download!")

    def test_college_admin_blocked_from_super_admin_views(self):
        """College Admin is redirected away from Super Admin management pages."""
        c = self.Client()
        c.force_login(self.user_pragati)

        res1 = c.get('/college-admins/', follow=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn('/college/dashboard/', res1.url)

        res2 = c.get('/audit-logs/', follow=False)
        self.assertEqual(res2.status_code, 302)
        self.assertIn('/college/dashboard/', res2.url)

    def test_export_data_isolation(self):
        """Exports contain only records belonging to the authenticated college."""
        import openpyxl
        import io
        c = self.Client()
        c.force_login(self.user_aditya)

        res = c.get('/college/offer-letters/export-excel/')
        self.assertEqual(res.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(res.content))
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            col_name = row[5]
            self.assertIn('Aditya', col_name)
