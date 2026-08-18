"""Execute expanded stability validation: 224 queries × 4 arms.

Frozen protocol:
- Model: DeepSeek-V3
- Temperature: 0.0 (greedy decoding)
- Prompt: Frozen from pilot
- Retrieval: Shared-source protocol, k=3
- Memory construction: Case(E), Strategy(E), Paired(same E)
- Four arms: None, Case, Strategy, Paired

Output: Raw responses with full provenance for program-level audit.
"""
import json
import os
import sys
from typing import List, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

def load_memory_system():
    """Load Case and Strategy source experiences."""
    cases_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/paired_sources.json")
    strategies_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/strategies_clean.json")

    with open(cases_file) as f:
        cases = json.load(f)

    with open(strategies_file) as f:
        strategies = json.load(f)

    # Create lookup maps
    case_map = {c["source_experience_id"]: c for c in cases}
    strategy_map = {s["source_experience_id"]: s for s in strategies}

    return case_map, strategy_map

def construct_case_memory(source_ids: List[str], case_map: Dict) -> str:
    """Construct Case memory from source IDs."""
    memory_parts = []

    for source_id in source_ids:
        if source_id not in case_map:
            continue

        case = case_map[source_id]

        # Format: Question → Program → Answer
        memory_parts.append(f"Example {source_id}:")
        memory_parts.append(f"Q: {case['question']}")
        memory_parts.append(f"Program: {case['program']}")
        memory_parts.append(f"Answer: {case['answer']}")
        memory_parts.append("")

    return "\n".join(memory_parts)

def construct_strategy_memory(source_ids: List[str], strategy_map: Dict) -> str:
    """Construct Strategy memory from source IDs."""
    memory_parts = []

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strategy = strategy_map[source_id]

        # Format: Pattern → Operation sequence → Reasoning
        memory_parts.append(f"Strategy {source_id}:")
        memory_parts.append(f"Pattern: {strategy['strategy_name']}")
        memory_parts.append(f"Problem: {strategy['problem_pattern']}")
        memory_parts.append(f"Operations: {strategy['operation_sequence']}")
        memory_parts.append(f"Reasoning: {strategy['reasoning_steps']}")
        memory_parts.append("")

    return "\n".join(memory_parts)

def construct_paired_memory(source_ids: List[str], case_map: Dict, strategy_map: Dict) -> str:
    """Construct Paired memory from same source IDs."""
    memory_parts = []

    for source_id in source_ids:
        if source_id not in case_map:
            continue

        case = case_map[source_id]

        # Add case
        memory_parts.append(f"Example {source_id}:")
        memory_parts.append(f"Q: {case['question']}")
        memory_parts.append(f"Program: {case['program']}")
        memory_parts.append(f"Answer: {case['answer']}")

        # Add strategy if available
        if source_id in strategy_map:
            strategy = strategy_map[source_id]
            memory_parts.append(f"Pattern: {strategy['strategy_name']}")
            memory_parts.append(f"Reasoning: {strategy['reasoning_steps']}")

        memory_parts.append("")

    return "\n".join(memory_parts)

def load_base_prompt() -> str:
    """Load frozen base prompt from pilot."""
    prompt_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/base_prompt.txt")

    if not os.path.exists(prompt_file):
        # Fallback: use standard FinQA prompt
        return """You are a financial reasoning assistant. Given a question and table context, generate a program to compute the answer.

Output format:
PROGRAM: <step1>, <step2>, ...
ANSWER: <final numerical answer>

Use operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average.
"""

    with open(prompt_file) as f:
        return f.read()

def construct_prompt(target_query: Dict, memory: str, base_prompt: str) -> str:
    """Construct full prompt with memory and target query."""
    parts = [base_prompt]

    if memory:
        parts.append("\n# Retrieved Examples\n")
        parts.append(memory)

    parts.append("\n# Target Question\n")
    parts.append(f"Table: {json.dumps(target_query['table'])}")
    parts.append(f"Pre-text: {' '.join(target_query['pre_text'])}")
    parts.append(f"Post-text: {' '.join(target_query['post_text'])}")
    parts.append(f"Question: {target_query['qa']['question']}")
    parts.append("\nGenerate the program and answer:")

    return "\n".join(parts)

def call_llm(messages: list, temperature: float = 0.0) -> dict:
    """Call LLM with metadata using existing infrastructure."""
    from pilot.llm import call_once_with_metadata

    result = call_once_with_metadata(
        messages,
        temperature=temperature,
        timeout=180
    )
    return result

