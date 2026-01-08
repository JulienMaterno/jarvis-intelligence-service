"""
Seed Mem0 with key facts from Aaron's comprehensive profile.

This extracts the most important, reusable facts that the AI should know
without needing to query a document every time.
"""

import asyncio
import httpx
import json

BASE_URL = "https://jarvis-intelligence-service-qkz4et4n4q-as.a.run.app"

# Key facts extracted from comprehensive profile - these are the stable, important facts
# that the AI should always have easy access to via Mem0 semantic search
PROFILE_MEMORIES = [
    # Identity & Background
    {"memory": "Aaron Pütting is a 26-year-old German industrial engineer", "type": "fact"},
    {"memory": "Has dual master's degrees: RWTH Aachen (Mechanical Engineering) and Tsinghua University (Industrial Engineering) with 3.9/4.0 GPA", "type": "fact"},
    {"memory": "Speaks German (native), English (fluent), and basic Spanish & Mandarin", "type": "fact"},
    {"memory": "Email: aaron.j.putting@gmail.com", "type": "fact"},
    
    # Career History
    {"memory": "Was employee #3 at Algenie, an Australian microalgae climate tech startup (Oct 2024 - Dec 2025)", "type": "fact"},
    {"memory": "Interned at Roland Berger, Monitor Deloitte, Bayer AG, and Porsche AG", "type": "fact"},
    {"memory": "Rejected consulting offers from Roland Berger and Monitor Deloitte to pursue entrepreneurship", "type": "fact"},
    {"memory": "3 months voluntary basic training in German Federal Armed Forces (armored infantry)", "type": "fact"},
    {"memory": "Appointed Notion Ambassador after impressing the Notion team with advanced usage", "type": "fact"},
    
    # Technical Skills
    {"memory": "Technical skills: Python, C++, VBA, Java, ESP32 microcontrollers, PID loops, SolidWorks, Power BI", "type": "fact"},
    
    # Personality & Decision Making
    {"memory": "Has 'Optimizer's Paradox': gut reaction is usually correct, but builds analytical frameworks to validate, sometimes getting trapped in analysis", "type": "insight"},
    {"memory": "Pattern: uses elaborate analytical frameworks to validate emotional decisions already made", "type": "insight"},
    {"memory": "Tends to keep options open (chose generic mechanical engineering, went into consulting for this reason)", "type": "insight"},
    {"memory": "Gets seduced by own analytical processes - mistakes quality of analysis for correctness of direction", "type": "insight"},
    
    # Core Values & Motivators
    {"memory": "Core values: realism over blind optimism, accuracy, follow-through, consistency, authentic communication over polished positioning", "type": "preference"},
    {"memory": "Values impact over scale: 'Would rather NOT scale if it means having a bigger impact'", "type": "preference"},
    {"memory": "Non-negotiable: needs community and belonging, not just mission alignment", "type": "preference"},
    {"memory": "Primary motivators: intellectual growth, sustainability impact, community/belonging, autonomy combined with connection", "type": "preference"},
    {"memory": "Frustrated by: vagueness, inefficiency, surface-level conversation, people who don't deliver promises, environments without energy/trust", "type": "preference"},
    
    # The Algenie Revelation (Key Learning)
    {"memory": "Left Algenie realization: 'Impact + Autonomy + Belonging = Fulfillment' - Belonging is NOT optional", "type": "insight"},
    {"memory": "Key quote from Algenie: 'Mission gives purpose; people give life. I left not because I stopped believing in the vision, but because I stopped feeling alive in it.'", "type": "insight"},
    {"memory": "Lost trust in Algenie CEO Nick due to unrealistic optimism disconnected from facts and repeated unfounded claims", "type": "fact"},
    {"memory": "Algenie felt like 'a bunch of fighters for the same mission, but not a team' - high autonomy became isolation", "type": "insight"},
    
    # Career Exploration (Current State)
    {"memory": "Three career paths being considered: (1) Found own startup (long-term preference), (2) Join VC (1-2 year learning), (3) Build small side business first", "type": "fact"},
    {"memory": "Target sectors: FoodTech, AgriTech, BioTech, Climate Tech, Longevity", "type": "preference"},
    {"memory": "VC concerns: loneliness (biggest issue - could recreate Algenie isolation), inauthentic networking, delays founder commitment", "type": "insight"},
    {"memory": "Realization about VC: 'If I were VC, I would get annoyed watching other people building shit' - prefers building", "type": "insight"},
    {"memory": "Applied to Entrepreneurs First (London), Antler, and Network School - but uncertain if right fit", "type": "fact"},
    
    # Geographic Considerations
    {"memory": "Geographic framework: 'Singapore money, Vietnam build, Indonesia ship'", "type": "insight"},
    {"memory": "Vietnam recommended over Indonesia by multiple sources due to: direct communication, walkability, growing ecosystem", "type": "insight"},
    {"memory": "Indonesia challenges: $3 switching cost kills loyalty, corruption, yes-saying culture, work ethics concerns", "type": "insight"},
    {"memory": "Political/cultural concerns about US/San Francisco making him question building there", "type": "preference"},
    
    # Project Jarvis
    {"memory": "Building 'Jarvis' - personal AI operating system connecting conversations, meetings, reflections, emails, tasks", "type": "fact"},
    {"memory": "Jarvis thesis: 'The future belongs to those who build their memory today' - data infrastructure advantage", "type": "insight"},
    {"memory": "Self-aware that Jarvis might be 'productive procrastination' from harder career decisions", "type": "insight"},
    {"memory": "Interest disconnect: stated interests (FoodTech, Climate) vs actual building (productivity tools like Jarvis)", "type": "insight"},
    {"memory": "On Jarvis: 'Probably one of the most productive procrastinations ever, but still a procrastination'", "type": "insight"},
    
    # Identity Crisis / Unresolved Tensions
    {"memory": "In transition between 'high-performing generalist who keeps options open' and 'mission-driven builder/founder'", "type": "insight"},
    {"memory": "Pattern recognition: 'Jarvis helps whatever I do next' sounds like the same 'keep options open' habit - suspicious", "type": "insight"},
    {"memory": "Critical question to answer: 'What would you build if you weren't trying to solve world hunger?'", "type": "insight"},
    
    # Lifestyle & Routines
    {"memory": "Morning routine: wake 5-5:30am, morning block for personal projects/networking until 7:30", "type": "fact"},
    {"memory": "Highly prioritizes 8 hours sleep", "type": "preference"},
    {"memory": "Exercise: daily gym (strength training), tennis (19+ years), swimming (2km in 37:30), running", "type": "fact"},
    {"memory": "Currently limited by shoulder injury (preventing most sports)", "type": "fact"},
    {"memory": "Supplements: creatine, magnesium glycinate, vitamin D3", "type": "fact"},
    {"memory": "Can do 5 minutes at 4°C cold plunge", "type": "fact"},
    {"memory": "Struggles to actually rest without building systems - 'really bad at feeling unproductive'", "type": "insight"},
    
    # Key Relationships
    {"memory": "Professional references: Nick Hazell (Algenie CEO), Carina Kießling (Roland Berger mentor), John Martin (Algenie CTO)", "type": "fact"},
    {"memory": "Close friend Alinta has Australian biochar/algae background", "type": "relationship"},
    
    # Newsletter
    {"memory": "Publishes 'Exploring Out Loud' newsletter documenting his journey with authentic vulnerability", "type": "fact"},
]


