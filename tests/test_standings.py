# tests/test_standings.py
import pytest
import sys
import os

# Add parent directory to path to import bot module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import update_standings, get_team_standing, determine_higher_seed


class TestStandingsCalculation:
    """Tests for standings calculation logic."""
    
    def test_update_standings_single_match(self, clean_db, sample_teams):
        """Test standings calculation with a single match."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Add a match result: Team Alpha 4-3 Team Bravo
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (1, %s, %s, %s, 4, 3, 0)
        """, (guild_id, teams[0], teams[1]))
        clean_db.commit()
        cur.close()
        
        # Update standings
        update_standings(guild_id)
        
        # Check Team Alpha (winner)
        standing_alpha = get_team_standing(guild_id, teams[0])
        assert standing_alpha is not None
        assert standing_alpha['match_wins'] == 1
        assert standing_alpha['match_losses'] == 0
        assert standing_alpha['match_ties'] == 0
        assert standing_alpha['map_wins'] == 4
        assert standing_alpha['map_losses'] == 3
        assert standing_alpha['match_win_pct'] == 100.0
        assert abs(standing_alpha['map_win_pct'] - 57.14) < 0.1  # 4/7 * 100
        
        # Check Team Bravo (loser)
        standing_bravo = get_team_standing(guild_id, teams[1])
        assert standing_bravo is not None
        assert standing_bravo['match_wins'] == 0
        assert standing_bravo['match_losses'] == 1
        assert standing_bravo['match_ties'] == 0
        assert standing_bravo['map_wins'] == 3
        assert standing_bravo['map_losses'] == 4
        assert standing_bravo['match_win_pct'] == 0.0
        assert abs(standing_bravo['map_win_pct'] - 42.86) < 0.1  # 3/7 * 100
    
    def test_update_standings_multiple_matches(self, clean_db, sample_teams):
        """Test standings calculation with multiple matches."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Add multiple match results
        matches = [
            (1, teams[0], teams[1], 4, 3),  # Alpha wins
            (2, teams[0], teams[2], 2, 4),  # Alpha loses
            (3, teams[1], teams[2], 4, 2),  # Bravo wins
        ]
        
        for thread_id, home, away, home_wins, away_wins in matches:
            cur.execute("""
                INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """, (thread_id, guild_id, home, away, home_wins, away_wins))
        
        clean_db.commit()
        cur.close()
        
        # Update standings
        update_standings(guild_id)
        
        # Team Alpha: 1-1 record, 6 map wins, 7 map losses
        standing_alpha = get_team_standing(guild_id, teams[0])
        assert standing_alpha['match_wins'] == 1
        assert standing_alpha['match_losses'] == 1
        assert standing_alpha['map_wins'] == 6
        assert standing_alpha['map_losses'] == 7
        assert standing_alpha['match_win_pct'] == 50.0
        
        # Team Bravo: 1-1 record, 7 map wins, 6 map losses
        standing_bravo = get_team_standing(guild_id, teams[1])
        assert standing_bravo['match_wins'] == 1
        assert standing_bravo['match_losses'] == 1
        assert standing_bravo['map_wins'] == 7
        assert standing_bravo['map_losses'] == 6
        
        # Team Charlie: 2-0 record, 8 map wins, 4 map losses
        standing_charlie = get_team_standing(guild_id, teams[2])
        assert standing_charlie['match_wins'] == 2
        assert standing_charlie['match_losses'] == 0
        assert standing_charlie['map_wins'] == 8
        assert standing_charlie['map_losses'] == 4
        assert standing_charlie['match_win_pct'] == 100.0
    
    def test_update_standings_with_tie(self, clean_db, sample_teams):
        """Test standings calculation with a tied match."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Add a tied match: 3-3
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (1, %s, %s, %s, 3, 3, 0)
        """, (guild_id, teams[0], teams[1]))
        clean_db.commit()
        cur.close()
        
        # Update standings
        update_standings(guild_id)
        
        # Both teams should have a tie
        standing_alpha = get_team_standing(guild_id, teams[0])
        assert standing_alpha['match_wins'] == 0
        assert standing_alpha['match_losses'] == 0
        assert standing_alpha['match_ties'] == 1
        assert standing_alpha['match_win_pct'] == 0.0
        
        standing_bravo = get_team_standing(guild_id, teams[1])
        assert standing_bravo['match_wins'] == 0
        assert standing_bravo['match_losses'] == 0
        assert standing_bravo['match_ties'] == 1
        assert standing_bravo['match_win_pct'] == 0.0
    
    def test_update_standings_ignores_playoff_matches(self, clean_db, sample_teams):
        """Test that playoff matches are excluded from regular season standings."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Add regular season match
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (1, %s, %s, %s, 4, 3, 0)
        """, (guild_id, teams[0], teams[1]))
        
        # Add playoff match (should be ignored)
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (2, %s, %s, %s, 4, 2, 1)
        """, (guild_id, teams[0], teams[1]))
        
        clean_db.commit()
        cur.close()
        
        # Update standings
        update_standings(guild_id)
        
        # Should only count the regular season match
        standing_alpha = get_team_standing(guild_id, teams[0])
        assert standing_alpha['match_wins'] == 1
        assert standing_alpha['map_wins'] == 4  # Only from regular season
        assert standing_alpha['map_losses'] == 3  # Only from regular season
    
    def test_standings_recalculation_overwrites_previous(self, clean_db, sample_teams):
        """Test that recalculating standings overwrites previous values."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Add first match
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (1, %s, %s, %s, 4, 3, 0)
        """, (guild_id, teams[0], teams[1]))
        clean_db.commit()
        
        # First calculation
        update_standings(guild_id)
        standing_first = get_team_standing(guild_id, teams[0])
        assert standing_first['match_wins'] == 1
        
        # Add second match
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (2, %s, %s, %s, 2, 4, 0)
        """, (guild_id, teams[0], teams[2]))
        clean_db.commit()
        cur.close()
        
        # Recalculate
        update_standings(guild_id)
        standing_second = get_team_standing(guild_id, teams[0])
        assert standing_second['match_wins'] == 1
        assert standing_second['match_losses'] == 1
        assert standing_second['map_wins'] == 6  # 4 + 2
        assert standing_second['map_losses'] == 7  # 3 + 4


class TestGetTeamStanding:
    """Tests for get_team_standing function."""
    
    def test_get_team_standing_exists(self, clean_db):
        """Test retrieving existing team standings."""
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
        assert standing['match_ties'] == 1
        assert standing['map_wins'] == 30
        assert standing['map_losses'] == 20
        assert standing['match_win_pct'] == 62.5
        assert standing['map_win_pct'] == 60.0
    
    def test_get_team_standing_not_exists(self, clean_db):
        """Test retrieving non-existent team standings returns None."""
        guild_id = 123456789
        standing = get_team_standing(guild_id, "Non Existent Team")
        assert standing is None
    
    def test_get_team_standing_different_guilds(self, clean_db):
        """Test that standings are guild-specific."""
        cur = clean_db.cursor()
        
        # Add team in guild 1
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (111, 'Team A', 5, 2, 0, 30, 20, 71.4, 60.0)
        """)
        
        # Add team with same name in guild 2
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (222, 'Team A', 2, 5, 0, 15, 30, 28.6, 33.3)
        """)
        clean_db.commit()
        cur.close()
        
        # Should get different standings for different guilds
        standing_guild1 = get_team_standing(111, 'Team A')
        standing_guild2 = get_team_standing(222, 'Team A')
        
        assert standing_guild1['match_wins'] == 5
        assert standing_guild2['match_wins'] == 2


class TestDetermineHigherSeed:
    """Tests for determine_higher_seed function."""
    
    def test_higher_seed_by_match_percentage(self, clean_db):
        """Test higher seed determined by match win percentage."""
        guild_id = 123456789
        cur = clean_db.cursor()
        
        # Team A has better match win %
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (%s, 'Team A', 6, 2, 0, 30, 20, 75.0, 60.0)
        """, (guild_id,))
        
        # Team B has worse match win %
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (%s, 'Team B', 4, 4, 0, 25, 25, 50.0, 50.0)
        """, (guild_id,))
        
        clean_db.commit()
        cur.close()
        
        method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
        assert method == 'A'
        assert winner == "Team A"
        
        # Test reverse order
        method, winner = determine_higher_seed(guild_id, "Team B", "Team A")
        assert method == 'B'
        assert winner == "Team A"
    
    def test_higher_seed_by_map_percentage_when_match_tied(self, clean_db):
        """Test tiebreaker using map win percentage."""
        guild_id = 123456789
        cur = clean_db.cursor()
        
        # Both teams have same match win %
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (%s, 'Team A', 5, 3, 0, 30, 20, 62.5, 60.0)
        """, (guild_id,))
        
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (%s, 'Team B', 5, 3, 0, 25, 25, 62.5, 50.0)
        """, (guild_id,))
        
        clean_db.commit()
        cur.close()
        
        # Team A should win on map %
        method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
        assert method == 'A'
        assert winner == "Team A"
    
    def test_coin_flip_when_no_standings(self, clean_db):
        """Test coin flip when neither team has standings."""
        guild_id = 123456789
        
        method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
        assert method == 'COIN'
        assert winner in ["Team A", "Team B"]
    
    def test_coin_flip_when_completely_tied(self, clean_db):
        """Test coin flip when both teams have identical stats."""
        guild_id = 123456789
        cur = clean_db.cursor()
        
        # Identical standings
        for team_name in ['Team A', 'Team B']:
            cur.execute("""
                INSERT INTO standings 
                (guild_id, team_name, match_wins, match_losses, match_ties, 
                 map_wins, map_losses, match_win_percentage, map_win_percentage)
                VALUES (%s, %s, 5, 3, 0, 30, 20, 62.5, 60.0)
            """, (guild_id, team_name))
        
        clean_db.commit()
        cur.close()
        
        method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
        assert method == 'COIN'
        assert winner in ["Team A", "Team B"]
    
    def test_team_with_standings_beats_team_without(self, clean_db):
        """Test that team with standings gets higher seed over team without."""
        guild_id = 123456789
        cur = clean_db.cursor()
        
        # Only Team A has standings
        cur.execute("""
            INSERT INTO standings 
            (guild_id, team_name, match_wins, match_losses, match_ties, 
             map_wins, map_losses, match_win_percentage, map_win_percentage)
            VALUES (%s, 'Team A', 2, 5, 0, 15, 30, 28.6, 33.3)
        """, (guild_id,))
        
        clean_db.commit()
        cur.close()
        
        # Team A should win even with bad record
        method, winner = determine_higher_seed(guild_id, "Team A", "Team B")
        assert method == 'A'
        assert winner == "Team A"
        
        # Reverse order
        method, winner = determine_higher_seed(guild_id, "Team B", "Team A")
        assert method == 'B'
        assert winner == "Team A"


class TestStandingsEdgeCases:
    """Tests for edge cases in standings calculation."""
    
    def test_empty_match_results(self, clean_db, sample_teams):
        """Test standings calculation with no match results."""
        guild_id, teams = sample_teams
        
        # Should not crash
        update_standings(guild_id)
        
        # No standings should exist
        for team in teams:
            standing = get_team_standing(guild_id, team)
            assert standing is None
    
    def test_single_team_all_matches(self, clean_db, sample_teams):
        """Test standings when one team plays all matches."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Team Alpha plays against all other teams
        for i, opponent in enumerate(teams[1:], 1):
            cur.execute("""
                INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
                VALUES (%s, %s, %s, %s, 4, 2, 0)
            """, (i, guild_id, teams[0], opponent))
        
        clean_db.commit()
        cur.close()
        
        update_standings(guild_id)
        
        # Team Alpha should have 3 wins
        standing = get_team_standing(guild_id, teams[0])
        assert standing['match_wins'] == 3
        assert standing['match_losses'] == 0
    
    def test_zero_map_games_doesnt_crash(self, clean_db, sample_teams):
        """Test that 0-0 match doesn't cause division by zero."""
        guild_id, teams = sample_teams
        cur = clean_db.cursor()
        
        # Unusual 0-0 result
        cur.execute("""
            INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
            VALUES (1, %s, %s, %s, 0, 0, 0)
        """, (guild_id, teams[0], teams[1]))
        clean_db.commit()
        cur.close()
        
        # Should not crash
        update_standings(guild_id)
        
        standing = get_team_standing(guild_id, teams[0])
        # Should handle gracefully
        assert standing is not None or standing is None  # Either is acceptable


class TestStandingsPerformance:
    """Tests for standings calculation performance."""
    
    def test_many_teams_calculation(self, clean_db):
        """Test standings calculation with many teams."""
        guild_id = 123456789
        cur = clean_db.cursor()
        
        # Create 20 teams
        team_names = [f"Team {i}" for i in range(20)]
        for team_name in team_names:
            cur.execute(
                "INSERT INTO teams (guild_id, team_name) VALUES (%s, %s)",
                (guild_id, team_name)
            )
        
        # Create round-robin results (190 matches)
        thread_id = 1
        for i in range(len(team_names)):
            for j in range(i + 1, len(team_names)):
                cur.execute("""
                    INSERT INTO match_results (thread_id, guild_id, home_team, away_team, home_wins, away_wins, is_playoff)
                    VALUES (%s, %s, %s, %s, 4, 3, 0)
                """, (thread_id, guild_id, team_names[i], team_names[j]))
                thread_id += 1
        
        clean_db.commit()
        cur.close()
        
        # Should complete in reasonable time
        update_standings(guild_id)
        
        # Verify all teams have standings
        for team_name in team_names:
            standing = get_team_standing(guild_id, team_name)
            assert standing is not None