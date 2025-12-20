# 🌐 Jarvis Ecosystem Architecture

## Overview

Jarvis is a **distributed AI-powered productivity system** composed of **4 microservices** that work together to process voice notes, analyze content, extract insights, and sync everything to Notion. This document explains the complete ecosystem and how all services interact.

---

## The 4 Services

### 1. 🧠 **Intelligence Service** (THIS REPO)
**Repository**: `jarvis-intelligence-service`  
**Technology**: Python + FastAPI  
**Deployment**: Google Cloud Run  
**Purpose**: The CORE AI brain - all analysis happens here

**Responsibilities**:
- Receives transcripts from Audio Pipeline
- Analyzes content using Claude AI (Anthropic)
- Extracts structured data: meetings, reflections, journals, tasks
- Saves everything to Supabase database
- Provides chat interface for Telegram Bot
- Manages CRM (contacts) information

**Endpoints**:
- `POST /api/v1/analyze` - Analyze transcript and save to DB
- `POST /api/v1/process/{transcript_id}` - Process existing transcript
- `POST /api/v1/chat` - AI chat with context
- `GET /health` - Health check

---

### 2. 🎙️ **Audio Pipeline Service**
**Repository**: `jarvis-audio-pipeline`  
**Technology**: Python + Whisper/Deepgram (speech-to-text)  
**Purpose**: Transcribes audio files to text

**Flow**:
```
1. User uploads audio file (MP3, M4A, WAV)
2. Audio Pipeline transcribes using Whisper/Deepgram
3. Sends transcript to Intelligence Service
4. Intelligence Service analyzes and saves to DB
5. Sync Service pushes to Notion
```

**Responsibilities**:
- Monitor audio uploads (from Google Drive, Dropbox, local folder)
- Transcribe audio to text
- Call Intelligence Service with transcript
- Handle transcription errors and retries

**Key Integration**:
```python
# Audio Pipeline calls Intelligence Service
response = requests.post(
    "https://intelligence-service-url/api/v1/analyze",
    json={
        "filename": "meeting_john_2024.mp3",
        "transcript": "Today I met with John...",
        "audio_duration_seconds": 180,
        "language": "en",
        "recording_date": "2024-12-20"
    }
)
```

---

### 3. 💬 **Telegram Bot Service**
**Repository**: `jarvis-telegram-bot`  
**Technology**: Python + python-telegram-bot  
**Purpose**: User interface for chat and commands

**Capabilities**:
1. **Chat**: Send messages to Jarvis, get AI responses
2. **Voice notes**: Send voice messages, get them transcribed and analyzed
3. **Quick tasks**: Create tasks via chat
4. **Notifications**: Receive alerts about meetings, deadlines

**Flow for Chat**:
```
1. User sends message in Telegram
2. Bot receives message
3. Bot calls Intelligence Service /api/v1/chat
4. Intelligence Service uses Claude with Supabase context
5. Bot sends AI response back to user
```

**Flow for Voice Notes**:
```
1. User sends voice note in Telegram
2. Bot downloads audio file
3. Bot calls Audio Pipeline for transcription
4. Audio Pipeline → Intelligence Service → Supabase
5. Bot notifies user: "Processed! Created 1 meeting, 3 tasks"
```

**Key Integration**:
```python
# Telegram Bot calls Intelligence Service
response = requests.post(
    "https://intelligence-service-url/api/v1/chat",
    json={
        "message": "What meetings do I have this week?",
        "user_id": telegram_user_id
    }
)
```

---

### 4. 🔄 **Sync Service**
**Repository**: `jarvis-sync-service`  
**Technology**: Python + Notion API  
**Purpose**: Pushes data from Supabase to Notion

**What It Syncs**:
- ✅ Tasks → Notion Tasks database
- 📅 Meetings → Notion Meetings database  
- 💭 Reflections → Notion Reflections database
- 📔 Journals → Notion Journals database

