#!/usr/bin/env python3
"""
Fidelity Death Experiment - Execution Script

Phase A: 30-query manipulation pilot (120 API calls)
Phase B: Full 224-query experiment (896 API calls)

Design:
- 4 corruption levels: 0%, 10%, 25%, 50%
- Paired comparison with fixed retrieval
- Deterministic corruption from manifest
- Complete provenance tracking
"""

import json
import os
import sys
import time
from openai import OpenAI
from typing import Dict, List

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'
SOURCE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

sys.path.insert(0, SOURCE_PATH)


def render_document(target: Dict) -> str:
    """Render complete document."""
    parts = []

    if 'pre_text' in target and target['pre_text']:
        parts.append("# Document Context\n")
        parts.append(" ".join(target['pre_text']))
        parts.append("\n")

    if 'table' in target and target['table']:
        parts.append("\n# Table\n")
        for row in target['table']:
            parts.append(" | ".join(str(cell) for cell in row))
        parts.append("\n")

    if 'post_text' in target and target['post_text']:
        parts.append("\n# Additional Context\n")
        parts.append(" ".join(target['post_text']))
        parts.append("\n")

    return "\n".join(parts)


def build_memory_section(
    source_ids: List[str],
    corruption_level: str,
    manifest: Dict,
    target_id: str,
    faithful_map: Dict,
    corrupted_map: Dict
) -> str:
    """Build memory section with appropriate corruption."""

    memory_parts = ["# Relevant Experience\n"]

    # Get corruption assignments for this target
    assignments = manifest[corruption_level]
    target_assignments = {
        a['source_id']: a for a in assignments
        if a['target_id'] == target_id
    }

    for source_id in source_ids:
        assignment = target_assignments.get(source_id)

        if not assignment:
            # Source not in faithful set, skip
            continue

        if assignment['corrupted']:
            # Use corrupted version
            corruption_type = assignment['corruption_type']
            key = f"{source_id}_{corruption_type}"

            if key in corrupted_map:
                source = corrupted_map[key]
            else:
                # Fallback to faithful if corruption failed
                if source_id in faithful_map:
                    source = faithful_map[source_id]
                else:
                    continue
        else:
            # Use faithful version
            if source_id in faithful_map:
                source = faithful_map[source_id]
            else:
                continue

        # Format source
        memory_parts.append(f"\n## Pattern: {source.get('strategy_name', 'N/A')}")
        memory_parts.append(f"\nWhen to use: {source.get('problem_pattern', '')}")
        memory_parts.append(f"\nReasoning approach:")
        memory_parts.append(source.get('reasoning_steps', ''))
        memory_parts.append(f"\nOperand identification:")
        memory_parts.append(source.get('operand_roles', ''))
        memory_parts.append("")

    return "\n".join(memory_parts)


SYSTEM_PROMPT = """You are a financial reasoning assistant specialized in generating executable programs for financial question answering.

Your task: Given a financial document with tables and a question, generate an executable FinQA program that answers the question.

FinQA Program Syntax:
- Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average
- Arguments: numbers, const_X (e.g. const_100, const_m1), #N (reference to step N result), table row labels
- Format: operation(arg1, arg2)
- Multi-step: operation1(a, b), operation2(#0, c), operation3(#1, d)
- Example: divide(100, 50), multiply(#0, 2) → result = 4

Requirements:
- Extract values from the CURRENT document
- Generate complete, executable programs
- Use exact values from tables and text

Output Format:
PROGRAM: <executable FinQA program>
ANSWER: <numerical answer>
"""

OUTPUT_INSTRUCTION = """Generate an executable FinQA program to answer the question using values from the current document.

PROGRAM: <your executable program>
ANSWER: <your numerical answer>"""


def build_prompt(
    target: Dict,
    corruption_level: str,
    manifest: Dict,
    faithful_map: Dict,
    corrupted_map: Dict
) -> str:
    """Build complete prompt."""

    document = render_document(target)
    question = target['qa']['question']
    source_ids = target['shared_source_ids']

    memory = build_memory_section(
        source_ids,
        corruption_level,
        manifest,
        target['id'],
        faithful_map,
        corrupted_map
    )

    return f"""{SYSTEM_PROMPT}

{document}

# Question

{question}

{memory}

{OUTPUT_INSTRUCTION}
"""


