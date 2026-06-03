import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
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

# ========== إعدادات التسجيل ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("AbdellahVenturesBot")

# ========== فئة الإعدادات ==========
class Config:
    # متغيرات البيئة الأساسية
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    
    # إعدادات Render
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # مثال: https://mybot.onrender.com
    PORT = int(os.getenv("PORT", "8443"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-999")
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None
    
    # قوالب البريد الإلكتروني
    OPTION_A_SUBJECT = "Quick question about {business_name}"
    OPTION_A_BODY = "Hi {owner_name},\n\nI came across {business_name} in {city}. We add 20-40% more inbound leads using AI.\n\nOpen for a 10-min call?\n\nBest,\nEhab\nAbdellah Ventures LLC"
    
    # نموذج Gemini (يفضل استخدام نموذج مستقر)
    GEMINI_MODEL = "gemini-1.5-flash"  # تغيير إلى نموذج متاح
    
    @classmethod
    def validate(cls):
        """التحقق من وجود المتغيرات الأساسية"""
        required = ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY", "AUTHORIZED_USER_ID", "GOOGLE_SHEET_ID"]
        missing = [r for r in required if not os.getenv(r)]
        if missing:
            logger.critical(f"❌ المتغيرات الناقصة: {missing}")
            sys.exit(1)
        
        # حفظ ملف بيانات اعتماد Google Sheets إذا وجد
        if cls.GOOGLE_CREDS_JSON:
            try:
                json.loads(cls.GOOGLE_CREDS_JSON)  # التحقق من صحة JSON
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

# ========== محرك Gemini ==========
class GeminiEngine:
    def __init__(self):
        if Config.GEMINI_API_KEY:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
            logger.info("✅ Gemini Engine initialized")
        else:
            self.model = None
            logger.warning("⚠️ Gemini API key missing")

    async def analyze_sentiment(self, text: str) -> dict:
        if not self.model:
            return {"raw_response": "⚠️ Gemini غير متاح"}
        prompt = f"Analyze sentiment and return JSON (sentiment, confidence, summary, recommended_action):\n\"{text}\""
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return {"raw_response": response.text}
        except Exception as e:
            logger.error(f"Sentiment error: {e}")
            return {"raw_response": str(e)}

    async def process_command_intelligence(self, cmd: str, data: dict) -> str:
        if not self.model:
            return "⚠️ Gemini غير متاح"
        prompt = f"Provide 3-line tactical insight for operation '{cmd}' with data: {data}"
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text
        except Exception as e:
            return str(e)

    async def generate_outreach_variant(self, niche: str, city: str) -> str:
        if not self.model:
            return "Fallback Template active"
        prompt = f"Write direct B2B cold outreach for {niche} in {city}. Sender Ehab, Abdellah Ventures LLC. Max 100 words."
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text
        except Exception as e:
            return str(e)

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
                await asyncio.sleep(1.5)  # تجنب تجاوز الحدود
        return results[:max_results]

    async def execute_pipeline(self, niche: str, city: str) -> list:
        raw = await self.fetch_places(f"{niche} in {city}")
        if not raw:
            return []
        processed = []
        for p in raw:
            processed.append({
                "Category": niche,
                "Name": p.
