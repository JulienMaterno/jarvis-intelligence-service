# 🤖 Intelligence Service - LLM Integration Guide

> **For AI Agents / Coding Assistants**: This document explains how to interact with the Intelligence Service.

## ⚠️ CRITICAL: This is THE BRAIN

**ALL AI/LLM logic in the Jarvis ecosystem lives HERE and ONLY here.**

- ✅ Add AI features here
- ✅ Modify prompts here
- ✅ Add new analysis capabilities here
- ❌ DO NOT add AI/LLM calls in other services (Audio Pipeline, Telegram Bot, Sync Service)

---

## 🏗️ Architecture

```
jarvis-intelligence-service/
├── app/
│   ├── api/
│   │   ├── endpoints.py       # Main router
│   │   ├── models.py          # Pydantic models
│   │   └── routes/
│   │       ├── transcripts.py # /process/{id}, /analyze
│   │       ├── journaling.py  # /journal/evening-prompt
│   │       ├── contacts.py    # Contact CRUD + linking
│   │       ├── emails.py      # Email processing
│   │       └── calendar.py    # Calendar integration
│   │
│   ├── services/
│   │   ├── llm.py             # ClaudeMultiAnalyzer - MAIN AI LOGIC
│   │   ├── database.py        # SupabaseMultiDatabase
│   │   └── sync_trigger.py    # Triggers jarvis-sync-service
│   │
│   ├── features/              # ⭐ NEW MODULAR STRUCTURE
│   │   ├── analysis/
│   │   │   └── prompts.py     # Centralized LLM prompts
│   │   └── telegram/
│   │       └── notifications.py
│   │
│   └── shared/
│       └── constants.py       # Service URLs, language settings
│
└── main.py                    # FastAPI entry point
```

---

## 🔌 Primary Integration Points

### 1. For Audio Pipeline: `/api/v1/process/{transcript_id}`

This is how the Audio Pipeline sends transcripts for analysis:

```python
import httpx

async def analyze_transcript(transcript_id: str):
    """Send transcript to Intelligence Service for analysis."""
    
    url = f"{INTELLIGENCE_SERVICE_URL}/api/v1/process/{transcript_id}"
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url)
        return response.json()
```

**Response Format:**
```json
{
  "status": "success",
  "analysis": {
    "primary_category": "meeting|journal|reflection|task_planning|other",
    "meetings": [...],
    "journals": [...],
    "reflections": [...],
    "tasks": [...],
    "crm_updates": [...]
  },
  "db_records": {
    "transcript_id": "uuid",
    "meeting_ids": ["uuid"],
    "journal_ids": [],
    "reflection_ids": ["uuid"],
    "task_ids": ["uuid", "uuid"],
    "contact_matches": [
      {
        "searched_name": "John",
        "matched": false,
        "meeting_id": "uuid",
        "suggestions": [...]
      }
    ]
  }
}
```

### 2. For Telegram Bot: Contact Linking

```python
# Search contacts
GET /api/v1/contacts/search?q=John%20Smith&limit=5

# Link meeting to contact
PATCH /api/v1/meetings/{meeting_id}/link-contact
{"contact_id": "uuid"}

# Create new contact
POST /api/v1/contacts
{"first_name": "John", "last_name": "Smith"}
```

### 3. For Sync Service: Triggered Automatically

After creating records, the Intelligence Service triggers sync automatically:

```python
# In transcripts.py
background_tasks.add_task(trigger_syncs_for_records, db_records)
```

---

## 📊 Database Tables

### Core Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `transcripts` | Raw transcription text | `full_text`, `source_file`, `language` |
| `meetings` | Meeting records | `title`, `summary`, `contact_id`, `topics_discussed` |
| `journals` | Daily journal entries | `date`, `content`, `mood`, `sections` |
| `reflections` | Topic-based reflections | `title`, `topic_key`, `content`, `tags` |
| `tasks` | Action items | `title`, `status`, `origin_id`, `origin_type` |
| `contacts` | CRM contacts | `first_name`, `last_name`, `email`, `company` |

### Linking Fields

- `meetings.contact_id` → `contacts.id`
- `tasks.origin_id` → `meetings.id` OR `journals.id` OR `reflections.id`
- `meetings.source_transcript_id` → `transcripts.id`
- `reflections.source_transcript_id` → `transcripts.id`

---

## 🧠 LLM Configuration

### Model Selection

```python
# In app/services/llm.py
PRIMARY_MODEL = "claude-sonnet-4-5-20250929"
FALLBACK_MODEL = "claude-haiku-4-5-20251001"
```

### Prompt Location

**All prompts are centralized in:**
```
app/features/analysis/prompts.py
```

### Key Prompt Behaviors

1. **Language**: ALL output is in **English** regardless of input language
2. **Journal Detection**: Detects "today", "journal", "this morning", "tonight" etc.
3. **Filename Override**: If filename contains "Journal", force journal category
4. **Task Extraction**: Only TRUE action items (not passive events)
5. **CRM Updates**: Only for the person MET WITH, not everyone mentioned
6. **Reflection Routing**: Uses `topic_key` to append to existing topics

---

## 🔄 Data Flow

### Transcript Processing

