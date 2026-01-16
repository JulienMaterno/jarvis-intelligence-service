# Jarvis Intelligence Service - The Brain

## Service Overview
This is the **core AI service** that houses all intelligence logic for the Jarvis ecosystem. Every AI decision, analysis, and chat interaction flows through this service.

## Technology Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI with uvicorn
- **AI Model**: Claude Sonnet 4.5 (Anthropic API)
- **Database**: Supabase (PostgreSQL + REST API + pgvector)
- **Memory**: Mem0 for long-term context
- **Deployment**: Google Cloud Run (auto-deploy on master branch push)

## Architecture Principle
**All AI logic lives HERE**. Other services are simple pipes:
- Audio Pipeline: transcription only → calls us
- Sync Service: data movement only
- Telegram Bot: UI routing only → calls us
- Beeper Bridge: messaging API only → we call it
- Screenpipe Bridge: meeting capture → calls us

## Key Components

### API Endpoints
```
POST /api/v1/process/{transcript_id}     - Analyze transcript (multi-output)
POST /api/v1/chat                         - Chat (non-streaming)
POST /api/v1/chat/stream                  - Chat (SSE streaming)
POST /api/v1/journal/evening-prompt       - Generate journal prompt
POST /api/v1/briefings/check              - Generate meeting briefings
GET  /api/v1/contacts/search              - Search CRM contacts
PATCH /api/v1/meetings/{id}/link-contact  - Link contact to meeting
GET  /health                              - Health check
```

### Core Capabilities
1. **Multi-Output Analysis**: Single transcript → meetings + tasks + reflections + journals
2. **Chat Engine**: Natural language with 40+ tools
3. **Prompt Caching**: 90% cost savings on repeated requests
4. **Research Tools**: LinkedIn (Bright Data), web search (Brave)
5. **Messaging**: Draft and send via Beeper Bridge
6. **Calendar Integration**: Auto-briefings for upcoming meetings

### Available Tools (40+)
- Database queries (via MCP Server)
- Contact search & management
- Task creation and management
- Calendar operations (Google)
- Email drafting (Gmail)
- Beeper messaging (WhatsApp, LinkedIn, Slack, etc.)
- LinkedIn research (Bright Data)
- Web search (Brave)
- Memory operations (Mem0)
- Meeting briefings
- Journal prompts

## Development Commands

### Local Development
```bash
# Setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload --port 8000

# Test endpoints
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_chat.py -v

# Run specific test
pytest tests/test_chat.py::test_chat_endpoint -v
```

### Linting & Formatting
```bash
# Check code style
ruff check .

# Fix auto-fixable issues
ruff check . --fix

# Format code
ruff format .
```

### Deployment
```bash
# Automatic on push to master branch
git push origin master

# Manual deploy
gcloud run deploy jarvis-intelligence-service \
  --source . \
  --region us-central1

# View logs
gcloud run services logs read jarvis-intelligence-service --limit=50
```

## Code Standards

### Python Style
- Use type hints for all functions
- Docstrings for all public functions (Google style)
- Maximum line length: 100 characters
- Use Pydantic models for request/response validation
- Async/await for all I/O operations

### Error Handling
- Use try-except for external API calls
- Log all errors with context
- Return proper HTTP status codes:
  - 200: Success
  - 400: Bad request (validation error)
  - 401: Unauthorized
  - 404: Not found
  - 500: Internal server error
- Never expose internal errors to clients

### Example Function
```python
async def analyze_transcript(
    transcript_id: str,
    user_id: str
) -> AnalysisResult:
    """
    Analyzes a transcript using Claude AI.

    Args:
        transcript_id: UUID of transcript in database
        user_id: UUID of user who owns transcript

    Returns:
        AnalysisResult with meetings, tasks, reflections, journals

    Raises:
        TranscriptNotFoundError: If transcript doesn't exist
        APIError: If Claude API fails
    """
    try:
        # Implementation
        pass
    except Exception as e:
        logger.error(f"Analysis failed: {transcript_id}", exc_info=e)
        raise APIError("Failed to analyze transcript") from e
```

