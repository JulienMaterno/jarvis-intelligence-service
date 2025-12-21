import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

_SUPABASE_URL = os.getenv('SUPABASE_URL')
_SUPABASE_KEY = os.getenv('SUPABASE_KEY')

_ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')

_CLAUDE_MODEL_PRIMARY = os.getenv('CLAUDE_MODEL_PRIMARY') or os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-5-20250929')
_CLAUDE_MODEL_FALLBACKS = [
    model.strip()
    for model in os.getenv('CLAUDE_MODEL_FALLBACKS', 'claude-3-5-haiku-20241022').split(',')
    if model.strip()
]
_CLAUDE_MODEL_OPTIONS = [_CLAUDE_MODEL_PRIMARY] + [m for m in _CLAUDE_MODEL_FALLBACKS if m and m != _CLAUDE_MODEL_PRIMARY]

_SYNC_SERVICE_URL = os.getenv('SYNC_SERVICE_URL', 'https://jarvis-sync-service-776871804948.asia-southeast1.run.app')


class Config:
    """Central configuration for the intelligence service."""

    SUPABASE_URL = _SUPABASE_URL
    SUPABASE_KEY = _SUPABASE_KEY

    ANTHROPIC_API_KEY = _ANTHROPIC_API_KEY

    CLAUDE_MODEL_PRIMARY = _CLAUDE_MODEL_PRIMARY
    CLAUDE_MODEL_FALLBACKS = _CLAUDE_MODEL_FALLBACKS
    CLAUDE_MODEL = _CLAUDE_MODEL_PRIMARY
    CLAUDE_MODEL_OPTIONS = _CLAUDE_MODEL_OPTIONS

    SYNC_SERVICE_URL = _SYNC_SERVICE_URL


settings = Config()