**Sync Strategy**:
1. **Triggered Sync**: Intelligence Service calls Sync Service after creating new records
2. **Scheduled Sync**: Cron job runs every 15 minutes to catch any missed items

**Flow**:
```
1. Intelligence Service creates task in Supabase
2. Intelligence Service calls Sync Service: POST /sync/tasks
3. Sync Service queries Supabase for new tasks
4. Sync Service creates/updates Notion pages
5. Sync Service marks records as "synced" in Supabase
```

**Key Integration**:
```python
# Intelligence Service triggers sync
response = requests.post(
    "https://sync-service-url/sync/tasks",
    json={"force": False}
)
```

**Bidirectional Sync** (optional):
- Notion → Supabase for task completion status
- Allows marking tasks done in Notion, syncs back to Supabase

---

## Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUTS                              │
│  • Audio files (Google Drive, local folder)                      │
│  • Telegram messages/voice notes                                 │
└─────────────────┬───────────────────────────┬───────────────────┘
                  │                           │
                  ▼                           ▼
        ┌─────────────────────┐   ┌─────────────────────┐
        │  Audio Pipeline     │   │   Telegram Bot      │
        │  (Transcription)    │   │   (User Interface)  │
        └──────────┬──────────┘   └──────────┬──────────┘
                   │                          │
                   │ POST /api/v1/analyze    │ POST /api/v1/chat
                   │                          │
                   └──────────┬───────────────┘
                              ▼
                ┌─────────────────────────────┐
                │   Intelligence Service      │
                │   (THIS REPO)               │
                │   • Claude AI Analysis      │
                │   • Data Extraction         │
                │   • Database Operations     │
                └──────────┬──────────────────┘
                           │
                           │ Saves to
                           ▼
                ┌─────────────────────────────┐
                │      Supabase Database      │
                │   • Transcripts             │
                │   • Meetings                │
                │   • Reflections             │
                │   • Journals                │
                │   • Tasks                   │
                │   • Contacts (CRM)          │
                └──────────┬──────────────────┘
                           │
                           │ Reads & syncs
                           ▼
                ┌─────────────────────────────┐
                │      Sync Service           │
                │   (Supabase → Notion)       │
                └──────────┬──────────────────┘
                           │
                           │ Creates/updates
                           ▼
                ┌─────────────────────────────┐
                │      Notion Workspace       │
                │   • Tasks database          │
                │   • Meetings database       │
                │   • Reflections database    │
                │   • Journals database       │
                └─────────────────────────────┘
```

---

## Data Flow Examples

### Example 1: Processing a Voice Note

```
Step 1: User records voice note "Today I met with John about the new project"
        ↓
Step 2: Audio Pipeline receives MP3 file
        ↓
Step 3: Audio Pipeline transcribes with Whisper
        → Transcript: "Today I met with John about the new project..."
        ↓
Step 4: Audio Pipeline → Intelligence Service
        POST /api/v1/analyze
        {
          "filename": "voice_20241220.mp3",
          "transcript": "Today I met with John...",
          "audio_duration_seconds": 45
        }
        ↓
Step 5: Intelligence Service analyzes with Claude AI
        → Detects: 1 Meeting with John
        → Extracts: Topics discussed, follow-ups
        → Creates: CRM entry for John
        ↓
Step 6: Intelligence Service saves to Supabase
        → meetings table: New meeting record
        → contacts table: Update/create John's contact
        → transcripts table: Raw transcript
        ↓
Step 7: Intelligence Service triggers Sync Service
        POST /sync/meetings
        ↓
Step 8: Sync Service reads from Supabase
        → Finds new meeting
        → Creates Notion page in Meetings database
        ↓
Step 9: User sees meeting in Notion
```

---

### Example 2: Chatting with Jarvis via Telegram

```
Step 1: User sends Telegram message
        "What did John and I discuss last week?"
        ↓
Step 2: Telegram Bot receives message
        ↓
