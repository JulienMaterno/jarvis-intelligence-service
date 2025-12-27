# 🧠 Jarvis Intelligence Service

> **THE BRAIN of the Jarvis ecosystem.** ALL AI processing and business logic lives here exclusively.

## 🎯 Role in the Ecosystem

This service is the **single source of intelligence**. Other services are specialized:
- **Audio Pipeline** → Transcribes audio, then **calls this service** for analysis
- **Telegram Bot** → Receives user input, forwards voice memos, receives notifications
- **Sync Service** → Pure sync between Supabase, Notion, and Google

**Why centralized?** One place to maintain AI logic, prompts, and business rules. Easy to upgrade, easy to debug.

## 🌟 Features

- **Multi-Output Analysis**: Extract meetings, journals, reflections, and tasks from a single transcript
- **Smart Reflection Routing**: Automatically appends to existing topics via `topic_key` matching
- **Language Translation**: Transcripts in German/Turkish → English output
- **Contact Linking**: Auto-matches mentioned people to CRM contacts
- **Telegram Notifications**: Sends processing results to user
- **Evening Journal Prompts**: Generates personalized prompts with day context
- **Task Extraction**: Creates actionable tasks from any analyzed content

## 🧠 AI Models

- **Primary**: `claude-sonnet-4-5-20250929` (Anthropic)
- **Fallback**: `claude-3-5-haiku-20241022`

## 📁 Project Structure

```
jarvis-intelligence-service/
├── main.py                    # FastAPI entry point
├── app/
│   ├── api/
│   │   ├── endpoints.py       # Main router
│   │   ├── models.py          # Pydantic models
│   │   └── routes/
│   │       ├── transcripts.py # /process, /analyze
│   │       ├── journaling.py  # /journal/evening-prompt
│   │       ├── contacts.py    # Contact CRUD + linking
│   │       ├── emails.py      # Email processing
│   │       └── calendar.py    # Calendar integration
│   │
│   ├── services/
│   │   ├── llm.py             # ClaudeMultiAnalyzer
│   │   ├── database.py        # SupabaseMultiDatabase
│   │   └── sync_trigger.py    # Triggers sync service
│   │
│   ├── features/              # Modular feature modules
│   │   ├── analysis/
│   │   │   └── prompts.py     # Centralized LLM prompts
│   │   └── telegram/
│   │       └── notifications.py
│   │
│   └── shared/
│       └── constants.py       # Service URLs, config
│
└── migrations/                # SQL migrations
```

## 🚀 Setup & Deployment

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env

# Run locally
uvicorn main:app --reload --port 8000
```

**Environment Variables:**
```ini
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_KEY=eyJ...
TELEGRAM_BOT_URL=https://jarvis-telegram-bot-...
SYNC_SERVICE_URL=https://jarvis-sync-service-...
DEFAULT_TELEGRAM_CHAT_ID=123456789
```

### Deployment (Automated via GitHub)

**DO NOT** manually deploy. Push to `master` branch triggers Google Cloud Build automatically.

- **Cloud Build Trigger**: `jarvis-intelligence-service-deploy`
- **Branch**: `^master$`
- **Build Config**: `cloudbuild.yaml`
- **Secrets**: Google Secret Manager (injected at runtime)

```bash
# Deploy by pushing to master
git add -A && git commit -m "Your changes" && git push origin master
```

## 📚 Documentation

- **[AGENTS.md](./AGENTS.md)** - LLM/AI agent integration guide
- **[Data Linking Architecture](./docs/DATA_LINKING_ARCHITECTURE.md)** - Database relationships
- **[Cloud Architecture](./docs/CLOUD_ARCHITECTURE.md)** - Deployment details
- **[Ecosystem Architecture](./docs/ECOSYSTEM_ARCHITECTURE.md)** - All services overview

## 📚 Documentation

**Understanding the Architecture**:
- **[Cloud Architecture Guide](./docs/CLOUD_ARCHITECTURE.md)** - How Google Cloud Build and Cloud Run work for this service
- **[Ecosystem Architecture](./docs/ECOSYSTEM_ARCHITECTURE.md)** - Complete overview of all 4 Jarvis services and how they interact

## 🔌 API Endpoints

### Transcript Processing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/process/{transcript_id}` | POST | Analyze existing transcript |
| `/api/v1/analyze` | POST | Analyze raw transcript text |

### Journaling

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/journal/evening-prompt` | POST | Generate evening reflection prompt (includes ActivityWatch data if available) |

### Contacts

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/contacts/search` | GET | Search contacts by name |
| `/api/v1/contacts` | POST | Create new contact |
| `/api/v1/contacts/{id}` | GET | Get contact details |
| `/api/v1/contacts/{id}/interactions` | GET | Get all interactions |
| `/api/v1/meetings/{id}/link-contact` | PATCH | Link meeting to contact |

### Email & Calendar

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/emails` | POST | Create email record |
| `/api/v1/calendar-events` | POST | Create calendar event |
| `/api/v1/calendar-events/upcoming` | GET | Get upcoming events |

### Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | Service status |

## 🔗 Related Services

| Service | Communication |
|---------|---------------|
| **jarvis-audio-pipeline** | Sends transcripts via POST /api/v1/process/{id} |
| **jarvis-telegram-bot** | Receives notifications, handles contact linking |
| **jarvis-sync-service** | Receives sync triggers after record creation |
| **Supabase** | Direct database connection |

## 📝 For AI Agents

See **[AGENTS.md](./AGENTS.md)** for detailed integration guide including:
- API request/response formats
- Database schema
- Prompt configuration
- Error handling
- Debugging tips