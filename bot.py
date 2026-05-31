"""
Abdellah Ventures LLC — Telegram Command Center
Core bot with webhook server for Render deployment.

Commands:
  /start              - Initialize and verify connection
  /scrape [niche] [city] - Trigger lead scraper -> Google Sheets
  /launch_campaign    - Launch cold outreach (Option A messaging)
  /status             - Real-time KPI dashboard
  /sentiment [text]   - Run Gemini sentiment analysis
  /help               - List all available commands
"""

import logging
import os
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import Config
from security import authorization_check
from gemini_engine import gemini
from scraper_module import run_pipeline
from campaign_module import campaign_engine
from dashboard_module import dashboard

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  COMMAND HANDLERS
# ─────────────────────────────────────────────

@authorization_check
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize the bot and confirm connection."""
    welcome = (
        "🏢 *ABDELLAH VENTURES LLC*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *Telegram Command Center: ONLINE*\n"
        "🤖 Gemini Sentinel: CONNECTED\n"
        "📡 Webhook: ACTIVE\n\n"
        "Welcome back, Ehab. All systems operational.\n\n"
        "Available commands:\n"
        "  /scrape `[niche] [city]` — Scrape leads via Google Maps\n"
        "  /launch_campaign — Start outreach\n"
        "  /status — Dashboard KPIs\n"
        "  /sentiment `[text]` — AI analysis\n"
        "  /help — Full command list\n\n"
        "_Your mobile command center is ready._"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


@authorization_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display all available commands with descriptions."""
    help_text = (
        "📋 *COMMAND REFERENCE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔍 `/scrape [niche] [city]`\n"
        "   Triggers the Google Maps scraper v1.\n"
        "   Dumps phone & website into Sheets.\n"
        "   Example: `/scrape lawyer Miami`\n\n"
        "🚀 `/launch_campaign`\n"
        "   Initiates Cold Outreach Module.\n"
        "   Uses Option A optimized messaging.\n"
        "   AI generates enhanced variants.\n\n"
        "📊 `/status`\n"
        "   Real-time KPI dashboard:\n"
        "   • ROI Tracker\n"
        "   • Rotating Key Status\n"
        "   • Veto Panel Mode\n\n"
        "🧠 `/sentiment [text]`\n"
        "   Gemini-powered sentiment analysis.\n"
        "   Example: `/sentiment I need this setup`\n\n"
        "_Abdellah Ventures LLC — All rights reserved_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@authorization_check
async def scrape_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /scrape [niche] [city]
    Triggers the Google Maps scraper and dumps results to Google Sheets.
    """
    args = context.args

    if not args or len(args) < 2:
        await update.message.reply_text(
            "⚠️ *Usage:* `/scrape [niche] [city]`\n"
            "Example: `/scrape dentist Chicago`",
            parse_mode="Markdown",
        )
        return

    niche = args[0]
    city = " ".join(args[1:])

    status_msg = await update.message.reply_text(
        f"🔍 *SCRAPER ACTIVATED*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Niche: `{niche}`\n"
        f"📍 City: `{city}`\n"
        f"⏳ Extracting from Google Places API v1...\n\n"
        f"_Collecting phones, websites & ratings..._",
        parse_mode="Markdown",
    )

    try:
        # استدعاء دالة التشغيل المحدثة من ملف السكرابير الجديد
        result = run_pipeline(niche, city, max_results=40)

        if result:
            leads_found = len(result)
            # استدعاء ذكاء جيميلي لتحليل النتائج
            ai_insight = await gemini.process_command_intelligence("scrape", {"leads_found": leads_found, "niche": niche, "city": city})
            
            response = (
                f"✅ *SCRAPE COMPLETE*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 Niche: `{niche}`\n"
                f"📍 City: `{city}`\n"
                f"📊 Leads Found: *{leads_found}*\n"
                f"📝 Status: `pipeline_synced`\n\n"
                f"🧠 *Gemini Insight:*\n{ai_insight}\n\n"
                f"_Leads are ready in your Google Sheets pipeline._"
            )
        else:
            response = (
                f"⚠️ *SCRAPE COMPLETED — NO RESULTS*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 Niche: `{niche}`\n"
                f"📍 City: `{city}`\n"
                f"📊 Leads Found: 0\n\n"
                f"💡 Try checking your Google Maps API key or billing status."
            )

        await status_msg.edit_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        await status_msg.edit_text(
            f"❌ *SCRAPE ERROR*\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Error: `{str(e)[:200]}`\n\n"
            f"_Check logs on Render for details._",
            parse_mode="Markdown",
        )


@authorization_check
async def launch_campaign_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiates the Cold Outreach Module with Option A messaging."""
    status_msg = await update.message.reply_text(
        "🚀 *LAUNCHING CAMPAIGN...*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Preparing Option A messaging...\n"
        "🧠 Generating Gemini-enhanced variants...\n\n"
        "_Please wait..._",
        parse_mode="Markdown",
    )

    try:
        result = await campaign_engine.launch()

        if result["status"] == "no_leads":
            response = (
                "⚠️ *CAMPAIGN BLOCKED — NO LEADS*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 {result['message']}\n\n"
                "💡 Run `/scrape [niche] [city]` first to fill the pipeline."
            )
        else:
            response = (
                "✅ *CAMPAIGN LAUNCHED*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 Campaign ID: `{result['campaign_id']}`\n"
                f"📋 Target Sheet: `{result['target_sheet']}`\n"
                f"👥 Total Leads: *{result['total_leads']}*\n"
                f"📝 Messaging: *{result['messaging']}*\n"
                f"🕐 Launched At: `{result['launched_at']}`\n\n"
                f"🧠 *AI-Enhanced Variant:*\n"
                f"
http://googleusercontent.com/immersive_entry_chip/0

---

## 🏁 واش تدير درك؟
1. انسخ الكود هذا بالكامل.
2. ادخل لـ GitHub من تليفونك، وافتح ملف `bot.py` الحالي، واعمل استبدال (Paste) للكود القديم بهذا الكود النظيف.
3. دير **Commit**، وخلي راندر تعاود الـ Build وتطلع لايف صافية 100%! 🚀🔥🏁
