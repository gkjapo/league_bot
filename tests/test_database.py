import pytest

def test_database_connection(db_connection):
    """Test that database connection works."""
    cur = db_connection.cursor()
    cur.execute("SELECT 1")
    result = cur.fetchone()
    assert result[0] == 1
    cur.close()

def test_teams_table_exists(db_connection):
    """Test that teams table exists."""
    cur = db_connection.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'teams'
        )
    """)
    exists = cur.fetchone()[0]
    assert exists == True
    cur.close()

def test_cascade_delete_players(clean_db):
    """Test that deleting a team cascades to players."""
    guild_id = 123456789
    cur = clean_db.cursor()
    
    # Create team
    cur.execute("INSERT INTO teams (guild_id, team_name) VALUES (%s, 'Test Team') RETURNING team_id", (guild_id,))
    team_id = cur.fetchone()[0]
    
    # Add player
    cur.execute(
        "INSERT INTO players (guild_id, team_id, player_name) VALUES (%s, %s, 'Test Player')",
        (guild_id, team_id)
    )
    clean_db.commit()
    
    # Delete team
    cur.execute("DELETE FROM teams WHERE team_id=%s", (team_id,))
    clean_db.commit()
    
    # Check player was deleted
    cur.execute("SELECT COUNT(*) FROM players WHERE team_id=%s", (team_id,))
    count = cur.fetchone()[0]
    assert count == 0
    
    cur.close()