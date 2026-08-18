#!/usr/bin/env python3
"""
Canonical Evaluator V2

Strict implementation with true full-string consumption validation.

Key improvements over V1:
1. Strict nested parser with end-of-string validation
2. Strict linear parser with no leftover tokens
3. No silent fallback in correctness checking
4. Explicit evaluator_error category
5. Comprehensive malformed input rejection
"""

import json
import re
import sys
from typing import Dict, List, Tuple, Optional, Any

sys.path.insert(0, '/home/tiantian/keyan/pilot')


# ============================================================================
# STRICT PARSERS
# ============================================================================

def parse_nested_strict(program_str: str) -> Tuple[Optional[List[Tuple]], str]:
    """
    Strict nested expression parser with full-string consumption.

    Returns:
        (steps, error_msg)
    """
    s = program_str.strip()
    if not s:
        return None, "empty_string"

    pos = [0]

    def skip_whitespace():
        while pos[0] < len(s) and s[pos[0]] in ' \t':
            pos[0] += 1

    def match_char(ch):
        skip_whitespace()
        if pos[0] < len(s) and s[pos[0]] == ch:
            pos[0] += 1
            return True
        return False

    def parse_operation():
        skip_whitespace()
        start = pos[0]
        # Read operation name
        while pos[0] < len(s) and (s[pos[0]].isalpha() or s[pos[0]] == '_'):
            pos[0] += 1

        if pos[0] == start:
            return None, f"expected operation at position {pos[0]}"

        op_name = s[start:pos[0]]

        # Validate operation name is known
        VALID_OPS = ['add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
                     'table_max', 'table_min', 'table_sum', 'table_average']
        if op_name not in VALID_OPS:
            return None, f"unknown_operation: '{op_name}'"

        # Must have opening paren
        if not match_char('('):
            return None, f"expected '(' after operation '{op_name}' at position {pos[0]}"

        # Parse first argument
        arg1_result = parse_argument()
        if arg1_result[0] is None:
            return None, arg1_result[1]
        arg1 = arg1_result[0]

        # Must have comma
        if not match_char(','):
            return None, f"expected ',' after first argument at position {pos[0]}"

        # Parse second argument
        arg2_result = parse_argument()
        if arg2_result[0] is None:
            return None, arg2_result[1]
        arg2 = arg2_result[0]

        # Must have closing paren
        if not match_char(')'):
            return None, f"expected ')' after second argument at position {pos[0]}"

        return (op_name, arg1, arg2), ""

    def parse_argument():
        skip_whitespace()

        # Check if it's a nested operation
        # Look ahead for pattern: word_chars followed by '('
        saved_pos = pos[0]
        while pos[0] < len(s) and (s[pos[0]].isalpha() or s[pos[0]] == '_'):
            pos[0] += 1

        if pos[0] > saved_pos:
            # Found word chars, check for '('
            skip_whitespace()
            if pos[0] < len(s) and s[pos[0]] == '(':
                # It's a nested operation, restore and parse
                pos[0] = saved_pos
                return parse_operation()

        # Restore position
        pos[0] = saved_pos

        # Parse literal argument
        start = pos[0]
        # Read until comma or closing paren (at depth 0)
        while pos[0] < len(s) and s[pos[0]] not in ',)':
            pos[0] += 1

        if pos[0] == start:
            return None, f"expected argument at position {pos[0]}"

        arg_str = s[start:pos[0]].strip()
        if not arg_str:
            return None, f"empty argument at position {start}"

        # Validate argument doesn't contain invalid characters
        # Valid: numbers, #N, const_X, table row labels (can have spaces)
        # Invalid: trailing prose like "2 extra"
        # Simple check: if it has alphabetic chars, must be #N, const_X, or table label
        # If it has digits, check it doesn't have trailing non-numeric after number
        if re.search(r'\d+\s+[a-zA-Z]', arg_str):
            # Pattern like "2 extra" or "1 garbage"
            return None, f"invalid argument with trailing text: '{arg_str}'"

        return arg_str, ""

    # Parse root expression
    result = parse_operation()
    if result[0] is None:
        return None, result[1]

    root_expr = result[0]

    # CRITICAL: Check full string consumption
    skip_whitespace()
    if pos[0] < len(s):
        leftover = s[pos[0]:pos[0]+20]
        return None, f"trailing_content_at_position_{pos[0]}: '{leftover}...'"

    # Linearize AST
    steps = []
    def emit(node):
        op, a1, a2 = node

        def process_arg(a):
            if isinstance(a, tuple):
                idx = emit(a)
                return f'#{idx}'
            else:
                return a

        arg1_str = process_arg(a1)
        arg2_str = process_arg(a2)

        steps.append((op, arg1_str, arg2_str))
        return len(steps) - 1

    try:
        emit(root_expr)
    except Exception as e:
        return None, f"linearize_error: {e}"

    return steps, ""


