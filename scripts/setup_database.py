#!/usr/bin/env python3
"""Database setup script for the Ryness Weekly Sales database.

This script initializes a PostgreSQL database by:
1. Running the initial schema migration (0001_initial_schema.sql)
2. Loading reference/seed data (reference_data.sql)

Usage:
    python scripts/setup_database.py

The script reads the DATABASE_URL from the environment or from a .env file.
Example DATABASE_URL format:
    postgresql://username:password@host:port/database
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg


def load_env_file(env_path: Path) -> None:
    """Load environment variables from .env file."""
    if not env_path.exists():
        return
    
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Only set if not already in environment
                if key not in os.environ:
                    os.environ[key] = value


def run_sql_script(connection: psycopg.Connection, script_path: Path) -> None:
    """Execute a SQL script file."""
    print(f"Running {script_path.name}...")
    script = script_path.read_text(encoding='utf-8')
    
    with connection.cursor() as cur:
        cur.execute(script)
    
    connection.commit()
    print(f"✓ {script_path.name} completed successfully")


def setup_database() -> int:
    """Set up the database schema and load seed data."""
    # Get repository root
    root = Path(__file__).resolve().parents[1]
    
    # Load .env file if it exists
    env_file = root / '.env'
    load_env_file(env_file)
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Please either:", file=sys.stderr)
        print("  1. Set DATABASE_URL environment variable:", file=sys.stderr)
        print("     export DATABASE_URL='postgresql://user:pass@host/dbname'", file=sys.stderr)
        print("", file=sys.stderr)
        print("  2. Create a .env file with DATABASE_URL:", file=sys.stderr)
        print("     cp .env.example .env", file=sys.stderr)
        print("     # then edit .env with your database credentials", file=sys.stderr)
        return 1
    
    # Define paths to SQL scripts
    migration_file = root / 'db' / 'migrations' / '0001_initial_schema.sql'
    seed_file = root / 'db' / 'seeds' / 'reference_data.sql'
    
    # Check that SQL files exist
    if not migration_file.exists():
        print(f"Error: Migration file not found: {migration_file}", file=sys.stderr)
        return 1
    
    if not seed_file.exists():
        print(f"Error: Seed file not found: {seed_file}", file=sys.stderr)
        return 1
    
    # Connect to database
    print(f"Connecting to database...")
    try:
        conn = psycopg.connect(database_url)
    except Exception as e:
        print(f"Error: Failed to connect to database: {e}", file=sys.stderr)
        return 1
    
    print("✓ Connected to database successfully")
    print("")
    
    try:
        # Run migration
        run_sql_script(conn, migration_file)
        print("")
        
        # Load seed data
        run_sql_script(conn, seed_file)
        print("")
        
        print("=" * 60)
        print("Database setup completed successfully!")
        print("=" * 60)
        print("")
        print("Your database is now ready to use.")
        print("You can now run the parser and loader to ingest data:")
        print("  python -m ryness.parser <pdf_file>")
        print("")
        
        return 0
        
    except Exception as e:
        print(f"Error during setup: {e}", file=sys.stderr)
        conn.rollback()
        return 1
        
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(setup_database())
