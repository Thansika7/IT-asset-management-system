import psycopg2
try:
    conn = psycopg2.connect("postgresql://postgres.xndlrgzntulnyvjrqpgx:Kovan%4012345@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
    print("Connection successful")
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
