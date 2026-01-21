# 🧠 Jarvis Intelligence Service

> **THE BRAIN** - All AI processing happens here. One piece of the [Jarvis Ecosystem](https://github.com/JulienMaterno/jarvis-ecosystem).

---

**📚 New here?** Start with the [Jarvis Ecosystem Overview](https://github.com/JulienMaterno/jarvis-ecosystem) to understand how all 7 microservices work together. This README focuses on the **Intelligence Service** specifically.

---

## 🎯 This Service's Role

The Intelligence Service is the **single source of intelligence** in the Jarvis ecosystem. Think of it as the conductor of an orchestra:

| Other Service | What It Does | How Intelligence Service Fits In |
|---------------|--------------|----------------------------------|
| 🎤 **Audio Pipeline** | Transcribes voice memos | Receives transcripts → analyzes with Claude → extracts meetings/tasks/reflections |
| 📱 **Telegram Bot** | User interface (voice, text) | Receives user messages → processes with 40+ tools → sends responses |
| 🔄 **Sync Service** | Syncs data across platforms | Pure sync logic, no AI. Intelligence Service owns all business logic. |
| 💬 **Beeper Bridge** | Unified messaging gateway | Intelligence Service orchestrates: "send John a WhatsApp message" |
| 📹 **Screenpipe Bridge** | Auto-captures meetings | Sends meeting audio → Intelligence Service analyzes and structures |

**Why centralized AI?**
- ✅ Upgrade Claude Sonnet 4 → Sonnet 5 in ONE place
- ✅ Shared prompt caching across all features (90% cost savings)
- ✅ Single codebase for all AI behavior (easy to debug)
- ✅ Swap Claude for GPT-4o/Gemini without touching other services

This is the **only** service that calls the Anthropic API. Everything else is "dumb" infrastructure.

## 🌟 Features

### Core Capabilities
- **Multi-Output Analysis**: Extract meetings, journals, reflections, and tasks from a single transcript
- **Smart Reflection Routing**: Automatically appends to existing topics via `topic_key` matching
- **Language Translation**: Transcripts in German/Turkish → English output
- **Contact Linking**: Auto-matches mentioned people to CRM contacts
- **Telegram Notifications**: Sends processing results to user

### Conversational AI (Chat)
- **Natural Language Interface**: Ask questions, create records, search data
- **40+ Built-in Tools**: Database queries, task management, calendar, messaging
- **Prompt Caching**: 90% cost savings on repeated web chat requests
- **Memory System**: Mem0 integration for long-term context
- **Behavior Learning**: `remember_behavior` tool to teach new patterns

### Research Tools (Paid APIs)
- **LinkedIn Research**: Profile lookup, people search, company info (Bright Data)
- **Web Search**: General and news search (Brave Search API)
- **Batch Support**: Process multiple LinkedIn URLs efficiently

### Productivity Features
- **Evening Journal Prompts**: Personalized prompts with ActivityWatch data
- **Meeting Briefings**: Auto-generates context before meetings
- **Task Extraction**: Creates actionable tasks from any analyzed content
- **Email Drafts**: Create, list, send Gmail drafts
- **Calendar Management**: Create, update, reschedule events

### Messaging Integration
- **Unified Inbox**: WhatsApp, LinkedIn, Telegram, Slack via Beeper
- **Send Messages**: With user confirmation workflow
- **Chat History**: Search and retrieve message history

## 🧠 AI Models

| Purpose | Model | Cost/1M Tokens |
|---------|-------|----------------|
| **Chat (Haiku)** | `claude-haiku-4-5-20251001` | $0.80 in / $4.00 out |
| **Analysis (Sonnet)** | `claude-sonnet-4-5-20250929` | $3.00 in / $15.00 out |

### Prompt Caching (Web Chat)
- **First message**: Writes ~19K tokens to cache (25% premium)
- **Follow-up messages**: Reads from cache at **90% discount**
- **Cache TTL**: 5 minutes (ephemeral)

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
│   │       ├── chat.py        # /chat, /chat/completions (OpenAI-compatible)
│   │       ├── journaling.py  # /journal/evening-prompt
│   │       ├── contacts.py    # Contact CRUD + linking
│   │       ├── emails.py      # Email processing
│   │       ├── calendar.py    # Calendar integration
│   │       ├── briefing.py    # Meeting briefings
│   │       └── health.py      # Health check endpoints
│   │
│   ├── services/
│   │   ├── llm.py             # ClaudeMultiAnalyzer
│   │   ├── database.py        # SupabaseMultiDatabase
│   │   └── sync_trigger.py    # Triggers sync service
│   │
│   ├── features/
│   │   ├── analysis/
│   │   │   └── prompts.py     # Centralized LLM prompts
│   │   ├── briefing/
│   │   │   └── meeting_briefing.py
│   │   ├── chat/
│   │   │   ├── service.py     # ChatService with streaming
│   │   │   ├── tools.py       # 40+ tool implementations
│   │   │   └── storage.py     # Chat history persistence
│   │   ├── memory/
│   │   │   └── service.py     # Mem0 integration
│   │   ├── research/
│   │   │   ├── service.py     # Unified research service
│   │   │   ├── tools.py       # LinkedIn + web search tools
│   │   │   └── providers/     # LinkedIn (Bright Data), Web (Brave)
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
# Required
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_KEY=eyJ...
TELEGRAM_BOT_URL=https://jarvis-telegram-bot-...
SYNC_SERVICE_URL=https://jarvis-sync-service-...
DEFAULT_TELEGRAM_CHAT_ID=123456789

# Optional - Research Tools
BRIGHTDATA_API_KEY=...        # LinkedIn research (Bright Data)
BRAVE_API_KEY=...             # Web search (Brave Search API)
BEEPER_BRIDGE_URL=https://... # Beeper messaging bridge

# Optional - Memory
MEM0_API_KEY=...              # Mem0 cloud (or use local pgvector)
```

### Deployment (Automated via GitHub)

**DO NOT** manually deploy. Push to `master` branch triggers Google Cloud Build automatically.

- **Cloud Build Trigger**: `jarvis-intelligence-service-deploy`
- **Branch**: `^master$`
- **Region**: `asia-southeast1`
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

### Briefings

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/briefings/check` | POST | Check upcoming meetings and generate briefings |
| `/api/v1/briefings/event/{event_id}` | POST | Generate briefing for specific calendar event |
| `/api/v1/briefings/schedule-hourly` | POST | Scan and schedule briefings (Cloud Scheduler) |
| `/api/v1/briefings/send-due` | POST | Send due briefings (runs every minute) |

### Chat & Messaging

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat` | POST | Send chat message (non-streaming) |
| `/api/v1/chat/stream` | POST | Send chat message (streaming SSE) |
| `/api/v1/chat/usage` | GET | Get chat usage statistics |
| `/api/v1/chat/conversations` | GET | List all conversations |
| `/api/v1/chat/conversations/{id}` | GET | Get conversation history |
| `/api/v1/chat/conversations` | DELETE | Clear all conversations |
| `/api/v1/chat/conversations/{id}` | DELETE | Delete specific conversation |

### Research Tools (via Chat)

Available as Claude tools during chat conversations:
- `search_web` - Search the web via Brave Search API
- `get_linkedin_person_profile` - Full LinkedIn profile lookup
- `get_linkedin_company_profile` - Company information
- `search_linkedin_people` - Find people by criteria
- `get_recent_linkedin_posts` - Get recent posts by LinkedIn URL

### Beeper (Unified Messaging)

The service includes tools for sending/receiving messages via Beeper Bridge:
- `get_beeper_inbox` - List chats needing response
- `search_beeper_chats` - Find chats by name
- `send_beeper_message` - Send message (requires user confirmation)
- `archive_beeper_chat` - Archive handled chats

### Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | Service status |

## 🔗 Related Services

| Service | Communication |
|---------|---------------|
| **jarvis-audio-pipeline** | Sends transcripts via POST /api/v1/process/{id} |
| **jarvis-telegram-bot** | Receives notifications, handles contact linking, chat interface |
| **jarvis-sync-service** | Receives sync triggers after record creation |
| **jarvis-beeper-bridge** | Unified messaging (WhatsApp, LinkedIn, Slack, etc.) |
| **jarvis-screenpipe-bridge** | Sends meeting transcripts for analysis |
| **Supabase** | Direct database connection |

## 📝 For AI Agents

See **[AGENTS.md](./AGENTS.md)** for detailed integration guide including:
- API request/response formats
- Database schema
- Prompt configuration
- Error handling
- Debugging tips