#!/usr/bin/env python3
"""
Stage 36 Program-Level Audit - Canonical Script

This script performs a reproducible program-level audit of Stage 36 results.
All statistics must be generated from this script - no manual edits.

Input:
- target_queries.json (30 canonical targets)
- results_none.json, results_case.json, results_strategy.json, results_paired.json

Output:
- program_level_audit_canonical.json (single source of truth)
- program_level_audit_summary.json (aggregate statistics)
- program_level_audit_transitions.json (rescue/harm analysis)
"""

import json
import sys
import re
from typing import Dict, List, Any, Optional, Tuple

# Import FinQA official executor
sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps, exec_steps, official_normalize_result, match_result

# ============================================================================
# PROGRAM NORMALIZATION RULES
# ============================================================================

def extract_program_from_response(response: str) -> Optional[str]:
    """
    Extract program string from model response.

    Normalization rules:
    1. Find line starting with "PROGRAM:"
    2. Extract content after "PROGRAM:" prefix
    3. Remove markdown code fences (```)
    4. Strip whitespace
    5. Return None if no program found

    NO MODIFICATIONS based on gold answer or execution result.
    """
    lines = response.split('\n')
    program_lines = []
    in_program = False

    for line in lines:
        stripped = line.strip()

        # Start of program section
        if stripped.startswith('PROGRAM:'):
            in_program = True
            # Get content after PROGRAM: on same line
            content = stripped[8:].strip()
            if content and content != '```':
                program_lines.append(content)
            continue

        # In program section
        if in_program:
            # Stop at ANSWER: or next section
            if stripped.startswith('ANSWER:') or stripped.startswith('##'):
                break
            # Skip code fences
            if stripped == '```' or stripped.startswith('```'):
                continue
            # Add non-empty lines
            if stripped:
                program_lines.append(stripped)

    if not program_lines:
        return None

    # Join and final cleanup
    program = ' '.join(program_lines)
    # Remove trailing punctuation/explanation
    program = re.sub(r'\s*→.*$', '', program)
    # Remove inline comments after # (but not intermediate references like #0)
    program = re.sub(r'\s+#[^\d].*$', '', program)

    # Fix incomplete trailing operations (e.g., "add(2901,")
    # Count open/close parens to detect incomplete expressions
    open_count = program.count('(')
    close_count = program.count(')')
    if open_count > close_count:
        # Incomplete operation at end - truncate to last complete operation
        # Find last complete comma-separated step
        steps = program.split('),')
        if len(steps) > 1:
            # Keep all complete steps
            program = '), '.join(steps[:-1]) + ')'
        else:
            # Single incomplete step - cannot fix
            return None

    return program.strip() if program.strip() else None

def normalize_program(program: str) -> str:
    """
    Normalize program syntax for parsing.

    Allowed normalizations:
    1. Standardize whitespace around commas
    2. Handle const_X notation
    3. No operand modifications
    4. No operation modifications
    """
    if not program:
        return program

    # Standardize whitespace
    program = re.sub(r'\s*,\s*', ', ', program)
    program = re.sub(r'\s+', ' ', program)

    return program.strip()

# ============================================================================
# PROGRAM EXECUTION WITH TABLE SUPPORT
# ============================================================================

def execute_program_with_table(program_str: str, table_data: Any) -> Tuple[Optional[float], str]:
    """
    Execute program using official FinQA executor with table support.

    Returns:
        (result, status) where status is one of:
        - 'success': Executed successfully
        - 'parse_fail': Could not parse program
        - 'exec_fail': Parsed but execution failed
    """
    if not program_str:
        return None, 'parse_fail'

    try:
        # Detect format: linear (has top-level commas) or nested (single expression)
        depth = 0
        has_top_level_comma = False
        for c in program_str:
            if c == '(': depth += 1
            elif c == ')': depth -= 1
            elif c == ',' and depth == 0:
                has_top_level_comma = True
                break

        # Parse program to linear steps
        if has_top_level_comma:
            # Linear format: use parse_linear_steps
            steps = parse_linear_steps(program_str)
        else:
            # Nested format: use parse_program_re (nested parser)
            steps = parse_program_re(program_str)

        if not steps:
            return None, 'parse_fail'
    except Exception as e:
        return None, 'parse_fail'

    try:
        # Execute with table - exec_steps returns (ok, result)
        # FIX: exec_steps requires table to be a list, not None
        # If no table, pass empty list
        table = table_data if table_data is not None else []
        ok, result = exec_steps(steps, table)
        if not ok or result == "n/a":
            return None, 'exec_fail'
        return result, 'success'
    except Exception as e:
        return None, 'exec_fail'