def parse_linear_strict(program_str: str) -> Tuple[Optional[List[Tuple]], str]:
    """
    Strict linear program parser with no leftover tokens.

    Format: op1(a, b), op2(#0, c), op3(#1, d)

    Returns:
        (steps, error_msg)
    """
    # Split by top-level ", " (comma-space between operations)
    # Need to be careful with commas inside parentheses
    parts = []
    current = []
    depth = 0

    i = 0
    while i < len(program_str):
        c = program_str[i]

        if c == '(':
            depth += 1
            current.append(c)
        elif c == ')':
            depth -= 1
            current.append(c)
        elif c == ',' and depth == 0:
            # Top-level comma - end current operation
            if i + 1 < len(program_str) and program_str[i + 1] == ' ':
                # This is ", " separator
                parts.append(''.join(current).strip())
                current = []
                i += 1  # Skip the space
            else:
                # Comma not followed by space - might be malformed
                current.append(c)
        else:
            current.append(c)

        i += 1

    # Add last part
    if current:
        parts.append(''.join(current).strip())

    if not parts:
        return None, "no_operations_parsed"

    steps = []

    for idx, part in enumerate(parts):
        if not part:
            return None, f"empty_operation_at_index_{idx}"

        # Match pattern: op_name(arg1, arg2)
        match = re.match(r'^([a-z_]+)\((.+)\)$', part)
        if not match:
            return None, f"malformed_operation_at_index_{idx}: '{part[:50]}'"

        op_name = match.group(1)
        args_str = match.group(2)

        # Split arguments by comma (at depth 0 only)
        args = []
        arg_current = []
        arg_depth = 0

        for c in args_str:
            if c == '(':
                arg_depth += 1
                arg_current.append(c)
            elif c == ')':
                arg_depth -= 1
                arg_current.append(c)
            elif c == ',' and arg_depth == 0:
                # Argument separator
                args.append(''.join(arg_current).strip())
                arg_current = []
            else:
                arg_current.append(c)

        # Add last argument
        if arg_current:
            args.append(''.join(arg_current).strip())

        if len(args) != 2:
            return None, f"operation_must_have_2_args_at_index_{idx}: got {len(args)}"

        # Validate operation name is known (optional but catches typos)
        VALID_OPS = ['add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
                     'table_max', 'table_min', 'table_sum', 'table_average']
        if op_name not in VALID_OPS:
            return None, f"unknown_operation_at_index_{idx}: '{op_name}'"

        steps.append((op_name, args[0], args[1]))

    return steps, ""


def parse_program_v2_strict(program_str: str) -> Tuple[Optional[List[Tuple]], str]:
    """
    Unified strict parser with format detection.

    Returns:
        (steps, error_msg)
    """
    if not program_str:
        return None, "empty_program"

    program_str = program_str.strip()

    # Detect format: does it have top-level commas?
    depth = 0
    has_top_level_comma = False
    for c in program_str:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == ',' and depth == 0:
            has_top_level_comma = True
            break

    if has_top_level_comma:
        # Linear format
        return parse_linear_strict(program_str)
    else:
        # Nested format
        return parse_nested_strict(program_str)


# ============================================================================
# EXECUTION AND MATCHING
# ============================================================================

def execute_program_v2(steps: List[Tuple], table: List[List]) -> Tuple[bool, Any, str]:
    """
    Execute program with FinQA official semantics.

    Returns:
        (success, result, error_msg)
    """
    from executor import exec_steps

    try:
        success, result = exec_steps(steps, table)

        if not success:
            return False, None, "execution_failed"

        if result == "n/a":
            return False, None, "result_is_na"

        # Round to 5 decimals (FinQA official)
        if isinstance(result, (int, float)):
            result = round(float(result), 5)

        return True, result, ""

    except Exception as e:
        return False, None, f"exec_exception: {type(e).__name__}: {str(e)[:100]}"


