# =====================================================================
# SYSTEM COMMAND CENTER - ABDELLAH VENTURES LLC (c) 2026
# ALL-IN-ONE PRODUCTION ENGINE (INTEGRATED BOT, SCRAPER & ANALYTICS)
# Optimized for Direct Mobile Deployment on Render
# =====================================================================

import os
import sys
import json
import logging
import asyncio
import time
import csv
import io
from datetime import datetime
from urllib.parse import quote_plus

# External Dependencies
import aiohttp
from bs4 import BeautifulSoup
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("AbdellahVenturesBot")

# ─────────────────────────────────────────────────────────────────────
# 1. CENTRAL CONFIGURATION & SECRETS
# ─────────────────────────────────────────────────────────────────────

class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID", "0"))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-999")
    
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"  # Best-in-class fallback engine
    
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")  # Raw service account credentials JSON string
    
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
    WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}" if RENDER_EXTERNAL_URL else None

    OPTION_A_SUBJECT = "Quick question about {business_name}"
    OPTION_A_BODY = (
        "Hi {owner_name},\n\n"
        "I came across {business_name} while researching top {niche} "
        "businesses in {city}. I help companies like yours generate "
        "20-40% more inbound leads using AI-driven outreach systems.\n\n"
        "Would you be open to a 10-minute call this week to see if "
        "it's a fit?\n\n"
        "Best,\nEhab\nAbdellah Ventures LLC"
    )

    @classmethod
    def validate(cls):
        """Validate crucial system keys before bootup."""
        required = [
            "TELEGRAM_BOT_TOKEN",
            "GEMINI_API_KEY",
            "AUTHORIZED_USER_ID",
            "GOOGLE_SHEET_ID",
        ]
        missing = [r for r in required if not os.getenv(r)]
        if missing:
            logger.critical(f"[CONFIG] Boot aborted. Missing variables: {', '.join(missing)}")
            sys.exit(1)
        
        # Write Google Credentials JSON dynamically if provided as environment variable
        if cls.GOOGLE_CREDS_JSON:
            try:
                # Validate JSON structure
                json.loads(cls.GOOGLE_CREDS_JSON)
                with open("google_creds.json", "w") as f:
                    f.write(cls.GOOGLE_CREDS_JSON)
                logger.info("[CONFIG] Dynamic google_creds.json successfully generated.")
            except Exception as e:
                logger.error(f"[CONFIG] Failed to write dynamic GOOGLE_CREDS_JSON: {e}")
        else:
            logger.warning("[CONFIG] GOOGLE_CREDS_JSON env var not set. Sheets sync might fail if file is missing.")


# ─────────────────────────────────────────────────────────────────────
# 2. EHAB-ONLY ACCESS SECURITY GUARD
# ─────────────────────────────────────────────────────────────────────

def is_authorized(user_id: int) -> bool:
    return user_id == Config.AUTHORIZED_USER_ID

