#!/usr/bin/env python3
"""
Regenerate Clean Format-Neutral Strategies

Regenerate 27 contaminated sources with strict constraints:
1. No operations not in gold program
2. No ×100 unless gold program has const_100
3. Temperature = 0
4. Deterministic QC after generation

Total cost: 27 API calls
"""

import json
import os
import sys
from typing import Dict, List
from openai import OpenAI

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import parse_program_v2_strict


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


# ============================================================================
# REGENERATION PROMPT
# ============================================================================

def build_regeneration_prompt(case: Dict, gold_ops: List[str], gold_has_100: bool) -> str:
    """
    Build strict prompt for regenerating Format-Neutral strategy.

    Constraints:
    - Only use operations from gold program
    - No ×100 unless gold has const_100
    """

    gold_program = case['program']
    question = case['question']
    gold_answer = case.get('exe_ans', case.get('answer', 'N/A'))

    ops_list = ', '.join(gold_ops)

    constraint_100 = ""
    if not gold_has_100:
        constraint_100 = """
CRITICAL CONSTRAINT:
- The gold program does NOT multiply by 100
- The result is a DECIMAL (e.g., 0.14645), NOT a percentage (e.g., 14.645%)
- Do NOT mention "multiply by 100" or "convert to percentage"
- Do NOT add percentage conversion steps
"""
    else:
        constraint_100 = """
NOTE: The gold program includes multiplication by 100 for percentage conversion.
"""

    prompt = f"""You are a financial reasoning expert. Your task is to create a Format-Neutral reasoning strategy for the following solved problem.

## Solved Problem

Question: {question}

Gold Program: {gold_program}

Gold Answer: {gold_answer}

Operations used: {ops_list}

## Task

Generate a Format-Neutral strategy abstraction with:
1. strategy_name: Short descriptive name (5-10 words)
2. problem_pattern: When this reasoning pattern applies (2-3 sentences)
3. reasoning_steps: Step-by-step reasoning in natural language (4-6 steps, numbered)
4. operand_roles: Description of each operand/value needed (bullet points)
5. formula_template: Mathematical formula using descriptive variable names (NOT FinQA syntax)
6. units_convention: How units should be handled

## STRICT CONSTRAINTS

MUST follow these rules:

1. **Operation Fidelity**: Only mention operations that appear in the gold program
   - Gold operations: {ops_list}
   - Do NOT add operations not in this list
   - Do NOT omit operations from this list

2. **Scale Fidelity**:
{constraint_100}

3. **Format**: Natural language reasoning, NOT executable code
   - Use descriptive variable names (e.g., "numerator", "denominator")
   - NOT FinQA syntax (e.g., NOT "divide(<value1>, <value2>)")

4. **Generalization**: Describe the reasoning pattern, not the specific numbers

## Output Format

Return ONLY a JSON object with these exact fields:

{{
  "strategy_name": "...",
  "problem_pattern": "...",
  "reasoning_steps": "Step 1: ...\\nStep 2: ...\\nStep 3: ...\\nStep 4: ...",
  "operand_roles": "- role1: ...\\n- role2: ...",
  "formula_template": "...",
  "units_convention": "..."
}}

Do NOT include markdown code fences, do NOT include explanations outside the JSON.
"""

    return prompt


# ============================================================================
# API CALLING
# ============================================================================

def call_deepseek_api(prompt: str, api_key: str) -> str:
    """
    Call DeepSeek API with temperature=0.

    Returns raw response text.
    """
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=2000
    )

    return response.choices[0].message.content


def parse_strategy_response(response_text: str) -> Dict:
    """
    Parse strategy JSON from response.

    Handles markdown code fences if present.
    """
    import re

    # Remove markdown code fences if present
    text = re.sub(r'```json\s*', '', response_text)
    text = re.sub(r'```\s*$', '', text)
    text = text.strip()

    try:
        strategy = json.loads(text)
        return strategy
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse error: {e}")
        print(f"  Response: {text[:200]}...")
        return None


# ============================================================================
# MAIN REGENERATION
# ============================================================================

