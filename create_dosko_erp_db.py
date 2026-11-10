import pymssql

conn = pymssql.connect(server='127.0.0.1:5539', database='master', autocommit=True)
cur = conn.cursor()

# Check if DOSKO_ERP exists
cur.execute("SELECT name FROM sys.databases WHERE name = 'DOSKO_ERP'")
row = cur.fetchone()
if row:
    print("Database DOSKO_ERP already exists.")
else:
    print("Creating database DOSKO_ERP...")
    cur.execute("CREATE DATABASE DOSKO_ERP COLLATE Korean_Wansung_CI_AS")
    print("Database DOSKO_ERP created successfully!")

# Enable READ_COMMITTED_SNAPSHOT for high concurrency (non-blocking reads & writes)
cur.execute("ALTER DATABASE DOSKO_ERP SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE")
print("READ_COMMITTED_SNAPSHOT enabled successfully!")

conn.close()