async def seed_memories():
    """Seed all profile memories into Mem0."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        success = 0
        failed = 0
        
        for i, mem in enumerate(PROFILE_MEMORIES):
            try:
                response = await client.post(
                    f"{BASE_URL}/api/v1/memory",
                    json={
                        "content": mem["memory"],
                        "memory_type": mem["type"],
                        "metadata": {"source": "comprehensive_profile", "seeded": True}
                    }
                )
                # Check response - it might have validation issues in response model
                # but memory may still be added
                data = response.json()
                if response.status_code in (200, 201) or data.get("status") == "success":
                    success += 1
                    print(f"✓ [{i+1}/{len(PROFILE_MEMORIES)}] {mem['memory'][:60]}...")
                elif response.status_code == 422:
                    # Validation error in response model, but memory might be added
                    # Check by looking for "success" anywhere in response
                    if "success" in response.text:
                        success += 1
                        print(f"✓ [{i+1}/{len(PROFILE_MEMORIES)}] {mem['memory'][:60]}...")
                    else:
                        failed += 1
                        print(f"✗ [{i+1}/{len(PROFILE_MEMORIES)}] Failed: {response.text[:100]}")
                else:
                    failed += 1
                    print(f"✗ [{i+1}/{len(PROFILE_MEMORIES)}] Failed: {response.text[:100]}")
            except Exception as e:
                failed += 1
                print(f"✗ [{i+1}/{len(PROFILE_MEMORIES)}] Error: {e}")
        
        print(f"\n{'='*60}")
        print(f"Seeding complete: {success} succeeded, {failed} failed")
        print(f"Total memories in profile: {len(PROFILE_MEMORIES)}")


if __name__ == "__main__":
    asyncio.run(seed_memories())
