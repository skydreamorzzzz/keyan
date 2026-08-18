"""Downstream experiment: 4-arm pilot to isolate abstraction operator effect.

Arms:
- None: No memory retrieval
- Case: Top-3 Case(E) memories
- Strategy: Top-3 Strategy(E) memories
- Paired: Top-3 Case(E)+Strategy(E) pairs

Fixed variables:
- Model: DeepSeek-V3
- Temperature: 0.7
- Top-k: 3 (shared source IDs across all arms)
- Targets: 30 fixed dev queries
- Evaluator: Exact match on executable answer

Only variable: Memory representation

Output:
- Per-query results for each arm
- Transition pattern analysis
- Correlation with semantic/reasoning alignment
- H1-H5 signal assessment
"""
import json
import os
import sys
import time
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from pilot.llm import call_once_with_metadata

# Rate limiting
CALL_DELAY = 0.5  # 500ms between API calls

def load_experiment_data():
    """Load all required data for experiment."""
    base_path = os.path.join(ROOT, "pilot/stage36_paired_abstraction")

    # Load retrieval cache (30 targets with shared source IDs)
    with open(os.path.join(base_path, "retrieval_cache.json")) as f:
        retrieval_cache = json.load(f)

    # Load target queries
    with open(os.path.join(base_path, "target_queries.json")) as f:
        targets = json.load(f)

    # Load Case memories
    with open(os.path.join(base_path, "cases_clean.json")) as f:
        cases = json.load(f)
    cases_by_id = {c["source_experience_id"]: c for c in cases}

    # Load Strategy memories
    with open(os.path.join(base_path, "strategies_clean.json")) as f:
        strategies = json.load(f)
    strategies_by_id = {s["source_experience_id"]: s for s in strategies}

    # Load reasoning alignment diagnostics
    with open(os.path.join(base_path, "reasoning_alignment.json")) as f:
        alignment_data = json.load(f)

    return {
        "retrieval_cache": retrieval_cache,
        "targets": targets,
        "cases": cases_by_id,
        "strategies": strategies_by_id,
        "alignment": alignment_data
    }

def format_case_memory(case: Dict[str, Any]) -> str:
    """Format Case(E) memory for prompt."""
    return f"""## Case Memory

**Question**: {case['question']}

**Context**:
{case.get('retrieval_text', 'No context available')}

**Solution**:
Program: {case['program']}
Answer: {case['answer']}
Explanation: {case.get('explanation', 'N/A')}
"""

def format_strategy_memory(strategy: Dict[str, Any]) -> str:
    """Format Strategy(E) memory for prompt."""
    return f"""## Strategy Memory

**Strategy Name**: {strategy['strategy_name']}

**Problem Pattern**: {strategy['problem_pattern']}

**Operation Sequence**: {' → '.join(strategy['operation_sequence'])}

**Operand Roles**:
{chr(10).join(f"- {role}" for role in strategy['operand_roles'])}

**Reasoning Steps**:
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(strategy['reasoning_steps']))}

**Formula Template**: {strategy.get('formula', 'N/A')}

**Units Convention**: {strategy.get('units_convention', 'N/A')}

**Caveats**: {strategy.get('caveats', 'N/A')}
"""

def build_prompt(target: Dict[str, Any], memories: str) -> str:
    """Build reasoning prompt with or without memories."""
    # Extract target question and context
    question = target["qa"]["question"]
    pre_text = "\n".join(target.get("pre_text", []))
    post_text = "\n".join(target.get("post_text", []))
    table = target.get("table", {})

    # Format table if present
    table_str = ""
    if table and isinstance(table, list) and len(table) > 0:
        headers = table[0]
        rows = table[1:]
        if headers and rows:
            table_str = "\n**Table**:\n"
            table_str += " | ".join(str(h) for h in headers) + "\n"
            table_str += "-" * (len(headers) * 10) + "\n"
            for row in rows[:10]:  # Limit to 10 rows
                table_str += " | ".join(str(c) for c in row) + "\n"

    prompt = f"""You are a financial reasoning expert. Answer the question using the provided context.

{memories}

## Target Question

**Context (Pre-text)**:
{pre_text}

{table_str}

**Context (Post-text)**:
{post_text[:500]}...

**Question**: {question}

**Instructions**:
1. Understand what the question asks
2. Identify relevant values from the context
3. Determine the calculation steps needed
4. Execute the calculation
5. Provide the final numerical answer

Output format:
```
REASONING: [Your step-by-step reasoning]

PROGRAM: [Calculation in format: operation(arg1, arg2), ...]

ANSWER: [Final numerical answer]
```
"""
    return prompt

