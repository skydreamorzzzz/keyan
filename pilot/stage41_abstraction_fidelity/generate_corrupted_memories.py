#!/usr/bin/env python3
"""
Generate Corrupted Memories

Apply deterministic local mutations to faithful abstractions.

CRITICAL: Only mutate specific spans, keep rest identical.
NO LLM rewriting of entire strategies.

Corruption types:
1. Scale drift: Add/remove ×100 conversion
2. Operation drift: Swap one operation
3. Operand-role drift: Swap operand role descriptions
"""

import json
import re
import sys
from typing import Dict, Tuple

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'
SOURCE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def corrupt_scale_drift(source: Dict) -> Tuple[Dict, Dict]:
    """
    Apply scale drift corruption.

    If gold has no ×100: Add spurious percentage conversion
    If gold has ×100: Remove it (make decimal)
    """

    corrupted = source.copy()
    mutation_log = {
        'corruption_type': 'scale_drift',
        'mutations': []
    }

    gold_has_100 = source.get('gold_has_100', False)
    reasoning_steps = source.get('reasoning_steps', '')

    if gold_has_100:
        # Gold has ×100, remove it
        # Look for "multiply by 100" or "×100" or "percentage"
        new_reasoning = reasoning_steps

        # Remove multiplication by 100 phrases
        patterns = [
            (r'multiply\s+(?:the\s+)?(?:result\s+)?by\s+100', 'keep the result as is'),
            (r'×\s*100', ''),
            (r'\*\s*100', ''),
            (r'convert.*?to.*?percentage', 'keep as decimal ratio'),
            (r'express.*?as.*?percentage', 'express as decimal ratio'),
        ]

        for pattern, replacement in patterns:
            if re.search(pattern, new_reasoning, re.IGNORECASE):
                old_text = re.search(pattern, new_reasoning, re.IGNORECASE).group()
                new_reasoning = re.sub(pattern, replacement, new_reasoning, flags=re.IGNORECASE)
                mutation_log['mutations'].append({
                    'span': old_text,
                    'replaced_with': replacement
                })

        corrupted['reasoning_steps'] = new_reasoning
        corrupted['corruption_applied'] = 'scale_drift_remove_100'

    else:
        # Gold has no ×100, add it
        # Find a good insertion point (after division usually)
        new_reasoning = reasoning_steps

        # Look for division or ratio calculation
        if 'divide' in new_reasoning.lower() or 'ratio' in new_reasoning.lower():
            # Add percentage conversion phrase
            insertion = " Then multiply the result by 100 to express as a percentage."

            # Try to insert after a sentence mentioning division
            match = re.search(r'([^.]*(?:divide|ratio|proportion)[^.]*\.)', new_reasoning, re.IGNORECASE)
            if match:
                insert_pos = match.end()
                new_reasoning = new_reasoning[:insert_pos] + insertion + new_reasoning[insert_pos:]

                mutation_log['mutations'].append({
                    'span': insertion,
                    'inserted_after': match.group()
                })
            else:
                # Fallback: append to end
                new_reasoning += insertion
                mutation_log['mutations'].append({
                    'span': insertion,
                    'inserted_at': 'end'
                })

            corrupted['reasoning_steps'] = new_reasoning
            corrupted['corruption_applied'] = 'scale_drift_add_100'

    return corrupted, mutation_log


def corrupt_operation_drift(source: Dict) -> Tuple[Dict, Dict]:
    """
    Apply operation drift corruption.

    Swap one operation mention with a related but wrong operation.
    """

    corrupted = source.copy()
    mutation_log = {
        'corruption_type': 'operation_drift',
        'mutations': []
    }

    reasoning_steps = source.get('reasoning_steps', '')
    gold_ops = source.get('gold_operations', [])

    if not gold_ops:
        return corrupted, mutation_log

    # Define plausible swaps
    swap_map = {
        'add': 'subtract',
        'subtract': 'add',
        'multiply': 'divide',
        'divide': 'multiply'
    }

    # Find first swappable operation
    new_reasoning = reasoning_steps

    for gold_op in gold_ops:
        if gold_op in swap_map:
            wrong_op = swap_map[gold_op]

            # Look for operation mention in text
            pattern = rf'\b{gold_op}\b'
            match = re.search(pattern, new_reasoning, re.IGNORECASE)

            if match:
                old_span = match.group()
                new_reasoning = re.sub(pattern, wrong_op, new_reasoning, count=1, flags=re.IGNORECASE)

                mutation_log['mutations'].append({
                    'operation': gold_op,
                    'swapped_to': wrong_op,
                    'span': old_span
                })

                corrupted['reasoning_steps'] = new_reasoning
                corrupted['corruption_applied'] = f'operation_drift_{gold_op}_to_{wrong_op}'
                break

    return corrupted, mutation_log


