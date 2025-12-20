# 🧠 Jarvis Intelligence Service

> **THE CORE of the Jarvis ecosystem.** This is where ALL AI processing and business logic lives. All other services call this one.

## 🎯 Role in the Ecosystem

This service is the **single source of intelligence**. Other services are specialized:
- **Audio Pipeline** → Transcribes audio, then **calls this service** for analysis
- **Telegram Bot** → Receives user input, then **calls this service** for AI responses
- **Sync Service** → Pure sync, does NOT call this service

**Why centralized?** One place to maintain AI logic, prompts, and business rules. Easy to upgrade, easy to debug.

## 🌟 Features

*   **Smart Reflection Appending**: Automatically detects if a new reflection belongs to an existing topic (e.g., "Project Jarvis") and appends to it instead of creating a duplicate.
*   **Transcript Analysis**: Extracts meetings, reflections, and tasks from voice notes.
*   **Journal Processing**: Analyzes daily journals and creates tasks from `tomorrow_focus`.
*   **Chat Interface**: AI-powered chat with context (used by Telegram Bot).
*   **Task Extraction**: Automatically creates tasks from any analyzed content.
*   **Structured Output**: Converts unstructured text into database rows.

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

## 🔌 API Endpoints

### `POST /api/v1/process/{transcript_id}`
Analyzes a transcript and extracts structured data.

### `POST /api/v1/process-journal/{journal_id}`
Processes a journal entry and creates tasks from tomorrow_focus.

### `POST /api/v1/chat`
AI chat endpoint with Supabase context (used by Telegram Bot).

### `GET /health`
Health check endpoint.

### `GET /`
Returns `{"message": "Jarvis Intelligence Service Running"}`
