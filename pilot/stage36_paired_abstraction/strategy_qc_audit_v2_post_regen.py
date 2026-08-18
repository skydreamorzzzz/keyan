#!/usr/bin/env python3
"""
Post-Regeneration QC Audit

Run same QC audit on strategies_format_neutral_clean_v2.json to verify:
1. Contamination eliminated in regenerated sources
2. Original clean sources unchanged
3. Ready for clean experiment
"""

import json
import sys

sys.path.insert(0, '/home/tiantian/keyan/pilot/stage36_paired_abstraction')
from strategy_qc_audit_v2 import audit_source


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


def main():
    """Run QC audit on regenerated strategies."""

    print("="*80)
    print("POST-REGENERATION QC AUDIT")
    print("="*80)
    print()

    # Load data
    print("Loading data...")
    with open(f'{BASE_PATH}/cases_clean.json') as f:
        cases = json.load(f)
    case_map = {c['source_experience_id']: c for c in cases}

    with open(f'{BASE_PATH}/strategies_format_neutral_clean_v2.json') as f:
        strategies_clean = json.load(f)
    strategy_clean_map = {s['source_experience_id']: s for s in strategies_clean}

    # Load original audit for comparison
    with open(f'{BASE_PATH}/strategy_qc_audit_v2.json') as f:
        original_audit = json.load(f)
    original_contaminated = {r['source_id'] for r in original_audit['audit_results'] if r['contaminated']}

    print(f"  Cases: {len(cases)}")
    print(f"  Clean strategies: {len(strategies_clean)}")
    print(f"  Originally contaminated: {len(original_contaminated)}")
    print()

    # Audit each source
    print("Running audit on regenerated strategies...")
    audit_results = []

    for source_id in sorted(case_map.keys()):
        case = case_map[source_id]

        if source_id not in strategy_clean_map:
            print(f"  ⚠️  {source_id}: No strategy found")
            continue

        strategy = strategy_clean_map[source_id]

        result = audit_source(source_id, case, strategy)
        audit_results.append(result)

        # Report on previously contaminated sources
        if source_id in original_contaminated:
            if result['contaminated']:
                print(f"  ❌ {source_id}: Still contaminated - {result['reason']}")
            else:
                print(f"  ✓ {source_id}: Now clean (was contaminated)")

    print()

    # Compute statistics
    total = len(audit_results)
    operation_mismatches = sum(1 for r in audit_results if r['operation_mismatch'])
    scale_mismatches = sum(1 for r in audit_results if r['scale_mismatch'])
    contaminated = sum(1 for r in audit_results if r['contaminated'])

    # Check specific cases
    e002_result = next((r for r in audit_results if r['source_id'] == 'E002'), None)

    print("="*80)
    print("POST-REGENERATION STATISTICS")
    print("="*80)
    print(f"Total sources:           {total}")
    print(f"Operation mismatches:    {operation_mismatches} ({100*operation_mismatches/total:.1f}%)")
    print(f"Scale mismatches:        {scale_mismatches} ({100*scale_mismatches/total:.1f}%)")
    print(f"Total contaminated:      {contaminated} ({100*contaminated/total:.1f}%)")
    print()

    print("COMPARISON WITH ORIGINAL:")
    print(f"  Original contaminated:   {len(original_contaminated)} (34.6%)")
    print(f"  Post-regen contaminated: {contaminated} ({100*contaminated/total:.1f}%)")
    print(f"  Improvement:             {len(original_contaminated) - contaminated} sources cleaned")
    print()

    if e002_result:
        print("E002 POST-REGENERATION CHECK:")
        print(f"  Gold program: {e002_result['gold_program']}")
        print(f"  Strategy formula: {e002_result['strategy_formula']}")
        print(f"  Has ×100: {e002_result['has_multiply_100']}")
        print(f"  Scale mismatch: {e002_result['scale_mismatch']}")
        print(f"  Contaminated: {e002_result['contaminated']}")
        print(f"  Status: {'❌ STILL CONTAMINATED' if e002_result['contaminated'] else '✓ CLEAN'}")
        print()

    # List any remaining contaminated sources
    remaining_contaminated = [r for r in audit_results if r['contaminated']]
    if remaining_contaminated:
        print("⚠️  REMAINING CONTAMINATED SOURCES:")
        for r in remaining_contaminated:
            print(f"  {r['source_id']}: {r['reason']}")
        print()
    else:
        print("✓ NO CONTAMINATED SOURCES REMAINING")
        print()

    # Save results
    output = {
        'audit_results': audit_results,
        'statistics': {
            'total': total,
            'operation_mismatches': operation_mismatches,
            'scale_mismatches': scale_mismatches,
            'contaminated': contaminated,
            'contamination_rate': contaminated / total if total > 0 else 0.0
        },
        'comparison': {
            'original_contaminated': len(original_contaminated),
            'post_regen_contaminated': contaminated,
            'sources_cleaned': len(original_contaminated) - contaminated
        },
        'e002_check': e002_result,
        'note': 'QC audit after regenerating 27 contaminated sources'
    }

    output_file = f'{BASE_PATH}/strategy_qc_audit_v2_post_regen.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {output_file}")
    print("="*80)
    print()

    # Final verdict
    if contaminated == 0:
        print("✓✓✓ REGENERATION SUCCESSFUL ✓✓✓")
        print("All contamination eliminated. Ready for clean experiment.")
        print()
        print("Next step: Update clean_experiment_protocol_v2.py to use clean strategies")
        return True
    else:
        print("⚠️⚠️⚠️ REGENERATION INCOMPLETE ⚠️⚠️⚠️")
        print(f"{contaminated} sources still contaminated.")
        print("Review failures and consider manual fixing or re-regeneration.")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
