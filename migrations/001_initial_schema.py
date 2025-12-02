"""
Initial database schema
"""

def up(cur):
    """Apply migration"""
    # Teams table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        team_id SERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        team_name TEXT NOT NULL,
        UNIQUE(guild_id, team_name)
    )
    """)
    
    # Players table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        player_id SERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        team_id INTEGER REFERENCES teams(team_id) ON DELETE CASCADE,
        player_name TEXT NOT NULL,
        is_captain INTEGER DEFAULT 0
    )
    """)
    
    # Schedule table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedule (
        match_id SERIAL PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        week INTEGER NOT NULL,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL
    )
    """)
    
    # League settings table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS league_settings (
        guild_id BIGINT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY(guild_id, key)
    )
    """)
    
    # Match results table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS match_results (
        thread_id BIGINT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL,
        map_wins_a INTEGER NOT NULL,
        map_wins_b INTEGER NOT NULL,
        is_playoff INTEGER DEFAULT 0
    )
    """)

def down(cur):
    """Rollback migration"""
    cur.execute("DROP TABLE IF EXISTS match_results")
    cur.execute("DROP TABLE IF EXISTS league_settings")
    cur.execute("DROP TABLE IF EXISTS schedule")
    cur.execute("DROP TABLE IF EXISTS players")
    cur.execute("DROP TABLE IF EXISTS teams")