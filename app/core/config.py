import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (override=True to override empty env vars on Windows)
load_dotenv(override=True)

_SUPABASE_URL = os.getenv('SUPABASE_URL')
_SUPABASE_KEY = os.getenv('SUPABASE_KEY')

_ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

_CLAUDE_MODEL_PRIMARY = os.getenv('CLAUDE_MODEL_PRIMARY') or os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-5-20250929')
_CLAUDE_MODEL_FALLBACKS = [
    model.strip()
    for model in os.getenv('CLAUDE_MODEL_FALLBACKS', 'claude-haiku-4-5-20251001').split(',')
    if model.strip()
]
_CLAUDE_MODEL_OPTIONS = [_CLAUDE_MODEL_PRIMARY] + [m for m in _CLAUDE_MODEL_FALLBACKS if m and m != _CLAUDE_MODEL_PRIMARY]

# Service URLs (single source of truth)
_SYNC_SERVICE_URL = os.getenv('SYNC_SERVICE_URL', 'https://jarvis-sync-service-776871804948.asia-southeast1.run.app')
_TELEGRAM_BOT_URL = os.getenv('TELEGRAM_BOT_URL', 'https://jarvis-telegram-bot-qkz4et4n4q-as.a.run.app')
_AUDIO_PIPELINE_URL = os.getenv('AUDIO_PIPELINE_URL', 'https://jarvis-audio-pipeline-qkz4et4n4q-as.a.run.app')
_MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'https://jarvis-mcp-server-776871804948.asia-southeast1.run.app')

# Telegram config
_TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID', '0'))

# API Key for authentication
_INTELLIGENCE_SERVICE_API_KEY = os.getenv('INTELLIGENCE_SERVICE_API_KEY')


class Config:
    """Central configuration for the intelligence service."""

    # Database
    SUPABASE_URL = _SUPABASE_URL
    SUPABASE_KEY = _SUPABASE_KEY

    # AI/LLM
    ANTHROPIC_API_KEY = _ANTHROPIC_API_KEY
    CLAUDE_MODEL_PRIMARY = _CLAUDE_MODEL_PRIMARY
    CLAUDE_MODEL_FALLBACKS = _CLAUDE_MODEL_FALLBACKS
    CLAUDE_MODEL = _CLAUDE_MODEL_PRIMARY
    CLAUDE_MODEL_OPTIONS = _CLAUDE_MODEL_OPTIONS

    # Service URLs
    SYNC_SERVICE_URL = _SYNC_SERVICE_URL
    TELEGRAM_BOT_URL = _TELEGRAM_BOT_URL
    AUDIO_PIPELINE_URL = _AUDIO_PIPELINE_URL
    MCP_SERVER_URL = _MCP_SERVER_URL
    
    # Telegram
    TELEGRAM_CHAT_ID = _TELEGRAM_CHAT_ID

    # API Authentication
    INTELLIGENCE_SERVICE_API_KEY = _INTELLIGENCE_SERVICE_API_KEY


settings = Config()
