"""Upload a local audio file to the audio pipeline for processing."""
import os
import httpx
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

async def upload_audio(filepath: str, username: str = "aaron"):
    """Upload audio file to audio pipeline for transcription and analysis."""
    
    audio_pipeline_url = os.getenv('AUDIO_PIPELINE_URL', 'https://jarvis-audio-pipeline-qkz4et4n4q-as.a.run.app')
    url = f"{audio_pipeline_url}/process/upload"
    
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"File not found: {filepath}")
        return
    
    file_size_mb = filepath.stat().st_size / (1024 * 1024)
    print(f"File: {filepath.name}")
    print(f"Size: {file_size_mb:.1f} MB")
    print(f"Uploading to: {url}")
    print("\nThis may take several minutes for long recordings...")
    
    with open(filepath, 'rb') as f:
        files = {'file': (filepath.name, f, 'audio/ogg')}
        data = {'username': username}
        
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min timeout
            response = await client.post(url, files=files, data=data)
            
            print(f"\nStatus: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"\nResult:")
                print(f"  Status: {result.get('status', 'unknown')}")
                print(f"  Category: {result.get('category', 'unknown')}")
                print(f"  Summary: {result.get('summary', 'N/A')[:200]}")
                
                if 'details' in result:
                    details = result['details']
                    print(f"\nDetails:")
                    print(f"  Transcript ID: {details.get('transcript_id', 'N/A')}")
                    print(f"  Transcript length: {details.get('transcript_length', 0)} chars")
                    print(f"  Meetings created: {details.get('meetings_created', 0)}")
                    print(f"  Tasks created: {details.get('tasks_created', 0)}")
            else:
                print(f"Error: {response.text[:500]}")

if __name__ == "__main__":
    import sys
    
    # Default to the 150245 merged file
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = os.path.expanduser("~/.jarvis/meeting_recordings/manual_20260112_150245_merged_20260112_204625.ogg")
    
    asyncio.run(upload_audio(filepath))
