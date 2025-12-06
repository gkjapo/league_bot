import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path to import bot module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import is_schedule_locked, get_team_standing, determine_higher_seed, update_standings

def test_is_schedule_locked_true(clean_db):
    """Test schedule lock detection when locked."""
    guild_id = 123456789
    cur = clean_db.cursor()
    cur.execute(
        "INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'True')",
        (guild_id,)
    )
    clean_db.commit()
    cur.close()
    
    assert is_schedule_locked(guild_id) == True

def test_is_schedule_locked_false(clean_db):
    """Test schedule lock detection when unlocked."""
    guild_id = 123456789
    assert is_schedule_locked(guild_id) == False

def test_get_team_standing_exists(clean_db):
    """Test retrieving team standings."""
    guild_id = 123456789
    team_name = "Test Team"
    
    cur = clean_db.cursor()
    cur.execute("""
        INSERT INTO standings 
        (guild_id, team_name, match_wins, match_losses, match_ties, 
         map_wins, map_losses, match_win_percentage, map_win_percentage)
        VALUES (%s, %s, 5, 2, 1, 30, 20, 62.5, 60.0)
    """, (guild_id, team_name))
    clean_db.commit()
    cur.close()
    
    standing = get_team_standing(guild_id, team_name)
    assert standing is not None
    assert standing['match_wins'] == 5
    assert standing['match_losses'] == 2
    assert standing['match_win_pct'] == 62.5

def test_get_team_standing_not_exists(clean_db):
    """Test retrieving non-existent team standings."""
    guild_id = 123456789
    standing = get_team_standing(guild_id, "Non Existent Team")
    assert standing is None

def test_determine_higher_seed_by_match_percentage(clean_db):
    """Test higher seed determination by match win percentage."""
    guild_id = 123456789
    cur = clean_db.cursor()
    
    # Team A has better match win %
    cur.execute("""
        INSERT INTO standings 
        (guild_id, team_name, match_wins, match_losses, match_ties, 
         map_wins, map_losses, match_win_percentage, map_win_percentage)
        VALUES (%s, %s, 6, 2, 0, 30, 20, 75.0, 60.0)
    """, (guild_id, "Team A"))
    
    # Team B has worse match win %
    cur.execute("""
        INSERT INTO standings 
        (guild_id, team_name, match_wins, match_losses, match_ties, 
         map_wins, map_losses, match_win_percentage, map_win_percentage)
        VALUES (%s, %s, 4, 4, 0, 25, 25, 50.0, 50.0)
    """, (guild_id, "Team B"))
    
    clean_db.commit()
    cur.close()
    
    method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
    assert method == 'A'
    assert winner == "Team A"

def test_update_standings(clean_db, sample_teams):
    """Test standings calculation from match results."""
    guild_id, teams = sample_teams
    cur = clean_db.cursor()
    
    # Add some match results
    cur.execute("""
        INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
        VALUES (1, %s, %s, %s, 4, 3, 0)
    """, (guild_id, teams[0], teams[1]))
    
    cur.execute("""
        INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
        VALUES (2, %s, %s, %s, 2, 4, 0)
    """, (guild_id, teams[0], teams[2]))
    
    clean_db.commit()
    cur.close()
    
    # Update standings
    update_standings(guild_id)
    
    # Check Team Alpha standings
    standing = get_team_standing(guild_id, teams[0])
    assert standing is not None
    assert standing['match_wins'] == 1
    assert standing['match_losses'] == 1
    assert standing['map_wins'] == 6
    assert standing['map_losses'] == 7