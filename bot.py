import os, discord, gspread, datetime as dt
from discord.ext import commands, tasks
from dotenv import load_dotenv; load_dotenv()
from collections import defaultdict
import json

# Load projects
PROJECTS_FILE = "projects.json"
try:
    with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
        projects = json.load(f)
except Exception as e:
    print(f"Could not load {PROJECTS_FILE}: {e}")
    projects = {}

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
gc  = gspread.service_account("service_account.json")

@bot.slash_command(name="latest", description="Show today's Medical-AI news")
async def latest(ctx):
    await ctx.defer()
    today = dt.date.today().isoformat()
    try:
        ws = gc.open_by_key(os.environ["RAW_SHEET_ID"]).worksheet(today)
        rows = ws.get_all_records()
    except Exception:
        await ctx.send("No news items for today.")
        return
    if not rows:
        await ctx.send("No items yet.")
        return
    for r in reversed(rows[-10:]):
        # Remove embed, send plain text with title and URL in angle brackets
        title = r["Title"]
        url = r["URL"]
        summary = "\n".join(r["Summary"].split("\\n"))
        pub_date = r.get('pub_date', today)
        main_cat = r.get('Main Category', '')
        msg = f"**{title}**: <{url}>\n{summary}\n{pub_date} • {main_cat}"
        await ctx.send(msg)

@tasks.loop(hours=24)
async def morning_digest():
    ch = bot.get_channel(int(os.environ["YOUR_CHANNEL_ID"]))
    today = dt.date.today().isoformat()
    try:
        ws = gc.open_by_key(os.environ["RAW_SHEET_ID"]).worksheet(today)
        rows = ws.get_all_records()
    except Exception:
        await ch.send("No news items for today.")
        return
    if not rows:
        await ch.send("No news items for today.")
        return

    # Group by Main Category and Subcategory (for general digest)
    grouped = defaultdict(lambda: defaultdict(list))
    # Group by project
    project_news = defaultdict(list)
    for r in rows:
        grouped[r["Main Category"]][r["Subcategory"]].append(r)
        # Parse project field (should be a list, but may be string)
        # Check for both "project" and "Projects" keys (case sensitive)
        project_field = r.get("Projects") or r.get("projects") or r.get("project") or r.get("Project")
        if project_field:
            if isinstance(project_field, str):
                try:
                    # Try to parse as JSON list
                    project_list = json.loads(project_field)
                except Exception:
                    # If it's a comma-separated string, split it
                    if "," in project_field:
                        project_list = [p.strip() for p in project_field.split(",")]
                    else:
                        project_list = [project_field]
            else:
                project_list = project_field
            for project in project_list:
                if project and project != "No News":
                    project_news[project].append(r)

    # Helper to sort: NO (🩺) before YES (🌐)
    def sort_key(r):
        return (r["Cross-domain"] != "NO", r["Title"].lower())

    # --- Project Threads ---
    # Add a date-labeled thread for all news
    all_news_thread_title = f"📰 Medical-AI Daily Digest — {today}"
    # Simply create the thread - Discord will return existing thread if it already exists
    all_news_thread = await ch.create_thread(name=all_news_thread_title, type=discord.ChannelType.public_thread)
    
    # Process main digest by category in the all news thread
    for main_cat in grouped:
        await all_news_thread.send(f"# {main_cat}")
        for sub_cat in grouped[main_cat]:
            await all_news_thread.send(f"## {sub_cat}")
            # Sort so NO (🩺) first, then YES (🌐)
            for r in sorted(grouped[main_cat][sub_cat], key=sort_key):
                emoji = "🩺" if r["Cross-domain"] == "NO" else "🌐"
                title = r["Title"]
                url = r["URL"]
                summary = r["Summary"]
                app_context = r.get("Application Context") or r.get("application context")
                summary_lines = summary.strip().split("\n")
                blockquote_summary = '\n'.join(f'> {line}' for line in summary_lines)
                # Replace Markdown link with bold title and URL in angle brackets
                line = f"{emoji} **{title}**: <{url}>\n{blockquote_summary}"
                if app_context:
                    line += f"\n> _Application: {app_context}_"
                await all_news_thread.send(line)

    # Create project-specific threads
    for project_name in projects.keys():
        news_items = project_news.get(project_name, [])
        if news_items:
            thread_title = f"{project_name} — {today}"
            # Create thread - Discord will return existing thread if it already exists
            thread = await ch.create_thread(name=thread_title, type=discord.ChannelType.public_thread)
            # Post each news item in the thread
            for r in news_items:
                title = r["Title"]
                url = r["URL"]
                summary = r["Summary"]
                app_context = r.get("Application Context") or r.get("application context")
                summary_lines = summary.strip().split("\n")
                blockquote_summary = '\n'.join(f'> {line}' for line in summary_lines)
                line = f"**{title}**: <{url}>\n{blockquote_summary}"
                if app_context:
                    line += f"\n> _Application: {app_context}_"
                await thread.send(line)

