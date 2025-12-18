# Jarvis Intelligence Service

This service handles the "Intelligence" layer of the Jarvis ecosystem. It provides an API for analyzing transcripts using LLMs (Claude) and routing the results to the appropriate databases (Supabase).

## Features

- **Transcript Analysis**: Uses Claude 3.5 Haiku to analyze audio transcripts.
- **Multi-Database Routing**: Automatically categorizes content into Meetings, Reflections, Tasks, and CRM updates.
- **Supabase Integration**: Saves structured data directly to Supabase tables.

## Setup

1. **Install Dependencies**:
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Copy `.env.example` to `.env` and configure:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `ANTHROPIC_API_KEY`

3. **Run the Service**:
   ```bash
   python main.py
   ```
   The API will be available at `http://localhost:8000`.

## API Endpoints

### POST /api/v1/analyze

Analyzes a transcript and saves the results.

**Request Body:**
```json
{
  "transcript": "Full text of the transcript...",
  "filename": "recording.mp3",
  "recording_date": "2025-12-18",
  "audio_duration_seconds": 120.5,
  "language": "en"
}
```

**Response:**
```json
{
  "status": "success",
  "analysis": { ... },
  "db_records": {
    "transcript_id": "uuid",
    "meeting_ids": ["uuid"],
    "reflection_ids": [],
    "task_ids": ["uuid"]
  }
}
```
