"""Reprocess a transcript that has text but failed AI analysis."""
import os
import httpx
import asyncio
from dotenv import load_dotenv
load_dotenv()

async def reprocess_transcript(transcript_id: str):
    """Trigger AI analysis for an existing transcript."""
    
    # Get the intelligence service URL  
    intelligence_url = os.getenv('INTELLIGENCE_SERVICE_URL', 'https://jarvis-intelligence-service-qkz4et4n4q-as.a.run.app')
    
    url = f"{intelligence_url}/api/v1/process/{transcript_id}"
    
    print(f"Calling: {url}")
    print("This may take a few minutes for long transcripts...")
    
    async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for long transcripts
        response = await client.post(url)
        
        print(f"\nStatus: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\nResult: {result.get('status', 'unknown')}")
            
            if 'db_records' in result:
                records = result['db_records']
                print(f"  Transcript ID: {records.get('transcript_id', 'N/A')}")
                print(f"  Meeting IDs: {records.get('meeting_ids', [])}")
                print(f"  Task IDs: {records.get('task_ids', [])}")
                print(f"  Contact matches: {len(records.get('contact_matches', []))}")
                
                for cm in records.get('contact_matches', []):
                    name = cm.get('searched_name', 'Unknown')
                    matched = cm.get('matched', False)
                    status = "✓ Linked" if matched else "✗ Not matched"
                    print(f"    {name}: {status}")
                    
            if 'analysis' in result:
                analysis = result['analysis']
                print(f"\nAnalysis:")
                print(f"  Primary category: {analysis.get('primary_category', 'unknown')}")
                print(f"  Meetings: {len(analysis.get('meetings', []))}")
                print(f"  Tasks: {len(analysis.get('tasks', []))}")
        else:
            print(f"Error: {response.text[:500]}")

if __name__ == "__main__":
    # Transcript ID from previous check
    transcript_id = "e06e7774-bc10-4cc8-a1c1-41f783f6e844"
    asyncio.run(reprocess_transcript(transcript_id))
