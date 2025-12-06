import pytest
import psycopg2
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load test environment
load_dotenv()

@pytest.fixture
def db_connection():
    """Provide a test database connection."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "league_bot"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )
    yield conn
    # Check if connection is still open before rollback
    if not conn.closed:
        conn.rollback()
        conn.close()

@pytest.fixture
def clean_db(db_connection):
    """Clean test database before each test."""
    cur = db_connection.cursor()
    cur.execute("DELETE FROM match_results")
    cur.execute("DELETE FROM schedule")
    cur.execute("DELETE FROM standings")
    cur.execute("DELETE FROM players")
    cur.execute("DELETE FROM teams")
    cur.execute("DELETE FROM league_settings")
    db_connection.commit()
    cur.close()
    yield db_connection

@pytest.fixture
def sample_teams(clean_db):
    """Create sample teams in the database."""
    guild_id = 123456789
    cur = clean_db.cursor()
    
    teams = ["Team Alpha", "Team Bravo", "Team Charlie", "Team Delta"]
    for team_name in teams:
        cur.execute(
            "INSERT INTO teams (guild_id, team_name) VALUES (%s, %s)",
            (guild_id, team_name)
        )
    
    clean_db.commit()
    cur.close()
    yield guild_id, teams

@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.guild_id = 123456789
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.guild_permissions = MagicMock()
    interaction.user.guild_permissions.administrator = True
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.channel = MagicMock(spec=discord.TextChannel)
    return interaction

@pytest.fixture
def mock_thread():
    """Create a mock Discord thread."""
    thread = MagicMock(spec=discord.Thread)
    thread.id = 987654321
    thread.name = "Match 1 - Week 1: Team Alpha vs Team Bravo"
    thread.history = AsyncMock()
    return thread

@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot