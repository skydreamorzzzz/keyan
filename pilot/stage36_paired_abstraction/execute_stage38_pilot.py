#!/usr/bin/env python3
"""
Stage 38 Pilot: Format-Neutral Strategy + Grounded Program Sketch

Tests:
1. Format-Neutral Strategy (natural language, no operator lists)
2. Grounded Program Sketch (explicit operand binding instructions)

Against:
- Old Strategy (from Stage 37, reuse responses)
- Case (from Stage 37, reuse responses)

Goal: Isolate prompt-format confound from genuine grounding failure.
"""

import json
import os
import sys
from typing import List, Dict, Any
import time

# Add parent for LLM infrastructure
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

def call_llm(messages: list, temperature: float = 0.0) -> dict:
    """Call LLM using existing infrastructure."""
    from pilot.llm import call_once_with_metadata

    result = call_once_with_metadata(
        messages,
        temperature=temperature,
        timeout=180
    )
    return result

BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

def load_pilot_sample() -> Dict[str, List[str]]:
    """Load pilot sample target IDs."""
    with open(f'{BASE_PATH}/stage38_pilot_sample.json') as f:
        return json.load(f)


def load_targets(target_ids: List[str]) -> List[Dict]:
    """Load target queries by IDs."""
    with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
        all_targets = json.load(f)

    target_map = {t['id']: t for t in all_targets}
    return [target_map[tid] for tid in target_ids if tid in target_map]


def load_format_neutral_strategies() -> Dict[str, Dict]:
    """Load format-neutral Strategy representations."""
    with open(f'{BASE_PATH}/strategies_format_neutral.json') as f:
        strategies = json.load(f)
    return {s['source_experience_id']: s for s in strategies}


def load_grounded_sketches() -> Dict[str, Dict]:
    """Load Grounded Program Sketch representations."""
    with open(f'{BASE_PATH}/grounded_sketches.json') as f:
        sketches = json.load(f)
    return {s['source_experience_id']: s for s in sketches}


def construct_format_neutral_strategy_memory(source_ids: List[str],
                                               strategy_map: Dict) -> str:
    """Construct Format-Neutral Strategy memory (no operator lists)."""
    memory_parts = []

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strat = strategy_map[source_id]

        memory_parts.append(f"Strategy {source_id}: {strat['strategy_name']}")
        memory_parts.append(f"Problem pattern: {strat['problem_pattern']}")
        memory_parts.append(f"\nReasoning steps:\n{strat['reasoning_steps']}")
        memory_parts.append(f"\nOperand roles:\n{strat['operand_roles']}")

        if strat.get('formula_template'):
            memory_parts.append(f"Formula: {strat['formula_template']}")

        if strat.get('units_convention'):
            memory_parts.append(f"Units: {strat['units_convention']}")

        memory_parts.append("\n" + "="*60 + "\n")

    memory_parts.append("""
IMPORTANT: Generate a fully executable FinQA program with concrete operands
from the CURRENT document. Do NOT output just operator names.""")

    return "\n".join(memory_parts)


def construct_grounded_sketch_memory(source_ids: List[str],
                                      sketch_map: Dict) -> str:
    """Construct Grounded Program Sketch memory."""
    memory_parts = []

    for source_id in source_ids:
        if source_id not in sketch_map:
            continue

        sketch = sketch_map[source_id]

        memory_parts.append(f"Pattern {source_id}: {sketch['strategy_name']}")
        memory_parts.append(f"Problem: {sketch['problem_pattern']}")
        memory_parts.append(f"\nProgram sketch:\n{sketch['program_sketch']}")
        memory_parts.append(f"\nOperand bindings:\n{sketch['operand_bindings']}")
        memory_parts.append(f"\n{sketch['binding_instruction']}")
        memory_parts.append("\n" + "="*60 + "\n")

    return "\n".join(memory_parts)


def construct_prompt(target: Dict, memory_section: str, arm_name: str) -> str:
    """Construct prompt for query."""

    # Build document context
    pre_text = "\n".join(target['pre_text'])
    post_text = "\n".join(target['post_text'])

    # Build table
    table_rows = []
    for row in target['table_ori']:
        table_rows.append(" | ".join(row))
    table_str = "\n".join(table_rows)

    prompt = f"""You are a financial reasoning assistant. Given a document with text and a table, answer the question by generating a FinQA program.

Document context:
{pre_text}

Table:
{table_str}

{post_text}

Question: {target['qa']['question']}

{memory_section}

Generate a FinQA program to answer the question. The program should be a sequence of operations with concrete operands.

Output format:
PROGRAM: operation(arg1, arg2), operation(#0, arg3), ...
ANSWER: [final numeric answer]

Your response:"""

    return prompt


def run_pilot_arm(targets: List[Dict], arm_name: str,
                  memory_constructor, memory_data: Dict) -> List[Dict]:
    """Run pilot experiment for one arm."""

    results = []

    for i, target in enumerate(targets):
        print(f"[{arm_name}] {i+1}/{len(targets)}: {target['id']}")

        # Get source IDs for this target
        source_ids = target['shared_source_ids']

        # Construct memory
        memory_section = memory_constructor(source_ids, memory_data)

        # Construct prompt
        prompt = construct_prompt(target, memory_section, arm_name)

        # Call model
        try:
            messages = [{"role": "user", "content": prompt}]
            llm_result = call_llm(messages, temperature=0.0)

            result = {
                'target_id': target['id'],
                'arm': arm_name,
                'response': llm_result['text'],
                'runtime': llm_result.get('runtime', 0),
                'source_ids': source_ids,
                'gold_answer': target['qa']['exe_ans']
            }

            results.append(result)

            # Save incrementally
            output_file = f'{BASE_PATH}/results_{arm_name}_pilot.json'
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)

            print(f"  Saved to {output_file}")

            # Rate limit
            time.sleep(0.5)

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    return results


def main():
    """Run Stage 38 pilot experiment."""

    print("="*80)
    print("STAGE 38 PILOT: Format Confound Test")
    print("="*80)

    # Load pilot sample
    sample = load_pilot_sample()

    # Flatten all target IDs
    all_target_ids = []
    for category, ids in sample.items():
        all_target_ids.extend(ids)

    print(f"\nPilot sample: {len(all_target_ids)} targets")
    for category, ids in sample.items():
        print(f"  {category}: {len(ids)}")

    # Load targets
    targets = load_targets(all_target_ids)
    print(f"\nLoaded {len(targets)} target queries")

    # Load memory data
    fn_strategies = load_format_neutral_strategies()
    grounded_sketches = load_grounded_sketches()

    print(f"\nMemory loaded:")
    print(f"  Format-neutral strategies: {len(fn_strategies)}")
    print(f"  Grounded sketches: {len(grounded_sketches)}")

    # Run arms (Case and Old Strategy will be reused from Stage 37)
    print(f"\n{'='*80}")
    print("Running Format-Neutral Strategy arm...")
    print(f"{'='*80}")

    fn_results = run_pilot_arm(
        targets=targets,
        arm_name='format_neutral_strategy',
        memory_constructor=construct_format_neutral_strategy_memory,
        memory_data=fn_strategies
    )

    print(f"\n{'='*80}")
    print("Running Grounded Program Sketch arm...")
    print(f"{'='*80}")

    gs_results = run_pilot_arm(
        targets=targets,
        arm_name='grounded_sketch',
        memory_constructor=construct_grounded_sketch_memory,
        memory_data=grounded_sketches
    )

    print(f"\n{'='*80}")
    print("PILOT COMPLETE")
    print(f"{'='*80}")
    print(f"Format-Neutral Strategy: {len(fn_results)} responses")
    print(f"Grounded Sketch: {len(gs_results)} responses")
    print(f"\nNext: Run program-level audit on pilot results")


if __name__ == '__main__':
    main()
