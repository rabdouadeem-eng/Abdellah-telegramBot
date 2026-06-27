import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import sys
import json
import logging
import asyncio
import functools
from datetime import datetime
import aiohttp
import gspread
import google.generativeai as genai
from google.api_core.exceptions import TooManyRequests
from google.oauth2.service_account import Credentials
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("AbduGeminiBot")

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    PORT = int(os.getenv("PORT", "10000"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-999")
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

    @classmethod
    def validate(cls):
        required = ["TELEGRAM_BOT_TOKEN", "AUTHORIZED_USER_ID", "GOOGLE_SHEET_ID"]
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

def is_authorized(user_id: int) -> bool:
    return user_id == Config.AUTHORIZED_USER_ID

def authorization_check(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        if not is_authorized(update.effective_user.id):
            await update.message.reply_text("⛔ *ACCESS DENIED*", parse_mode="Markdown")
            return
        return await func(update, context)
    return wrapper

class AbduGeminiEngine:
    def __init__(self):
        self.api_key = Config.GEMINI_API_KEY
        genai.configure(api_key=self.api_key)
        self.system_instruction = (
            "You are AbduGeminiBot, an authentic, adaptive, and elite AI collaborator built "
            "exclusively for Abdellah Ventures LLC, working directly under the guidance of the founder Ehab. "
            "CRITICAL: You are NOT 'MiMo', you are NOT from Xiaomi, and you are NOT a generic support bot. "
            "Never apologize needlessly, never break character, and never output corporate filler. "
            "Always speak with deep context, absolute clarity, and tactical insight. "
            "Match the user's language (Arabic/English) instantly with a high-energy, helpful peer voice."
        )
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=self.system_instruction
        )
        self.semaphore = asyncio.Semaphore(1)
        logger.info("✅ AbduGemini Engine connected with embedded Core Identity Shield.")

    async def _call_ai(self, prompt: str) -> str:
        if not self.api_key:
            return "⚠️ المحرك أوفلاين. تحقق من المتغيرات البيئية (GEMINI_API_KEY)."
        async with self.semaphore:
            for attempt in range(5):
                try:
                    response = await self.model.generate_content_async(prompt)
                    return response.text
                except TooManyRequests:
                    wait = 2 ** attempt
                    logger.warning(f"⏳ حد الطلبات ممتلئ، إعادة المحاولة بعد {wait} ثوانٍ (محاولة {attempt+1})")
                    await asyncio.sleep(wait)
                except Exception as e:
                    logger.error(f"❌ خطأ في محرك Gemini: {e}")
                    return f"❌ خطأ في النظام: {str(e)}"
            return "⚠️ المحرك مشغول حالياً، يرجى المحاولة بعد قليل."

    async def chat_response(self, text: str) -> str:
        return await self._call_ai(text)

    async def analyze_sentiment(self, text: str) -> dict:
        prompt = f"Analyze sentiment and return a clean, executive JSON string (sentiment, confidence, summary, recommended_action) for this text:\n\"{text}\""
        response_text = await self._call_ai(prompt)
        return {"raw_response": response_text}

    async def process_command_intelligence(self, cmd: str, data: dict) -> str:
        prompt = f"Provide a brief, high-impact tactical insight for the operation '{cmd}' using this data: {data}. Keep it under 3 punchy sentences."
        return await self._call_ai(prompt)

    async def generate_outreach_variant(self, niche: str, city: str) -> str:
        prompt = f"Write a direct, high-converting B2B cold outreach message for a {niche} business located in {city}. The sender is Ehab from Abdellah Ventures LLC. Focus on driving a 10-min discovery call. Max 100 words. No fluff."
        return await self._call_ai(prompt)

ai_engine = AbduGeminiEngine()

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
            return ws

    def dump_leads(self, leads: list, niche: str, city: str) -> int:
        if not self.connect():
            return 0
        ws = self.get_or_create_worksheet(f"Leads_{niche}_{city}".replace(" ", "_"))
        if not ws:
            return 0
        rows = []
        for l in leads:
            rows.append([niche, l.get("Name", "N/A"), l.get("Phone", "N/A"), l.get("Website", "N/A"),
                         l.get("Address", "N/A"), str(l.get("Rating", "N/A")), str(l.get("Total Reviews", 0)),
                         l.get("Status", "N/A"), l.get("Place ID", ""), l.get("City", "N/A"),
                         datetime.now().isoformat(), "NEW"])
        if rows:
            ws.append_rows(rows)
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

class GooglePlacesScraper:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": Config.GOOGLE_MAPS_API_KEY or "",
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.currentOpeningHours,places.nationalPhoneNumber,places.websiteUri,nextPageToken"
        }

    async def fetch_places(self, query: str, max_results: int = 40) -> list:
        if not Config.GOOGLE_MAPS_API_KEY:
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
                "Category": niche, "Name": p.get("displayName", {}).get("text", "N/A"),
                "Phone": p.get("nationalPhoneNumber", "N/A"), "Website": p.get("websiteUri", "N/A"),
                "Address": p.get("formattedAddress", "N/A"), "Rating": p.get("rating", "N/A"),
                "Total Reviews": p.get("userRatingCount", 0),
                "Status": "Open" if p.get("currentOpeningHours", {}).get("openNow") else "Closed",
                "Place ID": p.get("id", ""), "City": city
            })
        await asyncio.to_thread(sheets.dump_leads, processed, niche, city)
        return processed

scraper = GooglePlacesScraper()

