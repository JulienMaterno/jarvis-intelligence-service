"""
Shared constants and configuration for the Intelligence Service.
"""

# Valid primary categories for transcript analysis
PRIMARY_CATEGORIES = {
    "meeting",
    "reflection", 
    "journal",
    "task_planning",
    "other",
}

# Telegram bot chat ID for notifications (from env in production)
import os
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "https://jarvis-telegram-bot-qkz4et4n4q-as.a.run.app")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

# Service URLs
SYNC_SERVICE_URL = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
AUDIO_PIPELINE_URL = os.getenv("AUDIO_PIPELINE_URL", "https://jarvis-audio-pipeline-qkz4et4n4q-as.a.run.app")

# Language settings
OUTPUT_LANGUAGE = "English"  # All outputs should be in English regardless of input language
