import os
import sys
import django
from django.db import connection

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'certificate_project.settings')
django.setup()

def cleanup_duplicates():
    print("=== STARTING PRE-MIGRATION DUPLICATE CLEANUP ===")
    
    with connection.cursor() as cursor:
        # Check if certificates_certificate_student table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='certificates_certificate_student';")
        if cursor.fetchone():
            print("[1] Cleaning up duplicates in certificates_certificate_student...")
            
            # Find duplicate roll numbers
            cursor.execute("""
                SELECT roll_number, COUNT(*) as cnt 
                FROM certificates_certificate_student 
                WHERE roll_number IS NOT NULL AND roll_number != ''
                GROUP BY roll_number 
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            print(f"Found {len(duplicates)} duplicate roll number group(s) in staging table.")
            
            for roll, count in duplicates:
                # Keep the first/oldest record (smallest ID), delete the rest
                cursor.execute("""
                    SELECT id FROM certificates_certificate_student 
                    WHERE roll_number = %s 
                    ORDER BY id ASC
                """, [roll])
                ids = [r[0] for r in cursor.fetchall()]
                keep_id = ids[0]
                delete_ids = ids[1:]
                
                print(f"  Roll '{roll}': keeping ID {keep_id}, deleting IDs: {delete_ids}")
                cursor.execute("""
                    DELETE FROM certificates_certificate_student 
                    WHERE id IN ({})
                """.format(",".join(map(str, delete_ids))))
        else:
            print("[1] Table certificates_certificate_student does not exist yet.")
            
        # Check if certificates_certificate table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='certificates_certificate';")
        if cursor.fetchone():
            print("[2] Cleaning up duplicates in certificates_certificate...")
            
            # Find duplicate roll numbers
            cursor.execute("""
                SELECT roll_number, COUNT(*) as cnt 
                FROM certificates_certificate 
                WHERE roll_number IS NOT NULL AND roll_number != ''
                GROUP BY roll_number 
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            print(f"Found {len(duplicates)} duplicate roll number group(s) in active certificates table.")
            
            for roll, count in duplicates:
                cursor.execute("""
                    SELECT id FROM certificates_certificate 
                    WHERE roll_number = %s 
                    ORDER BY id ASC
                """, [roll])
                ids = [r[0] for r in cursor.fetchall()]
                keep_id = ids[0]
                delete_ids = ids[1:]
                
                print(f"  Roll '{roll}': keeping ID {keep_id}, deleting IDs: {delete_ids}")
                cursor.execute("""
                    DELETE FROM certificates_certificate 
                    WHERE id IN ({})
                """.format(",".join(map(str, delete_ids))))
        else:
            print("[2] Table certificates_certificate does not exist yet.")
            
    print("=== CLEANUP COMPLETED SUCCESSFULLY ===")

def fix_sqlite_indices():
    print("=== FIXING SQLITE CONSTRAINT INDEXES ===")
    with connection.cursor() as cursor:
        # Save staging student data if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='certificates_certificate_student';")
        has_table = cursor.fetchone()
        
        student_data = []
        columns = []
        if has_table:
            print("  Backing up staging student data...")
            cursor.execute("PRAGMA table_info(certificates_certificate_student);")
            columns = [row[1] for row in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM certificates_certificate_student;")
            student_data = cursor.fetchall()
            
            print(f"  Saved {len(student_data)} staging records. Dropping old table...")
            cursor.execute("DROP TABLE certificates_certificate_student;")
            
        print("  Recreating clean staging table certificates_certificate_student...")
        create_sql = """
        CREATE TABLE "certificates_certificate_student" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "full_name" varchar(100) NOT NULL,
            "course" varchar(100) NULL,
            "roll_number" varchar(50) NOT NULL,
            "college_name" varchar(200) NOT NULL,
            "affiliated_name" varchar(200) NOT NULL,
            "start_date" date NULL,
            "end_date" date NULL,
            "issue_date" date NULL,
            "email" varchar(254) NOT NULL,
            "contact" varchar(20) NOT NULL,
            "gender" varchar(10) NOT NULL,
            "internship_title" varchar(200) NULL,
            "internship_duration" varchar(50) NULL,
            "institution_address" varchar(500) NULL,
            "created_at" datetime NOT NULL
        );
        """
        cursor.execute(create_sql)
        
        # Restore data if any (mapping only existing columns)
        if student_data and columns:
            print("  Restoring staging student data...")
            basic_columns = [
                "id", "full_name", "course", "roll_number", "college_name", "affiliated_name",
                "start_date", "end_date", "issue_date", "email", "contact", "gender",
                "internship_title", "internship_duration", "institution_address", "created_at"
            ]
            col_indices = []
            valid_cols = []
            for col in basic_columns:
                if col in columns:
                    col_indices.append(columns.index(col))
                    valid_cols.append(col)
                    
            if valid_cols:
                placeholders = ", ".join(["%s"] * len(valid_cols))
                insert_sql = f"INSERT INTO certificates_certificate_student ({', '.join(valid_cols)}) VALUES ({placeholders})"
                
                for row in student_data:
                    row_data = [row[idx] for idx in col_indices]
                    cursor.execute(insert_sql, row_data)
                print(f"  Successfully restored {len(student_data)} staging records.")

        # Drop any orphan indexes explicitly
        for idx in ['unique_offer_letter_combination', 'unique_certificate_with_dates', 'unique_certificate_no_dates', 'unique_certificate_roll_number', 'unique_student_roll_number']:
            try:
                cursor.execute(f"DROP INDEX IF EXISTS {idx};")
                print(f"  Dropped index: {idx}")
            except Exception as e:
                print(f"  Error dropping {idx}: {e}")
                
    print("=== SQLITE INDEX FIX COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    cleanup_duplicates()
    fix_sqlite_indices()
