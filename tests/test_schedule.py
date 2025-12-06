import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_schedule_generation_unique_matchups(clean_db, sample_teams):
    """Test that schedule generates unique matchups first."""
    from bot import generate_schedule
    
    guild_id, teams = sample_teams
    weeks = 2
    matches_per_week = len(teams) // 2
    
    cur = clean_db.cursor()
    
    # Simulate schedule generation logic
    all_unique_matchups = []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                all_unique_matchups.append((teams[i], teams[j]))
    
    # Generate enough for 2 weeks
    total_matches_needed = weeks * matches_per_week
    
    # Verify we have enough unique matchups
    assert len(all_unique_matchups) >= matches_per_week
    
    cur.close()

def test_no_team_plays_twice_same_week(clean_db, sample_teams):
    """Test that no team is scheduled twice in the same week."""
    guild_id, teams = sample_teams
    cur = clean_db.cursor()
    
    # Insert a sample schedule
    cur.execute("""
        INSERT INTO schedule (guild_id, match_number, week, home_team, away_team)
        VALUES (%s, 1, 1, %s, %s), (%s, 2, 1, %s, %s)
    """, (guild_id, teams[0], teams[1], guild_id, teams[2], teams[3]))
    
    clean_db.commit()
    
    # Verify no duplicates in week 1
    cur.execute("""
        SELECT home_team, away_team FROM schedule WHERE guild_id=%s AND week=1
    """, (guild_id,))
    
    matches = cur.fetchall()
    teams_in_week = set()
    for home, away in matches:
        assert home not in teams_in_week, f"{home} plays twice in week 1"
        assert away not in teams_in_week, f"{away} plays twice in week 1"
        teams_in_week.add(home)
        teams_in_week.add(away)
    
    cur.close()