def regenerate_contaminated_sources(api_key: str):
    """
    Regenerate 27 contaminated sources.
    """

    print("="*80)
    print("REGENERATE CLEAN FORMAT-NEUTRAL STRATEGIES")
    print("="*80)
    print()

    # Load data
    print("Loading data...")
    with open(f'{BASE_PATH}/cases_clean.json') as f:
        cases = json.load(f)
    case_map = {c['source_experience_id']: c for c in cases}

    with open(f'{BASE_PATH}/strategies_format_neutral.json') as f:
        strategies = json.load(f)
    strategy_map = {s['source_experience_id']: s for s in strategies}

    with open(f'{BASE_PATH}/strategy_qc_audit_v2.json') as f:
        audit = json.load(f)

    # Get contaminated source IDs
    contaminated_ids = [
        r['source_id'] for r in audit['audit_results']
        if r['contaminated']
    ]

    print(f"  Cases: {len(cases)}")
    print(f"  Strategies: {len(strategies)}")
    print(f"  Contaminated: {len(contaminated_ids)}")
    print()

    print("Contaminated sources:")
    for sid in contaminated_ids:
        reason = next(r['reason'] for r in audit['audit_results'] if r['source_id'] == sid)
        print(f"  {sid}: {reason}")
    print()

    # Confirm
    print(f"Will regenerate {len(contaminated_ids)} sources with {len(contaminated_ids)} API calls")
    print()

    # Regenerate each contaminated source
    regenerated = []
    failed = []

    for i, source_id in enumerate(contaminated_ids, 1):
        print(f"[{i}/{len(contaminated_ids)}] Regenerating {source_id}...")

        if source_id not in case_map:
            print(f"  ⚠️  Case not found, skipping")
            failed.append(source_id)
            continue

        case = case_map[source_id]
        gold_program = case['program']

        # Parse gold program to get operations
        steps, error = parse_program_v2_strict(gold_program)
        if steps is None:
            print(f"  ⚠️  Gold program parse failed: {error}")
            failed.append(source_id)
            continue

        gold_ops = [step[0] for step in steps]
        gold_has_100 = 'const_100' in gold_program or ', 100)' in gold_program or '(100,' in gold_program

        # Build prompt
        prompt = build_regeneration_prompt(case, gold_ops, gold_has_100)

        try:
            # Call API
            response_text = call_deepseek_api(prompt, api_key)

            # Parse response
            strategy = parse_strategy_response(response_text)

            if strategy is None:
                print(f"  ❌ Parse failed")
                failed.append(source_id)
                continue

            # Add metadata
            strategy['source_experience_id'] = source_id
            strategy['representation'] = 'format_neutral_strategy'
            strategy['regenerated'] = True
            strategy['regeneration_version'] = 'v2_clean'

            regenerated.append(strategy)
            print(f"  ✓ Regenerated successfully")

        except Exception as e:
            print(f"  ❌ API error: {e}")
            failed.append(source_id)

    print()
    print("="*80)
    print(f"Regeneration complete: {len(regenerated)} succeeded, {len(failed)} failed")
    print("="*80)
    print()

    if failed:
        print("Failed sources:")
        for sid in failed:
            print(f"  {sid}")
        print()

    # Build complete strategy map
    # Keep clean sources, replace contaminated with regenerated
    clean_strategies = []

    for strategy in strategies:
        source_id = strategy['source_experience_id']

        if source_id in contaminated_ids:
            # Use regenerated version
            regen = next((s for s in regenerated if s['source_experience_id'] == source_id), None)
            if regen:
                clean_strategies.append(regen)
            else:
                # Regeneration failed, keep original but mark
                strategy['regeneration_failed'] = True
                clean_strategies.append(strategy)
        else:
            # Keep original clean source
            clean_strategies.append(strategy)

    # Save
    output_file = f'{BASE_PATH}/strategies_format_neutral_clean_v2.json'
    with open(output_file, 'w') as f:
        json.dump(clean_strategies, f, indent=2)

    print(f"Saved: {output_file}")
    print(f"  Total: {len(clean_strategies)} strategies")
    print(f"  Regenerated: {len(regenerated)}")
    print(f"  Original clean: {len(clean_strategies) - len(regenerated)}")
    print()

    return regenerated, failed


def main():
    """Main entry point."""

    # Check for API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')

    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY environment variable not set")
        print()
        print("To set it:")
        print("  export DEEPSEEK_API_KEY='your-api-key'")
        print()
        sys.exit(1)

    regenerated, failed = regenerate_contaminated_sources(api_key)

    if failed:
        print("⚠️  Some regenerations failed - review failures above")
        sys.exit(1)
    else:
        print("✓ All regenerations successful")
        print()
        print("Next step: Run QC audit on regenerated strategies")
        print("  python3 strategy_qc_audit_v2_post_regen.py")


if __name__ == '__main__':
    main()
