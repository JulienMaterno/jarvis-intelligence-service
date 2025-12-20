# 🧠 Jarvis Intelligence Service

> **THE CORE of the Jarvis ecosystem.** This is where ALL AI processing and business logic lives. All other services call this one.

## 🎯 Role in the Ecosystem

This service is the **single source of intelligence**. Other services are specialized:
- **Audio Pipeline** → Transcribes audio, then **calls this service** for analysis
- **Telegram Bot** → Receives user input, then **calls this service** for AI responses
- **Sync Service** → Pure sync, does NOT call this service

**Why centralized?** One place to maintain AI logic, prompts, and business rules. Easy to upgrade, easy to debug.

## 🌟 Features

*   **Comprehensive Data Linking**: Fully interconnected database where contacts, meetings, emails, and calendar events link together automatically
*   **Email-Based Matching**: Automatic contact linking via email addresses for reliable connections
*   **Unified Interaction Timeline**: Query any contact and see all meetings, emails, and calendar events in one view
*   **Smart Reflection Appending**: Automatically detects if a new reflection belongs to an existing topic (e.g., "Project Jarvis") and appends to it instead of creating a duplicate.
*   **Transcript Analysis**: Extracts meetings, reflections, and tasks from voice notes.
*   **Journal Processing**: Analyzes daily journals and creates tasks from `tomorrow_focus`.
*   **Chat Interface**: AI-powered chat with context (used by Telegram Bot).
*   **Task Extraction**: Automatically creates tasks from any analyzed content.
*   **Structured Output**: Converts unstructured text into database rows.
*   **CRM Integration**: Contact management with automatic linking to all interactions

## 🧠 AI Models

*   **Primary Model**: `claude-sonnet-4-5-20250929` (Anthropic)
*   **Usage**: All complex reasoning, summarization, and extraction tasks.

## 🚀 Setup & Deployment

### 1. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py
```

**Environment Variables (.env):**
```ini
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_KEY=eyJ...
TELEGRAM_BOT_TOKEN=...  # For sending notifications
```

### 2. Deployment (CI/CD)

This service is automatically deployed to **Google Cloud Run** via **Google Cloud Build** whenever code is pushed to the `master` branch.

*   **Trigger**: Push to `master`
*   **Build Config**: `cloudbuild.yaml`
*   **Secrets**: Managed via Google Secret Manager (`SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`)

## 📚 Documentation

**Understanding the Architecture**:
- **[Data Linking Architecture](./docs/DATA_LINKING_ARCHITECTURE.md)** - Comprehensive guide to the interconnected data model, contact linking, and interaction tracking
- **[Cloud Architecture Guide](./docs/CLOUD_ARCHITECTURE.md)** - How Google Cloud Build and Cloud Run work for this service
- **[Ecosystem Architecture](./docs/ECOSYSTEM_ARCHITECTURE.md)** - Complete overview of all 4 Jarvis services and how they interact

## 🔌 API Endpoints

### Analysis & Processing

### `POST /api/v1/process/{transcript_id}`
Analyzes a transcript and extracts structured data.

### `POST /api/v1/process-journal/{journal_id}`
Processes a journal entry and creates tasks from tomorrow_focus.

### `POST /api/v1/chat`
AI chat endpoint with Supabase context (used by Telegram Bot).

### Contact Management

### `POST /api/v1/contacts`
Create a new contact in the CRM.

### `GET /api/v1/contacts/search?q={query}`
Search for contacts by name.

### `PATCH /api/v1/meetings/{meeting_id}/link-contact`
Link a contact to an existing meeting.

### `GET /api/v1/contacts/{contact_id}/interactions`
Get all interactions (meetings, emails, calendar events) for a contact.

### `GET /api/v1/contacts/{contact_id}/summary`
Get comprehensive summary with stats and upcoming events.

### Email Operations

### `POST /api/v1/emails`
Create email record with automatic contact linking.

### `PATCH /api/v1/emails/{email_id}/link`
Link email to meeting or contact.

### `GET /api/v1/emails/thread/{thread_id}`
Get all emails in a conversation thread.

### Calendar Events

### `POST /api/v1/calendar-events`
Create calendar event with automatic contact linking.

### `PATCH /api/v1/calendar-events/{event_id}/link`
Link calendar event to meeting or contact.

### `GET /api/v1/calendar-events/upcoming`
Get upcoming calendar events.

### System

### `GET /health`
Health check endpoint.

### `GET /`
Returns `{"message": "Jarvis Intelligence Service Running"}`
