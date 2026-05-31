import os
import sys
import json
import logging
import asyncio
from datetime import datetime
import aiohttp
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("AbdellahVenturesBot")

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-999")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None
    OPTION_A_SUBJECT = "Quick question about {business_name}"
    OPTION_A_BODY = "Hi {owner_name},\n\nI came across {business_name} in {city}. We add 20-40% more inbound leads using AI.\n\nOpen for a 10-min call?\n\nBest,\nEhab\nAbdellah Ventures LLC"

    @classmethod
    def validate(cls):
        req = ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "AUTHORIZED_USER_ID", "GOOGLE_SHEET_ID"]
        missing = [r for r in req if not os.getenv(r)]
        if missing:
            logger.critical(f"Missing env vars: {missing}")
            sys.exit(1)
        if cls.GOOGLE_CREDS_JSON:
            try:
                json.loads(cls.GOOGLE_CREDS_JSON)
                with open("google_creds.json", "w") as f: f.write(cls.GOOGLE_CREDS_JSON)
            except Exception as e: logger.error(f"Creds write fail: {e}")

def is_authorized(user_id: int) -> bool:
    return user_id == Config.AUTHORIZED_USER_ID

def authorization_check(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user: return
        if not is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ *ACCESS DENIED*")
            return
        return await func(update, context)
    return wrapper

class GeminiEngine:
    def __init__(self):
        if Config.GEMINI_API_KEY:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
        else: self.model = None

    async def analyze_sentiment(self, text: str) -> dict:
        if not self.model: return {"raw_response": "Offline"}
        p = f"Analyze sentiment and return JSON (sentiment, confidence, summary, recommended_action):\n\"{text}\""
        try:
            r = await asyncio.to_thread(self.model.generate_content, p)
            return {"raw_response": r.text}
        except Exception as e: return {"raw_response": str(e)}

    async def process_command_intelligence(self, cmd: str, data: dict) -> str:
        if not self.model: return "Offline"
        p = f"Provide 3-line tactical insight for operation '{cmd}' with data: {data}"
        try:
            r = await asyncio.to_thread(self.model.generate_content, p)
            return r.text
        except Exception as e: return str(e)

    async def generate_outreach_variant(self, niche: str, city: str) -> str:
        if not self.model: return "Fallback Template active"
        p = f"Write direct B2B cold outreach for {niche} in {city}. Sender Ehab, Abdellah Ventures LLC. Max 100 words."
        try:
            r = await asyncio.to_thread(self.model.generate_content, p)
            return r.text
        except Exception as e: return str(e)

gemini = GeminiEngine()

class SheetsConnector:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    def __init__(self):
        self.gc = None
        self.sheet = None

    def connect(self):
        if self.gc: return True
        try:
            if os.path.exists("google_creds.json"):
                creds = Credentials.from_service_account_file("google_creds.json", scopes=self.SCOPES)
                self.gc = gspread.authorize(creds)
                self.sheet = self.gc.open_by_key(Config.GOOGLE_SHEET_ID)
                return True
            return False
        except Exception as e: return False

    def get_or_create_worksheet(self, title: str):
        if not self.connect(): return None
        try: return self.sheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=1000, cols=12)
            ws.append_row(["Category", "Name", "Phone", "Website", "Address", "Rating", "Total Reviews", "Status", "Place ID", "City", "Timestamp", "Campaign Stage"])
            return ws

    def dump_leads(self, leads: list, niche: str, city: str) -> int:
        if not self.connect(): return 0
        ws = self.get_or_create_worksheet(f"Leads_{niche}_{city}".replace(" ", "_"))
        if not ws: return 0
        rows = [[niche, l.get("Name","N/A"), l.get("Phone","N/A"), l.get("Website","N/A"), l.get("Address","N/A"), str(l.get("Rating","N/A")), str(l.get("Total Reviews",0)), l.get("Status","N/A"), l.get("Place ID",""), city, datetime.now().isoformat(), "NEW"] for l in leads]
        if rows: ws.append_rows(rows)
        return len(rows)

    def get_lead_count(self) -> dict:
        if not self.connect(): return {}
        counts = {}
        try:
            for ws in self.sheet.worksheets():
                if ws.title.startswith("Leads_"): counts[ws.title] = max(0, len(ws.col_values(1)) - 1)
        except Exception: pass
        return counts

sheets = SheetsConnector()

