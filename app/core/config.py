import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Central configuration for the intelligence service."""
    
    # =========================================================================
    # SUPABASE (Primary Data Store)
    # =========================================================================
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # =========================================================================
    # CLAUDE API
    # =========================================================================
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
    CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-3-5-haiku-20241022')

settings = Config()
            ('SUPABASE_KEY', cls.SUPABASE_KEY),
            ('ANTHROPIC_API_KEY', cls.ANTHROPIC_API_KEY),
        ]
        
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
