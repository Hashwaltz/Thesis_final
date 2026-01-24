import sqlite3
import os

DB_PATH = os.path.join("main_app","instance", "hr_and_payroll.db")

def delete_all(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(f"DELETE FROM {table_name};")
    conn.commit()

    conn.close()
    print(f"✅ All records deleted from '{table_name}'")

if __name__ == "__main__":
    delete_all("attendance") 
