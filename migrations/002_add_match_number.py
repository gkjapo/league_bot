"""
Add match_number column to schedule table
"""

def up(cur):
    """Apply migration"""
    # Check if match_number column exists
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='schedule' AND column_name='match_number'
    """)
    
    if cur.fetchone() is None:
        # Add the match_number column
        cur.execute("ALTER TABLE schedule ADD COLUMN match_number INTEGER")
        
        # Populate match_number for existing records, grouped by guild_id
        cur.execute("""
            WITH numbered AS (
                SELECT 
                    match_id,
                    guild_id,
                    ROW_NUMBER() OVER (PARTITION BY guild_id ORDER BY match_id) as num
                FROM schedule
            )
            UPDATE schedule s
            SET match_number = n.num
            FROM numbered n
            WHERE s.match_id = n.match_id
        """)
        
        # Add the unique constraint
        cur.execute("ALTER TABLE schedule ADD CONSTRAINT schedule_guild_match_unique UNIQUE (guild_id, match_number)")
        
        # Make match_number NOT NULL now that it has values
        cur.execute("ALTER TABLE schedule ALTER COLUMN match_number SET NOT NULL")

def down(cur):
    """Rollback migration"""
    cur.execute("ALTER TABLE schedule DROP CONSTRAINT IF EXISTS schedule_guild_match_unique")
    cur.execute("ALTER TABLE schedule DROP COLUMN IF EXISTS match_number")