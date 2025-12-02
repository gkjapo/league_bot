"""
Create standings table to track team statistics
"""

def up(cur):
    """Apply migration"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            standing_id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            team_name TEXT NOT NULL,
            match_wins INTEGER DEFAULT 0,
            match_losses INTEGER DEFAULT 0,
            match_ties INTEGER DEFAULT 0,
            map_wins INTEGER DEFAULT 0,
            map_losses INTEGER DEFAULT 0,
            match_win_percentage DECIMAL(5,2) DEFAULT 0.00,
            map_win_percentage DECIMAL(5,2) DEFAULT 0.00,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guild_id, team_name)
        )
    """)
    
    # Create index for faster lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_standings_guild_team 
        ON standings(guild_id, team_name)
    """)

def down(cur):
    """Rollback migration"""
    cur.execute("DROP INDEX IF EXISTS idx_standings_guild_team")
    cur.execute("DROP TABLE IF EXISTS standings")