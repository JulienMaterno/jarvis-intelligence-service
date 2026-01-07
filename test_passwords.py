import psycopg

old_password = '7G65BBNtoAd1ewfK'
new_password = 'gRbfD2R8inQh7G6F'

for label, pwd in [('OLD', old_password), ('NEW', new_password)]:
    conninfo = f'host=aws-1-ap-southeast-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.ojnllduebzfxqmiyinhx password={pwd} sslmode=require'
    try:
        conn = psycopg.connect(conninfo)
        print(f'{label} password: WORKS')
        conn.close()
    except Exception as e:
        print(f'{label} password: FAILED - {str(e)[:50]}')
