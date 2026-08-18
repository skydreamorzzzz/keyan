#!/usr/bin/env python3
"""
Build Corruption Manifest

Deterministically generate corruption assignments for fidelity experiment.

Design:
- 4 corruption levels: 0% (faithful), 10%, 25%, 50%
- 3 corruption types: Scale drift, Operation drift, Operand-role drift
- Fixed seed for reproducibility
- Corruption is LOCAL MUTATION, not LLM rewrite

Mutation happens at source-level:
- Each retrieved source can be faithful or corrupted
- Target with k=3 retrieval → 3 source units
- Corruption level = % of source units corrupted

Example:
- 10% level: ~10% of all source units across all targets are corrupted
- Implemented as: assign corruption to sources deterministically
"""

import json
import random
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from canonical_evaluator_v2 import parse_program_v2_strict

BASE_PATH = '/home/tiantian/keyan/pilot/stage41_abstraction_fidelity'
SOURCE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

SEED = 42  # Fixed for reproducibility


def load_faithful_sources() -> Tuple[List[Dict], Dict]:
    """Load faithful sources (clean subset from clean_v2)."""

    # Load clean_v2 strategies
    with open(f'{SOURCE_PATH}/strategies_format_neutral_clean_v2.json') as f:
        strategies = json.load(f)

    # Load QC results
    with open(f'{SOURCE_PATH}/strategy_qc_audit_v2_post_regen.json') as f:
        qc_data = json.load(f)

    # Filter to clean sources only
    contaminated_ids = {
        r['source_id'] for r in qc_data['audit_results']
        if r['contaminated']
    }

    faithful_sources = [
        s for s in strategies
        if s['source_experience_id'] not in contaminated_ids
    ]

    # Load gold structures from cases
    with open(f'{SOURCE_PATH}/cases_clean.json') as f:
        cases = json.load(f)

    case_map = {c['source_experience_id']: c for c in cases}

    # Add gold structure to each source
    for source in faithful_sources:
        sid = source['source_experience_id']
        if sid in case_map:
            case = case_map[sid]
            steps, _ = parse_program_v2_strict(case['program'])
            if steps:
                source['gold_operations'] = [step[0] for step in steps]
                source['gold_has_100'] = 'const_100' in case['program'] or ', 100)' in case['program']
            else:
                source['gold_operations'] = []
                source['gold_has_100'] = False

    source_map = {s['source_experience_id']: s for s in faithful_sources}

    return faithful_sources, source_map


def assign_corruption_type(source: Dict, rng: random.Random) -> str:
    """
    Assign corruption type based on source characteristics.

    Priority:
    1. If has scale_100 in gold → candidate for scale drift
    2. If multi-step → candidate for operation drift
    3. If ratio/division → candidate for operand-role drift
    """

    gold_ops = source.get('gold_operations', [])
    has_100 = source.get('gold_has_100', False)

    candidates = []

    # Scale drift: only if source has potential for ratio/percentage confusion
    if 'divide' in gold_ops:
        candidates.append('scale_drift')

    # Operation drift: if multi-step or has arithmetic
    if len(gold_ops) > 1 or any(op in ['add', 'subtract', 'multiply', 'divide'] for op in gold_ops):
        candidates.append('operation_drift')

    # Operand-role drift: if has division or subtraction (can swap roles)
    if 'divide' in gold_ops or 'subtract' in gold_ops:
        candidates.append('operand_role_drift')

    if not candidates:
        # Fallback to scale drift
        candidates = ['scale_drift']

    return rng.choice(candidates)


def build_corruption_manifest(
    targets: List[Dict],
    faithful_sources: List[Dict],
    corruption_levels: List[float]
) -> Dict:
    """
    Build corruption manifest with fixed seed.

    Returns manifest with corruption assignments for each level.
    """

    rng = random.Random(SEED)

    # Build list of all (target_id, source_id) pairs
    all_units = []

    for target in targets:
        target_id = target['id']
        source_ids = target.get('shared_source_ids', [])

        for source_id in source_ids:
            all_units.append({
                'target_id': target_id,
                'source_id': source_id
            })

    total_units = len(all_units)

    print(f"Total source units: {total_units}")
    print(f"  224 targets × k=3 = {224 * 3} (expected)")
    print()

    # Shuffle units with fixed seed
    rng.shuffle(all_units)

    # Build manifest for each corruption level
    manifest = {}

    faithful_source_ids = {s['source_experience_id'] for s in faithful_sources}

    for level in corruption_levels:
        level_key = f"{int(level*100)}%"

        # Determine how many units to corrupt
        n_corrupt = int(total_units * level)

        # Assign corruption to first n_corrupt units (after shuffle)
        level_assignments = []

        for i, unit in enumerate(all_units):
            target_id = unit['target_id']
            source_id = unit['source_id']

            # Skip if source is not in faithful set
            if source_id not in faithful_source_ids:
                continue

            if i < n_corrupt:
                # Corrupted
                source = next(s for s in faithful_sources if s['source_experience_id'] == source_id)
                corruption_type = assign_corruption_type(source, rng)

                level_assignments.append({
                    'target_id': target_id,
                    'source_id': source_id,
                    'corrupted': True,
                    'corruption_type': corruption_type
                })
            else:
                # Faithful
                level_assignments.append({
                    'target_id': target_id,
                    'source_id': source_id,
                    'corrupted': False,
                    'corruption_type': None
                })

        manifest[level_key] = level_assignments

        # Stats
        n_corrupted = sum(1 for a in level_assignments if a['corrupted'])
        actual_rate = n_corrupted / len(level_assignments) if level_assignments else 0

        print(f"Level {level_key}:")
        print(f"  Target: {n_corrupt} units")
        print(f"  Actual: {n_corrupted} units ({100*actual_rate:.1f}%)")

        # Corruption type breakdown
        type_counts = {}
        for a in level_assignments:
            if a['corrupted']:
                ctype = a['corruption_type']
                type_counts[ctype] = type_counts.get(ctype, 0) + 1

        print(f"  Types: {type_counts}")
        print()

    return manifest


def main():
    """Build corruption manifest."""

    print("="*80)
    print("BUILD CORRUPTION MANIFEST")
    print("="*80)
    print()

    # Load targets
    with open(f'{SOURCE_PATH}/expanded_sample_queries.json') as f:
        targets = json.load(f)

    print(f"Targets: {len(targets)}")

    # Load faithful sources
    faithful_sources, source_map = load_faithful_sources()

    print(f"Faithful sources: {len(faithful_sources)}/78 (74 clean from clean_v2)")
    print()

    # Define corruption levels
    corruption_levels = [0.0, 0.10, 0.25, 0.50]

    print(f"Corruption levels: {[f'{int(l*100)}%' for l in corruption_levels]}")
    print(f"Seed: {SEED}")
    print()

    # Build manifest
    manifest = build_corruption_manifest(targets, faithful_sources, corruption_levels)

    # Save
    output = {
        'seed': SEED,
        'corruption_levels': corruption_levels,
        'faithful_sources': len(faithful_sources),
        'total_targets': len(targets),
        'manifest': manifest,
        'note': 'Deterministic corruption assignment with fixed seed'
    }

    output_file = f'{BASE_PATH}/corruption_manifest.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_file}")
    print()
    print("Next: Generate corrupted versions")
    print("  python3 generate_corrupted_memories.py")


if __name__ == '__main__':
    main()
