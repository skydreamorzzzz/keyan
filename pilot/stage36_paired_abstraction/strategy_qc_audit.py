#!/usr/bin/env python3
"""
Strategy QC Audit: Check for operation hallucination

Specifically检查:
1. Source gold program 的实际 operations
2. Strategy abstraction 中提到的 operations
3. 是否 Strategy 新增了 source 没有的 operations (特别是 *100, /100)
4. Scale/unit convention 是否一致

输出 audit report CSV 和 JSON
"""

import json
import re
import sys
from typing import List, Set, Dict, Tuple

sys.path.insert(0, '/home/tiantian/keyan/pilot')
from executor import parse_program_re, parse_linear_steps


def extract_operations_from_program(program_str: str) -> List[str]:
    """
    从 gold program 字符串中提取 operations.

    正确解析 program，不是逐字符迭代。
    """
    if not program_str or program_str == 'N/A':
        return []

    # Normalize
    normalized = program_str.replace('\n', ', ')

    try:
        # Detect format
        depth = 0
        has_top_level_comma = False
        for c in normalized:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 0:
                has_top_level_comma = True
                break

        # Parse
        if has_top_level_comma:
            steps = parse_linear_steps(normalized)
        else:
            steps = parse_program_re(normalized)

        # Extract operations
        ops = [step[0] for step in steps]
        return ops

    except Exception as e:
        # Fallback: regex extraction
        ops = re.findall(r'(table_\w+|\w+)(?=\()', program_str)
        return ops


def extract_operations_from_strategy_text(strategy_dict: Dict) -> Set[str]:
    """
    从 Strategy dict 中提取提到的 operations.

    检查所有文本字段。
    """
    strategy_text = json.dumps(strategy_dict).lower()

    # Known operations
    all_ops = [
        'add', 'subtract', 'multiply', 'divide', 'exp', 'greater',
        'table_max', 'table_min', 'table_sum', 'table_average'
    ]

    mentioned = set()
    for op in all_ops:
        if op in strategy_text or op.replace('_', ' ') in strategy_text:
            mentioned.add(op)

    # Check for percentage conversion mentions
    if 'multiply by 100' in strategy_text or '*100' in strategy_text or '* 100' in strategy_text:
        mentioned.add('multiply_by_100')

    if 'divide by 100' in strategy_text or '/100' in strategy_text or '/ 100' in strategy_text:
        mentioned.add('divide_by_100')

    if 'const_100' in strategy_text:
        mentioned.add('const_100')

    return mentioned


def check_operation_hallucination(
    source_program: str,
    strategy_dict: Dict
) -> Dict:
    """
    检查 Strategy 是否添加了 source 没有的 operations.
    """
    source_ops = extract_operations_from_program(source_program)
    source_ops_set = set(source_ops)

    strategy_ops = extract_operations_from_strategy_text(strategy_dict)

    # Check for hallucinated operations
    hallucinated = strategy_ops - source_ops_set

    # Special check: percentage conversion hallucination
    has_percentage_hallucination = False
    if ('multiply_by_100' in hallucinated or
        'const_100' in hallucinated or
        'divide_by_100' in hallucinated):
        # Check if source has any percentage conversion
        has_source_pct = any(
            'multiply' in source_ops and ('100' in source_program or 'const_100' in source_program)
            for _ in [1]
        )
        if not has_source_pct:
            has_percentage_hallucination = True

    return {
        'source_ops': source_ops,
        'strategy_mentions': list(strategy_ops),
        'hallucinated_ops': list(hallucinated),
        'has_percentage_hallucination': has_percentage_hallucination,
        'clean': len(hallucinated) == 0
    }


def audit_all_strategies():
    """
    Audit all Strategy abstractions.
    """
    BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'

    print("="*80)
    print("STRATEGY QC AUDIT: Operation Hallucination Check")
    print("="*80)
    print()

    # Load sources
    with open(f'{BASE_PATH}/paired_sources.json') as f:
        sources = json.load(f)

    # Load abstractions (if they exist as separate file)
    # Otherwise they're in the same sources file with 'strategy' representation

    # Filter to strategy representations
    strategies = [s for s in sources if s.get('representation') == 'strategy']

    print(f"Found {len(strategies)} strategy abstractions")
    print()

    # Run audit
    audit_results = []
    hallucination_count = 0
    percentage_hallucination_count = 0

    for strategy in strategies:
        source_id = strategy['source_experience_id']

        # Find corresponding case (same source, but 'case' representation)
        case = next((s for s in sources if
                    s['source_experience_id'] == source_id and
                    s.get('representation') == 'case'), None)

        if case is None:
            print(f"WARNING: No case found for {source_id}")
            continue

        # Get gold program from case
        source_program = case.get('program', '')

        # Audit
        result = check_operation_hallucination(source_program, strategy)
        result['source_id'] = source_id

        audit_results.append(result)

        if not result['clean']:
            hallucination_count += 1
            if result['has_percentage_hallucination']:
                percentage_hallucination_count += 1

    print(f"Audit complete:")
    print(f"  Total strategies: {len(audit_results)}")
    print(f"  Clean (no hallucination): {len(audit_results) - hallucination_count}")
    print(f"  With hallucination: {hallucination_count}")
    print(f"  With percentage hallucination: {percentage_hallucination_count}")
    print()

    # Show examples
    hallucinated = [r for r in audit_results if not r['clean']]
    if len(hallucinated) > 0:
        print(f"Examples of hallucination (first 10):")
        for r in hallucinated[:10]:
            print(f"\n  {r['source_id']}:")
            print(f"    Source ops: {r['source_ops']}")
            print(f"    Strategy mentions: {r['strategy_mentions']}")
            print(f"    Hallucinated: {r['hallucinated_ops']}")
            if r['has_percentage_hallucination']:
                print(f"    ⚠️  PERCENTAGE CONVERSION HALLUCINATION")

    # Save results
    output = {
        'total': len(audit_results),
        'clean': len(audit_results) - hallucination_count,
        'with_hallucination': hallucination_count,
        'with_percentage_hallucination': percentage_hallucination_count,
        'details': audit_results
    }

    output_file = f'{BASE_PATH}/strategy_qc_audit.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print()
    print("="*80)
    print(f"Saved to {output_file}")
    print("="*80)

    return output


if __name__ == '__main__':
    audit_all_strategies()