Step 3: Telegram Bot → Intelligence Service
        POST /api/v1/chat
        {
          "message": "What did John and I discuss last week?",
          "user_id": "telegram_123"
        }
        ↓
Step 4: Intelligence Service queries Supabase
        → Searches meetings with John
        → Finds meeting from last week
        ↓
Step 5: Intelligence Service calls Claude AI
        → Provides meeting context
        → Generates conversational response
        ↓
Step 6: Intelligence Service → Telegram Bot
        {
          "response": "Last Tuesday you met with John to discuss the new biotech project. He mentioned..."
        }
        ↓
Step 7: Telegram Bot sends message to user
```

---

### Example 3: Daily Journal Processing

```
Step 1: User records evening journal
        "Today was productive. Morning: gym, work on Arduino project.
         Afternoon: Meeting with Sarah. Tomorrow: finish documentation."
        ↓
Step 2: Audio Pipeline transcribes
        ↓
Step 3: Intelligence Service analyzes
        → Detects: Journal entry
        → Extracts: 
          - Mood: Good
          - Sports: Gym
          - Key events: Arduino project, meeting with Sarah
          - Tomorrow focus: "finish documentation"
        ↓
Step 4: Intelligence Service saves
        → journals table: Journal entry
        → tasks table: Task "finish documentation" (from tomorrow_focus)
        → meetings table: Meeting with Sarah (if mentioned)
        ↓
Step 5: Sync Service pushes to Notion
        → Journal page created in Journals database
        → Task appears in Tasks database
```

---

## Service Responsibilities Matrix

| Service | AI Analysis | Database Ops | User Interface | External Sync |
|---------|------------|--------------|----------------|---------------|
| **Intelligence** | ✅ YES | ✅ YES | ❌ NO | ❌ NO |
| **Audio Pipeline** | ❌ NO | ❌ NO | ❌ NO | ❌ NO |
| **Telegram Bot** | ❌ NO | ❌ NO | ✅ YES | ❌ NO |
| **Sync Service** | ❌ NO | ✅ Read-only | ❌ NO | ✅ YES |

### Key Principle: **Single Responsibility**

- **Intelligence Service**: The ONLY service that does AI analysis
- **Audio Pipeline**: The ONLY service that does transcription
- **Telegram Bot**: The ONLY service that talks to users
- **Sync Service**: The ONLY service that writes to Notion

This separation ensures:
- Easy debugging (know exactly which service to check)
- Independent scaling (scale transcription separately from AI)
- Clear upgrade paths (upgrade Claude without touching other services)

---

## Database Schema (Supabase)

### Core Tables

#### 1. `transcripts`
Stores raw audio transcripts before analysis.

```sql
transcripts
├── id (uuid)
├── created_at (timestamp)
├── source_file (text) -- Original audio filename
├── full_text (text) -- Raw transcript
├── audio_duration_seconds (int)
├── language (text) -- "en", "de", etc.
└── processed (boolean) -- Has it been analyzed?
```

#### 2. `meetings`
Structured meeting records.

```sql
meetings
├── id (uuid)
├── created_at (timestamp)
├── date (date) -- Meeting date
├── title (text)
├── location (text)
├── contact_id (uuid) -- FK to contacts
├── summary (text)
├── topics_discussed (jsonb) -- Array of {topic, details[]}
├── people_mentioned (text[])
├── follow_up_conversation (jsonb)
├── transcript_id (uuid) -- FK to transcripts
├── notion_page_id (text) -- Synced to Notion
└── notion_synced_at (timestamp)
```

#### 3. `reflections`
Personal thoughts and learnings.

```sql
reflections
├── id (uuid)
├── created_at (timestamp)
├── date (date)
├── title (text)
├── topic_key (text) -- For recurring topics: "project-jarvis"
├── tags (text[])
├── sections (jsonb) -- Array of {heading, content}
├── transcript_id (uuid)
├── notion_page_id (text)
└── notion_synced_at (timestamp)
```

#### 4. `journals`
Daily journal entries.

```sql
journals
├── id (uuid)
├── created_at (timestamp)
├── date (date) -- Journal date
├── summary (text)
├── mood (text) -- "Great", "Good", "Okay", etc.
├── effort (text) -- "High", "Medium", "Low"
├── sports (text[]) -- ["Running", "Gym"]
├── key_events (text[])
├── accomplishments (text[])
├── challenges (text[])
├── gratitude (text[])
├── tomorrow_focus (text[]) -- Becomes tasks
├── sections (jsonb)
├── transcript_id (uuid)
├── notion_page_id (text)
└── notion_synced_at (timestamp)
```

#### 5. `tasks`
Action items extracted from content.

```sql
tasks
├── id (uuid)
├── created_at (timestamp)
├── title (text)
├── description (text)
├── due_date (date)
├── completed (boolean)
├── origin_type (text) -- "meeting", "journal", "reflection"
├── origin_id (uuid) -- ID of parent record
├── notion_page_id (text)
└── notion_synced_at (timestamp)
```

#### 6. `contacts`
CRM for people you meet.

```sql
contacts
├── id (uuid)
├── created_at (timestamp)
├── first_name (text)
├── last_name (text)
├── company (text)
├── position (text)
├── email (text)
├── phone (text)
├── location (text)
├── personal_notes (text) -- Family, hobbies, upcoming events
├── last_met_date (date)
├── deleted_at (timestamp) -- Soft delete
└── notion_page_id (text)
```

---

## API Communication Patterns

### 1. Audio Pipeline → Intelligence Service

```http
POST https://intelligence-service-url/api/v1/analyze
Content-Type: application/json

