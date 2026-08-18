#!/usr/bin/env python3
"""
Build Faithful Abstractions

Construct execution-faithful natural language abstractions from gold programs.

Requirements:
1. No specific numeric operands from source
2. Operation sequence matches gold program exactly
3. Scale convention matches gold program exactly
4. No spurious operations
5. No missing operations
6. No program template/sketch
7. Preserves reasoning intent

Strategy: Use LLM with strict constraints to generate faithful abstractions.
"""

import json
import sys
import os
from openai import OpenAI
from typing import Dict, List, Tuple

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import parse_program_v2_strict

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'
SOURCE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def extract_gold_structure(program: str) -> Dict:
    """Extract structural metadata from gold program."""
    steps, error = parse_program_v2_strict(program)

    if steps is None:
        return None

    operations = [step[0] for step in steps]

    # Check for const_100 (percentage conversion)
    has_scale_100 = 'const_100' in program or ', 100)' in program or '(100,' in program

    # Check for const_m1 (negation)
    has_negation = 'const_m1' in program or ', -1)' in program or '(-1,' in program

    # Check for table operations
    has_table_op = any(op.startswith('table_') for op in operations)

    return {
        'operations': operations,
        'n_operations': len(operations),
        'has_scale_100': has_scale_100,
        'has_negation': has_negation,
        'has_table_op': has_table_op,
        'is_single_step': len(operations) == 1,
        'is_multi_step': len(operations) > 1
    }


def build_faithful_prompt(case: Dict, gold_struct: Dict) -> str:
    """
    Build prompt for faithful abstraction generation.

    CRITICAL CONSTRAINTS:
    - Operation sequence must match gold exactly
    - Scale convention must match gold exactly
    - No program template
    - Natural language only
    """

    question = case['question']
    gold_program = case['program']
    gold_answer = case.get('exe_ans', case.get('answer', 'N/A'))

    ops_list = ', '.join(gold_struct['operations'])
    n_ops = gold_struct['n_operations']

    scale_constraint = ""
    if gold_struct['has_scale_100']:
        scale_constraint = """
SCALE REQUIREMENT:
- The gold program multiplies by 100 for percentage conversion
- Your abstraction MUST mention this percentage conversion/scaling by 100
- Do NOT omit the ×100 step
"""
    else:
        scale_constraint = """
SCALE REQUIREMENT:
- The gold program does NOT multiply by 100
- The result is a DECIMAL ratio, NOT a percentage
- Do NOT mention "multiply by 100" or "convert to percentage"
- Use terms like "ratio", "proportion", "decimal result"
"""

    prompt = f"""You are creating an execution-faithful reasoning abstraction for a financial problem.

## Solved Problem

Question: {question}

Gold Program: {gold_program}

Gold Answer: {gold_answer}

Gold Operations: {ops_list} (count: {n_ops})

## CRITICAL CONSTRAINTS

Your abstraction MUST be execution-faithful:

1. **Operation Fidelity**: Describe EXACTLY {n_ops} operation(s): {ops_list}
   - Do NOT add operations not in gold program
   - Do NOT omit operations from gold program
   - Operation sequence must match gold program exactly

2. **Scale Fidelity**:
{scale_constraint}

3. **No Program Template**: Use natural language only
   - Do NOT include executable FinQA syntax
   - Do NOT include program sketch with placeholders
   - Describe reasoning in natural language

4. **No Specific Operands**: Do NOT mention specific numbers from this problem
   - Describe operand roles generically (e.g., "numerator", "denominator")
   - Do NOT copy actual values like "19.8" or "135.2"

5. **Generalization**: Describe the reasoning pattern, not this specific instance

## Output Format

Return ONLY valid JSON with these fields:

{{
  "strategy_name": "Short descriptive name (5-10 words)",
  "problem_pattern": "When this reasoning applies (2-3 sentences)",
  "reasoning_steps": "Step 1: ...\\nStep 2: ...\\nStep 3: ...",
  "operand_roles": "- role1: description\\n- role2: description",
  "units_convention": "How units should be handled"
}}

VERIFICATION CHECKLIST (check before returning):
- ✓ Operation count is {n_ops}
- ✓ Operations match: {ops_list}
- ✓ Scale convention matches gold program
- ✓ No program template/sketch included
- ✓ No specific operands from this problem
"""

    return prompt


def generate_faithful_abstraction(case: Dict, gold_struct: Dict, client: OpenAI) -> Dict:
    """Generate faithful abstraction via LLM."""

    prompt = build_faithful_prompt(case, gold_struct)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2000
        )

        response_text = response.choices[0].message.content

        # Parse JSON
        import re
        text = re.sub(r'```json\s*', '', response_text)
        text = re.sub(r'```\s*$', '', text)
        text = text.strip()

        abstraction = json.loads(text)

        return abstraction, None

    except Exception as e:
        return None, str(e)


def main():
    """Build faithful abstractions."""

    print("="*80)
    print("BUILD FAITHFUL ABSTRACTIONS")
    print("="*80)
    print()

    # Check API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Load cases
    with open(f'{SOURCE_PATH}/cases_clean.json') as f:
        cases = json.load(f)

    print(f"Loaded {len(cases)} source cases")
    print()

    # Extract gold structures
    print("Extracting gold program structures...")
    cases_with_structure = []

    for case in cases:
        source_id = case['source_experience_id']
        gold_program = case['program']

        gold_struct = extract_gold_structure(gold_program)

        if gold_struct is None:
            print(f"  ⚠️  {source_id}: Failed to parse gold program")
            continue

        case['gold_structure'] = gold_struct
        cases_with_structure.append(case)

    print(f"  Parsed: {len(cases_with_structure)}/{len(cases)}")
    print()

    # Generate faithful abstractions
    print("Generating faithful abstractions...")
    print()

    faithful_abstractions = []
    failed = []

    for i, case in enumerate(cases_with_structure, 1):
        source_id = case['source_experience_id']
        print(f"[{i}/{len(cases_with_structure)}] Generating {source_id}...")

        abstraction, error = generate_faithful_abstraction(
            case,
            case['gold_structure'],
            client
        )

        if abstraction is None:
            print(f"  ❌ Failed: {error}")
            failed.append(source_id)
            continue

        # Add metadata
        abstraction['source_experience_id'] = source_id
        abstraction['gold_program'] = case['program']
        abstraction['gold_structure'] = case['gold_structure']
        abstraction['representation'] = 'faithful_abstraction'

        faithful_abstractions.append(abstraction)
        print(f"  ✓ Generated")

    print()
    print(f"Generated: {len(faithful_abstractions)}/{len(cases_with_structure)}")

    if failed:
        print(f"Failed: {len(failed)}")
        for sid in failed:
            print(f"  {sid}")

    print()

    # Save
    output_file = f'{BASE_PATH}/faithful_abstractions_raw.json'
    with open(output_file, 'w') as f:
        json.dump(faithful_abstractions, f, indent=2)

    print(f"Saved: {output_file}")
    print()
    print("Next: Run structural QC to verify fidelity")
    print("  python3 faithful_abstraction_qc.py")


if __name__ == '__main__':
    main()
