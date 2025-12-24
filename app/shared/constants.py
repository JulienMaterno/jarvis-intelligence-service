"""
Shared constants and configuration for the Intelligence Service.

Note: Service URLs and Telegram config are now centralized in app.core.config.
This module re-exports them for backwards compatibility.
"""

from app.core.config import settings

# Valid primary categories for transcript analysis
PRIMARY_CATEGORIES = {
    "meeting",
    "reflection", 
    "journal",
    "task_planning",
    "other",
}

# Language settings
OUTPUT_LANGUAGE = "English"  # All outputs should be in English regardless of input language

# Re-export from centralized config (for backwards compatibility)
TELEGRAM_BOT_URL = settings.TELEGRAM_BOT_URL
TELEGRAM_CHAT_ID = settings.TELEGRAM_CHAT_ID
SYNC_SERVICE_URL = settings.SYNC_SERVICE_URL
AUDIO_PIPELINE_URL = settings.AUDIO_PIPELINE_URL
