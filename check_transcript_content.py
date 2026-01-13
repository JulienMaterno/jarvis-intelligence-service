"""Check what the transcript contains - is it one-sided or both?"""
import os
from supabase import create_client

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get the 91-min transcript
result = sb.table("transcripts").select("id, source_file, full_text, segments, speakers").eq(
    "source_file", "manual_20260112_131528_recompressed.ogg"
).execute()

if result.data:
    t = result.data[0]
    print(f"Transcript: {t['source_file']}")
    print(f"Length: {len(t['full_text'])} chars")
    print(f"Speakers: {t.get('speakers', 'N/A')}")
    
    # Check segments for speaker info
    segments = t.get('segments')
    if segments:
        print(f"\nSegments: {len(segments)}")
        # Count unique speakers
        if isinstance(segments, list):
            speakers = set()
            for seg in segments:
                if isinstance(seg, dict) and 'speaker' in seg:
                    speakers.add(seg['speaker'])
            print(f"Unique speakers in segments: {speakers}")
    
    # Print first 2000 chars to see the style
    print(f"\n=== FIRST 2000 CHARS ===")
    print(t['full_text'][:2000])
    
    # Check for speaker markers in text
    print(f"\n=== SPEAKER ANALYSIS ===")
    text = t['full_text']
    
    # Count potential speaker indicators
    speaker_0 = text.count('SPEAKER_00') + text.count('Speaker 0') + text.count('[0]')
    speaker_1 = text.count('SPEAKER_01') + text.count('Speaker 1') + text.count('[1]')
    
    print(f"Speaker 0/00 mentions: {speaker_0}")
    print(f"Speaker 1/01 mentions: {speaker_1}")
    
    # Check for typical conversation patterns (back and forth)
    lines = text.split('.')
    print(f"Total sentences: {len(lines)}")
else:
    print("Transcript not found")
