#!/usr/bin/env python3
"""Run the chat_messages migration against Supabase."""

import os
import sys
import subprocess

def get_secret(secret_name):
    """Get secret from Google Cloud Secret Manager."""
    result = subprocess.run(
        f'gcloud secrets versions access latest --secret={secret_name} --project=jarvis-478401',
        capture_output=True,
        text=True,
        shell=True
    )
    if result.returncode != 0:
        print(f"Failed to get secret {secret_name}: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def main():
    # Get credentials
    print("Getting Supabase credentials...")
    db_password = get_secret('SUPABASE_DB_PASSWORD')
    
    # Use the pooler endpoint with transaction mode
    # aws-0-ap-southeast-1.pooler.supabase.com
    conn_str = f'postgresql://postgres.ojnllduebzfxqmiyinhx:{db_password}@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require'
    
    # Read migration file
    migration_path = os.path.join(os.path.dirname(__file__), 'migrations', '004_chat_messages_letta.sql')
    print(f"Reading migration from: {migration_path}")
    
    with open(migration_path, 'r') as f:
        sql = f.read()
    
    print(f"SQL length: {len(sql)} chars")
    
    # Connect and execute
    import psycopg2
    
    print("Connecting to Supabase...")
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    
    print("Executing migration...")
    cur = conn.cursor()
    cur.execute(sql)
    
    print("✅ Migration executed successfully!")
    
    # Verify the table exists
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'chat_messages' ORDER BY ordinal_position")
    columns = cur.fetchall()
    print(f"\nchat_messages table columns:")
    for col_name, col_type in columns:
        print(f"  - {col_name}: {col_type}")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
