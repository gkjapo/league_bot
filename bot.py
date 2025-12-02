import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import random
import json

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "league_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# -----------------------------
# Load veto flows
# -----------------------------
with open("veto_flows.json", "r") as f:
    VETO_FLOWS = json.load(f)
    SIDE_NAMES = VETO_FLOWS.get("sides", ["Home Side", "Away Side"])

# -----------------------------
# Database Connection
# -----------------------------
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Note: Database initialization is now handled by migrations
# Run: python migrate.py up

# -----------------------------
# Bot setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# -----------------------------
# Helper functions
# -----------------------------
def is_guild_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

def is_schedule_locked(guild_id: int) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM league_settings WHERE guild_id=%s AND key='locked'", (guild_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row and row[0] == "True"

def get_team_captains(guild_id: int, team_name: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT player_id FROM players
    WHERE guild_id=%s AND team_id = (SELECT team_id FROM teams WHERE guild_id=%s AND team_name=%s) AND is_captain=1
    """, (guild_id, guild_id, team_name))
    result = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return result

# -----------------------------
# BO7 Veto Session Classes
# -----------------------------
class ModeVetoState:
    """Tracks veto state for a single mode."""
    def __init__(self, mode_name: str, available_maps: list):
        self.mode_name = mode_name
        self.available_maps = available_maps.copy()
        self.veto_flow = VETO_FLOWS.get(mode_name, [])
        self.current_step = 0
        self.banned_maps = []
        self.picked_maps = []  # List of (map_name, side_picker) tuples
        self.current_pick_map = None  # Temporary storage for map that needs side selection

    def get_current_action(self):
        """Returns (team, action_type, detail) e.g., ('A', 'BAN', None) or ('B', 'PICK_MAP', '1')"""
        if self.current_step >= len(self.veto_flow):
            return None, None, None
        
        step = self.veto_flow[self.current_step]
        parts = step.split("_")
        team = parts[0]
        action = "_".join(parts[1:])  # e.g., "BAN", "PICK_MAP_1", "PICK_SIDE_MAP_1"
        
        if "PICK_MAP" in action:
            map_num = action.split("_")[-1]  # Get the map number
            return team, "PICK_MAP", map_num
        elif "PICK_SIDE" in action:
            map_num = action.split("_")[-1]
            return team, "PICK_SIDE", map_num
        elif "BAN" in action:
            return team, "BAN", None
        
        return team, action, None

    def is_complete(self):
        return self.current_step >= len(self.veto_flow)

class MatchVetoSession:
    """Tracks veto state in a thread."""
    def __init__(self, thread, team_a_name, team_b_name):
        self.thread = thread
        self.team_a_name = team_a_name
        self.team_b_name = team_b_name
        self.selected_sides = None
        self.mode_states = {}
        self.current_mode = None
        self.mode_order = ["hardpoint", "search", "overload"]
        self.mode_index = 0

    def get_team_name(self, team_letter: str) -> str:
        return self.team_a_name if team_letter == "A" else self.team_b_name

class SideSelectionView(View):
    def __init__(self, session: MatchVetoSession):
        super().__init__(timeout=None)
        self.session = session

    @discord.ui.button(label="Team A side", style=discord.ButtonStyle.secondary)
    async def pick_a(self, interaction: discord.Interaction, button: Button):
        self.session.selected_sides = "A"
        await interaction.response.send_message(
            f"{self.session.team_a_name} selected side A.\n{self.session.team_b_name} is side B.",
            ephemeral=False
        )
        self.disable_all_buttons()
        await interaction.message.edit(view=self)
        
        # Now start the veto process
        await self.start_veto_process(interaction)

    @discord.ui.button(label="Team B side", style=discord.ButtonStyle.secondary)
    async def pick_b(self, interaction: discord.Interaction, button: Button):
        self.session.selected_sides = "B"
        await interaction.response.send_message(
            f"{self.session.team_a_name} selected side B.\n{self.session.team_b_name} is side A.",
            ephemeral=False
        )
        self.disable_all_buttons()
        await interaction.message.edit(view=self)
        
        # Now start the veto process
        await self.start_veto_process(interaction)

    async def start_veto_process(self, interaction: discord.Interaction):
        """Start the first mode veto after side selection"""
        await interaction.channel.send("Starting veto process...")
        
        # Start first mode
        mode_name = self.session.mode_order[0]
        default_maps = {
            "hardpoint": ["Blackheart", "Colossus", "Den", "Exposure", "Scar"],
            "search": ["Colossus", "Den", "Exposure", "Raid", "Scar"],
            "overload": ["Den", "Exposure", "Scar"]
        }
        
        maps = default_maps.get(mode_name, [])
        mode_state = ModeVetoState(mode_name, maps)
        self.session.mode_states[mode_name] = mode_state
        
        team, action_type, detail = mode_state.get_current_action()
        team_name = self.session.get_team_name(team)
        
        if action_type == "BAN":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **BAN** a map:",
                view=view
            )
        elif action_type == "PICK_MAP":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **PICK** a map for Map {detail}:",
                view=view
            )

    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True

class MapSideView(View):
    """View for picking side on a specific map."""
    def __init__(self, session: MatchVetoSession, mode_state: ModeVetoState, map_name: str):
        super().__init__(timeout=None)
        self.session = session
        self.mode_state = mode_state
        self.map_name = map_name

    @discord.ui.button(label="JSOC", style=discord.ButtonStyle.primary, custom_id="side_jsoc")
    async def pick_jsoc(self, interaction: discord.Interaction, button: Button):
        team, action_type, detail = self.mode_state.get_current_action()
        team_name = self.session.get_team_name(team)
        
        await interaction.response.send_message(
            f"**{team_name}** selected **{SIDE_NAMES[0]}** on **{self.map_name}**",
            ephemeral=False
        )
        
        self.mode_state.picked_maps.append((self.map_name, SIDE_NAMES[0], team))
        self.mode_state.current_step += 1
        
        self.disable_all_buttons()
        await interaction.message.edit(view=self)
        
        # Continue to next step
        await self.continue_veto(interaction)

    @discord.ui.button(label="GUILD", style=discord.ButtonStyle.primary, custom_id="side_guild")
    async def pick_guild(self, interaction: discord.Interaction, button: Button):
        team, action_type, detail = self.mode_state.get_current_action()
        team_name = self.session.get_team_name(team)
        
        await interaction.response.send_message(
            f"**{team_name}** selected **{SIDE_NAMES[1]}** on **{self.map_name}**",
            ephemeral=False
        )
        
        self.mode_state.picked_maps.append((self.map_name, SIDE_NAMES[1], team))
        self.mode_state.current_step += 1
        
        self.disable_all_buttons()
        await interaction.message.edit(view=self)
        
        # Continue to next step
        await self.continue_veto(interaction)

    async def continue_veto(self, interaction: discord.Interaction):
        if self.mode_state.is_complete():
            await self.finish_mode_veto(interaction)
        else:
            team, action_type, detail = self.mode_state.get_current_action()
            team_name = self.session.get_team_name(team)
            
            if action_type == "BAN":
                view = MapVetoView(self.session, self.mode_state)
                await interaction.channel.send(
                    f"{team_name}, please **BAN** a map:",
                    view=view
                )
            elif action_type == "PICK_MAP":
                view = MapVetoView(self.session, self.mode_state)
                await interaction.channel.send(
                    f"{team_name}, please **PICK** a map for Map {detail}:",
                    view=view
                )

    async def finish_mode_veto(self, interaction: discord.Interaction):
        # Show summary
        summary = f"**{self.mode_state.mode_name.upper()} veto complete!**\n"
        if self.mode_state.banned_maps:
            summary += f"Banned: {', '.join(self.mode_state.banned_maps)}\n"
        if self.mode_state.picked_maps:
            summary += f"\nMaps:\n"
            for i, (map_name, side, team) in enumerate(self.mode_state.picked_maps, 1):
                team_name = self.session.get_team_name(team)
                # Get the other team
                other_team = 'B' if team == 'A' else 'A'
                other_team_name = self.session.get_team_name(other_team)
                other_side = SIDE_NAMES[1] if side == SIDE_NAMES[0] else SIDE_NAMES[0]
                
                summary += f"  Map {i}: **{map_name}**\n"
                summary += f"    • {team_name}: {side}\n"
                summary += f"    • {other_team_name}: {other_side}\n"
        
        await interaction.channel.send(summary)
        
        # Move to next mode
        self.session.mode_index += 1
        if self.session.mode_index < len(self.session.mode_order):
            await self.start_next_mode(interaction)
        else:
            await interaction.channel.send("**All vetos complete! Match is ready to begin.**")

    async def start_next_mode(self, interaction: discord.Interaction):
        mode_name = self.session.mode_order[self.session.mode_index]
        
        # Get map pool for this mode
        default_maps = {
            "hardpoint": ["Blackheart", "Colossus", "Den", "Exposure", "Scar"],
            "search": ["Colossus", "Den", "Exposure", "Raid", "Scar"],
            "overload": ["Den", "Exposure", "Scar"]
        }
        
        maps = default_maps.get(mode_name, [])
        mode_state = ModeVetoState(mode_name, maps)
        self.session.mode_states[mode_name] = mode_state
        
        team, action_type, detail = mode_state.get_current_action()
        team_name = self.session.get_team_name(team)
        
        if action_type == "BAN":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **BAN** a map:",
                view=view
            )
        elif action_type == "PICK_MAP":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **PICK** a map for Map {detail}:",
                view=view
            )

    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True

class MapVetoView(View):
    """Interactive veto/pick buttons for step-by-step veto."""
    def __init__(self, session: MatchVetoSession, mode_state: ModeVetoState):
        super().__init__(timeout=None)
        self.session = session
        self.mode_state = mode_state
        
        # Add buttons for available maps
        for map_name in mode_state.available_maps:
            button = Button(
                label=map_name, 
                style=discord.ButtonStyle.primary, 
                custom_id=f"veto_{map_name}"
            )
            button.callback = self.create_map_callback(map_name)
            self.add_item(button)

    def create_map_callback(self, map_name: str):
        async def callback(interaction: discord.Interaction):
            team, action_type, detail = self.mode_state.get_current_action()
            
            if action_type == "BAN":
                self.mode_state.banned_maps.append(map_name)
                self.mode_state.available_maps.remove(map_name)
                team_name = self.session.get_team_name(team)
                await interaction.response.send_message(
                    f"**{team_name}** banned **{map_name}**",
                    ephemeral=False
                )
                self.mode_state.current_step += 1
                
                # Disable buttons and continue
                self.disable_all_buttons()
                await interaction.message.edit(view=self)
                await self.show_next_step(interaction)
                
            elif action_type == "PICK_MAP":
                # Map picked, now need side selection
                self.mode_state.available_maps.remove(map_name)
                team_name = self.session.get_team_name(team)
                await interaction.response.send_message(
                    f"**{team_name}** picked **{map_name}** for Map {detail}",
                    ephemeral=False
                )
                self.mode_state.current_step += 1
                
                # Disable buttons
                self.disable_all_buttons()
                await interaction.message.edit(view=self)
                
                # Now show side selection
                next_team, next_action, next_detail = self.mode_state.get_current_action()
                if next_action == "PICK_SIDE":
                    next_team_name = self.session.get_team_name(next_team)
                    side_view = MapSideView(self.session, self.mode_state, map_name)
                    await interaction.channel.send(
                        f"{next_team_name}, please pick a **SIDE** for **{map_name}**:",
                        view=side_view
                    )
        
        return callback

    async def show_next_step(self, interaction: discord.Interaction):
        team, action_type, detail = self.mode_state.get_current_action()
        
        if self.mode_state.is_complete():
            await self.finish_mode_veto(interaction)
        elif action_type == "BAN":
            team_name = self.session.get_team_name(team)
            new_view = MapVetoView(self.session, self.mode_state)
            await interaction.channel.send(
                f"{team_name}, please **BAN** a map:",
                view=new_view
            )
        elif action_type == "PICK_MAP":
            team_name = self.session.get_team_name(team)
            new_view = MapVetoView(self.session, self.mode_state)
            await interaction.channel.send(
                f"{team_name}, please **PICK** a map for Map {detail}:",
                view=new_view
            )

    async def finish_mode_veto(self, interaction: discord.Interaction):
        # Show summary
        summary = f"**{self.mode_state.mode_name.upper()} veto complete!**\n"
        if self.mode_state.banned_maps:
            summary += f"Banned: {', '.join(self.mode_state.banned_maps)}\n"
        if self.mode_state.picked_maps:
            summary += f"\nMaps:\n"
            for i, (map_name, side, team) in enumerate(self.mode_state.picked_maps, 1):
                team_name = self.session.get_team_name(team)
                # Get the other team
                other_team = 'B' if team == 'A' else 'A'
                other_team_name = self.session.get_team_name(other_team)
                other_side = SIDE_NAMES[1] if side == SIDE_NAMES[0] else SIDE_NAMES[0]
                
                summary += f"  Map {i}: **{map_name}**\n"
                summary += f"    • {team_name}: {side}\n"
                summary += f"    • {other_team_name}: {other_side}\n"
        
        await interaction.channel.send(summary)
        
        # Move to next mode
        self.session.mode_index += 1
        if self.session.mode_index < len(self.session.mode_order):
            await self.start_next_mode(interaction)
        else:
            await interaction.channel.send("**All vetos complete! Match is ready to begin.**")

    async def start_next_mode(self, interaction: discord.Interaction):
        mode_name = self.session.mode_order[self.session.mode_index]
        
        # Get map pool for this mode
        default_maps = {
            "hardpoint": ["Blackheart", "Colossus", "Den", "Exposure", "Scar"],
            "search": ["Colossus", "Den", "Exposure", "Raid", "Scar"],
            "overload": ["Den", "Exposure", "Scar"]
        }
        
        maps = default_maps.get(mode_name, [])
        mode_state = ModeVetoState(mode_name, maps)
        self.session.mode_states[mode_name] = mode_state
        
        team, action_type, detail = mode_state.get_current_action()
        team_name = self.session.get_team_name(team)
        
        if action_type == "BAN":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **BAN** a map:",
                view=view
            )
        elif action_type == "PICK_MAP":
            view = MapVetoView(self.session, mode_state)
            await interaction.channel.send(
                f"\n**{mode_name.upper()} VETO**\n{team_name}, please **PICK** a map for Map {detail}:",
                view=view
            )

    def disable_all_buttons(self):
        for child in self.children:
            child.disabled = True

# -----------------------------
# Team Commands
# -----------------------------
@tree.command(name="show_teams", description="List all teams and their players with IDs")
async def show_teams(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT team_id, team_name FROM teams WHERE guild_id=%s", (guild_id,))
    teams = cur.fetchall()
    
    if not teams:
        cur.close()
        conn.close()
        return await interaction.response.send_message("No teams found.", ephemeral=True)
    
    embed = discord.Embed(title="Teams and Players")
    for team_id, team_name in teams:
        cur.execute("SELECT player_name FROM players WHERE guild_id=%s AND team_id=%s", (guild_id, team_id))
        players = [row[0] for row in cur.fetchall()]
        embed.add_field(name=f"{team_name} (ID {team_id})", value=", ".join(players) or "No players", inline=False)
    
    cur.close()
    conn.close()
    await interaction.response.send_message(embed=embed)
    
@tree.command(name="register_team", description="Register a new team (Admin only)")
@app_commands.describe(team_name="Name of the team to register")
async def register_team(interaction: discord.Interaction, team_name: str):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT team_id FROM teams WHERE guild_id=%s AND team_name=%s", (guild_id, team_name))
    if cur.fetchone():
        cur.close()
        conn.close()
        return await interaction.response.send_message(f"Team '{team_name}' already exists.", ephemeral=True)

    cur.execute("INSERT INTO teams (guild_id, team_name) VALUES (%s, %s)", (guild_id, team_name))
    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message(f"Team '{team_name}' registered successfully.", ephemeral=False)

@tree.command(name="add_player", description="Add a player to a team")
@app_commands.describe(team_id="Team ID", player_name="Player's name", is_captain="Is this player a captain?")
async def add_player(interaction: discord.Interaction, team_id: int, player_name: str, is_captain: bool=False):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT team_name FROM teams WHERE guild_id=%s AND team_id=%s", (guild_id, team_id))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return await interaction.response.send_message(f"No team found with ID {team_id}.", ephemeral=True)

    cur.execute(
        "INSERT INTO players (guild_id, team_id, player_name, is_captain) VALUES (%s, %s, %s, %s)",
        (guild_id, team_id, player_name, int(is_captain))
    )
    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message(f"Player '{player_name}' added to team '{row[0]}'.", ephemeral=False)


# -----------------------------
# Schedule Commands
# -----------------------------
@tree.command(name="generate_schedule", description="Generate a league schedule (Admin only)")
@app_commands.describe(weeks="Number of weeks for the league")
async def generate_schedule(interaction: discord.Interaction, weeks: int):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id

    if is_schedule_locked(guild_id):
        return await interaction.response.send_message("Schedule is locked and cannot be changed.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT team_name FROM teams WHERE guild_id=%s", (guild_id,))
    teams = [row[0] for row in cur.fetchall()]
    if len(teams) < 2:
        cur.close()
        conn.close()
        return await interaction.response.send_message("At least 2 teams are required to generate a schedule.", ephemeral=True)

    cur.execute("DELETE FROM schedule WHERE guild_id=%s", (guild_id,))

    matchups = []
    match_number = 1
    for week in range(1, weeks + 1):
        shuffled = teams[:]
        random.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            team_a = shuffled[i]
            team_b = shuffled[i + 1]
            matchups.append((guild_id, match_number, week, team_a, team_b))
            match_number += 1

    cur.executemany("INSERT INTO schedule (guild_id, match_number, week, team_a, team_b) VALUES (%s, %s, %s, %s, %s)", matchups)
    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message(f"Generated schedule for {weeks} weeks with {len(matchups)} matches.", ephemeral=False)


@tree.command(name="lock_schedule", description="Lock schedule to prevent changes (Admin only)")
async def lock_schedule(interaction: discord.Interaction):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id

    if is_schedule_locked(guild_id):
        return await interaction.response.send_message("Schedule is already locked.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'True') ON CONFLICT (guild_id, key) DO UPDATE SET value='True'", (guild_id,))
    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message("Schedule has been locked and cannot be changed.", ephemeral=False)

@tree.command(name="unlock_schedule", description="Unlock schedule to allow changes (Admin only)")
async def unlock_schedule(interaction: discord.Interaction):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id

    if not is_schedule_locked(guild_id):
        return await interaction.response.send_message("Schedule is not locked.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'False') ON CONFLICT (guild_id, key) DO UPDATE SET value='False'", (guild_id,))
    conn.commit()
    cur.close()
    conn.close()

    await interaction.response.send_message("Schedule has been unlocked and can now be modified.", ephemeral=False)

@tree.command(name="create_match_threads", description="Create match threads for a specific week (Admin only)")
@app_commands.describe(channel="Channel to create match threads in", week="Week number to create threads for")
async def create_match_threads(interaction: discord.Interaction, channel: discord.TextChannel, week: int):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id
    
    await interaction.response.defer(ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT match_number, team_a, team_b FROM schedule WHERE guild_id=%s AND week=%s ORDER BY match_number", (guild_id, week))
    matches = cur.fetchall()
    cur.close()
    conn.close()
    
    if not matches:
        return await interaction.followup.send(f"No matches found for week {week}.", ephemeral=True)
    
    created_threads = []
    for match_number, team_a, team_b in matches:
        thread_name = f"Match {match_number} - Week {week}: {team_a} vs {team_b}"
        
        # Check if thread already exists
        existing_thread = None
        for thread in channel.threads:
            if thread.name == thread_name:
                existing_thread = thread
                break
        
        if existing_thread:
            created_threads.append(f"{existing_thread.mention} (already exists)")
        else:
            thread = await channel.create_thread(
                name=thread_name, 
                type=discord.ChannelType.public_thread, 
                auto_archive_duration=1440
            )
            created_threads.append(thread.mention)

    await interaction.followup.send(
        f"Match threads created for Week {week}:\n" + "\n".join(created_threads),
        ephemeral=True
    )

@tree.command(name="delete_schedule", description="Delete schedule and match threads (Admin only)")
@app_commands.describe(channel="Channel where match threads were created")
async def delete_schedule(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_guild_admin(interaction):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT match_number, team_a, team_b, week FROM schedule WHERE guild_id=%s", (guild_id,))
    matches = cur.fetchall()
    
    if not matches:
        cur.close()
        conn.close()
        return await interaction.response.send_message("No schedule found.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    deleted_threads = []
    for match_number, team_a, team_b, week in matches:
        # Try both old and new thread name formats
        thread_names = [
            f"Match {match_number} - Week {week}: {team_a} vs {team_b}",
            f"Week {week}: {team_a} vs {team_b}",
            f"{team_a} vs {team_b}"
        ]
        for thread in channel.threads:
            if thread.name in thread_names:
                try:
                    await thread.delete()
                    deleted_threads.append(thread.name)
                    break
                except Exception as e:
                    print(f"Failed to delete thread {thread.name}: {e}")

    cur.execute("DELETE FROM schedule WHERE guild_id=%s", (guild_id,))
    cur.execute("INSERT INTO league_settings (guild_id, key, value) VALUES (%s, 'locked', 'False') ON CONFLICT (guild_id, key) DO UPDATE SET value='False'", (guild_id,))
    conn.commit()
    cur.close()
    conn.close()

    await interaction.followup.send("Deleted schedule and match threads:\n" + "\n".join(deleted_threads), ephemeral=True)
    
@tree.command(name="show_schedule", description="Show the current league schedule")
async def show_schedule(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT match_number, week, team_a, team_b FROM schedule WHERE guild_id=%s ORDER BY match_number", (guild_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return await interaction.response.send_message("No schedule found.", ephemeral=True)
    
    # Group matches by week
    weeks_data = {}
    for match_number, week, team_a, team_b in rows:
        if week not in weeks_data:
            weeks_data[week] = []
        weeks_data[week].append((match_number, team_a, team_b))
    
    # Create multiple embeds if needed (25 field limit per embed)
    embeds = []
    current_embed = discord.Embed(title="League Schedule")
    field_count = 0
    
    for week in sorted(weeks_data.keys()):
        matches = weeks_data[week]
        
        # Create week header as a single field with all matches
        matches_text = "\n".join([f"Match {num}: {ta} vs {tb}" for num, ta, tb in matches])
        
        # Check if adding this would exceed limit
        if field_count >= 24:  # Leave room for one more field
            embeds.append(current_embed)
            current_embed = discord.Embed(title="League Schedule (continued)")
            field_count = 0
        
        current_embed.add_field(
            name=f"Week {week}",
            value=matches_text,
            inline=False
        )
        field_count += 1
    
    # Add the last embed
    if field_count > 0:
        embeds.append(current_embed)
    
    # Send the first embed
    await interaction.response.send_message(embed=embeds[0])
    
    # Send additional embeds as follow-ups
    for embed in embeds[1:]:
        await interaction.followup.send(embed=embed)

# -----------------------------
# Match Commands
# -----------------------------
@tree.command(name="start_match", description="Start a BO7 veto in an existing match thread")
async def start_match(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("This command must be used inside a match thread.", ephemeral=True)

    thread = interaction.channel
    parts = thread.name.split(" vs ")
    if len(parts) < 2:
        return await interaction.response.send_message("Cannot determine teams from thread name.", ephemeral=True)

    # Extract team names - handle both "Match X - Week Y: Team A vs Team B" and "Week Y: Team A vs Team B"
    team_a_part = parts[0].strip()
    if ": " in team_a_part:
        team_a = team_a_part.split(": ")[-1]
    else:
        team_a = team_a_part
    
    team_b = parts[1].strip()

    session = MatchVetoSession(thread, team_a, team_b)

    # Side selection - veto will start AFTER side is picked
    side_view = SideSelectionView(session)
    await interaction.response.send_message(f"{team_a}, pick your side:", view=side_view)

@tree.command(name="show_match", description="Show the complete mapset for this match")
async def show_match(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("This command must be used inside a match thread.", ephemeral=True)

    thread = interaction.channel
    parts = thread.name.split(" vs ")
    if len(parts) < 2:
        return await interaction.response.send_message("Cannot determine teams from thread name.", ephemeral=True)

    # Extract team names - handle both formats
    team_a_part = parts[0].strip()
    if ": " in team_a_part:
        team_a = team_a_part.split(": ")[-1]
    else:
        team_a = team_a_part
    
    team_b = parts[1].strip()
    
    embed = discord.Embed(
        title=f"Match: {team_a} vs {team_b}",
        description="**Complete Mapset**",
        color=discord.Color.green()
    )

    # Search through messages for mode veto summaries
    mode_data = {"hardpoint": [], "search": [], "overload": []}
    current_mode = None
    
    async for message in thread.history(limit=200, oldest_first=True):
        if message.author == bot.user:
            content = message.content
            
            # Detect mode completion messages
            if "HARDPOINT veto complete!" in content:
                current_mode = "hardpoint"
            elif "SEARCH veto complete!" in content:
                current_mode = "search"
            elif "OVERLOAD veto complete!" in content:
                current_mode = "overload"
            
            # Extract map and side information
            if current_mode and "Map " in content and ":" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("Map "):
                        # Extract map name
                        map_info = line.split("**")
                        if len(map_info) >= 2:
                            map_name = map_info[1]
                            # Get next two lines for sides
                            if i + 2 < len(lines):
                                side_lines = lines[i+1:i+3]
                                mode_data[current_mode].append({
                                    "map": map_name,
                                    "sides": side_lines
                                })
    
    # Build embed fields
    map_counter = 1
    for mode_name in ["hardpoint", "search", "overload"]:
        maps = mode_data[mode_name]
        if maps:
            mode_display = mode_name.upper()
            for map_info in maps:
                map_name = map_info["map"]
                sides_text = "\n".join(map_info["sides"])
                
                embed.add_field(
                    name=f"Map {map_counter}: {mode_display} - {map_name}",
                    value=sides_text if sides_text.strip() else "Sides TBD",
                    inline=False
                )
                map_counter += 1

    if map_counter == 1:
        embed.description = "No veto data found. Run `/start_match` to begin the veto process."
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="set_result", description="Set match result")
@app_commands.describe(map_wins_a="Maps won by Team A", map_wins_b="Maps won by Team B", playoff="Is playoff match?")
async def set_result(interaction: discord.Interaction, map_wins_a: int, map_wins_b: int, playoff: bool=False):
    if not isinstance(interaction.channel, discord.Thread):
        return await interaction.response.send_message("Use this command inside a match thread.", ephemeral=True)

    guild_id = interaction.guild_id
    thread = interaction.channel
    parts = thread.name.split(" vs ")
    if len(parts) < 2:
        return await interaction.response.send_message("Cannot determine teams from thread name.", ephemeral=True)
    
    # Extract actual team names - handle both formats
    team_a_part = parts[0].strip()
    if ": " in team_a_part:
        team_a = team_a_part.split(": ")[-1]
    else:
        team_a = team_a_part
    
    team_b = parts[1].strip()

    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO match_results (thread_id, guild_id, team_a, team_b, map_wins_a, map_wins_b, is_playoff)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (thread_id) DO UPDATE SET
        guild_id=%s, team_a=%s, team_b=%s, map_wins_a=%s, map_wins_b=%s, is_playoff=%s
    """, (thread.id, guild_id, team_a, team_b, map_wins_a, map_wins_b, int(playoff),
          guild_id, team_a, team_b, map_wins_a, map_wins_b, int(playoff)))
    conn.commit()
    cur.close()
    conn.close()
    
    await interaction.response.send_message(f"Result recorded: {team_a} {map_wins_a} - {map_wins_b} {team_b}", ephemeral=False)

