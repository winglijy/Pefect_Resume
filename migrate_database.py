#!/usr/bin/env python3
"""Migration script to add is_default column to resumes table."""

from sqlalchemy import create_engine, text
from src.models.database import get_database_url

def migrate_database():
    """Add is_default column if it doesn't exist."""
    engine = create_engine(get_database_url(), connect_args={"check_same_thread": False})
    
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("PRAGMA table_info(resumes)"))
        columns = [row[1] for row in result]
        
        if 'is_default' not in columns:
            print("Adding is_default column to resumes table...")
            conn.execute(text("ALTER TABLE resumes ADD COLUMN is_default INTEGER DEFAULT 0"))
            conn.commit()
            print("✓ Migration complete!")
        else:
            print("✓ Column already exists, no migration needed.")
    
    print("Database migration check complete.")

if __name__ == "__main__":
    migrate_database()