def execute_arm(
    arm_name: str,
    targets: List[Dict[str, Any]],
    retrieval_cache: List[Dict[str, Any]],
    cases: Dict[str, Any],
    strategies: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Execute one arm of the experiment."""
    print(f"Executing {arm_name} arm...")
    print()

    results = []

    for i, target in enumerate(targets):
        target_id = target["id"]
        gold_answer = target["qa"].get("exe_ans", target["qa"].get("answer"))

        # Get retrieval for this target
        retrieval = next((r for r in retrieval_cache if r["target_id"] == target_id), None)
        if not retrieval:
            print(f"  WARNING: No retrieval for {target_id}")
            continue

        # Build memories based on arm
        memories = ""
        if arm_name == "Case":
            for source_id in retrieval["shared_source_ids"]:
                case = cases.get(source_id)
                if case:
                    memories += format_case_memory(case) + "\n\n"

        elif arm_name == "Strategy":
            for source_id in retrieval["shared_source_ids"]:
                strategy = strategies.get(source_id)
                if strategy:
                    memories += format_strategy_memory(strategy) + "\n\n"

        elif arm_name == "Paired":
            for source_id in retrieval["shared_source_ids"]:
                case = cases.get(source_id)
                strategy = strategies.get(source_id)
                if case:
                    memories += format_case_memory(case) + "\n"
                if strategy:
                    memories += format_strategy_memory(strategy) + "\n\n"

        # None arm: no memories

        # Build prompt
        prompt = build_prompt(target, memories)

        # Call API
        print(f"  [{i+1}/{len(targets)}] {target_id[:30]}...")

        try:
            # Format as messages for LLM client
            messages = [{"role": "user", "content": prompt}]

            result_data = call_once_with_metadata(
                messages,
                max_tokens=2048,
                temperature=0.7,
                timeout=180
            )

            response = result_data["text"]
            time.sleep(CALL_DELAY)

            # Parse answer from response
            predicted_answer = parse_answer(response)

            # Evaluate
            em = evaluate_exact_match(predicted_answer, gold_answer)

            result = {
                "target_id": target_id,
                "arm": arm_name,
                "gold_answer": gold_answer,
                "predicted_answer": predicted_answer,
                "exact_match": em,
                "response": response,
                "shared_source_ids": retrieval["shared_source_ids"]
            }

            results.append(result)

            status = "✓" if em else "✗"
            print(f"    {status} Predicted: {predicted_answer}, Gold: {gold_answer}")

        except Exception as e:
            print(f"    ERROR: {e}")
            result = {
                "target_id": target_id,
                "arm": arm_name,
                "gold_answer": gold_answer,
                "predicted_answer": None,
                "exact_match": False,
                "error": str(e),
                "shared_source_ids": retrieval["shared_source_ids"]
            }
            results.append(result)

    print()
    arm_em = sum(r["exact_match"] for r in results) / len(results) if results else 0.0
    print(f"{arm_name} arm: {arm_em*100:.1f}% EM ({sum(r['exact_match'] for r in results)}/{len(results)})")
    print()

    return results

def parse_answer(response: str) -> Any:
    """Extract answer from model response."""
    # Look for ANSWER: line
    lines = response.split("\n")
    for line in lines:
        if line.strip().startswith("ANSWER:"):
            answer_str = line.strip()[7:].strip()
            # Try to parse as number
            try:
                # Check if percentage (contains %)
                is_percentage = "%" in answer_str

                # Remove common formatting
                answer_str = answer_str.replace(",", "").replace("$", "").replace("%", "")
                if answer_str:
                    value = float(answer_str)
                    # Convert percentage to decimal if needed
                    if is_percentage:
                        value = value / 100.0
                    return value
            except:
                return answer_str

    # Fallback: return last number in response
    import re
    numbers = re.findall(r'-?\d+\.?\d*', response)
    if numbers:
        try:
            return float(numbers[-1])
        except:
            pass

    return None

def evaluate_exact_match(predicted, gold, tolerance=0.01) -> bool:
    """Evaluate exact match with numerical tolerance.

    Note: Stage 36 uses answer-only evaluation (not program execution).
    This is less strict than official FinQA program execution evaluation.
    We use 1% relative tolerance for small numbers (<1) to handle precision loss
    from model text output (e.g., 0.0356 vs 0.03558).
    """
    if predicted is None or gold is None:
        return False

    try:
        pred_num = float(predicted)
        gold_num = float(gold)

        # Use relative tolerance for all non-zero numbers
        if abs(gold_num) > 0:
            return abs(pred_num - gold_num) / abs(gold_num) < tolerance
        else:
            # For zero, use absolute tolerance
            return abs(pred_num - gold_num) < tolerance

    except:
        # String comparison
        return str(predicted).strip().lower() == str(gold).strip().lower()

def analyze_transitions(all_results: Dict[str, List[Dict]]):
    """Analyze per-query transitions across arms."""
    print("=" * 80)
    print("TRANSITION PATTERN ANALYSIS")
    print("=" * 80)
    print()

    # Build per-query EM matrix
    targets = set(r["target_id"] for results in all_results.values() for r in results)

    query_results = {}
    for target_id in targets:
        query_results[target_id] = {}
        for arm_name, results in all_results.items():
            result = next((r for r in results if r["target_id"] == target_id), None)
            if result:
                query_results[target_id][arm_name] = result["exact_match"]

    # Count transition patterns
    transitions = {
        "none_wrong_case_correct": 0,
        "none_wrong_strategy_correct": 0,
        "none_wrong_paired_correct": 0,
        "case_correct_strategy_wrong": 0,
        "case_wrong_strategy_correct": 0,
        "paired_beats_both": 0,
        "paired_worse_than_best": 0,
        "all_wrong": 0,
        "all_correct": 0,
    }

    transition_examples = {key: [] for key in transitions.keys()}

    for target_id, arms in query_results.items():
        none_em = arms.get("None", False)
        case_em = arms.get("Case", False)
        strategy_em = arms.get("Strategy", False)
        paired_em = arms.get("Paired", False)

        # None → X transitions
        if not none_em and case_em:
            transitions["none_wrong_case_correct"] += 1
            transition_examples["none_wrong_case_correct"].append(target_id)

        if not none_em and strategy_em:
            transitions["none_wrong_strategy_correct"] += 1
            transition_examples["none_wrong_strategy_correct"].append(target_id)

        if not none_em and paired_em:
            transitions["none_wrong_paired_correct"] += 1
            transition_examples["none_wrong_paired_correct"].append(target_id)

        # Case vs Strategy
        if case_em and not strategy_em:
            transitions["case_correct_strategy_wrong"] += 1
            transition_examples["case_correct_strategy_wrong"].append(target_id)

        if not case_em and strategy_em:
            transitions["case_wrong_strategy_correct"] += 1
            transition_examples["case_wrong_strategy_correct"].append(target_id)

        # Paired complementarity
        best_single = case_em or strategy_em
        if paired_em and not best_single:
            transitions["paired_beats_both"] += 1
            transition_examples["paired_beats_both"].append(target_id)

        if not paired_em and best_single:
            transitions["paired_worse_than_best"] += 1
            transition_examples["paired_worse_than_best"].append(target_id)

        # All correct/wrong
        if none_em and case_em and strategy_em and paired_em:
            transitions["all_correct"] += 1

        if not (none_em or case_em or strategy_em or paired_em):
            transitions["all_wrong"] += 1
            transition_examples["all_wrong"].append(target_id)

    # Print transition counts
    n_targets = len(query_results)
    print(f"Total queries: {n_targets}")
    print()

    print("Transition patterns:")
    for pattern, count in transitions.items():
        pct = count / n_targets * 100 if n_targets > 0 else 0
        print(f"  {pattern}: {count} ({pct:.1f}%)")
        if transition_examples[pattern][:2]:
            print(f"    Examples: {', '.join(transition_examples[pattern][:2])}")
    print()

    return transitions, query_results

def correlate_with_diagnostics(
    query_results: Dict[str, Dict[str, bool]],
    retrieval_cache: List[Dict],
    alignment_data: List[Dict]
):
    """Correlate EM with semantic similarity and reasoning alignment."""
    print("=" * 80)
    print("CORRELATION WITH DIAGNOSTICS")
    print("=" * 80)
    print()

    # Build alignment lookup
    alignment_lookup = {}
    for entry in alignment_data:
        key = (entry["target_id"], entry["source_id"])
        alignment_lookup[key] = entry

    # For each query-arm, compute average alignment of retrieved sources
    correlations = []

    for target_id, arms in query_results.items():
        # Get retrieval for this target
        retrieval = next((r for r in retrieval_cache if r["target_id"] == target_id), None)
        if not retrieval:
            continue

        # Compute average diagnostics across top-3 sources
        semantic_sims = []
        family_overlaps = []
        multiset_sims = []
        structure_aligns = []

        for source_id in retrieval["shared_source_ids"]:
            key = (target_id, source_id)
            alignment = alignment_lookup.get(key)
            if alignment:
                semantic_sims.append(alignment["semantic_similarity"])
                family_overlaps.append(alignment["operation_family_overlap"])
                multiset_sims.append(alignment["operation_multiset_similarity"])
                structure_aligns.append(alignment["structure_alignment"])

        if not semantic_sims:
            continue

        avg_semantic = sum(semantic_sims) / len(semantic_sims)
        avg_family = sum(family_overlaps) / len(family_overlaps)
        avg_multiset = sum(multiset_sims) / len(multiset_sims)
        avg_structure = sum(structure_aligns) / len(structure_aligns)

        # Record EM for each arm
        for arm_name, em in arms.items():
            correlations.append({
                "target_id": target_id,
                "arm": arm_name,
                "exact_match": em,
                "avg_semantic_similarity": avg_semantic,
                "avg_operation_family_overlap": avg_family,
                "avg_operation_multiset_similarity": avg_multiset,
                "avg_structure_alignment": avg_structure
            })

    # Compute Spearman correlations per arm
    from scipy.stats import spearmanr
    import numpy as np

    print("Spearman correlations (EM vs diagnostics):")
    print()

    for arm_name in ["None", "Case", "Strategy", "Paired"]:
        arm_data = [c for c in correlations if c["arm"] == arm_name]
        if len(arm_data) < 10:  # Need minimum samples
            continue

        ems = [c["exact_match"] for c in arm_data]
        semantics = [c["avg_semantic_similarity"] for c in arm_data]
        families = [c["avg_operation_family_overlap"] for c in arm_data]
        multisets = [c["avg_operation_multiset_similarity"] for c in arm_data]
        structures = [c["avg_structure_alignment"] for c in arm_data]

        # Check for variance
        if np.var(ems) == 0:
            print(f"{arm_name} arm: All same EM, cannot compute correlation")
            continue

        corr_sem, _ = spearmanr(ems, semantics)
        corr_fam, _ = spearmanr(ems, families)
        corr_multi, _ = spearmanr(ems, multisets)
        corr_struct, _ = spearmanr(ems, structures)

        print(f"{arm_name} arm:")
        print(f"  EM vs Semantic Similarity:         ρ = {corr_sem:.3f}")
        print(f"  EM vs Operation Family Overlap:    ρ = {corr_fam:.3f}")
        print(f"  EM vs Operation Multiset Sim:      ρ = {corr_multi:.3f}")
        print(f"  EM vs Structure Alignment:         ρ = {corr_struct:.3f}")
        print()

    return correlations

def main():
    print("=" * 80)
    print("STAGE 36: Downstream 4-Arm Experiment")
    print("=" * 80)
    print()

    # Load data
    print("Loading experiment data...")
    data = load_experiment_data()
    print()

    # Execute each arm
    all_results = {}

    for arm_name in ["None", "Case", "Strategy", "Paired"]:
        results = execute_arm(
            arm_name,
            data["targets"],
            data["retrieval_cache"],
            data["cases"],
            data["strategies"]
        )
        all_results[arm_name] = results

        # Save intermediate results
        output_file = os.path.join(
            ROOT,
            f"pilot/stage36_paired_abstraction/results_{arm_name.lower()}.json"
        )
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Saved {arm_name} results to {output_file}")
        print()

    # Aggregate analysis
    print("=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)
    print()

    for arm_name, results in all_results.items():
        em_rate = sum(r["exact_match"] for r in results) / len(results)
        n_correct = sum(r["exact_match"] for r in results)
        print(f"{arm_name:12s}: {em_rate*100:5.1f}% EM  ({n_correct}/{len(results)} correct)")
    print()

    # Transition analysis
    transitions, query_results = analyze_transitions(all_results)

    # Correlation analysis
    correlations = correlate_with_diagnostics(
        query_results,
        data["retrieval_cache"],
        data["alignment"]
    )

    # Save all results
    final_output = {
        "aggregate": {
            arm_name: {
                "em_rate": sum(r["exact_match"] for r in results) / len(results),
                "n_correct": sum(r["exact_match"] for r in results),
                "n_total": len(results)
            }
            for arm_name, results in all_results.items()
        },
        "transitions": transitions,
        "query_results": query_results,
        "correlations": correlations
    }

    output_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/experiment_results.json")
    with open(output_file, 'w') as f:
        json.dump(final_output, f, indent=2)

    print(f"Saved final results to {output_file}")
    print()
    print("✓ Downstream experiment complete")

if __name__ == "__main__":
    main()
