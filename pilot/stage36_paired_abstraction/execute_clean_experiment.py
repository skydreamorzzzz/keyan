#!/usr/bin/env python3
"""
Execute Clean Experiment

Run Clean-FN vs Clean-FN+Sketch comparison (448 API calls).

Cost: 2 arms × 224 queries = 448 API calls
Model: DeepSeek-V4-Flash (deepseek-chat)
Temperature: 0
"""

import json
import os
import sys
import time
from openai import OpenAI
from typing import Dict, List

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from clean_experiment_protocol_v2 import CleanExperimentProtocol


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def call_deepseek_api(prompt: str, client: OpenAI) -> str:
    """Call DeepSeek API with temperature=0."""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"    API Error: {e}")
        return None


def execute_arm(arm_name: str, arm_type: str, protocol: CleanExperimentProtocol, client: OpenAI) -> List[Dict]:
    """Execute one arm of the experiment."""

    print(f"\n{'='*80}")
    print(f"EXECUTING ARM: {arm_name}")
    print(f"{'='*80}\n")

    # Generate prompts
    print("Generating prompts...")
    prompt_records = protocol.generate_arm_data(arm_type)
    total = len(prompt_records)
    print(f"  Total queries: {total}")
    print()

    # Execute queries
    results = []
    failed = []

    for i, record in enumerate(prompt_records, 1):
        target_id = record['target_id']

        if i % 10 == 0:
            print(f"[{i}/{total}] Processing {target_id}...")

        # Call API
        response_text = call_deepseek_api(record['prompt'], client)

        if response_text is None:
            print(f"  ❌ {target_id}: API call failed")
            failed.append(target_id)
            continue

        # Save result
        result = {
            'target_id': target_id,
            'arm': arm_type,
            'prompt': record['prompt'],
            'response': response_text,
            'source_ids': record['source_ids'],
            'gold_program': record['gold_program'],
            'gold_answer': record['gold_answer']
        }
        results.append(result)

        # Rate limiting: small delay
        if i < total:
            time.sleep(0.1)

    print()
    print(f"Completed: {len(results)}/{total} succeeded")
    if failed:
        print(f"Failed: {len(failed)} queries")
        for tid in failed[:10]:
            print(f"  {tid}")
    print()

    # Save results
    output_file = f'{BASE_PATH}/results_{arm_type}.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Saved: {output_file}")

    return results, failed


def main():
    """Execute clean experiment."""

    print("="*80)
    print("CLEAN EXPERIMENT EXECUTION")
    print("="*80)
    print()

    # Check API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Initialize protocol
    protocol = CleanExperimentProtocol()
    protocol.load_data()

    print("="*80)
    print("EXPERIMENT PARAMETERS")
    print("="*80)
    print(f"Model: deepseek-chat")
    print(f"Temperature: 0.0")
    print(f"Queries per arm: 224")
    print(f"Total API calls: 448 (2 arms × 224)")
    print(f"Strategy source: strategies_format_neutral_clean_v2.json")
    print(f"Contamination: 4/78 (5.1%, filtered)")
    print()

    input("Press ENTER to start execution (or Ctrl+C to cancel)...")
    print()

    start_time = time.time()

    # Execute Arm 1: Clean-FN
    results_fn, failed_fn = execute_arm(
        "Clean Format-Neutral",
        "clean_fn",
        protocol,
        client
    )

    # Execute Arm 2: Clean-FN+Sketch
    results_fns, failed_fns = execute_arm(
        "Clean Format-Neutral + Sketch",
        "clean_fn_sketch",
        protocol,
        client
    )

    elapsed = time.time() - start_time

    # Summary
    print()
    print("="*80)
    print("EXECUTION COMPLETE")
    print("="*80)
    print(f"Clean-FN: {len(results_fn)}/224 succeeded")
    print(f"Clean-FN+Sketch: {len(results_fns)}/224 succeeded")
    print(f"Total API calls: {len(results_fn) + len(results_fns)}")
    print(f"Elapsed time: {elapsed/60:.1f} minutes")
    print()

    if failed_fn or failed_fns:
        print("⚠️  Some queries failed:")
        print(f"  Clean-FN: {len(failed_fn)} failures")
        print(f"  Clean-FN+Sketch: {len(failed_fns)} failures")
        print()

    print("Next steps:")
    print("  1. Evaluate results with canonical_evaluator_v2.py")
    print("  2. Statistical analysis (McNemar + Bootstrap CI)")
    print("  3. Generate final report")
    print()
    print("="*80)


if __name__ == '__main__':
    main()
