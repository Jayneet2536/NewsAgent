script_content = '''from src.nodes.researcher import researcher_node

plan_str = """- Search for “AI research breakthroughs last 7 days” – prioritize first to capture the most time‑sensitive developments.  
- Search for “Indian startup funding rounds past week” – second priority to get recent investment news.  
- Search for “Indian cricket match results and news last 7 days” – third priority, as sports updates are frequent but less likely to impact broader research.  
- Search for “AI startup ecosystem India updates 7 days” – follow‑up query to link AI and Indian startups.  
- Search for “Emerging AI technologies in Indian cricket analytics 7 days” – niche query combining AI and cricket for specialized insights.  
- Search for “Upcoming AI conferences or webinars India this week” – to identify imminent events.  
- Search for “New cricket player contracts with Indian tech startups 7 days” – to explore cross‑industry collaborations."""

state = {
    'interests': ['AI', 'Indian startups', 'cricket'],
    'plan': plan_str
}

if __name__ == '__main__':
    result = researcher_node(state)
    articles = result.get('articles', [])
    print(f"Total Articles Fetched: {len(articles)}")
    if articles:
        print("Keys in Article object:", list(articles[0].keys()))
    else:
        print("No articles returned")
'''

with open("test_researcher.py", "w", encoding="utf-8") as f:
    f.write(script_content)

print("File test_researcher.py created successfully.")