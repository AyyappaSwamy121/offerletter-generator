import sqlite3
import os

db_path = 'db.sqlite3'
if not os.path.exists(db_path):
    db_path = '/www/wwwroot/python/offer letter system 2/offer letter/db.sqlite3'

print(f"Connecting to database at: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Scanning for duplicate roll numbers using raw SQL...")
cursor.execute("SELECT id, roll_number FROM certificates_certificate WHERE roll_number IS NOT NULL AND roll_number != '' ORDER BY id ASC")
rows = cursor.fetchall()

from collections import defaultdict
roll_groups = defaultdict(list)
for row_id, roll in rows:
    key = roll.strip().upper()
    roll_groups[key].append(row_id)

deleted_count = 0
for roll, ids in roll_groups.items():
    if len(ids) > 1:
        print(f"Found {len(ids)} records for Roll Number: {roll}")
        to_keep = ids[0]
        to_delete = ids[1:]
        print(f"  Keeping: ID={to_keep}")
        for dup_id in to_delete:
            print(f"  Deleting duplicate: ID={dup_id}")
            cursor.execute("DELETE FROM certificates_certificate WHERE id = ?", (dup_id,))
            deleted_count += 1

conn.commit()
conn.close()
print(f"\nCleanup completed. Removed {deleted_count} duplicate records from certificates_certificate.")