## Environment Variables
Required in `.env` (never commit):
```bash
# Core
ANTHROPIC_API_KEY=sk-ant-xxx
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# Integrations
NOTION_API_KEY=secret_xxx
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
MEM0_API_KEY=xxx

# External APIs
BRIGHT_DATA_API_KEY=xxx  # LinkedIn research
BRAVE_API_KEY=xxx        # Web search

# Service URLs
BEEPER_BRIDGE_URL=https://beeper-bridge.xxx
AUDIO_PIPELINE_URL=https://jarvis-audio-pipeline-xxx.run.app

# Config
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Database Schema (Key Tables)

### transcripts
- Raw audio transcriptions
- Fields: id, user_id, text, created_at, processed_at

### meetings
- Extracted meeting records
- Fields: id, transcript_id, title, attendees, topics, action_items, notion_page_id

### tasks
- Action items from meetings or journals
- Fields: id, title, description, status, due_date, notion_page_id

### reflections
- Topic-based reflections from transcripts
- Fields: id, topic, content, related_meetings, notion_page_id

### journals
- Daily journal entries
- Fields: id, date, content, mood, highlights, notion_page_id

### contacts
- CRM database
- Fields: id, name, email, phone, company, linkedin_url, notion_page_id

## Autonomous Operation Guidelines

### Before Making Changes
1. **Always** read the file first
2. Check if it affects any API endpoints (breaking changes?)
3. Verify if tests exist for the code
4. Consider impact on other services that call this endpoint

### When Adding New Features
1. Add endpoint to appropriate router file (e.g., `routers/chat.py`)
2. Create Pydantic models for request/response
3. Add business logic in `services/` directory
4. Add tests in `tests/` directory
5. Update OpenAPI documentation (automatic via FastAPI)
6. Test locally before pushing

### When Adding New Tools
1. Create tool definition in `tools/` directory
2. Follow existing tool pattern (function + schema)
3. Add to `available_tools` list in chat service
4. Add unit tests for tool logic
5. Test tool via chat endpoint

### When Modifying AI Prompts
1. Prompts live in `prompts/` directory
2. Use Anthropic prompt caching for efficiency
3. Test prompt changes thoroughly (they affect quality)
4. Consider cost implications of longer prompts

### Testing Requirements
- Unit tests for business logic
- Integration tests for API endpoints
- Mock external services (Anthropic, Supabase, Beeper)
- Test both success and error cases
- Minimum 70% coverage for new code

### Safety Rules - Always Ask Before:
- Modifying database schemas
- Changing core AI prompts (affects quality)
- Modifying tool definitions (breaking changes)
- Changing API response formats (affects clients)
- Pushing directly to master branch
- Installing new major dependencies

### Performance Considerations
- Use prompt caching for repeated context (90% savings)
- Stream responses for better UX (`/chat/stream`)
- Batch database queries where possible
- Use async/await for I/O operations
- Monitor Anthropic API usage (check /cost)

## Common Issues & Solutions

### Issue: Claude API rate limiting
**Solution**: Implement exponential backoff, check rate limit headers

### Issue: Supabase connection errors
**Solution**: Check SUPABASE_URL and SUPABASE_KEY, verify network connectivity

### Issue: Slow response times
**Solution**: Enable prompt caching, optimize database queries, use streaming

### Issue: Tool execution failures
**Solution**: Check tool logs, verify external service connectivity (Beeper, MCP Server)

### Issue: Contact matching ambiguity
**Solution**: Return multiple matches, let user confirm via Telegram Bot

## Deployment Pipeline
```
1. Push to master branch
2. GitHub webhook triggers Google Cloud Build
3. Cloud Build runs: docker build
4. Cloud Build deploys to Cloud Run
5. Cloud Run health check: /health
6. Traffic switches to new revision
7. Old revision kept for rollback
```

## Monitoring & Debugging

### Health Check
```bash
curl https://jarvis-intelligence-service-xxx.run.app/health
```

### View Logs
```bash
# Last 50 logs
gcloud run services logs read jarvis-intelligence-service --limit=50

# Follow logs (real-time)
gcloud run services logs tail jarvis-intelligence-service

# Filter by severity
gcloud run services logs read jarvis-intelligence-service --log-filter="severity=ERROR"
```

### Database Queries
Use MCP Server or direct Supabase client to query:
```python
supabase.table('transcripts').select('*').order('created_at', desc=True).limit(10)
```

## Cost Optimization
- Use Claude Sonnet (not Opus) for most operations
- Enable prompt caching (cache system prompts)
- Batch operations where possible
- Monitor usage with `/cost` command
- Use streaming for long responses

## Security Considerations
- Never log API keys or tokens
- Validate all user input (Pydantic models)
- Use environment variables for secrets
- Rate limit endpoints if exposed publicly
- Sanitize database queries (use parameterized queries)
- Verify user ownership before operations

## Integration Points

### Called By:
- Audio Pipeline: `/api/v1/process/{transcript_id}` after transcription
- Telegram Bot: `/api/v1/chat` for user messages
- Screenpipe Bridge: `/api/v1/process/meeting-transcript` after meeting
- Web Chat: `/api/v1/chat/stream` for chat interface
- Cloud Scheduler: `/api/v1/briefings/check` daily

### Calls:
- Beeper Bridge: Send messages via Beeper
- MCP Server: Database queries via MCP protocol
- Anthropic API: Claude AI for all analysis
- Mem0 API: Long-term memory storage
- Bright Data: LinkedIn research
- Brave Search: Web search
- Notion API: CRM operations
- Google APIs: Calendar, Contacts, Gmail

## Quick Reference

| Task | Command |
|------|---------|
| Run locally | `uvicorn main:app --reload` |
| Run tests | `pytest tests/ -v` |
| Lint code | `ruff check .` |
| Format code | `ruff format .` |
| Deploy | Push to master (auto-deploy) |
| View logs | `gcloud run services logs tail jarvis-intelligence-service` |
| Health check | `curl https://<url>/health` |

## Project Context
This is the **most critical service** in the Jarvis ecosystem. All intelligence flows through here. Other services are simple, focused pipes that either prepare data for us (Audio Pipeline) or execute our decisions (Beeper Bridge).

Keep this service:
- Fast (use caching, streaming)
- Reliable (error handling, retries)
- Smart (high-quality prompts)
- Maintainable (clear code, good tests)
- Secure (validate input, protect secrets)