@bot.slash_command(name="testdigest", description="Test the morning digest output")
async def testdigest(ctx):
    await ctx.defer()
    await run_testdigest(ctx.channel)

@bot.slash_command(name="debugprojects", description="Debug project parsing")
async def debugprojects(ctx):
    await ctx.defer()
    today = dt.date.today().isoformat()
    try:
        raw_sheet_id = "1BIvwyfsvV2a797NqtV1aXjI6FpuxlIjPGKGCkdgHVqM"
        ws = gc.open_by_key(raw_sheet_id).worksheet(today)
        rows = ws.get_all_records()
    except Exception as e:
        await ctx.send(f"Error accessing spreadsheet: {e}")
        return
    
    if not rows:
        await ctx.send("No rows found in today's sheet.")
        return

    # Group by project
    project_news = defaultdict(list)
    all_project_fields = []
    
    for i, r in enumerate(rows):
        # Debug: collect all project fields we find
        project_field = r.get("Projects") or r.get("projects") or r.get("project") or r.get("Project")
        all_project_fields.append(f"Row {i+1}: {project_field}")
        
        if project_field:
            if isinstance(project_field, str):
                try:
                    # Try to parse as JSON list
                    project_list = json.loads(project_field)
                except Exception:
                    # If it's a comma-separated string, split it
                    if "," in project_field:
                        project_list = [p.strip() for p in project_field.split(",")]
                    else:
                        project_list = [project_field]
            else:
                project_list = project_field
            for project in project_list:
                if project and project != "No News":
                    project_news[project].append(r)

    # Send debug info
    await ctx.send(f"**Debug Info for {today}**")
    await ctx.send(f"Total rows: {len(rows)}")
    
    # Show all available column names
    if rows:
        await ctx.send(f"**Available columns in spreadsheet:**")
        column_names = list(rows[0].keys())
        await ctx.send(f"All columns: {column_names}")
        
        # Look for any column that might contain project info
        project_like_columns = [col for col in column_names if 'project' in col.lower()]
        await ctx.send(f"Project-like columns: {project_like_columns}")
    
    await ctx.send(f"Projects from projects.json: {list(projects.keys())}")
    await ctx.send(f"Projects found in data: {list(project_news.keys())}")
    await ctx.send(f"Project news counts: {dict((k, len(v)) for k, v in project_news.items())}")
    
    # Show first few project fields
    await ctx.send("**First 5 project fields found:**")
    for field in all_project_fields[:5]:
        await ctx.send(field)
        
    # Show first row data for inspection
    if rows:
        await ctx.send("**First row data:**")
        first_row = rows[0]
        for key, value in first_row.items():
            await ctx.send(f"  {key}: {value}")
            if len(f"  {key}: {value}") > 100:  # Truncate long values
                break

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')
    
    # Automatically run testdigest in the specified channel
    try:
        channel_id = int(os.environ["YOUR_CHANNEL_ID"])
        channel = bot.get_channel(channel_id)
        if channel:
            print(f"Running automatic digest in channel: {channel.name}")
            # Run the testdigest logic directly
            await run_testdigest(channel)
        else:
            print(f"Could not find channel with ID: {channel_id}")
    except Exception as e:
        print(f"Error running automatic digest: {e}")

