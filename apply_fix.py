import os

utils_path = "/www/wwwroot/python/offer letter system 2/offer letter/certificates/utils.py"

if os.path.exists(utils_path):
    print("Fixing utils.py...")
    with open(utils_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Define the exact text to replace inside generate_certificate_image
    target_start = "def generate_certificate_image(certificate_obj, template_name='OfferLetter'):"
    target_end = "draw = ImageDraw.Draw(template)"
    
    start_pos = content.find(target_start)
    if start_pos != -1:
        # Find the draw line *after* the function starts
        end_pos = content.find(target_end, start_pos)
        if end_pos != -1:
            # We replace everything from target_start up to target_end
            old_block = content[start_pos : end_pos + len(target_end)]
            new_block = """def generate_certificate_image(certificate_obj, template_name='OfferLetter'):
    try:
        template, template_path = _resolve_template_image(template_name)
        draw = ImageDraw.Draw(template)"""
            
            content = content.replace(old_block, new_block)
            
            with open(utils_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("Successfully updated generate_certificate_image in utils.py!")
        else:
            print("Error: Could not find draw context line.")
    else:
        print("Error: Could not find generate_certificate_image function start.")
else:
    print("Error: utils.py path does not exist.")

# Kill the specific active Python processes we saw running
import subprocess
print("Killing active Django server processes...")
subprocess.run(["kill", "-9", "982261", "982263", "982278", "982286"])

# Start the servers back up cleanly
print("Restarting Django servers...")
subprocess.run("nohup /www/wwwroot/python/offer\\ letter\\ system\\ 2/offer\\ letter/venv/bin/python /www/wwwroot/python/offer\\ letter\\ system\\ 2/offer\\ letter/manage.py runserver 127.0.0.1:8003 &", shell=True)
subprocess.run("nohup /www/wwwroot/python/offer\\ letter\\ system\\ 2/offer\\ letter/venv/bin/python /www/wwwroot/python/offer\\ letter\\ system\\ 2/offer\\ letter/manage.py runserver 127.0.0.1:8093 &", shell=True)
print("Django server restarted successfully!")
