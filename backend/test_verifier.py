# test_verifier_alone.py
import logging
from src.nodes.verifier import verifier_node
from src.config import settings

logging.basicConfig(level=logging.INFO)

# Create a deliberately bad draft with hallucinations
bad_draft = """
## Indian Startups
- **Zomato Raises $10 Billion**: Zomato raised $10 billion from Elon Musk.
- **Ola Acquires Google**: Ola bought Google for $5 billion.

## Cricket
- **India Wins Moon Cup**: India defeated Pakistan on the moon.
"""

# Source articles (the truth)
articles = [
    {
        "title": "Zomato Raises $100 Million",
        "url": "https://example.com/zomato",
        "content": "Zomato raised $100 million in Series G funding from existing investors.",
        "snippet": "Zomato raises $100M",
        "topic": "Indian startups"
    },
    {
        "title": "Ola Partners with Google",
        "url": "https://example.com/ola",
        "content": "Ola announced a strategic partnership with Google for AI-powered mobility solutions.",
        "snippet": "Ola and Google partner",
        "topic": "Indian startups"
    }
]

state = {
    "draft": bad_draft,
    "articles": articles,
    "retry_count": 0,
    "verification_score": 0
}

print("=" * 60)
print("🔍 Testing Verifier with Bad Draft")
print("=" * 60)

result = verifier_node(state)

print(f"✅ Verification Score: {result['verification_score']}/100")
print(f"✅ Retry Count: {result['retry_count']}")
print(f"🔴 This should be LOW (the draft has hallucinations)")

print("\n" + "=" * 60)
print("If score < threshold (80), the graph will loop back to writer")
print("If score >= threshold, the graph will end")
print("=" * 60)