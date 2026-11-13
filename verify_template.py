import os
import django
from django.conf import settings
from django.template import Template, Context

# Minimal settings to allow template parsing
if not settings.configured:
    settings.configure(
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'APP_DIRS': True,
        }],
        INSTALLED_APPS=[
            'django.contrib.staticfiles',
        ]
    )
    django.setup()

file_path = r"c:\Users\ASUS\OneDrive\Desktop\certificate_system final after modi\certificate_system\templates\certificates\generate.html"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We just want to check syntax, so creating a Template object is enough
    print(f"Parsing {file_path}...")
    t = Template(content)
    print("SUCCESS: Template syntax is valid.")

except Exception as e:
    print(f"ERROR: {e}")