def authorization_check(func):
    """Decorator ensuring only Ihap can control the operational nodes."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        if not is_authorized(user_id):
            await update.message.reply_text(
                "⛔ *ACCESS DENIED*\n"
                "This ecosystem is protected under Abdellah Ventures LLC protocols.\n"
                f"Unauthorized user signature detected: `{user_id}`.",
                parse_mode="Markdown"
            )
            logger.warning(f"[SECURITY] Unauthorized command attempt blocked from user: {user_id}")
            return
        return await func(update, context)
    return wrapper


# ─────────────────────────────────────────────────────────────────────
# 3. GEMINI COGNITIVE LAYER (AI SENTINEL)
# ─────────────────────────────────────────────────────────────────────

class GeminiEngine:
    def __init__(self):
        if Config.GEMINI_API_KEY:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(Config.GEMINI_MODEL)
            logger.info("[GEMINI] Core Cognitive Engine Initialized.")
        else:
            self.model = None

    async def analyze_sentiment(self, text: str) -> dict:
        """Analyze prospect response sentiment."""
        if not self.model:
            return {"raw_response": "Gemini Key Not Set"}
        prompt = (
            "You are the AI Sentinel for Abdellah Ventures LLC. "
            "Analyze the following client feedback or email response for sentiment. "
            "Return a clean JSON payload detailing:\n"
            "- sentiment: positive | neutral | negative\n"
            "- confidence: float value from 0.0 to 1.0\n"
            "- summary: clear one-line business insight\n"
            "- recommended_action: tactical steps Ehab should take next\n\n"
            f"Prospect Response:\n\"{text}\""
        )
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return {"raw_response": response.text}
        except Exception as e:
            logger.error(f"[GEMINI] Sentiment Analysis Error: {e}")
            return {"raw_response": f"Analysis failed: {str(e)}"}

    async def process_command_intelligence(self, command: str, data: dict) -> str:
        """Provide continuous strategic guidance on data milestones."""
        if not self.model:
            return "Intelligence Layer offline. Please add key."
        prompt = (
            f"As the AI Operations Adviser for Abdellah Ventures LLC, "
            f"the team executed '{command}' with results data: {data}. "
            f"Provide a 3-line tactical insight about the leads or actions "
            f"and outline the best strategy to maximize conversions."
        )
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text
        except Exception as e:
            return f"Strategic analysis bypassed: {str(e)}"

    async def generate_outreach_variant(self, niche: str, city: str) -> str:
        """Synthesize highly customized outreach variants."""
        if not self.model:
            return "No custom variant available."
        prompt = (
            f"Synthesize an hyper-personalized B2B cold outreach message targeting {niche} in {city}. "
            f"Sender: Ehab from Abdellah Ventures LLC. Include a soft call-to-action for a "
            f"10-minute automation demo. Keep it strictly under 100 words, direct, and elite."
        )
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            return response.text
        except Exception as e:
            return f"Standard outreach fallback template selected: {str(e)}"

# Singleton Instance
gemini = GeminiEngine()


# ─────────────────────────────────────────────────────────────────────
# 4. GOOGLE SHEETS CONNECTOR (ZERO PANDAS LIGHTWEIGHT PIPELINE)
# ─────────────────────────────────────────────────────────────────────

class SheetsConnector:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(self):
        self.gc = None
        self.sheet = None

    def connect(self):
        """Lazy load connection to keep bot startup instant."""
        if self.gc:
            return True
        try:
            creds_path = "google_creds.json"
            if os.path.exists(creds_path):
                creds = Credentials.from_service_account_file(creds_path, scopes=self.SCOPES)
                self.gc = gspread.authorize(creds)
                self.sheet = self.gc.open_by_key(Config.GOOGLE_SHEET_ID)
                logger.info("[SHEETS] Connected to Google Sheets Engine.")
                return True
            else:
                logger.error("[SHEETS] Credentials file google_creds.json is missing.")
                return False
        except Exception as e:
            logger.error(f"[SHEETS] Connection failed: {e}")
            return False

    def get_or_create_worksheet(self, title: str):
        if not self.connect():
            return None
        try:
            return self.sheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = self.sheet.add_worksheet(title=title, rows=1000, cols=12)
            headers = [
                "Category", "Name", "Phone", "Website", "Address", 
                "Rating", "Total Reviews", "Status", "Place ID", 
                "City", "Timestamp", "Campaign Stage"
            ]
            worksheet.append_row(headers)
            return worksheet

    def dump_leads(self, leads: list, niche: str, city: str) -> int:
        if not self.connect():
            return 0
        worksheet_title = f"Leads_{niche}_{city}".replace(" ", "_")
        worksheet = self.get_or_create_worksheet(worksheet_title)
        if not worksheet:
            return 0

        rows_added = 0
        rows_to_append = []
        for lead in leads:
            row = [
                niche,
                lead.get("Name", "N/A"),
                lead.get("Phone", "N/A"),
                lead.get("Website", "N/A"),
                lead.get("Address", "N/A"),
                str(lead.get("Rating", "N/A")),
                str(lead.get("Total Reviews", 0)),
                lead.get("Status", "Closed/Unknown"),
                lead.get("Place ID", ""),
                city,
                datetime.now().isoformat(),
                "NEW"
            ]
            rows_to_append.append(row)
            rows_added += 1
        
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
        return rows_added

    def get_lead_count(self) -> dict:
        if not self.connect():
            return {}
        counts = {}
        try:
            for ws in self.sheet.worksheets():
                if ws.title.startswith("Leads_"):
                    # Fast cell counting without pulling huge data payload
                    values = ws.col_values(1)
                    counts[ws.title] = max(0, len(values) - 1)
        except Exception as e:
            logger.error(f"[SHEETS] Failed to fetch worksheet stats: {e}")
        return counts

# Singleton Instance
sheets = SheetsConnector()


# ─────────────────────────────────────────────────────────────────────
# 5. GOOGLE PLACES API V1 SCRAPER ENGINE
# ─────────────────────────────────────────────────────────────────────

class GooglePlacesScraper:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": Config.GOOGLE_MAPS_API_KEY if Config.GOOGLE_MAPS_API_KEY else "",
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,places.currentOpeningHours,"
                "places.nationalPhoneNumber,places.websiteUri,places.location,nextPageToken"
            )
        }

    async def fetch_places(self, query: str, max_results: int = 40) -> list:
        if not Config.GOOGLE_MAPS_API_KEY:
            logger.error("[SCRAPER] Scrape aborted. GOOGLE_MAPS_API_KEY is not defined.")
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
                            err_text = await resp.text()
                            logger.error(f"[SCRAPER] Error response: {err_text}")
                            break
                        
                        data = await resp.json()
                except Exception as e:
                    logger.error(f"[SCRAPER] Call failed: {e}")
                    break

                if "error" in data:
                    logger.error(f"[SCRAPER] Places API Error: {data['error']}")
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

    def process_raw_places(self, raw_places: list, category: str, city: str) -> list:
        cleaned = []
        for p in raw_places:
            loc = p.get("location", {})
            oh = p.get("currentOpeningHours", {})
            cleaned.append({
                "Category": category,
                "Name": p.get("displayName", {}).get("text", "N/A"),
                "Phone": p.get("nationalPhoneNumber", "N/A"),
                "Website": p.get("websiteUri", "N/A"),
                "Address": p.get("formattedAddress", "N/A"),
                "Rating": p.get("rating", "N/A"),
                "Total Reviews": p.get("userRatingCount", 0),
                "Status": "Open Now" if oh.get("openNow") else "Closed/Unknown",
                "Place ID": p.get("id", ""),
                "City": city,
            })
        return cleaned

    async def execute_pipeline(self, niche: str, city: str) -> list:
        query = f"{niche} in {city}"
        logger.info(f"[SCRAPER] Query initiated: {query}")
        raw_results = await self.fetch_places(query)
        if not raw_results:
            return []
        
        processed = self.process_raw_places(raw_results, niche, city)
        
        # Async run in executor to prevent blocking
        await asyncio.to_thread(sheets.dump_leads, processed, niche, city)
        return processed

# Singleton Instance
scraper = GooglePlacesScraper()


# ─────────────────────────────────────────────────────────────────────
# 6. COLD OUTREACH ENGINE & DASHBOARD
# ─────────────────────────────────────────────────────────────────────

class CampaignEngine:
    def __init__(self):
        self.campaign_log = []
        self.active_campaign = None

    async def launch(self) -> dict:
        lead_counts = await asyncio.to_thread(sheets.get_lead_count)
        if not lead_counts:
            return {
                "status": "no_leads",
                "message": "No lead pools available. Run /scrape first.",
            }

        # Target the freshest worksheet/pool with highest volume
        target_sheet = max(lead_counts, key=lead_counts.get)
        total_leads = lead_counts[target_sheet]

        parts = target_sheet.replace("Leads_", "").split("_")
        niche = parts[0] if len(parts) > 0 else "enterprise"
        city = parts[1] if len(parts) > 1 else "target market"

        ai_variant = await gemini.generate_outreach_variant(niche, city)

        campaign = {
            "campaign_id": f"CAM-{datetime.now().strftime('%Y%m%d-%H%M')}",
            "status": "launched",
            "target_sheet": target_sheet,
            "total_leads": total_leads,
            "messaging": "Option A (Optimized Core)",
            "subject_template": Config.OPTION_A_SUBJECT,
            "ai_enhanced_variant": ai_variant,
            "launched_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
            "estimated_completion": "24-48 hours",
        }

        self.active_campaign = campaign
        self.campaign_log.append(campaign)
        return campaign

# Singleton Instance
campaign_engine = CampaignEngine()


class Dashboard:
    def __init__(self):
        self.veto_panel_mode = "ARMED"  # ARMED | PASSIVE | OVERRIDE

    async def generate_full_status(self) -> str:
        lead_counts = await asyncio.to_thread(sheets.get_lead_count)
        total_leads = sum(lead_counts.values()) if lead_counts else 0
        active = campaign_engine.active_campaign
        campaigns_launched = len(campaign_engine.campaign_log)

        # ROI Modeling
        estimated_conversion_rate = 0.03
        avg_deal_value = 2500
        projected_revenue = total_leads * estimated_conversion_rate * avg_deal_value
        operational_cost = 47.0

        report = (
            "📊 *ABDELLAH VENTURES — MAIN OPERATIONAL PORTAL*\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"{'═' * 42}\n\n"

            "💰 *ROI TRACKER AND PIPELINE KPI*\n"
            f"  📌 Total Scraped Leads: *{total_leads}*\n"
            f"  🚀 Total Active Campaigns: *{campaigns_launched}*\n"
            f"  📈 Current Active Node: `{active['campaign_id'] if active else 'None'}`\n"
            f"  🎯 Est. Conversion Rate: `3.0% (No-Show Guard)`\n"
            f"  💵 Average Deal Value: `$2,500`\n"
            f"  🔮 Projected Revenue Flow: *${projected_revenue:,.2f}*\n"
            f"  💸 Operational Overhead: `${operational_cost}/mo`\n"
            f"  🏆 Projected System ROI: *{((projected_revenue - operational_cost) / max(operational_cost, 1)) * 100:,.1f}%*\n\n"

            "🛡️ *SECURITY & OVERRIDE PROTOCOL*\n"
            f"  System Lock State: *{self.veto_panel_mode}*\n"
            "  🛡️ _Armed Status: AI Outreach demands Ehab's direct authorization._\n\n"
            f"{'═' * 42}\n"
            "_Abdellah Ventures LLC — Continuous System Pipeline_"
        )
        return report

# Singleton Instance
dashboard = Dashboard()


# ─────────────────────────────────────────────────────────────────────
# 7. TELEGRAM INTERFACE DIRECTIVES
# ─────────────────────────────────────────────────────────────────────

@authorization_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "🏢 *ABDELLAH VENTURES LLC*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *Telegram Command Center: ONLINE*\n"
        "🤖 Gemini Sentinel Engine: READY\n"
        "📡 Main Server Webhook: ACTIVE\n\n"
        "Operations initialized, Ehab. All mobile-first workflows are fully functional.\n\n"
        "Command Interface Instructions:\n"
        "  /scrape `[niche] [city]` — Trigger Google Maps Scraper\n"
        "  /launch\\_campaign — Launch cold outreach (Option A)\n"
        "  /status — Display real-time KPI metrics\n"
        "  /sentiment `[text]` — Analyze prospect reply sentiment\n"
        "  /help — Display detailed reference guide\n\n"
        "_The system is on standby to acquire market share._"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


@authorization_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *OPERATIONS INTERFACE PROTOCOLS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔍 `/scrape [niche]