async def run_testdigest(ch):
    """Extract the testdigest logic so it can be called both from slash command and on_ready"""
    today = dt.date.today().isoformat()
    try:
        raw_sheet_id = "1BIvwyfsvV2a797NqtV1aXjI6FpuxlIjPGKGCkdgHVqM"
        if not raw_sheet_id:
            await ch.send("Error: RAW_SHEET_ID environment variable is not set.")
            return
        try:
            book = gc.open_by_key(raw_sheet_id)
        except Exception as e:
            await ch.send(f"Error: Could not open spreadsheet with RAW_SHEET_ID. Exception: {e}")
            return
        try:
            ws = book.worksheet(today)
        except Exception as e:
            await ch.send(f"Error: No worksheet found for today's date ({today}). Exception: {e}")
            return
        try:
            rows = ws.get_all_records()
        except Exception as e:
            await ch.send(f"Error: Could not read records from worksheet for {today}. Exception: {e}")
            return
    except Exception as e:
        await ch.send(f"Unknown error occurred: {e}")
        return
    if not rows:
        await ch.send("No news items for today (worksheet is empty).")
        return

    # Group by Main Category and Subcategory (for general digest)
    grouped = defaultdict(lambda: defaultdict(list))
    # Group by project
    project_news = defaultdict(list)
    for r in rows:
        grouped[r["Main Category"]][r["Subcategory"]].append(r)
        # Parse project field (should be a list, but may be string)
        # Check for both "project" and "Projects" keys (case sensitive)
        project_field = r.get("Projects") or r.get("projects") or r.get("project") or r.get("Project")
        if project_field:
            if isinstance(project_field, str):
                try:
                    # Try to parse as JSON list
                    project_list = json.loads(project_field)
                except Exception:
                    # If it's a comma-separated string, split it
                    if "," in project_field:
                        project_list = [p.strip() for p in project_field.split(",")]
                    else:
                        project_list = [project_field]
            else:
                project_list = project_field
            for project in project_list:
                if project and project != "No News":
                    project_news[project].append(r)

    # Helper to sort: NO (🩺) before YES (🌐)
    def sort_key(r):
        return (r["Cross-domain"] != "NO", r["Title"].lower())

    # --- Project Threads ---
    # Add a date-labeled thread for all news
    all_news_thread_title = f"📰 Medical-AI Daily Digest — {today}"
    # Simply create the thread - Discord will return existing thread if it already exists
    all_news_thread = await ch.create_thread(name=all_news_thread_title, type=discord.ChannelType.public_thread)
    
    # Process main digest by category in the all news thread
    for main_cat in grouped:
        await all_news_thread.send(f"# {main_cat}")
        for sub_cat in grouped[main_cat]:
            await all_news_thread.send(f"## {sub_cat}")
            # Sort so NO (🩺) first, then YES (🌐)
            for r in sorted(grouped[main_cat][sub_cat], key=sort_key):
                emoji = "🩺" if r["Cross-domain"] == "NO" else "🌐"
                title = r["Title"]
                url = r["URL"]
                summary = r["Summary"]
                app_context = r.get("Application Context") or r.get("application context")
                summary_lines = summary.strip().split("\n")
                blockquote_summary = '\n'.join(f'> {line}' for line in summary_lines)
                # Replace Markdown link with bold title and URL in angle brackets
                line = f"{emoji} **{title}**: <{url}>\n{blockquote_summary}"
                if app_context:
                    line += f"\n> _Application: {app_context}_"
                await all_news_thread.send(line)

    # Create project-specific threads
    for project_name in projects.keys():
        news_items = project_news.get(project_name, [])
        if news_items:
            thread_title = f"{project_name} — {today}"
            # Create thread - Discord will return existing thread if it already exists
            thread = await ch.create_thread(name=thread_title, type=discord.ChannelType.public_thread)
            # Post each news item in the thread
            for r in news_items:
                title = r["Title"]
                url = r["URL"]
                summary = r["Summary"]
                app_context = r.get("Application Context") or r.get("application context")
                summary_lines = summary.strip().split("\n")
                blockquote_summary = '\n'.join(f'> {line}' for line in summary_lines)
                line = f"**{title}**: <{url}>\n{blockquote_summary}"
                if app_context:
                    line += f"\n> _Application: {app_context}_"
                await thread.send(line)

bot.run(os.environ["DISCORD_TOKEN"])