{
  "filename": "meeting_2024_12_20.mp3",
  "transcript": "Today I met with John Smith...",
  "audio_duration_seconds": 180,
  "language": "en",
  "recording_date": "2024-12-20"
}
```

**Response**:
```json
{
  "status": "success",
  "analysis": {
    "primary_category": "meeting",
    "meetings": [...],
    "tasks": [...],
    "crm_updates": [...]
  },
  "db_records": {
    "transcript_id": "uuid-123",
    "meeting_ids": ["uuid-456"],
    "task_ids": ["uuid-789"],
    "contact_matches": [...]
  }
}
```

---

### 2. Telegram Bot → Intelligence Service (Chat)

```http
POST https://intelligence-service-url/api/v1/chat
Content-Type: application/json

{
  "message": "What meetings do I have this week?",
  "user_id": "telegram_12345"
}
```

**Response**:
```json
{
  "response": "You have 3 meetings this week:\n1. Monday with John...",
  "context_used": ["meetings", "tasks"]
}
```

---

### 3. Intelligence Service → Sync Service

```http
POST https://sync-service-url/sync/meetings
Content-Type: application/json

{
  "force": false
}
```

**Response**:
```json
{
  "status": "success",
  "synced": 5,
  "errors": 0,
  "duration_seconds": 2.3
}
```

---

## Deployment Architecture

### Production Deployment

```
┌────────────────────────────────────────────────────┐
│              Google Cloud Platform                 │
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │  Intelligence Service                    │    │
│  │  • Cloud Run                             │    │
│  │  • asia-southeast1 region                │    │
│  │  • Auto-scaling: 0-10 instances          │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │  Audio Pipeline (if on GCP)              │    │
│  │  • Cloud Run / Compute Engine            │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │  Telegram Bot (if on GCP)                │    │
│  │  • Cloud Run / Compute Engine            │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
│  ┌──────────────────────────────────────────┐    │
│  │  Sync Service (if on GCP)                │    │
│  │  • Cloud Run + Cloud Scheduler           │    │
│  └──────────────────────────────────────────┘    │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│              External Services                     │
│                                                    │
│  ┌──────────────┐  ┌──────────────┐              │
│  │   Supabase   │  │    Notion    │              │
│  │  (Database)  │  │  (Frontend)  │              │
│  └──────────────┘  └──────────────┘              │
│                                                    │
│  ┌──────────────┐  ┌──────────────┐              │
│  │  Anthropic   │  │   Telegram   │              │
│  │   (Claude)   │  │     Bot      │              │
│  └──────────────┘  └──────────────┘              │
└────────────────────────────────────────────────────┘
```

---

## Environment Variables

Each service needs specific environment variables:

### Intelligence Service
```bash
ANTHROPIC_API_KEY=sk-ant-...      # Claude AI API key
SUPABASE_URL=https://...          # Supabase project URL
SUPABASE_KEY=eyJ...               # Supabase API key
SYNC_SERVICE_URL=https://...      # Sync Service endpoint (optional)
```

### Audio Pipeline
```bash
INTELLIGENCE_SERVICE_URL=https://...  # Intelligence Service endpoint
WHISPER_MODEL=large-v2                # Whisper model size
AUDIO_SOURCE=google_drive             # Where to monitor for audio
GOOGLE_DRIVE_FOLDER_ID=...            # Google Drive folder
```

### Telegram Bot
```bash
TELEGRAM_BOT_TOKEN=...                # Bot token from @BotFather
INTELLIGENCE_SERVICE_URL=https://...  # Intelligence Service endpoint
AUDIO_PIPELINE_URL=https://...        # Audio Pipeline endpoint (for voice notes)
```

### Sync Service
```bash
SUPABASE_URL=https://...          # Supabase project URL
SUPABASE_KEY=eyJ...               # Supabase API key
NOTION_API_KEY=secret_...         # Notion integration token
NOTION_TASKS_DATABASE_ID=...      # Notion database IDs
NOTION_MEETINGS_DATABASE_ID=...
NOTION_REFLECTIONS_DATABASE_ID=...
```

---

## Scaling Considerations

### When to Scale Each Service

1. **Intelligence Service**: 
   - Scale when: Many simultaneous analysis requests
   - Bottleneck: Claude API rate limits
   - Solution: Increase Cloud Run max instances, implement queueing

2. **Audio Pipeline**:
   - Scale when: Large backlog of audio files
   - Bottleneck: Transcription compute time
   - Solution: Parallel processing, multiple instances

3. **Telegram Bot**:
   - Scale when: Many users chatting simultaneously
   - Bottleneck: Usually not an issue (lightweight)
   - Solution: Standard Cloud Run auto-scaling

4. **Sync Service**:
   - Scale when: Large number of records to sync
   - Bottleneck: Notion API rate limits (3 requests/second)
   - Solution: Batch processing, respect rate limits

---

## Security & Access Control

### API Authentication

Currently, services use **direct HTTP calls** without authentication. For production:

1. **Use API Keys**: Each service has a secret API key
2. **Use Cloud IAM**: GCP services authenticate via service accounts
3. **Use VPC**: Keep services on private network

Example with API key:
```python
headers = {
    "Authorization": f"Bearer {INTELLIGENCE_SERVICE_API_KEY}"
}
response = requests.post(url, headers=headers, json=data)
```

### Supabase Row-Level Security (RLS)

Enable RLS to restrict data access:
```sql
-- Only allow service role to write
CREATE POLICY "Service writes only"
ON meetings FOR INSERT
TO service_role
USING (true);

