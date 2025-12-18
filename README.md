# 🧠 Jarvis Intelligence Service

> The "Brain" of the operation. A FastAPI service running on Cloud Run that analyzes transcripts using Claude 3.5 Haiku.

## 🌟 Features

*   **AI Analysis**: Uses Anthropic's Claude 3.5 Haiku to extract insights, tasks, and summaries.
*   **Structured Data**: Converts unstructured text into structured database rows (Meetings, Tasks, Reflections).
*   **API Driven**: Exposes a REST API for other services to trigger analysis.
*   **Scalable**: Deployed on Google Cloud Run (Serverless).

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
```

### 2. Deploy to Google Cloud Run

This service is designed to run on Cloud Run.

```bash
# 1. Build and Submit
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/jarvis-intelligence-service

# 2. Deploy
gcloud run deploy jarvis-intelligence-service \
  --image gcr.io/YOUR_PROJECT_ID/jarvis-intelligence-service \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated
```

## 🔌 API Endpoints

### `POST /api/v1/process/{transcript_id}`

Triggers the analysis for a specific transcript that is already saved in Supabase.

**Path Parameters:**
*   `transcript_id`: UUID of the transcript in the `transcripts` table.

**Response:**
```json
{
  "status": "success",
  "transcript_id": "123-abc...",
  "analysis": {
    "summary": "...",
    "tasks": [...],
    "reflections": [...]
  }
}
```

### `GET /api/v1/health`
Returns `{"status": "healthy"}` if the service is up.
