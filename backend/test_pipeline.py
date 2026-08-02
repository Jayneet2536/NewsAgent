# test_full_pipeline.py
import logging
from src.nodes.researcher import researcher_node
from src.nodes.writer import writer_node

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

# Use the exact plan from your planner
plan_str = """- Search for "AI research breakthroughs last 7 days" – prioritize first to capture the most time‑sensitive developments.  
- Search for "Indian startup funding rounds past week" – second priority to get recent investment news.  
- Search for "Indian cricket match results and news last 7 days" – third priority, as sports updates are frequent but less likely to impact broader research.  
- Search for "AI startup ecosystem India updates 7 days" – follow‑up query to link AI and Indian startups.  
- Search for "Emerging AI technologies in Indian cricket analytics 7 days" – niche query combining AI and cricket for specialized insights.  
- Search for "Upcoming AI conferences or webinars India this week" – to identify imminent events.  
- Search for "New cricket player contracts with Indian tech startups 7 days" – to explore cross‑industry collaborations."""

# Initial state
state = {
    'interests': ['AI', 'Indian startups', 'cricket'],
    'plan': plan_str,
    'articles': [],
    'draft': '',
    'verification_score': 0,
    'retry_count': 0,
    'final_digest': ''
}

print("=" * 60)
print("🔍 STEP 1: Running Researcher...")
print("=" * 60)
research_result = researcher_node(state)
articles = research_result.get('articles', [])
print(f"✅ Fetched {len(articles)} articles")

if articles:
    print(f"📰 Sample article: {articles[0].get('title', 'No title')}")
    print(f"   URL: {articles[0].get('url', 'No URL')}")
    print(f"   Topic: {articles[0].get('topic', 'No topic')}")
else:
    print("❌ No articles fetched. Check Tavily API key.")
    exit()

# Update state with articles
state.update(research_result)

print("\n" + "=" * 60)
print("✍️ STEP 2: Running Writer...")
print("=" * 60)

writer_result = writer_node(state)
draft = writer_result.get('draft', '')

print("\n" + "=" * 60)
print("📰 FINAL DIGEST:")
print("=" * 60)
print(draft)

print("\n" + "=" * 60)
print(f"📊 Stats: {len(articles)} articles → {len(draft)} character digest")
print("=" * 60)