def run_experiment_arm(
    arm_name: str,
    corruption_level: str,
    targets: List[Dict],
    manifest: Dict,
    faithful_map: Dict,
    corrupted_map: Dict,
    client: OpenAI,
    pilot_only: bool = False
) -> List[Dict]:
    """Run one experimental arm."""

    print(f"\n{'='*80}")
    print(f"ARM: {arm_name} (corruption level: {corruption_level})")
    print(f"{'='*80}\n")

    if pilot_only:
        # Use first 30 targets for pilot
        targets_to_run = targets[:30]
        print(f"PILOT MODE: Running first 30 targets")
    else:
        targets_to_run = targets
        print(f"FULL MODE: Running all {len(targets)} targets")

    results = []

    for i, target in enumerate(targets_to_run, 1):
        target_id = target['id']

        if i % 10 == 0:
            print(f"[{i}/{len(targets_to_run)}] Processing {target_id}...")

        # Build prompt
        prompt = build_prompt(
            target,
            corruption_level,
            manifest,
            faithful_map,
            corrupted_map
        )

        # Call API
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2000
            )

            response_text = response.choices[0].message.content

            result = {
                'target_id': target_id,
                'arm': arm_name,
                'corruption_level': corruption_level,
                'prompt': prompt,
                'response': response_text,
                'source_ids': target['shared_source_ids'],
                'gold_program': target['qa']['program'],
                'gold_answer': target['qa']['exe_ans'],
                'model': 'deepseek-chat',
                'temperature': 0.0,
                'timestamp': time.time()
            }

            results.append(result)

        except Exception as e:
            print(f"  ❌ {target_id}: {e}")
            continue

        # Rate limiting
        if i < len(targets_to_run):
            time.sleep(0.1)

    print(f"\nCompleted: {len(results)}/{len(targets_to_run)}")
    return results


def main():
    """Execute fidelity experiment."""

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['pilot', 'full'], required=True)
    parser.add_argument('--levels', nargs='+', default=['0%', '10%', '25%', '50%'])
    args = parser.parse_args()

    print("="*80)
    print("FIDELITY DEATH EXPERIMENT")
    print("="*80)
    print(f"Phase: {args.phase}")
    print(f"Levels: {args.levels}")
    print()

    # Check API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Load data
    print("Loading data...")

    with open(f'{SOURCE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)

    with open(f'{BASE_PATH}/corruption_manifest.json') as f:
        manifest_data = json.load(f)

    with open(f'{SOURCE_PATH}/strategies_format_neutral_clean_v2.json') as f:
        strategies = json.load(f)

    with open(f'{BASE_PATH}/corrupted_sources.json') as f:
        corrupted_sources = json.load(f)

    # Load QC to get faithful set
    with open(f'{SOURCE_PATH}/strategy_qc_audit_v2_post_regen.json') as f:
        qc_data = json.load(f)

    contaminated_ids = {r['source_id'] for r in qc_data['audit_results'] if r['contaminated']}
    faithful_sources = [s for s in strategies if s['source_experience_id'] not in contaminated_ids]
    faithful_map = {s['source_experience_id']: s for s in faithful_sources}
    corrupted_map = corrupted_sources

    manifest = manifest_data['manifest']

    print(f"  Targets: {len(targets)}")
    print(f"  Faithful sources: {len(faithful_map)}")
    print(f"  Corrupted versions: {len(corrupted_map)}")
    print()

    pilot_mode = (args.phase == 'pilot')

    # Run arms
    start_time = time.time()
    all_results = {}

    for level in args.levels:
        arm_name = f"Corruption_{level}"

        results = run_experiment_arm(
            arm_name,
            level,
            targets,
            manifest,
            faithful_map,
            corrupted_map,
            client,
            pilot_only=pilot_mode
        )

        all_results[arm_name] = results

        # Save incrementally
        output_file = f'{BASE_PATH}/results_{args.phase}_{level.replace("%", "pct")}.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Saved: {output_file}\n")

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "="*80)
    print("EXECUTION COMPLETE")
    print("="*80)

    total_calls = sum(len(results) for results in all_results.values())
    print(f"Total API calls: {total_calls}")
    print(f"Elapsed time: {elapsed/60:.1f} minutes")
    print()

    for arm_name, results in all_results.items():
        print(f"{arm_name}: {len(results)} responses")

    print()
    print("Next: Evaluate results")
    print("  python3 evaluate_fidelity_experiment.py")


if __name__ == '__main__':
    main()
