"""
Database schema definition for RenewalRadar subscription manager.
Defines the SQLite tables and their structure.
"""

import sqlite3
from pathlib import Path
import os
import datetime

# Schema version
SCHEMA_VERSION = 1


def get_db_path():
    """Get the path to the database file."""
    home_dir = Path.home()
    app_dir = home_dir / ".renewalradar"

    if not app_dir.exists():
        app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "subscriptions.db"


def initialize_db():
    """Initialize the SQLite database with the required schema."""
    db_path = get_db_path()

    # Create a database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Create subscriptions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        cost REAL NOT NULL,
        billing_cycle TEXT NOT NULL,
        currency TEXT NOT NULL,
        start_date TEXT NOT NULL,
        renewal_date TEXT NOT NULL,
        trial_end_date TEXT NOT NULL,
        payment_method TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        notes TEXT,
        status TEXT DEFAULT 'active'
        
    )
    ''')

    # Create metadata table for schema version tracking
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')

    # Insert or update schema version
    cursor.execute('''
    INSERT OR REPLACE INTO metadata (key, value) 
    VALUES ('schema_version', ?)
    ''', (str(SCHEMA_VERSION),))

    # Commit the changes
    conn.commit()
    conn.close()

    return db_path


if __name__ == "__main__":
    db_path = initialize_db()
    print(f"Database initialized at: {db_path}")