def check_correctness_v2(result: Any, gold_answer: Any) -> Tuple[bool, str]:
    """
    Check correctness with FinQA official semantics.

    NO silent fallback.

    Handles both numeric results and string results (for greater operation).

    Returns:
        (correct, error_msg)
    """
    try:
        # Check if both are strings (for greater operation: "yes"/"no")
        if isinstance(result, str) and isinstance(gold_answer, str):
            # String comparison (case-insensitive)
            correct = result.lower().strip() == gold_answer.lower().strip()
            return correct, ""

        # Otherwise, numeric comparison
        result_num = float(result)
        gold_num = float(gold_answer)

        # Exact comparison after rounding
        correct = abs(result_num - gold_num) < 1e-9

        return correct, ""

    except (ValueError, TypeError) as e:
        # Cannot compare - this is an evaluator error
        return False, f"evaluator_error_compare: {type(e).__name__}"


# ============================================================================
# RESPONSE EXTRACTION
# ============================================================================

def extract_program_case_insensitive(response_text: str) -> Optional[str]:
    """
    Extract program with case-insensitive PROGRAM marker.

    Handles: PROGRAM: / Program: / program: / PrOgRaM: etc.
    """
    # Case-insensitive regex
    match = re.search(
        r'(?i)program:\s*(.+?)(?=\n(?:answer|ANSWER):|$)',
        response_text,
        re.DOTALL | re.IGNORECASE
    )

    if not match:
        return None

    raw = match.group(1).strip()

    # Remove code fences
    raw = re.sub(r'```(?:python|finqa)?\s*', '', raw)
    raw = re.sub(r'```\s*$', '', raw)

    return raw if raw else None


def normalize_program_v2(raw_program: str) -> str:
    """
    Normalize program for parsing.

    - Replace newlines with commas
    - Standardize whitespace
    - Remove inline comments
    - Remove duplicate commas
    """
    if not raw_program:
        return raw_program

    # Replace ", \n" or ",\n" with ", "
    normalized = re.sub(r',\s*\n', ', ', raw_program)
    # Replace remaining "\n" with ", "
    normalized = normalized.replace('\n', ', ')

    # Remove inline comments (# followed by non-digit)
    normalized = re.sub(r'\s*#(?![0-9])[^\n,]*', '', normalized)

    # Standardize whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    # Remove duplicate commas
    normalized = re.sub(r',\s*,+', ',', normalized)

    # Standardize comma spacing
    normalized = re.sub(r'\s*,\s*', ', ', normalized)

    return normalized.strip()


def check_operator_only(program: str) -> bool:
    """Check if program is operator-only (no operands)."""
    return bool(re.match(r'^[a-z_]+(?:\s*,\s*[a-z_]+)*\s*$', program))


# ============================================================================
# MAIN EVALUATION
# ============================================================================

