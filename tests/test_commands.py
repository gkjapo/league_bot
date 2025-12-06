import pytest
from unittest.mock import patch, MagicMock, Mock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import after path is set
import bot

def create_mock_connection(clean_db):
    """Helper to create a mock connection that doesn't close."""
    mock_conn = MagicMock()
    mock_conn.cursor = clean_db.cursor
    mock_conn.commit = clean_db.commit
    mock_conn.rollback = clean_db.rollback
    mock_conn.close = MagicMock()  # Don't actually close
    return mock_conn

@pytest.mark.asyncio
async def test_register_team_command(mock_interaction, clean_db):
    """Test team registration command."""
    mock_interaction.guild_id = 123456789
    
    # Access the actual callback function from the Command object
    register_team_func = bot.register_team.callback
    
    # Create a mock connection that doesn't actually close
    mock_conn = create_mock_connection(clean_db)
    
    # Patch at module level
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        await register_team_func(mock_interaction, "New Team")
    
    # Verify response
    assert mock_interaction.response.send_message.called
    call_args = str(mock_interaction.response.send_message.call_args)
    assert "registered successfully" in call_args.lower()
    
    # Verify database - use the real connection
    cur = clean_db.cursor()
    cur.execute("SELECT team_name FROM teams WHERE guild_id=123456789 AND team_name='New Team'")
    result = cur.fetchone()
    assert result is not None
    assert result[0] == "New Team"
    cur.close()

def test_is_guild_admin(mock_interaction):
    """Test admin check function."""
    # Test admin user
    mock_interaction.user.guild_permissions.administrator = True
    assert bot.is_guild_admin(mock_interaction) == True
    
    # Test non-admin user
    mock_interaction.user.guild_permissions.administrator = False
    assert bot.is_guild_admin(mock_interaction) == False

def test_is_schedule_locked(clean_db):
    """Test schedule lock detection."""
    guild_id = 123456789
    
    # Create a mock connection that doesn't close
    mock_conn = create_mock_connection(clean_db)
    
    # Initially unlocked (no settings)
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        result = bot.is_schedule_locked(guild_id)
        assert result == False
    
    # Add lock setting
    cur = clean_db.cursor()
    cur.execute(
        "INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'True')",
        (guild_id,)
    )
    clean_db.commit()
    cur.close()
    
    # Create new mock for second call
    mock_conn2 = create_mock_connection(clean_db)
    
    # Now it's locked
    with patch.object(bot, 'get_db_connection', return_value=mock_conn2):
        result = bot.is_schedule_locked(guild_id)
        assert result == True

def test_is_schedule_unlocked_explicit(clean_db):
    """Test schedule lock detection with explicit False value."""
    guild_id = 123456789
    
    # Add explicit unlock setting
    cur = clean_db.cursor()
    cur.execute(
        "INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'False')",
        (guild_id,)
    )
    clean_db.commit()
    cur.close()
    
    # Create mock connection
    mock_conn = create_mock_connection(clean_db)
    
    # Should be unlocked
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        result = bot.is_schedule_locked(guild_id)
        assert result == False

@pytest.mark.asyncio
async def test_register_team_duplicate(mock_interaction, clean_db):
    """Test registering a team that already exists."""
    mock_interaction.guild_id = 123456789
    
    # First, add a team
    cur = clean_db.cursor()
    cur.execute("INSERT INTO teams (guild_id, team_name) VALUES (%s, %s)", (123456789, "Existing Team"))
    clean_db.commit()
    cur.close()
    
    register_team_func = bot.register_team.callback
    
    # Create mock connection
    mock_conn = create_mock_connection(clean_db)
    
    # Try to register the same team again
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        await register_team_func(mock_interaction, "Existing Team")
    
    # Verify response indicates duplicate
    assert mock_interaction.response.send_message.called
    call_args = str(mock_interaction.response.send_message.call_args)
    assert "already exists" in call_args.lower()

@pytest.mark.asyncio
async def test_add_player_command(mock_interaction, clean_db):
    """Test adding a player to a team."""
    mock_interaction.guild_id = 123456789
    
    # Create a team first
    cur = clean_db.cursor()
    cur.execute("INSERT INTO teams (guild_id, team_name) VALUES (%s, %s) RETURNING team_id", 
                (123456789, "Test Team"))
    team_id = cur.fetchone()[0]
    clean_db.commit()
    cur.close()
    
    add_player_func = bot.add_player.callback
    
    # Create mock connection
    mock_conn = create_mock_connection(clean_db)
    
    # Add a player
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        await add_player_func(mock_interaction, team_id, "Player One", False)
    
    # Verify response
    assert mock_interaction.response.send_message.called
    call_args = str(mock_interaction.response.send_message.call_args)
    assert "added" in call_args.lower()
    
    # Verify in database
    cur = clean_db.cursor()
    cur.execute("SELECT player_name FROM players WHERE team_id=%s", (team_id,))
    result = cur.fetchone()
    assert result is not None
    assert result[0] == "Player One"
    cur.close()

@pytest.mark.asyncio
async def test_show_teams_command(mock_interaction, sample_teams, clean_db):
    """Test show teams command."""
    guild_id, teams = sample_teams
    mock_interaction.guild_id = guild_id
    
    show_teams_func = bot.show_teams.callback
    
    # Create mock connection
    mock_conn = create_mock_connection(clean_db)
    
    # Call show_teams
    with patch.object(bot, 'get_db_connection', return_value=mock_conn):
        await show_teams_func(mock_interaction)
    
    # Verify response was called with an embed
    assert mock_interaction.response.send_message.called
    call_args = mock_interaction.response.send_message.call_args
    # Check that an embed was passed
    assert 'embed' in call_args[1] or len(call_args[0]) > 0