import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import sys
import json
import logging
import asyncio
from datetime import datetime
import aiohttp
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# ========== إعدادات التسجيل ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("AbdellahVenturesBot")

# ========== فئة الإعدادات ==========
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # هنا مفتاح OpenRouter (sk-or-...)
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    PORT = int(os.getenv("PORT", "8443"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-999")
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None
    
    OPTION_A_SUBJECT = "Quick question about {business_name}"
    OPTION_A_BODY = "Hi {owner_name},\n\nI came across {business_name} in {city}. We add 20-40% more inbound leads using AI.\n\nOpen for a 10-min call?\n\nBest,\nEhab\nAbdellah Ventures LLC"
    
    OPENROUTER_MODEL = "google/gemini-1.5-flash"
    
    @classmethod
    def validate(cls):
        required = ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "AUTHORIZED_USER_ID", "GOOGLE_SHEET_ID"]
        missing = [r for r in required if not os.getenv(r)]
        if missing:
            logger.critical(f"❌ المتغيرات الناقصة: {missing}")
            sys.exit(1)
        
        if cls.GOOGLE_CREDS_JSON:
            try:
                json.loads(cls.GOOGLE_CREDS_JSON)
                with open("google_creds.json", "w") as f:
                    f.write(cls.GOOGLE_CREDS_JSON)
                logger.info("✅ تم حفظ google_creds.json")
            except Exception as e:
                logger.error(f"❌ فشل حفظ google_creds.json: {e}")

# ========== التحقق من الصلاحية ==========
def is_authorized(user_id: int) -> bool:
    return user_id == Config.AUTHORIZED_USER_ID

def authorization_check(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        if not is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ *ACCESS DENIED*", parse_mode="Markdown")
            return
        return await func(update, context)
    return wrapper

# ========== محرك الاتصال بـ OpenRouter ==========
class GeminiEngine:
    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.api_key:
            logger.info("✅ OpenRouter Engine initialized")
        else:
            logger.warning("⚠️ API key missing for OpenRouter")

    async def _call_ai(self, prompt: str) -> str:
        if not self.api_key:
            return "⚠️ المحرك أوفلاين. تحقق من مفتاح الـ API."
        
        payload = {
            "model": Config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, headers=self.headers, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content']
                    else:
                        error_data = await resp.text()
                        logger.error(f"OpenRouter Error: Status {resp.status} - {error_data}")
                        return f"❌ خطأ من الخادم (Status {resp.status})"
        except Exception as e:
            logger.error(f"Connection error to OpenRouter: {e}")
            return f"❌ فشل الاتصال بالمحرك: {str(e)}"

    async def chat_response(self, text: str) -> str:
        system_prompt = "You are an authentic, adaptive AI collaborator with a touch of wit, helping the user Ehab manage his automated growth agency Abdellah Ventures LLC. Match his energy and style."
        return await self._call_ai(f"{system_prompt}\nUser says: {text}")

    async def analyze_sentiment(self, text: str) -> dict:
        prompt = f"Analyze sentiment and return JSON (sentiment, confidence, summary, recommended_action):\n\"{text}\""
        response_text = await self._call_ai(prompt)
        return {"raw_response": response_text}

    async def process_command_intelligence(self, cmd: str, data: dict) -> str:
        prompt = f"Provide 3-line tactical insight for operation '{cmd}' with data: {data}"
        return await self._call_ai(prompt)

    async def generate_outreach_variant(self, niche: str, city: str) -> str:
        prompt = f"Write direct B2B cold outreach for {niche} in {city}. Sender Ehab, Abdellah Ventures LLC. Max 100 words."
        return await self._call_ai(prompt)

gemini = GeminiEngine()

# ========== الاتصال بـ Google Sheets ==========
class SheetsConnector:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    def __init__(self):
        self.gc = None
        self.sheet = None

    def connect(self):
        if self.gc:
            return True
        try:
            if os.path.exists("google_creds.json"):
                creds = Credentials.from_service_account_file("google_creds.json", scopes=self.SCOPES)
                self.gc = gspread.authorize(creds)
                self.sheet = self.gc.open_by_key(Config.GOOGLE_SHEET_ID)
                logger.info("✅ Google Sheets connected")
                return True
            else:
                logger.error("❌ google_creds.json not found")
                return False
        except Exception as e:
            logger.error(f"❌ Sheets connection error: {e}")
            return False

    def get_or_create_worksheet(self, title: str):
        if not self.connect():
            return None
        try:
            return self.sheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=1000, cols=12)
            ws.append_row(["Category", "Name", "Phone", "Website", "Address", "Rating", "Total Reviews", "Status", "Place ID", "City", "Timestamp", "Campaign Stage"])
            logger.info(f"✅ Created new worksheet: {title}")
            return ws

    def dump_leads(self, leads: list, niche: str, city: str) -> int:
        if not self.connect():
            return 0
        ws = self.get_or_create_worksheet(f"Leads_{niche}_{city}".replace(" ", "_"))
        if not ws:
            return 0
        rows = []
        for l in leads:
            rows.append([
                niche,
                l.get("Name", "N/A"),
                l.get("Phone", "N/A"),
                l.get("Website", "N/A"),
                l.get("Address", "N/A"),
                str(l.get("Rating", "N/A")),
                str(l.get("Total Reviews", 0)),
                l.get("Status", "N/A"),
                l.get("Place ID", ""),
                city,
                datetime.now().isoformat(),
                "NEW"
            ])
        if rows:
            ws.append_rows(rows)
            logger.info(f"✅ Dumped {len(rows)} leads to {ws.title}")
        return len(rows)

    def get_lead_count(self) -> dict:
        if not self.connect():
            return {}
        counts = {}
        try:
            for ws in self.sheet.worksheets():
                if ws.title.startswith("Leads_"):
                    counts[ws.title] = max(0, len(ws.col_values(1)) - 1)
        except Exception as e:
            logger.error(f"Error getting lead counts: {e}")
        return counts

sheets = SheetsConnector()

# ========== ماسح Google Places ==========
class GooglePlacesScraper:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": Config.GOOGLE_MAPS_API_KEY or "",
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.currentOpeningHours,places.nationalPhoneNumber,places.websiteUri,nextPageToken"
        }

    async def fetch_places(self, query: str, max_results: int = 40) -> list:
        if not Config.GOOGLE_MAPS_API_KEY:
            logger.error("❌ Google Maps API key missing")
            return []
        url = "https://places.googleapis.com/v1/places:searchText"
        results = []
        page_token = None
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while len(results) < max_results:
                body = {"textQuery": query, "languageCode": "en", "maxResultCount": 20}
                if page_token:
                    body["pageToken"] = page_token
                try:
                    async with session.post(url, json=body, timeout=15) as resp:
                        if resp.status != 200:
                            logger.error(f"Places API error: {resp.status}")
                            break
                        data = await resp.json()
                except Exception as e:
                    logger.error(f"Request error: {e}")
                    break
                places = data.get("places", [])
                if not places:
                    break
                results.extend(places)
                page_token = data.get("nextPageToken")
                if not page_token or len(results) >= max_results:
                    break
                await asyncio.sleep(1.5)
        return results[:max_results]

    async def execute_pipeline(self, niche: str, city: str) -> list:
        raw = await self.fetch_places(f"{niche} in {city}")
        if not raw:
            return []
        processed = []
        for p in raw:
            processed.append({
                "Category": niche,
                "Name": p.get("displayName", {}).get("text", "N/A"),
                "Phone": p.get("nationalPhoneNumber", "N/A"),
                "Website": p.get("websiteUri", "N/A"),
                "Address": p.get("formattedAddress", "N/A"),
                "Rating": p.get("rating", "N/A"),
                "Total Reviews": p.get("userRatingCount", 0),
                "Status": "Open" if p.get("currentOpeningHours", {}).get("openNow") else "Closed",
                "Place ID": p.get("id", ""),
                "City": city
            })
        await asyncio.to_thread(sheets.dump_leads, processed, niche, city)
        logger.info(f"✅ Processed {len(processed)} leads for {niche} in {city}")
        return processed

scraper = GooglePlacesScraper()

# ========== محرك الحملات ==========
class CampaignEngine:
    def __init__(self):
        self.campaign_log = []
        self.active_campaign = None

    async def launch(self) -> dict:
        lc = await asyncio.to_thread(sheets.get_lead_count)
        if not lc:
            return {"status": "no_leads", "message": "No lead pools. Run /scrape first."}
        target_sheet = max(lc, key=lc.get)
        parts = target_sheet.replace("Leads_", "").split("_")
        niche = parts[0] if len(parts) > 0 else "enterprise"
        city = parts[1] if len(parts) > 1 else "market"
        variant = await gemini.generate_outreach_variant(niche, city)
        campaign = {
            "campaign_id": f"CAM-{datetime.now().strftime('%Y%m%d-%H%M')}",
            "status": "launched",
            "target_sheet": target_sheet,
            "total_leads": lc[target_sheet],
            "messaging": "Option A Core",
            "ai_enhanced_variant": variant,
            "launched_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        self.active_campaign = campaign
        self.campaign_log.append(campaign)
        logger.info(f"🚀 Campaign launched: {campaign['campaign_id']}")
        return campaign

campaign_engine = CampaignEngine()

# ========== أوامر البوت ==========
@authorization_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏢 *ABDELLAH VENTURES LLC*\n✅ Core Interface Online.\nUse `/help` for system directives.",
        parse_mode="Markdown"
    )

@authorization_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *SYSTEM MANUAL*\n\n"
        "🔍 `/scrape [niche] [city]` - Scrape leads from Google Places\n"
        "🚀 `/launch_campaign` - Launch outreach campaign\n"
        "📊 `/status` - Show lead counts and active campaign\n"
        "🧠 `/sentiment [text]` - Analyze sentiment of text\n"
        "❓ `/help` - This message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@authorization_check
async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Format: `/scrape [niche] [city]`\nExample: `/scrape cafes casablanca`", parse_mode="Markdown")
        return
    niche = context.args[0]
    city = " ".join(context.args[1:])
    msg = await update.message.reply_text("⏳ *Extraction initiated...*", parse_mode="Markdown")
    try:
        leads = await scraper.execute_pipeline(niche, city)
        if leads:
            insight = await gemini.process_command_intelligence("scrape", {"leads_found": len(leads), "niche": niche, "city": city})
            await msg.edit_text(
                f"✅ *Synced {len(leads)} Leads.*\n\n🧠 *Insight:* {insight}",
                parse_mode="Markdown"
            )
        else:
            await msg.edit_text("❌ Extraction returned 0 records. Check API key or try different niche/city.")
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        await msg.edit_text(f"❌ Error: {str(e)}")

@authorization_check
async def launch_campaign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🚀 *Igniting Campaign...*", parse_mode="Markdown")
    result = await campaign_engine.launch()
    if result.get("status") == "no_leads":
        await msg.edit_text("⚠️ Outreach blocked. Database empty. Use /scrape first.")
    else:
        await msg.edit_text(
            f"✅ *Campaign Active*\nID: `{result['campaign_id']}`\nLeads: *{result['total_leads']}*\n\n📝 *AI Outreach Variant:* \n{result['ai_enhanced_variant']}",
            parse_mode="Markdown"
        )

@authorization_check
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lead_counts = await asyncio.to_thread(sheets.get_lead_count)
    total = sum(lead_counts.values())
    active_camp = campaign_engine.active_campaign['campaign_id'] if campaign_engine.active_campaign else 'None'
    text = (
        f"📊 *OPERATIONAL KPI PORTAL*\n\n"
        f"📌 Total Leads: *{total}*\n"
        f"🚀 Active Campaign: `{active_camp}`\n"
        f"📁 Lead Sources: {len(lead_counts)} categories"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@authorization_check
async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/sentiment [text to analyze]`", parse_mode="Markdown")
        return
    text = " ".join(context.args)
    result = await gemini.analyze_sentiment(text)
    output = f"🧠 *SENTINEL REPORT*\n```json\n{result['raw_response']}\n```"
    await update.message.reply_text(output, parse_mode="Markdown")

# ========== معالج المحادثة الحرة المنفصلة ==========
@authorization_check
async def handle_free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.chat.send_action(action="typing")
    reply = await gemini.chat_response(user_text)
    await update.message.reply_text(reply)

# ========== الإعداد بعد بدء التطبيق ==========
async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "Initialize system"),
        BotCommand("scrape", "Scrape leads from Google Places"),
        BotCommand("launch_campaign", "Launch outreach campaign"),
        BotCommand("status", "Show KPIs"),
        BotCommand("sentiment", "Analyze text sentiment"),
        BotCommand("help", "Show manual")
    ])
    logger.info("✅ Bot commands registered")

# ========== التشغيل الرئيسي ==========
def main() -> None:
    Config.validate()
    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # إضافة معالجات الأوامر
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scrape", scrape_command))
    app.add_handler(CommandHandler("launch_campaign", launch_campaign_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("sentiment", sentiment_command))
    
    # إضافة معالج النصوص الحرة
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_chat))
    
    # تشغيل البوت
    if Config.WEBHOOK_URL and Config.RENDER_EXTERNAL_URL:
        logger.info(f"🚀 Starting webhook mode on port {Config.PORT}, path {Config.WEBHOOK_PATH}")
        app.run_webhook(
            listen="0.0.0.0",
            port=Config.PORT,
            url_path=Config.WEBHOOK_PATH,
            webhook_url=Config.WEBHOOK_URL
        )
    else:
        logger.info("🔄 WEBHOOK_URL not set, falling back to polling mode")
        app.run_polling()

if __name__ == "__main__":
    main()
