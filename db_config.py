# db_config.py
import psycopg2
import psycopg2.extras

def get_connection():
    return psycopg2.connect(
        host="ep-orange-lab-a5vjihxa-pooler.us-east-2.aws.neon.tech",
        database="neondb",
        user="neondb_owner",
        password="npg_6nyu9ixbdMOf",
        sslmode='require'
    )
