import logging
from src.graph.workflow import app

# Set logging to WARNING to keep the CLI output clean
logging.basicConfig(level=logging.WARNING)

print("=" * 60)
print("Starting the interactive workflow test...")
print("=" * 60)

# Get natural language input from the user
user_input = input("\nEnter your interests or topic to research (e.g., 'Latest AI advancements'): ")

if not user_input.strip():
    print("No input provided. Exiting.")
    exit(0)

initial_state = {
    "interests": [user_input.strip()],
    "retry_count": 0,
}

print(f"\nStarting workflow for: '{user_input.strip()}'\n")

try:
    final_state = dict(initial_state)
    
    # Use stream() to iterate through the steps as they execute
    for output in app.stream(initial_state):
        for node_name, node_state in output.items():
            print(f" -> [{node_name.upper()}] completed.")
            if isinstance(node_state, dict):
                final_state.update(node_state)

    if final_state:
        print("\nPlanner interests:", final_state.get("interests", []))
        print("\nSearch plan:")
        print(final_state.get("plan", "No plan produced"))

        print("\n" + "=" * 60)
        print("FINAL DIGEST:")
        print("=" * 60)
        print(final_state.get('final_digest') or final_state.get('draft', 'No draft produced'))

        print("\n" + "=" * 60)
        print("Stats:")
        print(f"Articles fetched: {len(final_state.get('articles', []))}")
        print(f"Verification Score: {final_state.get('verification_score', 'N/A')}")
        print(f"Retries: {final_state.get('retry_count', 0)}")
        print("=" * 60)
except Exception as e:
    print(f"\nWorkflow failed with error: {e}")
