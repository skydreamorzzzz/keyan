#!/usr/bin/env python3
"""
Regenerate Remaining 10 Contaminated Sources

Second pass with stricter prompts for sources that still failed QC.
"""

import json
import os
import sys
from typing import Dict, List
from openai import OpenAI

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import parse_program_v2_strict


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def build_stricter_prompt(case: Dict, gold_ops: List[str], gold_has_100: bool, previous_issue: str) -> str:
    """
    Build EXTRA strict prompt based on what failed in first regeneration.
    """

    gold_program = case['program']
    question = case['question']
    gold_answer = case.get('exe_ans', case.get('answer', 'N/A'))

    ops_list = ', '.join(gold_ops)
    ops_count = len(gold_ops)

    # Specific constraints based on issue type
    specific_constraint = ""

    if "percentage conversion" in previous_issue.lower():
        specific_constraint = """
⚠️ CRITICAL: This source FAILED first regeneration due to percentage conversion mention.

ABSOLUTE PROHIBITION:
- Do NOT use the word "percentage" in reasoning_steps
- Do NOT use the word "percent" in reasoning_steps
- Do NOT mention "convert to percentage"
- Do NOT mention "express as percentage"
- The result is a DECIMAL RATIO, not a percentage
- Use terms like "ratio", "proportion", "decimal result" instead
"""
    elif "extra ops:" in previous_issue.lower() or "missing ops:" in previous_issue.lower():
        specific_constraint = f"""
⚠️ CRITICAL: This source FAILED first regeneration due to operation mismatch.

ABSOLUTE REQUIREMENT:
- The gold program has EXACTLY {ops_count} operation(s): {ops_list}
- Your strategy must describe EXACTLY these {ops_count} operation(s)
- Do NOT add operations not in gold program
- Do NOT omit operations from gold program
- Count the operations in your reasoning_steps and verify it matches
"""

    constraint_100 = ""
    if not gold_has_100:
        constraint_100 = """
SCALE CONSTRAINT:
- Gold program does NOT have const_100 or multiply by 100
- Result is DECIMAL (e.g., 0.025), NOT percentage (e.g., 2.5%)
- Do NOT mention multiplying by 100
"""

    prompt = f"""You are creating a Format-Neutral reasoning strategy. This is a SECOND ATTEMPT after the first failed QC.

## Previous Failure
{previous_issue}

## Solved Problem

Question: {question}

Gold Program: {gold_program}

Operations: {ops_list} (count: {ops_count})

Gold Answer: {gold_answer}

## CRITICAL CONSTRAINTS

{specific_constraint}

{constraint_100}

## Additional Rules

1. Use natural language, NOT executable code syntax
2. Use descriptive variable names (e.g., "numerator / denominator")
3. Describe reasoning steps without mentioning specific numbers
4. Formula template should match gold operations EXACTLY

## Output Format

Return ONLY valid JSON:

{{
  "strategy_name": "...",
  "problem_pattern": "...",
  "reasoning_steps": "Step 1: ...\\nStep 2: ...\\n...",
  "operand_roles": "- role1: ...\\n- role2: ...",
  "formula_template": "...",
  "units_convention": "..."
}}

BEFORE returning, verify:
- ✓ Operation count matches gold program ({ops_count})
- ✓ No percentage conversion mentions (if prohibited)
- ✓ No ×100 mentions (if prohibited)
"""

    return prompt


def regenerate_remaining_sources(api_key: str, remaining_ids: list, previous_issues: dict):
    """
    Regenerate remaining contaminated sources with stricter prompts.
    """

    print("="*80)
    print("REGENERATE REMAINING CONTAMINATED SOURCES (Pass 2)")
    print("="*80)
    print()

    # Load data
    with open(f'{BASE_PATH}/cases_clean.json') as f:
        cases = json.load(f)
    case_map = {c['source_experience_id']: c for c in cases}

    with open(f'{BASE_PATH}/strategies_format_neutral_clean_v2.json') as f:
        strategies = json.load(f)
    strategy_map = {s['source_experience_id']: s for s in strategies}

    print(f"Regenerating {len(remaining_ids)} sources with stricter constraints")
    print()

    # Regenerate
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    regenerated = []
    failed = []

    for i, source_id in enumerate(remaining_ids, 1):
        print(f"[{i}/{len(remaining_ids)}] Regenerating {source_id}...")
        print(f"  Previous issue: {previous_issues[source_id]}")

        case = case_map[source_id]
        gold_program = case['program']

        # Parse gold program
        steps, error = parse_program_v2_strict(gold_program)
        if steps is None:
            print(f"  ⚠️  Gold program parse failed")
            failed.append(source_id)
            continue

        gold_ops = [step[0] for step in steps]
        gold_has_100 = 'const_100' in gold_program or ', 100)' in gold_program

        # Build stricter prompt
        prompt = build_stricter_prompt(case, gold_ops, gold_has_100, previous_issues[source_id])

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2000
            )

            response_text = response.choices[0].message.content

            # Parse
            import re
            text = re.sub(r'```json\s*', '', response_text)
            text = re.sub(r'```\s*$', '', text)
            text = text.strip()

            strategy = json.loads(text)
            strategy['source_experience_id'] = source_id
            strategy['representation'] = 'format_neutral_strategy'
            strategy['regenerated'] = True
            strategy['regeneration_version'] = 'v2_clean_pass2'

            regenerated.append(strategy)
            print(f"  ✓ Regenerated successfully")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed.append(source_id)

    print()
    print(f"Pass 2 complete: {len(regenerated)} succeeded, {len(failed)} failed")
    print()

    # Update strategy map
    for strategy in regenerated:
        source_id = strategy['source_experience_id']
        # Replace in list
        for i, s in enumerate(strategies):
            if s['source_experience_id'] == source_id:
                strategies[i] = strategy
                break

    # Save
    with open(f'{BASE_PATH}/strategies_format_neutral_clean_v2.json', 'w') as f:
        json.dump(strategies, f, indent=2)

    print(f"Saved updated: strategies_format_neutral_clean_v2.json")
    print()

    return regenerated, failed


def main():
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    # Load post-regen audit to get remaining issues
    with open(f'{BASE_PATH}/strategy_qc_audit_v2_post_regen.json') as f:
        audit = json.load(f)

    remaining = [r for r in audit['audit_results'] if r['contaminated']]
    remaining_ids = [r['source_id'] for r in remaining]
    previous_issues = {r['source_id']: r['reason'] for r in remaining}

    regenerated, failed = regenerate_remaining_sources(api_key, remaining_ids, previous_issues)

    if not failed:
        print("✓ All remaining sources regenerated")
        print()
        print("Next: Run QC audit again to verify")
        print("  python3 strategy_qc_audit_v2_post_regen.py")
    else:
        print(f"⚠️  {len(failed)} sources still failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
