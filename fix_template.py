import os

file_path = r"C:\Users\ASUS\OneDrive\Desktop\certificate_system final after modi\certificate_system\templates\certificates\generate.html"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
found = False
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    
    # Check for the problematic split tag
    if stripped.startswith('{% if offer_letter_data.internship_start_date and offer_letter_data.internship_end_date') and not stripped.endswith('%}'):
        # Check next line
        if i + 1 < len(lines) and lines[i+1].strip() == '%}':
            print(f"Found broken tag at line {i+1}")
            # Combine them
            # Keep indentation of the first line
            indent = line[:line.find('{%')]
            # Construct the single line IF tag
            combined = indent + '{% if offer_letter_data.internship_start_date and offer_letter_data.internship_end_date %}\n'
            new_lines.append(combined)
            i += 2
            found = True
            
            # Now checking for the multiline content inside the if block which typically follows immediately
            # Current i points to the line after '%}'
            if i < len(lines):
                next_line = lines[i]
                if '(From {{ offer_letter_data.internship_start_date }} to {{' in next_line:
                    if i + 1 < len(lines) and '}}' in lines[i+1]:
                         print(f"Found broken var content at line {i+1}")
                         # indent should be same or +4? assuming same for simplicity or extraction
                         indent_content = next_line[:next_line.find('(')]
                         combined_content = indent_content + '(From {{ offer_letter_data.internship_start_date }} to {{ offer_letter_data.internship_end_date }})\n'
                         new_lines.append(combined_content)
                         i += 2
            continue

    new_lines.append(line)
    i += 1

if found:
    print("Writing fixed file...")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Done.")
else:
    print("Pattern not found (already fixed?)")