-- Allow authenticated reads
CREATE POLICY "Authenticated reads"
ON meetings FOR SELECT
TO authenticated
USING (true);
```

---

## Monitoring & Observability

### Logging Strategy

Each service logs to stdout, which is captured by the platform:

```python
import logging
logger = logging.getLogger('ServiceName')

logger.info(f"Processing transcript {transcript_id}")
logger.error(f"Failed to analyze: {error}")
```

### Key Metrics to Track

1. **Intelligence Service**:
   - Requests per minute
   - Claude API latency
   - Error rate (failed analyses)
   - Database write latency

2. **Audio Pipeline**:
   - Transcriptions per hour
   - Transcription accuracy
   - Queue depth (pending files)

3. **Telegram Bot**:
   - Messages per hour
   - Response latency
   - User engagement

4. **Sync Service**:
   - Sync success rate
   - Records synced per run
   - Notion API errors

### Alerting

Set up alerts for:
- High error rates (> 5% for 5 minutes)
- Service downtime
- Database connection failures
- API quota exhaustion

---

## Cost Breakdown

Estimated monthly costs (low usage):

| Service | Platform | Cost |
|---------|----------|------|
| Intelligence Service | GCP Cloud Run | $0-5 (within free tier) |
| Audio Pipeline | GCP Cloud Run | $5-20 (compute-heavy) |
| Telegram Bot | GCP Cloud Run | $0-2 (within free tier) |
| Sync Service | GCP Cloud Run | $0-2 (within free tier) |
| Supabase | Supabase Free | $0 (500MB DB) |
| Notion | Notion Free/Personal | $0-$8 |
| Claude API | Anthropic | $10-50 (usage-based) |
| **Total** | | **~$15-85/month** |

---

## Development Workflow

### Local Development

Each service can run independently:

```bash
# Intelligence Service
cd jarvis-intelligence-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py

