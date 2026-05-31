@authorization_check
async def sentiment_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    /sentiment [text]
    Run Gemini-powered sentiment analysis.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Usage:* `/sentiment [text to analyze]`\n"
            "Example: `/sentiment I am very interested in your automation services!`",
            parse_mode="Markdown",
        )
        return

    text_to_analyze = " ".join(context.args)

    status_msg = await update.message.reply_text(
        "🧠 *SENTINEL SENTIMENT ANALYSIS V1.0*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Passing text to Gemini API layer...\n"
        "_Processing payload..._",
        parse_mode="Markdown",
    )

    try:
        # Pass data payload to the engine
        analysis = await gemini.analyze_sentiment(text_to_analyze)
        
        response_text = (
            "🧠 *SENTINEL ANALYSIS COMPLETE*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 *Input Text:* \"_{text_to_analyze[:150]}..._\"\n\n"
            f"📋 *Gemini Engine Output:*\n"
            f"```json\n"
            f"{analysis['raw_response']}\n"
            f"
```\n"
            "_Abdellah Ventures LLC — Intelligent Edge Ecosystem_"
        )
        
        await status_msg.edit_text(response_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Sentiment command error: {e}")
        await status_msg.edit_text(
            f"❌ *SENTINEL LAYER ERROR*\n"
            f"Error processing text payload: `{str(e)[:200]}`",
            parse_mode="Markdown",
        )


# ─────────────────────────────────────────────
#  WEBHOOK SERVER & CORE INITIALIZATION
# ─────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Set bot command list in Telegram interface post-boot."""
    bot_commands = [
        BotCommand("start", "Initialize and verify system connection"),
        BotCommand("scrape", "[niche] [city] - Trigger lead scraper engine"),
        BotCommand("launch_campaign", "Launch cold outreach sequence (Option A)"),
        BotCommand("status", "Pull real-time KPI dashboard summary"),
        BotCommand("sentiment", "[text] - Run Gemini sentiment analysis"),
        BotCommand("help", "List all available interface commands"),
    ]
    await application.bot.set_my_commands(bot_commands)
    logger.info("[BOT] Global menu command listing initialized.")


def main() -> None:
    """Initialize application router and start engine."""
    # Build the Application instance
    Config.validate()
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Wire up command routers to handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scrape", scrape_command))
    application.add_handler(CommandHandler("launch_campaign", launch_campaign_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("sentiment", sentiment_command))

    # Catch-all text block handler for debugging or manual override routing
    @authorization_check
    async def debug_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📡 *System Status:* Core commands are active. Use `/help` to see valid instruction sets.",
            parse_mode="Markdown"
        )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, debug_echo))

    # Production Webhook Configuration for Render Integration
    # Maps webhook url to standard async event loop runner natively using python-telegram-bot v20+
    logger.info(f"[WEBHOOK] Starting server mapping url: {Config.WEBHOOK_URL}")
    
    # Run the application via webhook inside Render's assigned port ecosystem
    port = int(os.environ.get("PORT", 8443))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=Config.WEBHOOK_PATH,
        webhook_url=Config.WEBHOOK_URL
    )


if __name__ == "__main__":
    main()
