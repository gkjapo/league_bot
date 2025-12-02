"""
Database migration runner
"""
import psycopg2
import os
import sys
from dotenv import load_dotenv
import importlib.util
from pathlib import Path

# Load environment variables
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "league_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def init_migrations_table(cur):
    """Create migrations tracking table if it doesn't exist"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def get_applied_migrations(cur):
    """Get list of already applied migrations"""
    cur.execute("SELECT migration_name FROM schema_migrations ORDER BY id")
    return {row[0] for row in cur.fetchall()}

def get_migration_files():
    """Get all migration files in order"""
    migrations_dir = Path(__file__).parent / "migrations"
    migration_files = sorted([
        f for f in migrations_dir.glob("*.py")
        if f.name != "__init__.py"
    ])
    return migration_files

def load_migration_module(filepath):
    """Load a migration file as a Python module"""
    spec = importlib.util.spec_from_file_location("migration", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_migrations(direction="up"):
    """Run pending migrations"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Initialize migrations tracking table
        init_migrations_table(cur)
        conn.commit()
        
        # Get applied migrations
        applied = get_applied_migrations(cur)
        
        # Get migration files
        migration_files = get_migration_files()
        
        if direction == "up":
            # Run pending migrations
            pending = [f for f in migration_files if f.stem not in applied]
            
            if not pending:
                print("✓ No pending migrations")
                return
            
            print(f"Running {len(pending)} migration(s)...")
            
            for migration_file in pending:
                print(f"  Applying {migration_file.stem}...", end=" ")
                
                # Load and run migration
                module = load_migration_module(migration_file)
                module.up(cur)
                
                # Record migration
                cur.execute(
                    "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                    (migration_file.stem,)
                )
                conn.commit()
                print("✓")
            
            print(f"✓ Successfully applied {len(pending)} migration(s)")
        
        elif direction == "down":
            # Rollback last migration
            if not applied:
                print("✓ No migrations to rollback")
                return
            
            # Get last applied migration
            cur.execute(
                "SELECT migration_name FROM schema_migrations ORDER BY id DESC LIMIT 1"
            )
            last_migration = cur.fetchone()[0]
            
            # Find the migration file
            migration_file = None
            for f in migration_files:
                if f.stem == last_migration:
                    migration_file = f
                    break
            
            if not migration_file:
                print(f"✗ Migration file not found: {last_migration}")
                return
            
            print(f"Rolling back {last_migration}...", end=" ")
            
            # Load and run rollback
            module = load_migration_module(migration_file)
            if hasattr(module, 'down'):
                module.down(cur)
                
                # Remove from migrations table
                cur.execute(
                    "DELETE FROM schema_migrations WHERE migration_name = %s",
                    (last_migration,)
                )
                conn.commit()
                print("✓")
            else:
                print("✗ No down() function defined")
    
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def show_status():
    """Show migration status"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        init_migrations_table(cur)
        conn.commit()
        
        applied = get_applied_migrations(cur)
        migration_files = get_migration_files()
        
        print("\nMigration Status:")
        print("-" * 60)
        
        for migration_file in migration_files:
            status = "✓ Applied" if migration_file.stem in applied else "○ Pending"
            print(f"{status}  {migration_file.stem}")
        
        print("-" * 60)
        print(f"Total: {len(migration_files)} | Applied: {len(applied)} | Pending: {len(migration_files) - len(applied)}\n")
    
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python migrate.py up       - Run pending migrations")
        print("  python migrate.py down     - Rollback last migration")
        print("  python migrate.py status   - Show migration status")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_status()
    elif command == "up":
        run_migrations("up")
    elif command == "down":
        run_migrations("down")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)