import os, json, hashlib, datetime as dt
import google.genai as genai, gspread, feedparser
from dotenv import load_dotenv

SOURCES_SHEET_ID = "1yvr3G5RU7zE9DatsCZdMNKNlKWUf9dMpiXCDFPrcAQM"
RAW_SHEET_ID     = "1BIvwyfsvV2a797NqtV1aXjI6FpuxlIjPGKGCkdgHVqM"

load_dotenv()
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash-001")     # ultra-cheap express model :contentReference[oaicite:7]{index=7}

gc     = gspread.service_account("service_account.json")  # bot-only creds :contentReference[oaicite:8]{index=8}
src_ws = gc.open_by_key("SOURCES_SHEET_ID").sheet1
dst_ws = gc.open_by_key("RAW_SHEET_ID").worksheet("raw_news")

for row in src_ws.get_all_records():
    feed = feedparser.parse(row["url"])                  # RSS/Atom auto-parsed :contentReference[oaicite:9]{index=9}
    if not feed.entries: continue
    entry = feed.entries[0]                              # newest item only
    url = entry.link
    # de-dup sheet via URL hash
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    if any(url_hash in r[0] for r in dst_ws.col_values(1)):  # col A holds hashes
        continue
    article = entry.get("summary", entry.title)[:8000]   # Flash token-safe
    prompt = f"""Return JSON {{title, published_date_iso, category, bullet_summary}} for: \"\"\"{article}\"\"\""""
    data = json.loads(model.generate_content(prompt).text)
    dst_ws.append_row([
        url_hash,
        data["published_date_iso"],
        data["category"],
        data["title"],
        url,
        "\n".join(data["bullet_summary"]),
        dt.datetime.utcnow().isoformat(timespec="seconds")
    ])
