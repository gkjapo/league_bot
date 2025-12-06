# migrations/004_rename_to_home_away.py
"""
Rename team_a/team_b to home_team/away_team in schedule and match_results tables
"""

def up(cur):
    """Apply migration"""
    # Update schedule table
    cur.execute("ALTER TABLE schedule RENAME COLUMN team_a TO home_team")
    cur.execute("ALTER TABLE schedule RENAME COLUMN team_b TO away_team")
    
    # Update match_results table
    cur.execute("ALTER TABLE match_results RENAME COLUMN team_a TO home_team")
    cur.execute("ALTER TABLE match_results RENAME COLUMN team_b TO away_team")
    cur.execute("ALTER TABLE match_results RENAME COLUMN map_wins_a TO home_wins")
    cur.execute("ALTER TABLE match_results RENAME COLUMN map_wins_b TO away_wins")

def down(cur):
    """Rollback migration"""
    # Revert schedule table
    cur.execute("ALTER TABLE schedule RENAME COLUMN home_team TO team_a")
    cur.execute("ALTER TABLE schedule RENAME COLUMN away_team TO team_b")
    
    # Revert match_results table
    cur.execute("ALTER TABLE match_results RENAME COLUMN home_team TO team_a")
    cur.execute("ALTER TABLE match_results RENAME COLUMN away_team TO team_b")
    cur.execute("ALTER TABLE match_results RENAME COLUMN home_wins TO map_wins_a")
    cur.execute("ALTER TABLE match_results RENAME COLUMN away_wins TO map_wins_b")