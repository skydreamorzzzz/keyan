#!/usr/bin/env python3
"""
Stage 39: Full 224-Query Validation
"""

import json
import os
import sys
import time
from typing import List, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from stage39_prompts import construct_prompt
from stage39_memory_constructors import (
    construct_case_memory,
    construct_format_neutral_memory,
    construct_format_neutral_with_binding_memory,
    construct_grounded_sketch_memory
)

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


def load_targets() -> List[Dict]:
    """Load all 224 target queries."""
    with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)

    assert len(targets) == 224, f"Expected 224 targets, got {len(targets)}"
    return targets


def load_memory_data():
    """Load all memory representations."""

    # Cases (from cases_clean.json)
    with open(f'{BASE_PATH}/cases_clean.json') as f:
        cases = json.load(f)
    case_map = {c['source_experience_id']: c for c in cases}

    # Format-Neutral Strategies
    with open(f'{BASE_PATH}/strategies_format_neutral.json') as f:
        strategies = json.load(f)
    strategy_map = {s['source_experience_id']: s for s in strategies}

    # Grounded Sketches
    with open(f'{BASE_PATH}/grounded_sketches.json') as f:
        sketches = json.load(f)
    sketch_map = {s['source_experience_id']: s for s in sketches}

    return case_map, strategy_map, sketch_map


def run_arm(targets: List[Dict], arm_name: str,
            memory_constructor, memory_data: Dict) -> List[Dict]:
    """Run full 224 queries for one arm."""

    results = []
    output_file = f'{BASE_PATH}/results_{arm_name}_full224.json'

    # Check if partial results exist
    if os.path.exists(output_file):
        with open(output_file) as f:
            results = json.load(f)
        print(f"Resuming {arm_name} from {len(results)}/224")

    for i, target in enumerate(targets):
        # Skip if already done
        if i < len(results):
            continue

        print(f"[{arm_name}] {i+1}/224: {target['id']}")

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
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)

            # Rate limit
            time.sleep(0.5)

        except Exception as e:
            print(f"  ERROR: {e}")
            # Continue to next query
            continue

    print(f"[{arm_name}] Complete: {len(results)}/224")
    return results


def main():
    """Run Stage 39 full 224-query validation."""

    print("="*80)
    print("STAGE 39: FULL 224-QUERY VALIDATION")
    print("="*80)

    # Load data
    targets = load_targets()
    case_map, strategy_map, sketch_map = load_memory_data()

    print(f"\nLoaded {len(targets)} target queries")
    print(f"Memory data: {len(case_map)} cases, {len(strategy_map)} strategies, {len(sketch_map)} sketches")

    # Case arm: REUSE from Stage 37
    print(f"\n{'='*80}")
    print("Case arm: REUSING results_case_expanded.json")
    print(f"{'='*80}")
    # Verify file exists
    assert os.path.exists(f'{BASE_PATH}/results_case_expanded.json')

    # Format-Neutral Strategy arm
    print(f"\n{'='*80}")
    print("Running Format-Neutral Strategy arm...")
    print(f"{'='*80}")

    fn_results = run_arm(
        targets=targets,
        arm_name='format_neutral',
        memory_constructor=construct_format_neutral_memory,
        memory_data=strategy_map
    )

    # Format-Neutral + Binding arm
    print(f"\n{'='*80}")
    print("Running Format-Neutral + Binding arm...")
    print(f"{'='*80}")

    fnb_results = run_arm(
        targets=targets,
        arm_name='format_neutral_binding',
        memory_constructor=construct_format_neutral_with_binding_memory,
        memory_data=strategy_map
    )

    # Grounded Sketch arm
    print(f"\n{'='*80}")
    print("Running Grounded Sketch arm...")
    print(f"{'='*80}")

    gs_results = run_arm(
        targets=targets,
        arm_name='grounded_sketch',
        memory_constructor=construct_grounded_sketch_memory,
        memory_data=sketch_map
    )

    print(f"\n{'='*80}")
    print("FULL 224 VALIDATION COMPLETE")
    print(f"{'='*80}")
    print(f"Total API calls: {len(fn_results) + len(fnb_results) + len(gs_results)}")
    print(f"\nNext: Run stage39_evaluator.py for program-level evaluation")


if __name__ == '__main__':
    main()