# Audio Pipeline
cd jarvis-audio-pipeline
pip install -r requirements.txt
python main.py

# Telegram Bot
cd jarvis-telegram-bot
pip install -r requirements.txt
python bot.py

# Sync Service
cd jarvis-sync-service
pip install -r requirements.txt
python main.py
```

### Testing Service Integration

Use `ngrok` or `localtunnel` to expose local services:

```bash
# Terminal 1: Run Intelligence Service locally
python main.py

# Terminal 2: Expose to internet
ngrok http 8000

# Update Audio Pipeline to use ngrok URL
export INTELLIGENCE_SERVICE_URL=https://abc123.ngrok.io
```

---

## Future Enhancements

### Planned Features

1. **Web Dashboard**: React app to view all data (alternative to Notion)
2. **Email Integration**: Process emails like voice notes
3. **Calendar Sync**: Bidirectional sync with Google Calendar
4. **Mobile App**: Native iOS/Android app
5. **Multi-language**: Support for German, Chinese, etc.
6. **Batch Processing**: Upload multiple audio files at once
7. **Analytics**: Insights on productivity, meeting frequency, etc.

---

## Repository Links

| Service | Repository | Technology | Deployment |
|---------|-----------|------------|------------|
| Intelligence | [jarvis-intelligence-service](https://github.com/JulienMaterno/jarvis-intelligence-service) | Python + FastAPI | Cloud Run |
| Audio Pipeline | [jarvis-audio-pipeline](https://github.com/JulienMaterno/jarvis-audio-pipeline) | Python + Whisper | Cloud Run |
| Telegram Bot | [jarvis-telegram-bot](https://github.com/JulienMaterno/jarvis-telegram-bot) | Python + PTB | Cloud Run |
| Sync Service | [jarvis-sync-service](https://github.com/JulienMaterno/jarvis-sync-service) | Python + Notion API | Cloud Run |

---

## Getting Help

- **Intelligence Service issues**: See [CLOUD_ARCHITECTURE.md](./CLOUD_ARCHITECTURE.md) in this repo
- **General questions**: Check each service's README.md
- **Integration problems**: Review API docs in this file

---

## Summary

Jarvis is a **microservices architecture** with clear separation of concerns:

1. **Audio Pipeline** → Transcribes audio
2. **Intelligence Service** → Analyzes content (THE BRAIN)
3. **Sync Service** → Pushes to Notion
4. **Telegram Bot** → User interface

All services communicate via **HTTP APIs** and share data through **Supabase**. The Intelligence Service is the heart of the system - everything flows through it.