def evaluate_response_v2(
    response_record: Dict,
    target: Dict
) -> Dict:
    """
    Canonical V2 evaluation with strict parsing and no silent fallbacks.
    """
    target_id = target['id']
    gold_answer = target['qa']['exe_ans']
    response_text = response_record['response']

    # Step 1: Extract program
    raw_program = extract_program_case_insensitive(response_text)

    if raw_program is None:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': None,
            'normalized_program': None,
            'parsed_steps': None,
            'execution_status': 'no_program',
            'execution_result': None,
            'program_correct': False,
            'error_category': 'extraction',
            'error_detail': 'no_program_marker_found'
        }

    # Step 2: Check operator-only
    if check_operator_only(raw_program):
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': raw_program,
            'parsed_steps': None,
            'execution_status': 'operator_only',
            'execution_result': None,
            'program_correct': False,
            'error_category': 'operator_only',
            'error_detail': 'no_operands'
        }

    # Step 3: Normalize
    normalized = normalize_program_v2(raw_program)

    # Step 4: Parse with strict validation
    steps, parse_error = parse_program_v2_strict(normalized)

    if steps is None:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': normalized,
            'parsed_steps': None,
            'execution_status': 'parse_fail',
            'execution_result': None,
            'program_correct': False,
            'error_category': 'parse',
            'error_detail': parse_error
        }

    # Step 5: Execute
    table = target.get('table', [])
    success, result, exec_error = execute_program_v2(steps, table)

    if not success:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': normalized,
            'parsed_steps': steps,
            'execution_status': 'exec_fail',
            'execution_result': None,
            'program_correct': False,
            'error_category': 'execution',
            'error_detail': exec_error
        }

    # Step 6: Check correctness (NO silent fallback)
    correct, compare_error = check_correctness_v2(result, gold_answer)

    if compare_error:
        return {
            'target_id': target_id,
            'arm': response_record.get('arm', 'unknown'),
            'gold_answer': gold_answer,
            'raw_program': raw_program,
            'normalized_program': normalized,
            'parsed_steps': steps,
            'execution_status': 'success',
            'execution_result': result,
            'program_correct': False,
            'error_category': 'evaluator_error',
            'error_detail': compare_error
        }

    return {
        'target_id': target_id,
        'arm': response_record.get('arm', 'unknown'),
        'gold_answer': gold_answer,
        'raw_program': raw_program,
        'normalized_program': normalized,
        'parsed_steps': steps,
        'execution_status': 'success',
        'execution_result': result,
        'program_correct': correct,
        'error_category': None if correct else 'wrong_result',
        'error_detail': None if correct else f'got_{result}_expected_{gold_answer}'
    }


def evaluate_arm_v2(
    arm_name: str,
    responses: List[Dict],
    target_map: Dict[str, Dict]
) -> Tuple[List[Dict], Dict]:
    """Evaluate all responses for one arm."""
    evaluations = []

    for resp in responses:
        target = target_map[resp['target_id']]
        eval_record = evaluate_response_v2(resp, target)
        evaluations.append(eval_record)

    # Compute metrics
    total = len(evaluations)
    correct = sum(1 for e in evaluations if e['program_correct'])

    error_categories = {}
    for e in evaluations:
        if not e['program_correct']:
            cat = e.get('error_category', 'unknown')
            error_categories[cat] = error_categories.get(cat, 0) + 1

    metrics = {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0,
        'error_categories': error_categories
    }

    return evaluations, metrics


def main():
    """Run canonical V2 evaluation on all historical arms."""
    import os
    BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

    print("="*80)
    print("CANONICAL EVALUATOR V2")
    print("="*80)
    print()

    # Load targets
    with open(os.path.join(BASE_PATH, 'expanded_sample_queries.json')) as f:
        targets = json.load(f)
    target_map = {t['id']: t for t in targets}
    print(f"Loaded {len(targets)} targets")
    print()

    # Define arms
    arms = {
        'Case_Stage37': os.path.join(BASE_PATH, 'results_case_expanded.json'),
        'Strategy_Stage37': os.path.join(BASE_PATH, 'results_strategy_expanded.json'),
        'Format-Neutral_Stage39': os.path.join(BASE_PATH, 'results_format_neutral_full224.json'),
        'Format-Neutral+Binding_Stage39': os.path.join(BASE_PATH, 'results_format_neutral_binding_full224.json'),
        'Grounded-Sketch_Stage39': os.path.join(BASE_PATH, 'results_grounded_sketch_full224.json'),
    }

    all_evaluations = {}
    all_metrics = {}

    for arm_name, filepath in arms.items():
        if not os.path.exists(filepath):
            print(f"Skipping {arm_name}: file not found")
            continue

        print(f"Evaluating {arm_name}...")
        with open(filepath) as f:
            responses = json.load(f)

        evaluations, metrics = evaluate_arm_v2(arm_name, responses, target_map)
        all_evaluations[arm_name] = evaluations
        all_metrics[arm_name] = metrics

        print(f"  Accuracy: {metrics['correct']}/{metrics['total']} ({100*metrics['accuracy']:.1f}%)")
        print(f"  Errors: {metrics['error_categories']}")
        print()

    # Save results
    output = {
        'evaluations': all_evaluations,
        'metrics': all_metrics,
        'evaluator': 'canonical_v2',
        'notes': 'Strict full-string consumption, no silent fallbacks'
    }

    output_file = os.path.join(BASE_PATH, 'canonical_v2_evaluations.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print("="*80)
    print(f"Saved to {output_file}")
    print("="*80)


if __name__ == '__main__':
    main()
