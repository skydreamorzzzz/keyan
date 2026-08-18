"""Generate Strategy(E) abstractions from Case(E) using LLM.

Uses DeepSeek V4 Flash with structured output to create abstract strategies.
Each Strategy(E) must:
- Derive from single Case(E) only
- Remove instance-specific details (company, year, values)
- Preserve operation structure
- Add operand role bindings
- No hallucination
"""
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

# Import after adding ROOT to path so pilot.config can be found
from pilot.llm import call_once_with_metadata

def load_prompts():
    """Load abstraction prompts."""
    prompts_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/abstraction_prompts.jsonl")
    prompts = []
    with open(prompts_file) as f:
        for line in f:
            prompts.append(json.loads(line))
    return prompts

def generate_abstraction(prompt_entry: dict) -> dict:
    """Call LLM to generate Strategy(E) from Case(E)."""
    source_id = prompt_entry["source_experience_id"]
    prompt = prompt_entry["prompt"]

    # Call LLM with JSON response format
    messages = [{"role": "user", "content": prompt}]

    result = call_once_with_metadata(
        messages=messages,
        max_tokens=1500,
        temperature=0.3,  # Some creativity for abstraction, but controlled
        timeout=180,
        response_format={"type": "json_object"}
    )

    response_text = result["text"]

    # Parse JSON response
    try:
        strategy = json.loads(response_text)
        strategy["source_experience_id"] = source_id
        strategy["representation"] = "strategy"
        return strategy
    except json.JSONDecodeError as e:
        print(f"ERROR parsing JSON for {source_id}: {e}")
        print(f"Response: {response_text[:200]}...")
        return None

def main():
    print("=" * 80)
    print("STAGE 36: Generate Strategy(E) Abstractions")
    print("=" * 80)
    print()

    # Load prompts
    prompts = load_prompts()
    print(f"Loaded {len(prompts)} abstraction prompts")
    print()

    # Generate abstractions
    strategies = []
    failed = []

    print("Generating abstractions (this will take ~2-3 minutes)...")
    print()

    for i, prompt_entry in enumerate(prompts, 1):
        source_id = prompt_entry["source_experience_id"]

        if i % 10 == 0:
            print(f"Progress: {i}/{len(prompts)} ({i/len(prompts)*100:.1f}%)")

        strategy = generate_abstraction(prompt_entry)

        if strategy:
            strategies.append(strategy)
        else:
            failed.append(source_id)

        # Rate limiting
        time.sleep(0.1)

    print()
    print(f"Generated {len(strategies)} strategies")
    print(f"Failed: {len(failed)}")

    if failed:
        print(f"Failed IDs: {failed}")
    print()

    # Save strategies
    output_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/strategies_raw.json")
    with open(output_file, 'w') as f:
        json.dump(strategies, f, indent=2)

    print(f"Saved to {output_file}")
    print()

    # Save cache for reproducibility
    cache_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/abstraction_generation_cache.jsonl")
    with open(cache_file, 'w') as f:
        for strategy in strategies:
            f.write(json.dumps(strategy) + '\n')

    print(f"Cache saved to {cache_file}")
    print()
    print("Next step: QC abstraction quality")
    print("  Script: pilot/stage36_paired_abstraction/qc_abstractions.py")

if __name__ == "__main__":
    main()
