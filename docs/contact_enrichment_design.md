# Contact Profile Enrichment Design

## Overview
Similar to reflections, contacts should have a growing "profile" field that accumulates learnings about the person over time.

## Data Sources

### 1. Meeting Summaries (Automatic)
When a meeting with a contact is processed:
- Extract key learnings about the person
- Add to their profile with source reference

### 2. LinkedIn Profile (Via BrightData API)
When contact has `linkedin_url`:
- Fetch profile via BrightData API
- Parse: headline, summary, experience, education
- Store as structured data

### 3. Manual Input
User can add notes via Notion or Telegram

## Schema Changes

### Supabase (contacts table)
```sql
-- Add profile_content column (similar to reflections.content)
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS profile_content TEXT;

-- Store LinkedIn data as structured JSON
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS linkedin_data JSONB;

-- Track when profile was last enriched
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS profile_enriched_at TIMESTAMPTZ;
```

### Notion Property
- Use the existing "Content" block (page body) for profile info
- Or add a "Notes" rich_text property

## Profile Content Format

```markdown
## Profile: John Smith

### Background
- Works at Acme Corp as CTO
- Previously at Google (2015-2020)
- Stanford CS graduate

### Key Learnings
- [2025-01-10 Meeting] Interested in AI startup opportunities
- [2025-01-05 Meeting] Has twin daughters, lives in SF
- [LinkedIn] 15+ years in tech leadership

### Communication Style
- Prefers WhatsApp over email
- Responds quickly in mornings
```

## Implementation Steps

1. **Add schema** (migration 018)
2. **Update meeting analysis** to extract contact learnings
3. **Create BrightData integration** for LinkedIn scraping
4. **Add append logic** similar to reflections
5. **Sync profile_content to Notion page body**

## Meeting Analysis Enhancement

In the intelligence service prompt, add:
```
For each person MET WITH (not just mentioned):
- Extract learnings: What did you learn about them?
- Include: interests, family, career updates, preferences
- Format: {"person": "John", "learnings": ["likes hiking", "has 2 kids"]}
```

## Notion Sync

The `profile_content` field would sync to Notion as the page body (not a property).
This requires updating the sync to use the blocks API for page content.

## Cost Considerations

- BrightData LinkedIn scraping: ~$0.01-0.05 per profile
- Only scrape once per contact (cache in linkedin_data)
- Re-scrape on demand or annually