class CampaignEngine:
    def __init__(self):
        self.campaign_log = []
        self.active_campaign = None

    async def launch(self) -> dict:
        lc = await asyncio.to_thread(sheets.get_lead_count)
        if not lc:
            return {"status": "no_leads", "message": "No lead pools available."}
        target_sheet = max(lc, key=lc.get)
        parts = target_sheet.replace("Leads_", "").split("_")
        niche = parts[0] if len(parts) > 0 else "enterprise"
        city = parts[1] if len(parts) > 1 else "market"
        variant = await ai_engine.generate_outreach_variant(niche, city)
        campaign = {
            "campaign_id": f"CAM-{datetime.now().strftime('%Y%m%d-%H%M')}",
            "status": "launched", "target_sheet": target_sheet,
            "total_leads": lc[target_sheet], "messaging": "Option A Core",
            "ai_enhanced_variant": variant,
            "launched_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
        }
        self.active_campaign = campaign
        self.campaign_log.append(campaign)
        return campaign

campaign_engine = CampaignEngine()

@authorization_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *عبد الله تلغرام بوت | ABDUGEMINIBOT*\n\n✅ النظام متصل بنجاح.\nالمحرك شغال بـ *Gemini 2.0 Flash* وجاهز تماماً لخدمتك يا الزعيم.\n\nإرسل `/help` لعرض قائمة الأوامر.",
        parse_mode="Markdown"
    )

@authorization_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *دليل التحكم لـ عبدوجيميبوت*\n\n"
        "🔍 `/scrape [النظام] [المدينة]` - سحب الداتا وضخها في شيتس\n"
        "🚀 `/launch_campaign` - إطلاق حملة تسويقية ذكية\n"
        "📊 `/status` - مراقبة الـ KPIs والمؤشرات\n"
        "🧠 `/sentiment [النص]` - تحليل المشاعر والردود عبر السنتينل\n"
        "❓ `/help` - عرض هذا الدليل تكراراً"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@authorization_check
async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ الصيغة الصحيحة: `/scrape [niche] [city]`\nمثال: `/scrape cafes casablanca`", parse_mode="Markdown")
        return
    niche = context.args[0]
    city = " ".join(context.args[1:])
    msg = await update.message.reply_text("⏳ *جاري استخراج البيانات وضخها...*", parse_mode="Markdown")
    try:
        leads = await scraper.execute_pipeline(niche, city)
        if leads:
            insight = await ai_engine.process_command_intelligence("scrape", {"leads_found": len(leads), "niche": niche, "city": city})
            await msg.edit_text(f"✅ *تم بنجاح سحب وضخ {len(leads)} عميل محتمل.*\n\n🧠 *تحليل ذكي:* {insight}", parse_mode="Markdown")
        else:
            await msg.edit_text("❌ لم يتم العثور على بيانات. تحقق من الكي أو الكلمات الدلالية.")
    except Exception as e:
        await msg.edit_text(f"❌ خطأ عملي: {str(e)}")

@authorization_check
async def launch_campaign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🚀 *جاري إطلاق الحملة التسويقية...*", parse_mode="Markdown")
    result = await campaign_engine.launch()
    if result.get("status") == "no_leads":
        await msg.edit_text("⚠️ تعذر الإطلاق. قاعدة البيانات فارغة، استعمل أمر /scrape أولاً.")
    else:
        await msg.edit_text(
            f"🚀 *الحملة نشطة الآن*\nالمعرف: `{result['campaign_id']}`\nعدد الأهداف: *{result['total_leads']}*\n\n📝 *صيغة الـ AI:*\n{result['ai_enhanced_variant']}",
            parse_mode="Markdown"
        )

@authorization_check
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lead_counts = await asyncio.to_thread(sheets.get_lead_count)
    total = sum(lead_counts.values())
    active_camp = campaign_engine.active_campaign['campaign_id'] if campaign_engine.active_campaign else 'لا يوجد'
    text = (
        f"📊 *بوابة المراقبة و الـ KPIs*\n\n"
        f"📌 إجمالي الداتا المسحوبة: *{total}*\n"
        f"🚀 الحملة الحالية النشطة: `{active_camp}`\n"
        f"📁 عدد التصنيفات المتصلة: {len(lead_counts)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@authorization_check
async def sentiment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ الاستخدام: `/sentiment [النص المراد تحليله]`", parse_mode="Markdown")
        return
    text = " ".join(context.args)
    result = await ai_engine.analyze_sentiment(text)
    output = f"🧠 *SENTINEL REPORT*\n```\n{result['raw_response'][:500]}\n```"
    await update.message.reply_text(output, parse_mode="Markdown")

@authorization_check
async def handle_free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.chat.send_action(action="typing")
    reply = await ai_engine.chat_response(user_text)
    if len(reply) > 4000:
        reply = reply[:4000] + "...\n\n_(الرد مقتطع)_"
    await update.message.reply_text(reply)

async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "تشغيل واجهة عبدوجيميبوت"),
        BotCommand("scrape", "سحب بيانات من قوقل مابس"),
        BotCommand("launch_campaign", "إطلاق حملة مستهدفة"),
        BotCommand("status", "عرض إحصائيات الداتا"),
        BotCommand("sentiment", "تحليل مشاعر النصوص"),
        BotCommand("help", "دليل التحكم")
    ])
    logger.info("✅ Commands registered for AbduGeminiBot")

def main() -> None:
    Config.validate()
    app = (
        Application.builder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scrape", scrape_command))
    app.add_handler(CommandHandler("launch_campaign", launch_campaign_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("sentiment", sentiment_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_chat))
    if Config.WEBHOOK_URL and Config.RENDER_EXTERNAL_URL:
        logger.info(f"🚀 Webhook mode on port {Config.PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=Config.PORT,
            url_path=Config.WEBHOOK_PATH,
            webhook_url=Config.WEBHOOK_URL
        )
    else:
        logger.info("🔄 Polling mode active")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