@tree.command(name="show_results", description="Show all match results")
async def show_results(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT team_a, team_b, map_wins_a, map_wins_b FROM match_results WHERE guild_id=%s ORDER BY thread_id", (guild_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return await interaction.response.send_message("No match results recorded yet.", ephemeral=True)
    
    embed = discord.Embed(title="League Match Results")
    for team_a, team_b, wins_a, wins_b in rows:
        embed.add_field(name=f"{team_a} vs {team_b}", value=f"{wins_a} - {wins_b}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="standings", description="Show league standings")
async def standings(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT team_a, team_b, map_wins_a, map_wins_b FROM match_results WHERE guild_id=%s", (guild_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return await interaction.response.send_message("No match results recorded yet.", ephemeral=True)

    stats = {}
    for team_a, team_b, wins_a, wins_b in rows:
        for team in [team_a, team_b]:
            if team not in stats:
                stats[team] = {"match_wins":0, "match_losses":0, "maps_won":0, "maps_lost":0}
        stats[team_a]["maps_won"] += wins_a
        stats[team_a]["maps_lost"] += wins_b
        stats[team_b]["maps_won"] += wins_b
        stats[team_b]["maps_lost"] += wins_a
        if wins_a > wins_b:
            stats[team_a]["match_wins"] += 1
            stats[team_b]["match_losses"] += 1
        elif wins_b > wins_a:
            stats[team_b]["match_wins"] += 1
            stats[team_a]["match_losses"] += 1

    def sort_key(item):
        team, s = item
        return (s["match_wins"], s["maps_won"]-s["maps_lost"], s["maps_won"])
    sorted_stats = sorted(stats.items(), key=sort_key, reverse=True)

    embed = discord.Embed(title="League Standings")
    for rank, (team, s) in enumerate(sorted_stats, start=1):
        embed.add_field(
            name=f"{rank}. {team}",
            value=f"Match W-L: {s['match_wins']}-{s['match_losses']}\nMaps W-L: {s['maps_won']}-{s['maps_lost']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# -----------------------------
# Help Command
# -----------------------------
@tree.command(name="help", description="List all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="League Bot Commands",
        description="Here are all available commands:",
        color=discord.Color.blue()
    )
    
    # Team Management
    embed.add_field(
        name="📋 Team Management",
        value=(
            "`/register_team <team_name>` - Register a new team (Admin)\n"
            "`/add_player <team_id> <player_name> [is_captain]` - Add player to team (Admin)\n"
            "`/show_teams` - List all teams and their players"
        ),
        inline=False
    )
    
    # Schedule Management
    embed.add_field(
        name="📅 Schedule Management",
        value=(
            "`/generate_schedule <weeks>` - Generate league schedule (Admin)\n"
            "`/show_schedule` - View current schedule\n"
            "`/lock_schedule` - Lock schedule to prevent changes (Admin)\n"
            "`/unlock_schedule` - Unlock schedule (Admin)\n"
            "`/create_match_threads <channel> <week>` - Create match threads for a week (Admin)\n"
            "`/delete_schedule <channel>` - Delete schedule and threads (Admin)"
        ),
        inline=False
    )
    
    # Match Management
    embed.add_field(
        name="🎮 Match Management",
        value=(
            "`/start_match` - Start veto process in match thread\n"
            "`/show_match` - Show complete mapset for this match\n"
            "`/set_result <map_wins_a> <map_wins_b> [playoff]` - Record match result\n"
            "`/show_results` - View all match results\n"
            "`/standings` - View league standings"
        ),
        inline=False
    )
    
    # General
    embed.add_field(
        name="ℹ️ General",
        value="`/help` - Show this help message",
        inline=False
    )
    
    embed.set_footer(text="Commands marked (Admin) require administrator permissions")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -----------------------------
# Bot Ready
# -----------------------------
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} ({bot.user.id})")
    try:
        await tree.sync()
    except Exception as e:
        print("Command sync failed:", e)

# -----------------------------
# Run Bot
# -----------------------------
bot.run(BOT_TOKEN)
