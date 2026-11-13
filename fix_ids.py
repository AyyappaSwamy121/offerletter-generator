import os
import django
import sys

# Add project root to path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
django.setup()

from certificates.models import Certificate

def fix_certificates():
    # Find certificates with missing IDs (null or empty string)
    # Note: We check for both just in case
    certs_null = Certificate.objects.filter(certificate_id__isnull=True)
    certs_empty = Certificate.objects.filter(certificate_id='')
    
    # Use list() to evaluate querysets to avoid issues if we modify them while iterating,
    # though save() shouldn't affect the filter unless we were filtering on something else.
    # Actually, once saved, they won't match the filter anymore, so iterating over the queryset might be safe or might skip some if pagination was involved (but it's not here).
    # Safest is to list them.
    
    all_certs = list(certs_null) + list(certs_empty)
    unique_certs = list(set(all_certs)) # Avoid duplicates if any overlap (which shouldn't happen with valid filters)
    
    print(f"Found {len(unique_certs)} certificates with missing IDs.")
    
    count = 0
    for cert in unique_certs:
        try:
            print(f"Updating ID for: {cert.full_name}...")
            cert.save()
            print(f"  -> New ID: {cert.certificate_id}")
            count += 1
        except Exception as e:
            print(f"Failed to update {cert.full_name}: {e}")
            
    print(f"Successfully updated {count} certificates.")

if __name__ == "__main__":
    fix_certificates()