```
1. Audio Pipeline saves transcript to Supabase
         │
         ▼
2. POST /api/v1/process/{transcript_id}
         │
         ├── Fetch transcript from DB
         │
         ├── Get existing reflection topics (for smart routing)
         │
         ├── Send to Claude AI (ClaudeMultiAnalyzer)
         │         │
         │         └── Returns structured JSON:
         │             - primary_category
         │             - meetings[]
         │             - journals[]
         │             - reflections[]
         │             - tasks[]
         │             - crm_updates[]
         │
         ├── Create records in Supabase:
         │     - Journals (with tasks from tomorrow_focus)
         │     - Meetings (with contact matching)
         │     - Reflections (append if topic_key exists)
         │     - Tasks (linked to origin)
         │
         ├── Trigger sync service (background)
         │
         └── Send Telegram notification (background)
```

### Reflection Appending Logic

```python
# Smart topic routing in transcripts.py
if topic_key:
    existing = db.find_similar_reflection(topic_key, tags, title)
    
    if existing:
        db.append_to_reflection(existing["id"], new_sections, ...)
    else:
        db.create_reflection(reflection_data, ...)
```

---

## 🚨 Error Handling

### Claude API Failures

The analyzer has automatic fallback:
1. Try PRIMARY_MODEL
2. If fails (rate limit, timeout), try FALLBACK_MODEL
3. If both fail, raise exception with details

### Database Failures

All database operations are wrapped in try/except with logging.
Failed operations don't crash the entire request - partial results may be returned.

---

## 🛠️ Adding New Features

### 1. Adding a New Analysis Type

```python
# 1. Update the prompt in app/features/analysis/prompts.py
# Add new output format in the JSON structure

# 2. Update models in app/api/models.py
class AnalysisResponse(BaseModel):
    new_field: List[NewType] = []

# 3. Handle in transcripts.py
for new_item in analysis.get("new_items", []):
    db.create_new_item(new_item)
```

### 2. Adding a New Notification

```python
# Add to app/features/telegram/notifications.py
def build_new_notification_message(data: dict) -> str:
    return f"🆕 New thing happened: {data['title']}"
```

### 3. Adding a New Endpoint

```python
# Create app/api/routes/new_feature.py
from fastapi import APIRouter

router = APIRouter(tags=["NewFeature"])

@router.post("/new-endpoint")
async def new_endpoint():
    ...

# Register in app/api/endpoints.py
from app.api.routes import new_feature
api_router.include_router(new_feature.router)
```

---

## ⚠️ Common Pitfalls

### 1. Journal vs Reflection Confusion

**Problem**: Transcript says "This is a journal entry for today" but creates a reflection instead.

**Solution**: The prompt now has explicit rules:
- Filename contains "Journal" → FORCE journal
- Keywords: "today", "tonight", "this morning" → journal
- Daily recap with events → journal (even if reflective)

### 2. Tasks Not Created

**Problem**: Transcript mentions "I need to do X" but no tasks created.

**Solution**: New prompt has aggressive task extraction:
- "I need to...", "Gotta do...", "Must remember to..."
- "Should probably...", "Need to figure out..."
- Creates tasks even from journals and reflections

### 3. German Transcripts Staying in German

**Problem**: Output is in German when input is German.

**Solution**: Prompt explicitly states:
```
OUTPUT LANGUAGE: English
ALL your output MUST be in ENGLISH, regardless of input language.
```

---

## 📡 External Service URLs

Defined in `app/shared/constants.py`:

```python
TELEGRAM_BOT_URL = os.getenv("TELEGRAM_BOT_URL", "https://jarvis-telegram-bot-...")
SYNC_SERVICE_URL = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-...")
AUDIO_PIPELINE_URL = os.getenv("AUDIO_PIPELINE_URL", "https://jarvis-audio-pipeline-...")
```

---

## 🚫 DO NOT MODIFY

1. **Database schema** without migrations
2. **Model names** without verifying availability (`anthropic.models.list()`)
3. **Supabase client initialization** in `app/core/database.py`

---

## ✅ Safe to Modify

- Prompts in `app/features/analysis/prompts.py`
- Notification messages in `app/features/telegram/notifications.py`
- Task extraction rules
- Log messages and error handling

---

## 🔗 Related Services

| Service | Role | This Service Interacts |
|---------|------|------------------------|
| **jarvis-audio-pipeline** | Transcription | Receives POST /api/v1/process/{id} |
| **jarvis-telegram-bot** | User interface | Sends notifications, handles contacts |
| **jarvis-sync-service** | Data sync | Receives sync triggers |
| **Supabase** | Database | Direct client connection |

---

## 📝 Debugging Tips

### Check Claude Response

```python
# Add to llm.py temporarily
logger.info("Claude raw response: %s", result_text[:500])
```

### Check Created Records

```sql
-- Recent meetings
SELECT * FROM meetings ORDER BY created_at DESC LIMIT 5;

-- Recent journals
SELECT * FROM journals ORDER BY created_at DESC LIMIT 5;

-- Recent tasks
SELECT * FROM tasks ORDER BY created_at DESC LIMIT 5;

-- Tasks linked to journals
SELECT t.*, j.title as journal_title 
FROM tasks t 
JOIN journals j ON t.origin_id = j.id 
WHERE t.origin_type = 'journal';
```

### Cloud Run Logs

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=jarvis-intelligence-service" --limit=50
```
