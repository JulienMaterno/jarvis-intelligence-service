"""
Seed Mem0 with key facts from Aaron's comprehensive profile.

This extracts the most important, reusable facts that the AI should know
without needing to query a document every time.
"""

import asyncio
import httpx
import json

BASE_URL = "https://jarvis-intelligence-service-qkz4et4n4q-as.a.run.app"

# Comprehensive extraction from profile - ALL important facts and insights
PROFILE_MEMORIES = [
    # ============ IDENTITY & BASICS ============
    {"memory": "Aaron Pütting is a 26-year-old German industrial engineer", "type": "fact"},
    {"memory": "Email: aaron.j.putting@gmail.com", "type": "fact"},
    {"memory": "Speaks German (native), English (fluent), and basic Spanish & Mandarin", "type": "fact"},
    {"memory": "Currently based in Ho Chi Minh City, Vietnam (as of January 2026)", "type": "fact"},
    
    # ============ EDUCATION ============
    {"memory": "Has dual master's degrees: RWTH Aachen (Mechanical Engineering) and Tsinghua University (Industrial Engineering) with 3.9/4.0 GPA", "type": "fact"},
    {"memory": "B.Sc. & M.Sc. from RWTH Aachen University, specialization in Business Development", "type": "fact"},
    {"memory": "Full Chinese Government (CSC) Scholarship for Tsinghua master's", "type": "fact"},
    {"memory": "Master thesis at Tsinghua: 'Assessing the Viability of Insect Farming for Food Waste Management in China'", "type": "fact"},
    {"memory": "Exchange semester at Linköping University, Sweden during RWTH studies", "type": "fact"},
    
    # ============ CAREER HISTORY ============
    {"memory": "Was employee #3 at Algenie, an Australian microalgae climate tech startup (Oct 2024 - Dec 2025)", "type": "fact"},
    {"memory": "At Algenie: Built revolutionary helical photobioreactor technology and techno-economic assessment model", "type": "fact"},
    {"memory": "At Algenie: Engineered automated algae inoculation platform and worked on supply chains with Chinese suppliers", "type": "fact"},
    {"memory": "Interned at Roland Berger (Jun-Aug 2023): Market analysis for cooling tech, decarbonization strategy for energy supplier", "type": "fact"},
    {"memory": "Interned at Monitor Deloitte (Apr-Jun 2023): Global launch strategy for digital health precision medicine", "type": "fact"},
    {"memory": "Interned at Bayer AG (Feb-May 2022): Change management in Pharma R&D, Excel/Power BI planning tools", "type": "fact"},
    {"memory": "Interned at Porsche AG (Feb-Sep 2021): Risk identification in pre-series production, bachelor thesis on time determination in assembly lines", "type": "fact"},
    {"memory": "Rejected consulting offers from Roland Berger and Monitor Deloitte to pursue entrepreneurship", "type": "fact"},
    {"memory": "3 months voluntary basic training in German Federal Armed Forces (armored infantry), mentored 7 recruits", "type": "fact"},
    {"memory": "Appointed Notion Ambassador after impressing the Notion team with advanced usage", "type": "fact"},
    
    # ============ TECHNICAL SKILLS ============
    {"memory": "Programming skills: Python, C++, VBA, Java", "type": "fact"},
    {"memory": "Hardware skills: ESP32 microcontrollers, PID loops, electronics, bioprocess systems", "type": "fact"},
    {"memory": "Software tools: Advanced PowerPoint & Excel, SolidWorks, Power BI & Power Automate", "type": "fact"},
    {"memory": "Systems expertise: Notion (Ambassador-level), Supabase, various automation tools", "type": "fact"},
    
    # ============ PERSONALITY - OPTIMIZER'S PARADOX ============
    {"memory": "Has 'Optimizer's Paradox': gut reaction is usually correct, but builds analytical frameworks to validate, sometimes getting trapped in analysis", "type": "insight"},
    {"memory": "Pattern: uses elaborate analytical frameworks to validate emotional decisions already made", "type": "insight"},
    {"memory": "Gets seduced by own analytical processes - mistakes quality of analysis for correctness of direction", "type": "insight"},
    {"memory": "When forced to make gut decisions (changing flights, leaving Algenie), they tend to be correct - should trust intuition more", "type": "insight"},
    {"memory": "Psychological commitment happens during planning - gets invested in frameworks rather than outcomes", "type": "insight"},
    
    # ============ PERSONALITY - KEEPING OPTIONS OPEN ============
    {"memory": "Tends to keep options open (chose generic mechanical engineering, went into consulting for this reason)", "type": "insight"},
    {"memory": "Pattern recognition: 'Jarvis helps whatever I do next' sounds like the same 'keep options open' habit - suspicious of this", "type": "insight"},
    {"memory": "In transition between 'high-performing generalist who keeps options open' and 'mission-driven builder/founder'", "type": "insight"},
    {"memory": "Old identity: 'High-performing generalist who keeps options open' - consulting was perfect for this", "type": "insight"},
    {"memory": "New identity forming: 'Mission-driven builder/founder' - requires closing doors, accepting trade-offs", "type": "insight"},
    
    # ============ PERSONALITY - OTHER TRAITS ============
    {"memory": "Cognitive style: Highly analytical, first-principles thinker, iterative learner", "type": "insight"},
    {"memory": "Decision-making: Rational surface, emotional core - uses analysis to validate gut decisions", "type": "insight"},
    {"memory": "Work ethic: Disciplined, structured, strong follow-through, proactive problem solver", "type": "insight"},
    {"memory": "Communication: Direct yet considerate, prefers concise well-thought-out exchanges", "type": "preference"},
    {"memory": "Self-image: High-performing but humble, occasionally self-critical or prone to over-optimization", "type": "insight"},
    {"memory": "Naturally inclined to optimize around problems rather than solve them directly", "type": "insight"},
    {"memory": "At Algenie, built morning routines to compensate for team dysfunction rather than addressing it", "type": "insight"},
    
    # ============ CORE VALUES & MOTIVATORS ============
    {"memory": "Core values: realism over blind optimism, accuracy, follow-through, consistency, authentic communication over polished positioning", "type": "preference"},
    {"memory": "Values impact over scale: 'Would rather NOT scale if it means having a bigger impact'", "type": "preference"},
    {"memory": "Primary motivators: intellectual growth, sustainability impact, community/belonging, autonomy combined with connection", "type": "preference"},
    {"memory": "Frustrated by: vagueness, inefficiency, surface-level conversation, people who don't deliver promises, environments without energy/trust", "type": "preference"},
    {"memory": "Non-negotiable: needs community and belonging, not just mission alignment", "type": "preference"},
    {"memory": "Can sense cultural energy deeply - when the 'room feels alive', performs at best; when it doesn't, motivation drops", "type": "insight"},
    
    # ============ THE ALGENIE STORY ============
    {"memory": "Went to Australia by accident - spreadsheet mishap led to interviewing with fish farming startup instead of Vietnam thesis", "type": "fact"},
    {"memory": "Quit first Australian job (Aquacultr) after 5 days when CEO revealed mushroom-inspired pivot to underwater fish speakers", "type": "fact"},
    {"memory": "Found Algenie through LinkedIn outreach in Sydney, started same day without signing anything - 'so un-German'", "type": "fact"},
    {"memory": "Two weeks after starting Algenie, learned he didn't need the thesis anymore - stayed because he enjoyed the work", "type": "fact"},
    
    # ============ THE ALGENIE REVELATION ============
    {"memory": "Left Algenie realization: 'Impact + Autonomy + Belonging = Fulfillment' - Belonging is NOT optional", "type": "insight"},
    {"memory": "Key quote from Algenie: 'Mission gives purpose; people give life. I left not because I stopped believing in the vision, but because I stopped feeling alive in it.'", "type": "insight"},
    {"memory": "Lost trust in Algenie CEO Nick due to unrealistic optimism disconnected from facts and repeated unfounded claims", "type": "fact"},
    {"memory": "Algenie felt like 'a bunch of fighters for the same mission, but not a team' - high autonomy became isolation", "type": "insight"},
    {"memory": "Key realization: was often right when disagreed with Nick's decisions, despite initially deferring due to limited experience", "type": "insight"},
    {"memory": "Missing role models at Algenie: Nick and Renske didn't deliver the mentorship expected", "type": "fact"},
    {"memory": "The Deloitte dinner contrast: within minutes felt welcomed, connected, energized - revealed what was missing at Algenie", "type": "insight"},
    {"memory": "Final lesson from Algenie: Meaningful work isn't enough without shared energy", "type": "insight"},
    {"memory": "Autonomy only works when paired with belonging - freedom without shared purpose drains energy instead of fueling it", "type": "insight"},
    
    # ============ CAREER EXPLORATION ============
    {"memory": "Three career paths being considered: (1) Found own startup (long-term preference), (2) Join VC (1-2 year learning), (3) Build small side business first", "type": "fact"},
    {"memory": "Target sectors: FoodTech, AgriTech, BioTech, Climate Tech, Longevity", "type": "preference"},
    {"memory": "Philosophy: Prioritizing impact-driven tangible solutions over generic B2B SaaS", "type": "preference"},
    {"memory": "Bill Gates principle: if a startup can't potentially remove 1 gigaton of CO₂/year in best case, what's the point?", "type": "insight"},
    
    # ============ VC CONSIDERATIONS ============
    {"memory": "VC concerns: loneliness (biggest issue - could recreate Algenie isolation), inauthentic networking, delays founder commitment", "type": "insight"},
    {"memory": "VC appeal: Breaking into Singapore (visa), networking as job, learn to invest, see fundraising side", "type": "insight"},
    {"memory": "Realization about VC: 'If I were VC, I would get annoyed watching other people building shit' - prefers building", "type": "insight"},
    {"memory": "VC might be 'consulting 2.0' - socially impressive middle path that delays founder commitment", "type": "insight"},
    {"memory": "Applied to Entrepreneurs First (London), Antler, and Network School - but uncertain if right fit", "type": "fact"},
    {"memory": "Value alignment discovery: Traditional VC requires 100x returns and massive scale, but Aaron wants impact over scale", "type": "insight"},
    {"memory": "Should explore: Focused Research Organizations (FROs), philanthropic funding (Emergent Ventures, Schmidt Futures), impact-first VCs", "type": "insight"},
    
    # ============ GEOGRAPHIC CONSIDERATIONS ============
    {"memory": "Geographic framework: 'Singapore money, Vietnam build, Indonesia ship'", "type": "insight"},
    {"memory": "Singapore: Good for biotech/regulated industries and VC scene, only viable SEA option for deep tech", "type": "insight"},
    {"memory": "Vietnam recommended over Indonesia by multiple sources: direct communication, walkability, growing ecosystem", "type": "insight"},
    {"memory": "Indonesia challenges: $3 switching cost kills loyalty, corruption, yes-saying culture, work ethics concerns, fragmented agriculture", "type": "insight"},
    {"memory": "Political/cultural concerns about US/San Francisco making him question building there", "type": "preference"},
    {"memory": "December 2025 journey: Bali (mistake) → Jakarta → back to Bali → left early for HCMC", "type": "fact"},
    {"memory": "Coming to Bali in December 2025 'was a mistake'", "type": "insight"},
    
    # ============ PROJECT JARVIS ============
    {"memory": "Building 'Jarvis' - personal AI operating system connecting conversations, meetings, reflections, emails, tasks", "type": "fact"},
    {"memory": "Jarvis thesis: 'The future belongs to those who build their memory today' - data infrastructure advantage", "type": "insight"},
    {"memory": "Jarvis tech stack: Supabase (PostgreSQL), bidirectional sync (Notion, Google, Apple), WhisperX transcription, Claude MCP, Beeper integration", "type": "fact"},
    {"memory": "Self-aware that Jarvis might be 'productive procrastination' from harder career decisions", "type": "insight"},
    {"memory": "On Jarvis: 'Probably one of the most productive procrastinations ever, but still a procrastination'", "type": "insight"},
    {"memory": "Interest disconnect: stated interests (FoodTech, Climate) vs actual building (productivity tools like Jarvis)", "type": "insight"},
    {"memory": "Jarvis question: 'What if the thing I can't stop building even when I know I should be doing something else is exactly the signal I should follow?'", "type": "insight"},
    {"memory": "Jarvis December 2025 progress: Supabase as source of truth, contact sync, Plot Chrome extension, smart evening journal, Beeper integration, Supabase MCP", "type": "fact"},
    
    # ============ UNRESOLVED TENSIONS ============
    {"memory": "Critical question: 'What would you build if you weren't trying to solve world hunger?'", "type": "insight"},
    {"memory": "Unresolved: VC still 'on the table' despite clarity that building excites him more", "type": "insight"},
    {"memory": "Unresolved: Jarvis continuing despite saying he'd cut it before networking", "type": "insight"},
    {"memory": "Unresolved: 'What to build' uncertainty keeping VC door open", "type": "insight"},
    {"memory": "Unresolved: People/belonging non-negotiable but currently building solo", "type": "insight"},
    {"memory": "Question to answer: 'If Jarvis didn't exist as an option, what decision would you make about the next 6 months?'", "type": "insight"},
    {"memory": "Question to answer: 'Where do you want to spend Christmas 2026?' - geographic commitment reveals deeper commitments", "type": "insight"},
    
    # ============ LIFESTYLE & ROUTINES ============
    {"memory": "Morning routine: wake 5-5:30am, morning block for personal projects/networking until 7:30", "type": "fact"},
    {"memory": "Highly prioritizes 8 hours sleep", "type": "preference"},
    {"memory": "Exercise: daily gym (strength training), tennis (19+ years), swimming (2km in 37:30), running", "type": "fact"},
    {"memory": "Currently limited by shoulder injury (preventing most sports)", "type": "fact"},
    {"memory": "Supplements: creatine, magnesium glycinate, vitamin D3", "type": "fact"},
    {"memory": "Can do 5 minutes at 4°C cold plunge - got into cold plunges in Bali", "type": "fact"},
    {"memory": "Struggles to actually rest without building systems - 'really bad at feeling unproductive'", "type": "insight"},
    {"memory": "Meal preps 3-4 days in advance, goal to cook at least twice a day, experimented with keto", "type": "fact"},
    {"memory": "Information diet: 24 books/year target, selective podcasts, deep AI usage, highly selective input", "type": "preference"},
    {"memory": "December was supposed to be rest and reflection, but way of rest seems to be building exciting systems", "type": "insight"},
    
    # ============ KEY RELATIONSHIPS ============
    {"memory": "Professional references: Nick Hazell (Algenie CEO), Carina Kießling (Roland Berger mentor), John Martin (Algenie CTO)", "type": "relationship"},
    {"memory": "Close friend Alinta has Australian biochar/algae background", "type": "relationship"},
    {"memory": "Friend Jonas starting at Igus in Germany", "type": "relationship"},
    {"memory": "Friend Zoe potentially joining in HCMC", "type": "relationship"},
    {"memory": "Alex Cheng - fellow explorer focused on emotional experiences", "type": "relationship"},
    {"memory": "Jakarta network: Dhirvan (CEO Swap Energy), Amelinda (venture studio), Vania (agriculture), Domex (B2C marketing)", "type": "relationship"},
    
    # ============ NEWSLETTER ============
    {"memory": "Publishes 'Exploring Out Loud' newsletter documenting his journey with authentic vulnerability - 4 editions published", "type": "fact"},
    {"memory": "Accidentally CC'd everyone in one newsletter edition, revealing the community", "type": "fact"},
    
    # ============ UNIQUE COMBINATION ============
    {"memory": "Rare combination: Technical depth (biotech, engineering, systems) + Business capability (strategy, modeling, fundraising) + Cross-cultural experience (Germany, China, Australia, SEA) + Can code AND understand VC", "type": "insight"},
    {"memory": "Superpower: Systematic ecosystem penetration - rapidly builds networks and comprehensive databases when entering new markets", "type": "insight"},
    {"memory": "Trap: Gets seduced by own analytical processes - mistakes quality of analysis for correctness of direction", "type": "insight"},
    {"memory": "Technical talent allocation insight: 'Technical talent is being systematically misallocated' - may be about himself", "type": "insight"},
    {"memory": "The 'Controlled Chaos' pattern: deliberately places himself in uncertain situations across countries, then systematically builds infrastructure to thrive", "type": "insight"},
    
    # ============ KEY QUOTES ============
    {"memory": "Quote: 'Mission gives purpose; people give life.'", "type": "insight"},
    {"memory": "Quote: 'Would rather NOT scale if it means having a bigger impact, than scale with a lower impact.'", "type": "insight"},
    {"memory": "Quote: 'I feel like the entire path of building a startup excites me more... If I were VC, I would get annoyed watching other people building shit.'", "type": "insight"},
    {"memory": "Quote: 'Probably one of the most productive procrastinations ever, but still a procrastination.'", "type": "insight"},
    {"memory": "Quote: 'Autonomy only works when paired with belonging.'", "type": "insight"},
    
    # ============ PHYSICAL SETBACKS DEC 2025 ============
    {"memory": "December 2025 setbacks: Broken Apple Watch, injured shoulder tendons, Bali belly (first week), cold, random infection (spent NYE in bed with fever)", "type": "fact"},
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
