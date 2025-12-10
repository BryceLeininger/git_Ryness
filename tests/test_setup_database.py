#!/usr/bin/env python3
"""Test the database setup script."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from testcontainers.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[1]

# Add scripts to path to import setup_database
sys.path.insert(0, str(ROOT / 'scripts'))

from setup_database import run_sql_script


def test_setup_database():
    """Test that the database setup script works correctly."""
    print("Starting PostgreSQL container...")
    
    with PostgresContainer("postgres:16-alpine") as postgres:
        # Get connection URL and convert from SQLAlchemy format to psycopg format
        database_url = postgres.get_connection_url()
        if database_url.startswith('postgresql+psycopg2://'):
            database_url = database_url.replace('postgresql+psycopg2://', 'postgresql://')
        print(f"✓ PostgreSQL container started")
        print(f"  Connection URL: {database_url}")
        
        # Connect to database
        print("\nConnecting to database...")
        conn = psycopg.connect(database_url, row_factory=dict_row)
        print("✓ Connected successfully")
        
        # Run migration
        migration_file = ROOT / 'db' / 'migrations' / '0001_initial_schema.sql'
        print(f"\nRunning migration: {migration_file.name}")
        run_sql_script(conn, migration_file)
        
        # Run seeds
        seed_file = ROOT / 'db' / 'seeds' / 'reference_data.sql'
        print(f"\nRunning seed file: {seed_file.name}")
        run_sql_script(conn, seed_file)
        
        # Verify tables exist
        print("\nVerifying database setup...")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """)
            tables = [row['table_name'] for row in cur.fetchall()]
        
        expected_tables = [
            'city_codes',
            'county_groups',
            'county_weekly_metrics',
            'developers',
            'product_types',
            'project_weekly_stats',
            'projects',
            'region_yearly_summary',
            'regions',
            'report_weeks',
            'weekly_financial_news',
        ]
        
        print(f"  Found {len(tables)} tables:")
        for table in tables:
            status = '✓' if table in expected_tables else '?'
            print(f"    {status} {table}")
        
        missing = set(expected_tables) - set(tables)
        assert not missing, f"Missing tables: {missing}"
        
        # Verify seed data
        print("\nVerifying seed data...")
        
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM regions")
            region_count = cur.fetchone()['c']
            print(f"  Regions: {region_count}")
            
            cur.execute("SELECT COUNT(*) AS c FROM product_types")
            product_count = cur.fetchone()['c']
            print(f"  Product types: {product_count}")
            
            cur.execute("SELECT COUNT(*) AS c FROM county_groups")
            county_count = cur.fetchone()['c']
            print(f"  County groups: {county_count}")
            
            cur.execute("SELECT COUNT(*) AS c FROM city_codes")
            city_count = cur.fetchone()['c']
            print(f"  City codes: {city_count}")
        
        assert region_count > 0, "No regions found in database"
        assert product_count > 0, "No product types found in database"
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✓ Database setup test completed successfully!")
        print("=" * 60)


if __name__ == '__main__':
    test_setup_database()