# ============================================================================
# MAIN AUDIT FUNCTION
# ============================================================================

def audit_program_level():
    """Main audit function - single source of truth."""

    print("=" * 80)
    print("STAGE 36 PROGRAM-LEVEL AUDIT - CANONICAL RUN")
    print("=" * 80)

    # Load canonical targets
    print("\n[1/6] Loading canonical targets...")
    with open('target_queries.json', 'r') as f:
        targets = json.load(f)

    # Build target lookup by ID
    target_lookup = {t['id']: t for t in targets}
    canonical_ids = set(target_lookup.keys())
    print(f"  Loaded {len(targets)} canonical targets")

    # Load all arm results
    print("\n[2/6] Loading arm results...")
    arms = ['none', 'case', 'strategy', 'paired']
    arm_data = {}

    for arm in arms:
        with open(f'results_{arm}.json', 'r') as f:
            arm_data[arm] = json.load(f)
        print(f"  {arm}: {len(arm_data[arm])} responses")

    # Validation assertions
    print("\n[3/6] Validating input consistency...")
    for arm in arms:
        assert len(arm_data[arm]) == 30, f"{arm} has {len(arm_data[arm])} responses, expected 30"
        arm_ids = set([r['target_id'] for r in arm_data[arm]])
        assert arm_ids == canonical_ids, f"{arm} target IDs do not match canonical set"
    print("  ✓ All assertions passed")

    # Build canonical audit matrix
    print("\n[4/6] Executing program-level audit...")
    audit_records = []

    for arm in arms:
        for response_data in arm_data[arm]:
            target_id = response_data['target_id']
            target = target_lookup[target_id]

            # Extract program
            raw_program = extract_program_from_response(response_data['response'])
            normalized_program = normalize_program(raw_program) if raw_program else None

            # Execute program with table
            if normalized_program:
                # Get table from target
                table = target.get('table', None)
                exec_result, exec_status = execute_program_with_table(normalized_program, table)
            else:
                exec_result = None
                exec_status = 'no_program'

            # Check program correctness
            # Gold answer is in qa.exe_ans (numeric) or qa.answer (string)
            gold_result = target['qa'].get('exe_ans')
            if gold_result is None:
                # Fallback to answer field
                gold_result = target['qa']['answer']
            program_correct = False

            if exec_status == 'success' and exec_result is not None:
                try:
                    program_correct = match_result(exec_result, gold_result)
                except:
                    program_correct = False

            # Determine failure reason
            failure_reason = None
            if not program_correct:
                if not raw_program:
                    failure_reason = 'no_program_line'
                elif not normalized_program:
                    failure_reason = 'empty_after_normalization'
                elif exec_status == 'parse_fail':
                    failure_reason = 'parse_failure'
                elif exec_status == 'exec_fail':
                    failure_reason = 'execution_failure'
                elif exec_status == 'success':
                    failure_reason = 'wrong_result'

            # Record
            record = {
                'target_id': target_id,
                'arm': arm,
                'gold_answer': gold_result,
                'raw_program': raw_program,
                'normalized_program': normalized_program,
                'execution_status': exec_status,
                'execution_result': exec_result,
                'program_correct': program_correct,
                'failure_reason': failure_reason,
                'answer_correct': response_data.get('exact_match', False)
            }

            audit_records.append(record)

    print(f"  Processed {len(audit_records)} records (120 total)")

    # Generate summary statistics
    print("\n[5/6] Computing summary statistics...")
    summary = compute_summary(audit_records)

    # Generate transition analysis
    print("\n[6/6] Analyzing transitions...")
    transitions = analyze_transitions(audit_records)

    # Save canonical output
    print("\nSaving outputs...")
    with open('program_level_audit_canonical.json', 'w') as f:
        json.dump(audit_records, f, indent=2)
    print("  ✓ program_level_audit_canonical.json")

    with open('program_level_audit_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    print("  ✓ program_level_audit_summary.json")

    with open('program_level_audit_transitions.json', 'w') as f:
        json.dump(transitions, f, indent=2)
    print("  ✓ program_level_audit_transitions.json")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print_summary(summary, transitions)

    # Final consistency check
    print("\n" + "=" * 80)
    print("CONSISTENCY CHECK")
    print("=" * 80)
    verify_consistency(audit_records, summary, transitions)

    print("\n✓ Audit complete - all outputs generated from single canonical source")

# ============================================================================
# SUMMARY COMPUTATION
# ============================================================================

def compute_summary(records: List[Dict]) -> Dict:
    """Compute aggregate statistics from audit records."""

    summary = {
        'total_records': len(records),
        'per_arm': {}
    }

    arms = ['none', 'case', 'strategy', 'paired']

    for arm in arms:
        arm_records = [r for r in records if r['arm'] == arm]

        total = len(arm_records)
        has_program = len([r for r in arm_records if r['raw_program'] is not None])
        parsed = len([r for r in arm_records if r['execution_status'] not in ['no_program', 'parse_fail']])
        executed = len([r for r in arm_records if r['execution_status'] == 'success'])
        program_correct = len([r for r in arm_records if r['program_correct']])
        answer_correct = len([r for r in arm_records if r['answer_correct']])

        summary['per_arm'][arm] = {
            'total': total,
            'has_program': has_program,
            'parsed': parsed,
            'executed': executed,
            'program_correct': program_correct,
            'answer_correct': answer_correct,
            'program_accuracy': program_correct / total if total > 0 else 0,
            'answer_accuracy': answer_correct / total if total > 0 else 0
        }

    return summary

# ============================================================================
# TRANSITION ANALYSIS
# ============================================================================

def analyze_transitions(records: List[Dict]) -> Dict:
    """Analyze rescue/harm patterns."""

    # Group by target_id
    by_target = {}
    for r in records:
        tid = r['target_id']
        if tid not in by_target:
            by_target[tid] = {}
        by_target[tid][r['arm']] = r

    # Analyze transitions
    transitions = {
        'rescues': {'case': [], 'strategy': [], 'paired': []},
        'harms': {'case': [], 'strategy': [], 'paired': []},
        'invariant_correct': [],
        'invariant_wrong': []
    }

    for tid, arms_data in by_target.items():
        none_correct = arms_data['none']['program_correct']

        # Check all correct or all wrong
        all_correct = all(arms_data[arm]['program_correct'] for arm in ['none', 'case', 'strategy', 'paired'])
        all_wrong = all(not arms_data[arm]['program_correct'] for arm in ['none', 'case', 'strategy', 'paired'])

        if all_correct:
            transitions['invariant_correct'].append(tid)
        elif all_wrong:
            transitions['invariant_wrong'].append(tid)
        else:
            # Check rescues and harms
            for mem_arm in ['case', 'strategy', 'paired']:
                mem_correct = arms_data[mem_arm]['program_correct']

                if not none_correct and mem_correct:
                    transitions['rescues'][mem_arm].append(tid)
                elif none_correct and not mem_correct:
                    transitions['harms'][mem_arm].append(tid)

    # Add counts
    transitions['rescue_counts'] = {arm: len(ids) for arm, ids in transitions['rescues'].items()}
    transitions['harm_counts'] = {arm: len(ids) for arm, ids in transitions['harms'].items()}
    transitions['invariant_correct_count'] = len(transitions['invariant_correct'])
    transitions['invariant_wrong_count'] = len(transitions['invariant_wrong'])

    return transitions

# ============================================================================
# OUTPUT FUNCTIONS
# ============================================================================

def print_summary(summary: Dict, transitions: Dict):
    """Print summary to console."""

    print("\nProgram-Level Accuracy:")
    print("-" * 40)
    for arm in ['none', 'case', 'strategy', 'paired']:
        stats = summary['per_arm'][arm]
        print(f"{arm:10s}: {stats['program_correct']:2d}/30 ({stats['program_accuracy']*100:5.1f}%)")

    print("\nAnswer-Level Accuracy (for comparison):")
    print("-" * 40)
    for arm in ['none', 'case', 'strategy', 'paired']:
        stats = summary['per_arm'][arm]
        print(f"{arm:10s}: {stats['answer_correct']:2d}/30 ({stats['answer_accuracy']*100:5.1f}%)")

    print("\nCoverage:")
    print("-" * 40)
    for arm in ['none', 'case', 'strategy', 'paired']:
        stats = summary['per_arm'][arm]
        print(f"{arm:10s}: parsed {stats['parsed']:2d}/30, executed {stats['executed']:2d}/30")

    print("\nTransitions:")
    print("-" * 40)
    print(f"Invariant correct (4/4 arms):  {transitions['invariant_correct_count']:2d}/30")
    print(f"Invariant wrong (0/4 arms):    {transitions['invariant_wrong_count']:2d}/30")
    print(f"Case rescues:                  {transitions['rescue_counts']['case']:2d}/30")
    print(f"Strategy rescues:              {transitions['rescue_counts']['strategy']:2d}/30")
    print(f"Paired rescues:                {transitions['rescue_counts']['paired']:2d}/30")
    print(f"Case harms:                    {transitions['harm_counts']['case']:2d}/30")
    print(f"Strategy harms:                {transitions['harm_counts']['strategy']:2d}/30")
    print(f"Paired harms:                  {transitions['harm_counts']['paired']:2d}/30")

def verify_consistency(records: List[Dict], summary: Dict, transitions: Dict):
    """Verify internal consistency of all outputs."""

    errors = []

    # Check total records
    if len(records) != 120:
        errors.append(f"Total records {len(records)} != 120")

    # Check per-arm counts
    for arm in ['none', 'case', 'strategy', 'paired']:
        arm_records = [r for r in records if r['arm'] == arm]
        if len(arm_records) != 30:
            errors.append(f"{arm} has {len(arm_records)} records != 30")

        # Check summary matches
        stats = summary['per_arm'][arm]
        if stats['total'] != 30:
            errors.append(f"{arm} summary total {stats['total']} != 30")

        actual_correct = len([r for r in arm_records if r['program_correct']])
        if stats['program_correct'] != actual_correct:
            errors.append(f"{arm} summary correct {stats['program_correct']} != actual {actual_correct}")

    # Check transition counts
    total_transitions = (transitions['invariant_correct_count'] +
                        transitions['invariant_wrong_count'])

    # Count memory-sensitive (not invariant)
    memory_sensitive = 30 - transitions['invariant_correct_count'] - transitions['invariant_wrong_count']

    # Check rescue IDs are valid
    all_target_ids = set([r['target_id'] for r in records if r['arm'] == 'none'])
    for arm in ['case', 'strategy', 'paired']:
        for tid in transitions['rescues'][arm]:
            if tid not in all_target_ids:
                errors.append(f"Rescue target {tid} not in canonical set")
        for tid in transitions['harms'][arm]:
            if tid not in all_target_ids:
                errors.append(f"Harm target {tid} not in canonical set")

    if errors:
        print("✗ CONSISTENCY ERRORS FOUND:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("✓ All consistency checks passed")
        print(f"  - 120 total records (30 per arm)")
        print(f"  - Summary counts match record counts")
        print(f"  - Transition IDs valid")
        print(f"  - {transitions['invariant_correct_count']} invariant correct + {transitions['invariant_wrong_count']} invariant wrong + {memory_sensitive} memory-sensitive = 30")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    audit_program_level()