class GooglePlacesScraper:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": Config.GOOGLE_MAPS_API_KEY or "",
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.currentOpeningHours,places.nationalPhoneNumber,places.websiteUri,nextPageToken"
        }

    async def fetch_places(self, query: str, max_results: int = 40) -> list:
        if not Config.GOOGLE_MAPS_API_KEY: return []
        url = "https://places.googleapis.com/v1/places:searchText"
        results = []
        page_token = None
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while len(results) < max_results:
                body = {"textQuery": query, "languageCode": "en", "maxResultCount": 20}
                if page_token: body["pageToken"] = page_token
                try:
                    async with session.post(url, json=body, timeout=15) as resp:
                        if resp.status != 200: break
                        data = await resp.json()
                except Exception: break
                places = data.get("places", [])
                if not places: break
                results.extend(places)
                page_token = data.get("nextPageToken")
                if not page_token or len(results) >= max_results: break
                await asyncio.sleep(1.5)
        return results[:max_results]

    async def execute_pipeline(self, niche: str, city: str) -> list:
        raw = await self.fetch_places(f"{niche} in {city}")
        if not raw: return []
        processed = [{
            "Category": niche, "Name": p.get("displayName", {}).get("text", "N/A"),
            "Phone": p.get("nationalPhoneNumber", "N/A"), "Website": p.get("websiteUri", "N/A"),
            "Address": p.get("formattedAddress", "N/A"), "Rating": p.get("rating", "N/A"),
            "Total Reviews": p.get("userRatingCount", 0), "Status": "Open" if p.get("currentOpeningHours", {}).get("openNow") else "Closed",
            "Place ID": p.get("id", ""), "City": city
        } for p in raw]
        await asyncio.to_thread(sheets.dump_leads, processed, niche, city)
        return processed

scraper = GooglePlacesScraper()

class CampaignEngine:
    def __init__(self):
        self.campaign_log = []
        self.active_campaign = None

    async def launch(self) -> dict:
        lc = await asyncio.to_thread(sheets.get_lead_count)
        if not lc: return {"status": "no_leads", "message": "No lead pools. Run /scrape first."}
        tgt = max(lc, key=lc.get)
        parts = tgt.replace("Leads_", "").split("_")
        niche, city = parts[0] if len(parts)>0 else "enterprise", parts[1] if len(parts)>1 else "market"
        variant = await gemini.generate_outreach_variant(niche, city)
        camp = {
            "campaign_id": f"CAM-{datetime.now().strftime('%Y%m%d-%H%M')}", "status": "launched",
            "target_sheet": tgt, "total_leads": lc[tgt], "messaging": "Option A Core",
            "ai_enhanced_variant": variant, "launched_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        self.active_campaign = camp
        self.campaign_log.append(camp)
        return camp

campaign_engine = CampaignEngine()

@authorization_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏢 *ABDELLAH VENTURES LLC*\n✅ Core Interface Online.\nUse `/help` for system directives.", parse_mode="Markdown")

@authorization_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    h = ("📋 *SYSTEM MANUAL*\n\n"
         "🔍 `/scrape [niche] [city]`\n"
         "🚀 `/launch_campaign`\n"
         "📊 `/status`\n"
         "🧠 `/sentiment [text]`")
    await update.message.reply_text(h, parse_mode="Markdown")

@authorization_check
async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: `/scrape [niche] [city]`")
        return
    niche, city = context.args[0], " ".join(context.args[1:])
    msg = await update.message.reply_text("⏳ *Extraction initiated...*", parse_mode="Markdown")
    res = await scraper.execute_pipeline(niche, city)
    if res:
        ai = await gemini.process_command_intelligence("scrape", {"leads_found": len(res), "niche": niche, "city": city})
        await msg.edit_text(f"✅ *Synced {len(res)} Leads.*\n\n🧠 *Insight:* {ai}", parse_mode="Markdown")
    else:
        await msg.edit_text("❌ Extraction returned 0 records.")

@authorization_check
async def launch_campaign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🚀 *Igniting Campaign...*", parse_mode="Markdown")
    res = await campaign_engine.launch()
    if res.get("status") == "no_leads":
        await msg.edit_text("⚠️ Outreach blocked. Database empty.")
    else:
        await msg.edit_text(f"✅ *Campaign Active*\nID: `{res['campaign_id']}`\nLeads: *{res['total_leads']}*", parse_mode="Markdown")

@authorization_check
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lc = await asyncio.to_thread(sheets.get_lead_count)
    tot = sum(lc.values())
    r = f"📊 *OPERATIONAL KPI PORTAL*\n\n📌 Total Leads: *{tot}*\n🚀 Active Node: `{campaign_engine.active_campaign['campaign_id'] if campaign_engine.active_campaign else 'None'}`"
    await update.message.reply_text(r, parse_mode="Markdown")

@authorization_check
async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    txt = " ".join(context.args)
    res = await gemini.analyze_sentiment(txt)
    await update.message.reply_text(f"🧠 *SENTINEL REPORT*\n```json\n{res['raw_response']}\n
```", parse_mode="Markdown")

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "Init"), BotCommand("scrape", "Scrape leads"),
        BotCommand("launch_campaign", "Launch outreach"), BotCommand("status", "KPI status"),
        BotCommand("sentiment", "Analyze response"), BotCommand("help", "Manual")
    ])

def main() -> None:
    Config.validate()
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scrape", scrape_command))
    app.add_handler(CommandHandler("launch_campaign", launch_campaign_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("sentiment", sentiment_command))
    
    port = int(os.environ.get("PORT", 8443))
    if Config.WEBHOOK_URL:
        app.run_webhook(listen="0.0.0.0", port=port, url_path=Config.WEBHOOK_PATH, webhook_url=Config.WEBHOOK_URL)
    else:
        app.run_polling()

if __name__ == "__main__":
    main()