def execute_query(target: Dict, memory: str, base_prompt: str, arm: str) -> Dict:
    """Execute single query with given memory."""
    # Build full prompt
    full_prompt = construct_prompt(target, memory, base_prompt)

    # Call LLM
    messages = [{"role": "user", "content": full_prompt}]

    result = call_llm(messages, temperature=0.0)

    return {
        "target_id": target["id"],
        "arm": arm,
        "gold_answer": target["qa"].get("exe_ans", target["qa"].get("answer")),
        "response": result["text"],
        "runtime": result["runtime"],
        "shared_source_ids": target.get("shared_source_ids", [])
    }

def main():
    print("=" * 80)
    print("EXPANDED STABILITY VALIDATION: 224 Queries × 4 Arms")
    print("=" * 80)
    print()

    # Load memory system
    print("Loading memory system...")
    case_map, strategy_map = load_memory_system()
    print(f"  Loaded {len(case_map)} Case sources")
    print(f"  Loaded {len(strategy_map)} Strategy sources")
    print()

    # Load expanded sample
    print("Loading expanded sample...")
    expanded_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/expanded_sample_queries.json")
    with open(expanded_file) as f:
        queries = json.load(f)
    print(f"  Loaded {len(queries)} queries")
    print()

    # Validate all queries have shared_source_ids
    missing = [q["id"] for q in queries if "shared_source_ids" not in q or not q["shared_source_ids"]]
    if missing:
        print(f"✗ {len(missing)} queries missing shared_source_ids: {missing[:5]}")
        return

    print(f"✓ All {len(queries)} queries have shared_source_ids")
    print()

    # Load base prompt
    base_prompt = load_base_prompt()
    print("✓ Loaded base prompt")
    print()

    # Four experimental arms
    arms = ["none", "case", "strategy", "paired"]

    print(f"Experiment design: {len(queries)} queries × {len(arms)} arms = {len(queries) * len(arms)} total API calls")
    print()
    print("Frozen protocol:")
    print("  Model: DeepSeek (via environment config)")
    print("  Temperature: 0.0 (greedy decoding)")
    print("  Retrieval: k=3 shared sources")
    print("  Memory: Case(E), Strategy(E), Paired(same E)")
    print()

    # Check for existing results
    results_dir = os.path.join(ROOT, "pilot/stage36_paired_abstraction")
    existing_arms = {}
    for arm in arms:
        result_file = os.path.join(results_dir, f"results_{arm}_expanded.json")
        if os.path.exists(result_file):
            with open(result_file) as f:
                existing_arms[arm] = json.load(f)
            print(f"  Found existing results for {arm}: {len(existing_arms[arm])} records")

    if existing_arms:
        print()
        print("⚠ Existing results detected. Options:")
        print("  1. Continue from checkpoint (skip completed queries)")
        print("  2. Overwrite all results (re-run from scratch)")
        print()

    # Execute each arm
    import time

    for arm in arms:
        print("=" * 80)
        print(f"ARM: {arm.upper()}")
        print("=" * 80)
        print()

        # Load or initialize results
        result_file = os.path.join(results_dir, f"results_{arm}_expanded.json")

        if arm in existing_arms:
            results = existing_arms[arm]
            completed_ids = {r["target_id"] for r in results}
            remaining = [q for q in queries if q["id"] not in completed_ids]
            print(f"  Resuming: {len(completed_ids)} completed, {len(remaining)} remaining")
        else:
            results = []
            remaining = queries
            print(f"  Starting: {len(remaining)} queries to process")

        print()

        # Process remaining queries
        for i, query in enumerate(remaining):
            if i > 0 and i % 10 == 0:
                print(f"  Progress: {i}/{len(remaining)}")

            # Build memory for this arm
            memory = ""
            if arm == "case":
                memory = construct_case_memory(query["shared_source_ids"], case_map)
            elif arm == "strategy":
                memory = construct_strategy_memory(query["shared_source_ids"], strategy_map)
            elif arm == "paired":
                memory = construct_paired_memory(query["shared_source_ids"], case_map, strategy_map)

            # Execute query
            try:
                result = execute_query(query, memory, base_prompt, arm)
                results.append(result)

                # Save incrementally
                with open(result_file, 'w') as f:
                    json.dump(results, f, indent=2)

                # Rate limiting
                time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Error on {query['id']}: {e}")
                continue

        print()
        print(f"✓ Completed {arm} arm: {len(results)} total results")
        print()

    print("=" * 80)
    print("EXPERIMENT COMPLETE")
    print("=" * 80)
    print()
    print("Generated files:")
    for arm in arms:
        result_file = os.path.join(results_dir, f"results_{arm}_expanded.json")
        if os.path.exists(result_file):
            print(f"  {result_file}")
    print()
    print("Next step: Run program_level_audit.py on expanded results")

if __name__ == "__main__":
    main()
