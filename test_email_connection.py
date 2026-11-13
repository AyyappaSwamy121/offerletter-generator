import os
import django
from django.conf import settings
from django.core.mail import send_mail

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
django.setup()

def test_email():
    print("Testing email configuration...")
    print(f"HOST: {settings.EMAIL_HOST}")
    print(f"PORT: {settings.EMAIL_PORT}")
    print(f"USER: {settings.EMAIL_HOST_USER}")
    # Do not print password
    
    try:
        send_mail(
            subject='Test Email from Certificate System',
            message='This is a test email to verify credentials.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_HOST_USER], # Send to self
            fail_silently=False,
        )
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

if __name__ == '__main__':
    test_email()
