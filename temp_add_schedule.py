# temp_add_schedule.py
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# IMPORTANT: Set your Discord server (guild) ID here
GUILD_ID = os.getenv("MANUAL_GUILD_ID")  # REPLACE THIS WITH YOUR ACTUAL GUILD ID

# Schedule data
schedule = [
    # Week 1
    (1, 1, "Statues", "Lord Punkd's BO"),
    (2, 1, "The Mother Cluckers", "Level 1 Crooks"),
    (3, 1, "Sticky Tip FC", "DEI Hires"),
    (4, 1, "Cornell 2027", "Zyns Coke n Addy"),
    
    # Week 2
    (5, 2, "Cornell 2027", "The Mother Cluckers"),
    (6, 2, "Lord Punkd's BO", "Sticky Tip FC"),
    (7, 2, "Zyns Coke n Addy", "DEI Hires"),
    (8, 2, "Level 1 Crooks", "Statues"),
    
    # Week 3
    (9, 3, "Cornell 2027", "Statues"),
    (10, 3, "Sticky Tip FC", "Zyns Coke n Addy"),
    (11, 3, "Lord Punkd's BO", "Level 1 Crooks"),
    (12, 3, "DEI Hires", "The Mother Cluckers"),
    
    # Week 4
    (13, 4, "Zyns Coke n Addy", "The Mother Cluckers"),
    (14, 4, "Lord Punkd's BO", "Cornell 2027"),
    (15, 4, "Sticky Tip FC", "Statues"),
    (16, 4, "DEI Hires", "Level 1 Crooks"),
    
    # Week 5
    (17, 5, "Statues", "DEI Hires"),
    (18, 5, "The Mother Cluckers", "Sticky Tip FC"),
    (19, 5, "Level 1 Crooks", "Cornell 2027"),
    (20, 5, "Zyns Coke n Addy", "Lord Punkd's BO"),
    
    # Week 6
    (21, 6, "Sticky Tip FC", "Cornell 2027"),
    (22, 6, "Zyns Coke n Addy", "Level 1 Crooks"),
    (23, 6, "The Mother Cluckers", "Statues"),
    (24, 6, "DEI Hires", "Lord Punkd's BO"),
    
    # Week 7
    (25, 7, "Cornell 2027", "DEI Hires"),
    (26, 7, "Statues", "Zyns Coke n Addy"),  # Note: Fixed typo from "Zynz" to "Zyns"
    (27, 7, "The Mother Cluckers", "Lord Punkd's BO"),
    (28, 7, "Level 1 Crooks", "Sticky Tip FC"),
]

def main():
    print(f"Connecting to database...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor()
    
    # First, let's verify all teams exist
    print(f"\nChecking teams for guild {GUILD_ID}...")
    cur.execute("SELECT team_name FROM teams WHERE guild_id=%s", (GUILD_ID,))
    existing_teams = set(row[0] for row in cur.fetchall())
    
    if not existing_teams:
        print(f"❌ No teams found for guild {GUILD_ID}. Please register teams first!")
        cur.close()
        conn.close()
        return
    
    print(f"✓ Found {len(existing_teams)} teams:")
    for team in sorted(existing_teams):
        print(f"  - {team}")
    
    # Check which teams from schedule are missing
    all_schedule_teams = set()
    for _, _, home, away in schedule:
        all_schedule_teams.add(home)
        all_schedule_teams.add(away)
    
    missing_teams = all_schedule_teams - existing_teams
    if missing_teams:
        print(f"\n⚠️  Warning: The following teams from the schedule don't exist in the database:")
        for team in sorted(missing_teams):
            print(f"  - {team}")
        print("\nYou need to register these teams first using /register_team")
        cur.close()
        conn.close()
        return
    
    # Clear existing schedule for this guild
    print(f"\nClearing existing schedule for guild {GUILD_ID}...")
    cur.execute("DELETE FROM schedule WHERE guild_id=%s", (GUILD_ID,))
    deleted_count = cur.rowcount
    print(f"✓ Deleted {deleted_count} existing matches")
    
    # Insert new schedule
    print(f"\nInserting new schedule...")
    matches_to_insert = [
        (GUILD_ID, match_num, week, home_team, away_team)
        for match_num, week, home_team, away_team in schedule
    ]
    
    cur.executemany(
        "INSERT INTO schedule (guild_id, match_number, week, home_team, away_team) VALUES (%s, %s, %s, %s, %s)",
        matches_to_insert
    )
    
    conn.commit()
    print(f"✓ Inserted {len(matches_to_insert)} matches")
    
    # Show summary
    print(f"\n{'='*60}")
    print(f"Schedule Summary:")
    print(f"{'='*60}")
    for week in range(1, 8):
        week_matches = [m for m in schedule if m[1] == week]
        print(f"\nWeek {week}: {len(week_matches)} matches")
        for match_num, _, home, away in week_matches:
            print(f"  Match {match_num}: {home} vs {away}")
    
    print(f"\n{'='*60}")
    print(f"✓ Schedule successfully added to guild {GUILD_ID}!")
    print(f"{'='*60}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("="*60)
    print("League Schedule Importer")
    print("="*60)
    print(f"\nGuild ID: {GUILD_ID}")
    print(f"Database: {DB_NAME} @ {DB_HOST}:{DB_PORT}")
    print("\n⚠️  Make sure to set the correct GUILD_ID at the top of this script!")
    
    response = input("\nContinue? (y/n): ")
    if response.lower() == 'y':
        main()
    else:
        print("Cancelled.")