import os, discord, gspread, datetime as dt
from discord.ext import commands, tasks
from dotenv import load_dotenv; load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
gc  = gspread.service_account("service_account.json")
ws  = gc.open_by_key("RAW_SHEET_ID").worksheet("raw_news")

@bot.slash_command(name="latest", description="Show today's Medical-AI news")
async def latest(ctx):
    await ctx.defer()
    today = dt.date.today().isoformat()
    rows  = [r for r in ws.get_all_records() if r["pub_date"] >= today][-10:]
    if not rows:
        await ctx.send("No items yet.")
        return
    for r in reversed(rows):
        embed = discord.Embed(title=r["title"], url=r["url"], description="\n".join(r["summary"].split("\\n")))
        embed.set_footer(text=f"{r['pub_date']} • {r['category']}")
        await ctx.send(embed=embed)

@tasks.loop(hours=24)
async def morning_digest():
    ch = bot.get_channel("YOUR_CHANNEL_ID")
    await bot.get_cog("latest").callback(ch)   # reuse same code

bot.run(os.environ["DISCORD_TOKEN"])