def corrupt_operand_role_drift(source: Dict) -> Tuple[Dict, Dict]:
    """
    Apply operand-role drift corruption.

    Swap operand role descriptions (e.g., numerator <-> denominator).
    """

    corrupted = source.copy()
    mutation_log = {
        'corruption_type': 'operand_role_drift',
        'mutations': []
    }

    operand_roles = source.get('operand_roles', '')
    gold_ops = source.get('gold_operations', [])

    # Only applicable if has division or subtraction
    if 'divide' not in gold_ops and 'subtract' not in gold_ops:
        return corrupted, mutation_log

    new_roles = operand_roles

    # Swap patterns
    swap_pairs = [
        ('numerator', 'denominator'),
        ('minuend', 'subtrahend'),
        ('new value', 'old value'),
        ('current', 'previous'),
        ('ending', 'beginning')
    ]

    for term1, term2 in swap_pairs:
        if term1 in new_roles.lower() and term2 in new_roles.lower():
            # Swap them
            # Use placeholders to avoid double-swap
            temp = new_roles
            temp = re.sub(rf'\b{term1}\b', '<<TEMP1>>', temp, flags=re.IGNORECASE)
            temp = re.sub(rf'\b{term2}\b', '<<TEMP2>>', temp, flags=re.IGNORECASE)
            temp = temp.replace('<<TEMP1>>', term2)
            temp = temp.replace('<<TEMP2>>', term1)

            new_roles = temp

            mutation_log['mutations'].append({
                'swapped': f'{term1} <-> {term2}'
            })

            corrupted['operand_roles'] = new_roles
            corrupted['corruption_applied'] = f'operand_role_drift_{term1}_{term2}'
            break

    return corrupted, mutation_log


def generate_corrupted_version(source: Dict, corruption_type: str) -> Tuple[Dict, Dict]:
    """Generate corrupted version based on type."""

    if corruption_type == 'scale_drift':
        return corrupt_scale_drift(source)
    elif corruption_type == 'operation_drift':
        return corrupt_operation_drift(source)
    elif corruption_type == 'operand_role_drift':
        return corrupt_operand_role_drift(source)
    else:
        return source.copy(), {'corruption_type': 'unknown'}


def main():
    """Generate corrupted memories."""

    print("="*80)
    print("GENERATE CORRUPTED MEMORIES")
    print("="*80)
    print()

    # Load faithful sources
    with open(f'{SOURCE_PATH}/strategies_format_neutral_clean_v2.json') as f:
        strategies = json.load(f)

    # Load QC to filter to faithful only
    with open(f'{SOURCE_PATH}/strategy_qc_audit_v2_post_regen.json') as f:
        qc_data = json.load(f)

    contaminated_ids = {
        r['source_id'] for r in qc_data['audit_results']
        if r['contaminated']
    }

    faithful_sources = [
        s for s in strategies
        if s['source_experience_id'] not in contaminated_ids
    ]

    # Load gold structures
    with open(f'{SOURCE_PATH}/cases_clean.json') as f:
        cases = json.load(f)

    case_map = {c['source_experience_id']: c for c in cases}

    # Add gold structure
    sys.path.insert(0, f'{SOURCE_PATH}')
    from canonical_evaluator_v2 import parse_program_v2_strict

    for source in faithful_sources:
        sid = source['source_experience_id']
        if sid in case_map:
            case = case_map[sid]
            steps, _ = parse_program_v2_strict(case['program'])
            if steps:
                source['gold_operations'] = [step[0] for step in steps]
                source['gold_has_100'] = 'const_100' in case['program'] or ', 100)' in case['program']

    source_map = {s['source_experience_id']: s for s in faithful_sources}

    print(f"Faithful sources: {len(faithful_sources)}")
    print()

    # Load corruption manifest
    with open(f'{BASE_PATH}/corruption_manifest.json') as f:
        manifest_data = json.load(f)

    manifest = manifest_data['manifest']

    # Generate corrupted versions for each corruption type
    print("Generating corrupted versions...")
    print()

    corrupted_sources = {}
    corruption_audit = []

    # Get all unique (source_id, corruption_type) pairs
    corruption_requests = set()

    for level_key, assignments in manifest.items():
        for assignment in assignments:
            if assignment['corrupted']:
                source_id = assignment['source_id']
                corruption_type = assignment['corruption_type']
                corruption_requests.add((source_id, corruption_type))

    print(f"Total corruption requests: {len(corruption_requests)}")
    print()

    for source_id, corruption_type in sorted(corruption_requests):
        if source_id not in source_map:
            print(f"  ⚠️  {source_id}: Not in faithful sources")
            continue

        source = source_map[source_id]

        # Generate corrupted version
        corrupted, mutation_log = generate_corrupted_version(source, corruption_type)

        key = f"{source_id}_{corruption_type}"
        corrupted_sources[key] = corrupted

        # Add to audit
        corruption_audit.append({
            'source_id': source_id,
            'corruption_type': corruption_type,
            'mutations': mutation_log['mutations'],
            'corruption_applied': corrupted.get('corruption_applied', 'none')
        })

    print(f"Generated {len(corrupted_sources)} corrupted versions")
    print()

    # Save corrupted sources
    output_corrupted = f'{BASE_PATH}/corrupted_sources.json'
    with open(output_corrupted, 'w') as f:
        json.dump(corrupted_sources, f, indent=2)

    print(f"Saved: {output_corrupted}")

    # Save audit
    output_audit = f'{BASE_PATH}/corruption_audit.json'
    with open(output_audit, 'w') as f:
        json.dump({
            'total_corrupted': len(corrupted_sources),
            'audit': corruption_audit
        }, f, indent=2)

    print(f"Saved: {output_audit}")
    print()

    print("Next: Build frozen retrieval manifest")
    print("  python3 build_frozen_retrieval.py")


if __name__ == '__main__':
    main()
