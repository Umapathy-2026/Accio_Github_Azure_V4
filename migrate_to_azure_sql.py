#!/usr/bin/env python3
"""
ACCIO — SQLite to Azure SQL Migration Script

This script copies all data from your local SQLite database to Azure SQL.
It is designed to be run ONE TIME only, before switching the app to Azure SQL.

Usage:
    1. Set the AZURE_SQL_CONNECTION_STRING environment variable with your Azure SQL ODBC connection string
    2. Run: python migrate_to_azure_sql.py

The script will:
    - Connect to the existing SQLite database (from instance/ticketing.db)
    - Connect to Azure SQL using the provided connection string
    - Create all tables in Azure SQL (if they don't exist)
    - Transfer all data (users, issue forms, tickets, approval logs, notifications, audit logs)
    - Report progress and any errors

Safe to re-run: uses INSERT OR IGNORE pattern, won't duplicate data on re-run.
"""

import os
import sys
from datetime import datetime

# Ensure we're in the project root
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────

SQLITE_PATH = os.path.join(script_dir, 'instance', 'ticketing.db')
AZURE_SQL_URI = os.getenv('SQLALCHEMY_DATABASE_URI') or os.getenv('AZURE_SQL_CONNECTION_STRING')

if not AZURE_SQL_URI:
    print("ERROR: Set SQLALCHEMY_DATABASE_URI or AZURE_SQL_CONNECTION_STRING environment variable.")
    print("Example:")
    print("  export SQLALCHEMY_DATABASE_URI='mssql+pyodbc://user:pass@accio-sql-server.database.windows.net:1433/accio?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no'")
    sys.exit(1)

if not os.path.exists(SQLITE_PATH):
    print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
    print("Make sure you've run the app at least once locally to create the database.")
    sys.exit(1)

print(f"✓ SQLite database found: {SQLITE_PATH}")
print(f"✓ Target: Azure SQL")
print()

# ── Step 1: Connect to both databases ──────────────────────────────────────

from sqlalchemy import create_engine, MetaData, Table, inspect
from sqlalchemy.orm import sessionmaker

print("Connecting to SQLite...")
sqlite_engine = create_engine(f'sqlite:///{SQLITE_PATH}', echo=False)
SQLiteSession = sessionmaker(bind=sqlite_engine)
sqlite_session = SQLiteSession()

print("Connecting to Azure SQL...")
try:
    azure_engine = create_engine(AZURE_SQL_URI, echo=False, pool_pre_ping=True)
    # Test connection
    with azure_engine.connect() as conn:
        conn.execute("SELECT 1")
    print("✓ Azure SQL connection successful!")
except Exception as e:
    print(f"ERROR: Failed to connect to Azure SQL: {e}")
    print()
    print("Troubleshooting tips:")
    print("  1. Make sure the connection string is correct")
    print("  2. Ensure Azure SQL firewall allows your IP (add in Portal → SQL Server → Networking)")
    print("  3. Make sure 'Allow Azure services' is enabled in SQL Server firewall rules")
    sys.exit(1)

AzureSession = sessionmaker(bind=azure_engine)
azure_session = AzureSession()

# ── Step 2: Create tables in Azure SQL ─────────────────────────────────────

print()
print("Creating tables in Azure SQL...")

# Import models to get table definitions
sys.path.insert(0, script_dir)
from app import create_app

# Create a temporary app context to get SQLAlchemy metadata
app = create_app()
from app import db as app_db

# Create all tables in Azure SQL
# We need to do this with the Azure SQL engine
app_db.metadata.create_all(bind=azure_engine)
print("✓ Tables created (if they didn't already exist)")

# ── Step 3: Get table references ──────────────────────────────────────────

from sqlalchemy import text

def table_exists(engine, table_name):
    """Check if table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def get_row_count(session, table_name):
    """Get row count for a table."""
    result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return result.scalar()

def copy_table(sqlite_session, azure_session, table_name, id_column='id'):
    """Copy data from SQLite table to Azure SQL table."""
    print(f"  Copying {table_name}...", end=" ")

    # Get existing count in Azure SQL
    existing_count = get_row_count(azure_session, table_name)
    if existing_count > 0:
        print(f"⚠ {existing_count} rows already exist, skipping (re-run safe)")
        return existing_count, 0

    # Read all rows from SQLite
    rows = sqlite_session.execute(text(f"SELECT * FROM {table_name}")).fetchall()
    if not rows:
        print("✓ 0 rows (empty)")
        return 0, 0

    # Get column names (excluding the auto-increment id for INSERT)
    columns = [col for col in rows[0]._fields]

    # Build INSERT statement
    col_list = ", ".join(columns)
    placeholders = ", ".join([f":{col}" for col in columns])
    insert_sql = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})")

    # Insert in batches of 100
    batch_size = 100
    total_inserted = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            for row in batch:
                params = {col: getattr(row, col) for col in columns}
                azure_session.execute(insert_sql, params)
            azure_session.commit()
            total_inserted += len(batch)
        except Exception as e:
            azure_session.rollback()
            # Try one at a time to find the problematic row
            for row in batch:
                try:
                    params = {col: getattr(row, col) for col in columns}
                    azure_session.execute(insert_sql, params)
                    azure_session.commit()
                    total_inserted += 1
                except Exception as row_e:
                    print(f"\n    ⚠ Skipping row {getattr(row, id_column, '?' )}: {row_e}")
                    azure_session.rollback()

    print(f"✓ {total_inserted} rows copied")
    return existing_count, total_inserted


# ── Step 4: Copy tables in order (respecting foreign keys) ─────────────────

print()
print("─" * 50)
print("MIGRATION STARTED")
print("─" * 50)
print()

TABLES_IN_ORDER = [
    'users',
    'issue_forms',
    'tickets',
    'approval_logs',
    'notifications',
    'admin_audit_log',
]

results = {}
for table_name in TABLES_IN_ORDER:
    if table_exists(sqlite_engine, table_name) and table_exists(azure_engine, table_name):
        existing, copied = copy_table(sqlite_session, azure_session, table_name)
        results[table_name] = {'existing': existing, 'copied': copied}
    else:
        print(f"  Skipping {table_name} (missing in source or target)")

# ── Step 5: Summary ──────────────────────────────────────────────────────

print()
print("─" * 50)
print("MIGRATION SUMMARY")
print("─" * 50)
print()
print(f"{'Table':<25} {'Rows Copied':<15}")
print("-" * 40)
total_copied = 0
for table, info in results.items():
    print(f"{table:<25} {info['copied']:<15}")
    total_copied += info['copied']
print("-" * 40)
print(f"{'TOTAL':<25} {total_copied:<15}")
print()

if total_copied == 0:
    print("No data was copied. This likely means Azure SQL already has data.")
    print("If you need to force a fresh copy, truncate the Azure SQL tables first.")
else:
    print(f"✓ Successfully copied {total_copied} rows to Azure SQL!")
    print()
    print("NEXT STEPS:")
    print("  1. Set SQLALCHEMY_DATABASE_URI in Azure Portal App Settings")
    print("  2. Restart the App Service")
    print("  3. Verify data appears in the app")
    print()
    print("To rollback: Remove SQLALCHEMY_DATABASE_URI from App Settings → app falls back to SQLite")

# Cleanup
sqlite_session.close()
azure_session.close()