import psycopg2

# ✅ Replace with your Neon DB credentials
conn = psycopg2.connect(
    host="ep-orange-lab-a5vjihxa-pooler.us-east-2.aws.neon.tech",
    database="neondb",
    user="neondb_owner",
    password="npg_6nyu9ixbdMOf",
    sslmode="require"
)

# ✅ Define the schema SQL
schema_sql = """
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    student_id VARCHAR(50) NOT NULL UNIQUE,
    branch VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    mobile VARCHAR(15),
    password VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS faculty (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    branch VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS gatepass_requests (
    id SERIAL PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'Pending',
    faculty_remark TEXT,
    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_student FOREIGN KEY (student_id)
        REFERENCES students(student_id)
);
"""

try:
    # ✅ Create a new cursor, execute the schema, commit
    with conn.cursor() as cur:
        cur.execute(schema_sql)
        conn.commit()
        print("✅ Tables created successfully in Neon PostgreSQL.")
except Exception as e:
    print("❌ Error creating tables:", e)
finally:
    conn.close()
