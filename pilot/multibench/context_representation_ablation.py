#!/usr/bin/env python3
"""
Context Representation Ablation Experiment

Compares rendering variants for MultiHiertt evidence coverage:
- Current: 600-char raw HTML preview
- Variant A: 2000-char raw HTML preview
- Variant B: Structured table (markdown/text with preserved relationships)

Zero API cost - purely deterministic offline analysis.
"""

import re
import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

sys.path.insert(0, '/home/tiantian/keyan')

import pyarrow.parquet as pq
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def normalize_numeric_forms(text: str) -> str:
    """
    Normalize numeric representations to canonical form.
    - Remove commas: 14,316 → 14316
    - Remove dollar signs: $10.2 → 10.2
    - Preserve negatives and decimals
    """
    # Remove commas from numbers
    text = re.sub(r'(\d),(\d)', r'\1\2', text)
    # Remove dollar signs adjacent to numbers
    text = re.sub(r'\$(\d)', r'\1', text)
    return text


def extract_source_operands(program: str) -> Set[str]:
    """
    Extract source operands from gold program, excluding:
    - Constants like 0, 1, 100 (common in percentage calculations)
    - Intermediate references: #0, #1, #2
    - Pure year values (4-digit numbers starting with 19 or 20)

    Returns normalized numeric strings.
    """
    if not program:
        return set()

    # First replace commas within function calls with spaces to separate operands
    # subtract(3195,5) -> subtract(3195 5)
    program_spaced = re.sub(r',', ' ', program)

    # Extract all numeric tokens (including negatives and decimals)
    tokens = re.findall(r'-?\d+\.?\d*', program_spaced)

    operands = set()
    for tok in tokens:
        # Skip common constants
        if tok in ('0', '1', '100'):
            continue
        # Skip year-like values (1900-2099)
        if re.match(r'^(19|20)\d{2}$', tok):
            continue
        # Skip single-digit numbers (likely constants)
        if len(tok) == 1:
            continue

        operands.add(tok)

    return operands


def render_html_preview(html: str, limit: int) -> str:
    """Render HTML table as truncated raw HTML (current baseline)."""
    if not html or not html.strip():
        return ""
    return html[:limit]


def render_structured_table(html: str, char_limit: int = 2000) -> str:
    """
    Render HTML table as structured text preserving row/column relationships.
    Format: markdown-like with headers and aligned columns.

    Falls back to regex-based parsing if BeautifulSoup not available.
    """
    if not html or not html.strip():
        return ""

    if HAS_BS4:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table')
            if not table:
                return html[:char_limit]

            rows = []
            headers = []

            # Extract headers from thead or first tr
            thead = table.find('thead')
            if thead:
                header_row = thead.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

            if not headers:
                first_row = table.find('tr')
                if first_row:
                    headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]

            # Extract data rows
            tbody = table.find('tbody') or table
            for tr in tbody.find_all('tr'):
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if cells and cells != headers:  # Skip header repetition
                    rows.append(cells)

            # Build markdown table
            if not rows:
                return html[:char_limit]

            # Ensure headers match column count
            if headers and len(headers) == len(rows[0]):
                lines = ['| ' + ' | '.join(headers) + ' |']
                lines.append('|' + '---|' * len(headers))
            else:
                lines = []

            for row in rows:
                lines.append('| ' + ' | '.join(row) + ' |')

            result = '\n'.join(lines)
            return result[:char_limit]

        except Exception:
            pass

    # Fallback: Simple regex-based extraction
    # Extract text between <td> and <th> tags, preserve row structure
    try:
        # Remove HTML tags but preserve structure with | separators
        text = html
        # Replace </tr> with newline
        text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
        # Replace <td> and <th> boundaries with |
        text = re.sub(r'</?t[dh][^>]*>', '|', text, flags=re.IGNORECASE)
        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up whitespace
        lines = []
        for line in text.split('\n'):
            cleaned = '|'.join(cell.strip() for cell in line.split('|') if cell.strip())
            if cleaned:
                lines.append('| ' + cleaned + ' |')

        result = '\n'.join(lines)
        return result[:char_limit]
    except Exception:
        return html[:char_limit]


def render_context_variant(
    gold_row: Dict,
    variant: str,
    html_limit: int = 600
) -> Tuple[str, int]:
    """
    Render context using specified variant.

    Returns: (rendered_text, approximate_token_count)
    """
    paragraphs = gold_row.get('paragraphs', []) or []
    tables_html = gold_row.get('tables', []) or []

    parts = []

    # Paragraphs (unchanged across variants)
    if paragraphs:
        para_text = ' '.join(paragraphs[:5])  # Limit to first 5 paragraphs
        parts.append(f"Paragraphs: {para_text}")

    # Tables (variant-dependent)
    if tables_html:
        if variant == 'html_600':
            for i, html in enumerate(tables_html, 1):
                preview = render_html_preview(html, limit=600)
                if preview.strip():
                    parts.append(f"Table {i}: {preview}")

        elif variant == 'html_2000':
            for i, html in enumerate(tables_html, 1):
                preview = render_html_preview(html, limit=2000)
                if preview.strip():
                    parts.append(f"Table {i}: {preview}")

        elif variant == 'structured':
            for i, html in enumerate(tables_html, 1):
                structured = render_structured_table(html, char_limit=2000)
                if structured.strip():
                    parts.append(f"Table {i}:\n{structured}")

    rendered = '\n\n'.join(parts)
    # Rough token estimate: ~4 chars per token
    token_estimate = len(rendered) // 4

    return rendered, token_estimate


def compute_coverage(
    gold_row: Dict,
    rendered_context: str,
    variant: str
) -> Dict:
    """
    Compute operand coverage for a single sample.

    Returns dict with:
    - source_operands: set of operands to find
    - found_operands: set of operands actually present
    - coverage_rate: fraction found
    - missing_operands: set of operands not found
    """
    program = gold_row.get('program', '')
    source_ops = extract_source_operands(program)

    if not source_ops:
        return {
            'source_operands': set(),
            'found_operands': set(),
            'coverage_rate': None,  # No operands to find
            'missing_operands': set(),
            'has_full_evidence': None
        }

    # Normalize both context and operands for comparison
    normalized_context = normalize_numeric_forms(rendered_context)

    found = set()
    for op in source_ops:
        # Check if operand appears in normalized context
        if op in normalized_context:
            found.add(op)

    coverage_rate = len(found) / len(source_ops)
    has_full = coverage_rate == 1.0

    return {
        'source_operands': source_ops,
        'found_operands': found,
        'coverage_rate': coverage_rate,
        'missing_operands': source_ops - found,
        'has_full_evidence': has_full
    }


def run_ablation(
    cache_path: Path,
    val_parquet: Path
) -> Dict:
    """
    Run ablation across all variants on cached samples.

    Returns structured results for reporting.
    """
    # Load validation data
    val_table = pq.read_table(str(val_parquet))
    gold_by_uid = {row['uid']: row for row in val_table.to_pylist()}

    # Load cache (use none arm only)
    cache = []
    with open(cache_path) as f:
        for line in f:
            if line.strip():
                cache.append(json.loads(line))

    none_records = [r for r in cache if r['arm'] == 'none']
    print(f"Loaded {len(none_records)} none-arm samples from cache")

    # Define variants
    variants = [
        ('html_600', '600-char HTML (baseline)'),
        ('html_2000', '2000-char HTML'),
        ('structured', 'Structured table (markdown-like)')
    ]

    results = {}

    for variant_key, variant_name in variants:
        print(f"\n[{variant_key}] Processing {variant_name}...")

        coverages = []
        token_costs = []
        samples_with_full = []
        samples_improved_from_baseline = []

        for rec in none_records:
            uid = rec['uid']
            gold = gold_by_uid[uid]

            # Skip samples without programs
            if not gold.get('program'):
                continue

            # Render context with this variant
            rendered, tokens = render_context_variant(gold, variant_key)

            # Compute coverage
            cov = compute_coverage(gold, rendered, variant_key)

            if cov['coverage_rate'] is not None:
                coverages.append(cov['coverage_rate'])
                token_costs.append(tokens)

                if cov['has_full_evidence']:
                    samples_with_full.append({
                        'uid': uid,
                        'question': gold['question'][:80],
                        'operands': list(cov['source_operands'])
                    })

                # Track improvement from baseline (only for non-baseline variants)
                if variant_key != 'html_600':
                    samples_improved_from_baseline.append({
                        'uid': uid,
                        'coverage': cov['coverage_rate'],
                        'found': list(cov['found_operands']),
                        'missing': list(cov['missing_operands'])
                    })

        # Aggregate statistics
        avg_coverage = sum(coverages) / len(coverages) if coverages else 0.0
        pct_full = len(samples_with_full) / len(coverages) * 100 if coverages else 0.0
        avg_tokens = sum(token_costs) / len(token_costs) if token_costs else 0

        results[variant_key] = {
            'name': variant_name,
            'avg_coverage': avg_coverage,
            'pct_samples_full_evidence': pct_full,
            'avg_token_cost': avg_tokens,
            'n_samples': len(coverages),
            'samples_with_full': samples_with_full[:5],  # Top 5 examples
            'samples_improved': samples_improved_from_baseline[:5] if variant_key != 'html_600' else []
        }

        print(f"  Avg coverage: {avg_coverage:.3f}")
        print(f"  Full evidence: {pct_full:.1f}%")
        print(f"  Avg tokens: {avg_tokens:.0f}")

    return results


def generate_report(results: Dict, output_path: Path):
    """Generate markdown report from ablation results."""

    lines = [
        "# Context Representation Ablation Results",
        "",
        "**Date**: 2026-08-18",
        "**Experiment**: Deterministic offline evidence coverage comparison",
        "**Samples**: 53 MultiHiertt validation samples with gold programs (from 60-sample cache)",
        "",
        "## Executive Summary",
        ""
    ]

    # Summary table
    lines.append("| Variant | Avg Coverage | Full Evidence % | Avg Tokens | Δ vs Baseline |")
    lines.append("|---------|------------:|----------------:|-----------:|-------------:|")

    baseline_cov = results['html_600']['avg_coverage']
    baseline_full = results['html_600']['pct_samples_full_evidence']

    for vkey in ['html_600', 'html_2000', 'structured']:
        r = results[vkey]
        delta_cov = r['avg_coverage'] - baseline_cov
        delta_full = r['pct_samples_full_evidence'] - baseline_full

        lines.append(
            f"| {r['name']} | {r['avg_coverage']:.3f} | {r['pct_samples_full_evidence']:.1f}% | "
            f"{r['avg_token_cost']:.0f} | +{delta_cov:.3f} ({delta_full:+.1f}%) |"
        )

    lines.extend([
        "",
        "## Key Findings",
        ""
    ])

    # Determine if structured offers improvement beyond char limit
    html_2k = results['html_2000']
    struct = results['structured']

    struct_advantage = struct['avg_coverage'] - html_2k['avg_coverage']

    lines.append(f"1. **Baseline (600-char HTML)**: {baseline_cov:.1%} coverage, {baseline_full:.1f}% samples with full evidence")
    lines.append(f"2. **Increasing char limit (2000-char HTML)**: {html_2k['avg_coverage']:.1%} coverage (+{html_2k['avg_coverage']-baseline_cov:.1%})")
    lines.append(f"3. **Structured table**: {struct['avg_coverage']:.1%} coverage (+{struct['avg_coverage']-baseline_cov:.1%} vs baseline)")
    lines.append(f"4. **Structured advantage over 2000-char HTML**: {struct_advantage:+.3f} ({struct_advantage*100:+.1f} percentage points)")
    lines.append("")

    if struct_advantage > 0.05:
        lines.append("**Conclusion**: Structured rendering offers **substantial improvement** beyond char limit increase.")
    elif struct_advantage > 0.01:
        lines.append("**Conclusion**: Structured rendering offers **modest improvement** beyond char limit increase.")
    else:
        lines.append("**Conclusion**: Structured rendering offers **negligible improvement** beyond char limit increase. Simply increasing char limit is sufficient.")

    lines.extend([
        "",
        "## Detailed Results by Variant",
        ""
    ])

    for vkey in ['html_600', 'html_2000', 'structured']:
        r = results[vkey]
        lines.extend([
            f"### {r['name']}",
            "",
            f"- **Average coverage**: {r['avg_coverage']:.3f}",
            f"- **Samples with full evidence**: {len(r['samples_with_full'])}/{r['n_samples']} ({r['pct_samples_full_evidence']:.1f}%)",
            f"- **Average token cost**: {r['avg_token_cost']:.0f}",
            ""
        ])

        if r['samples_with_full']:
            lines.append("Examples with full evidence:")
            for ex in r['samples_with_full'][:3]:
                lines.append(f"- `{ex['uid'][:8]}...`: \"{ex['question']}\" (operands: {', '.join(ex['operands'])})")
            lines.append("")

    lines.extend([
        "## Recommendation",
        ""
    ])

    # Decision logic
    if struct['pct_samples_full_evidence'] >= 70:
        lines.append("**Option A: Keep MultiHiertt with structured rendering**")
        lines.append(f"- Achieves {struct['pct_samples_full_evidence']:.1f}% full evidence coverage")
        lines.append(f"- Token cost: ~{struct['avg_token_cost']:.0f} tokens/sample")
        lines.append("- **Recommended** if structured rendering is cheap to implement")
    elif html_2k['pct_samples_full_evidence'] >= 70:
        lines.append("**Option A: Keep MultiHiertt with 2000-char HTML limit**")
        lines.append(f"- Achieves {html_2k['pct_samples_full_evidence']:.1f}% full evidence coverage")
        lines.append("- Simple fix: change `limit=600` to `limit=2000`")
        lines.append(f"- Token cost: ~{html_2k['avg_token_cost']:.0f} tokens/sample")
        lines.append("- **Recommended** if implementation cost matters")
    else:
        lines.append("**Option B: Drop MultiHiertt, use FinQA**")
        lines.append(f"- Even best variant achieves only {max(struct['pct_samples_full_evidence'], html_2k['pct_samples_full_evidence']):.1f}% full evidence")
        lines.append("- MultiHiertt table complexity too high for context rendering")
        lines.append("- FinQA Stage 1 complete, known to work")
        lines.append("- **Recommended** to conserve research budget")

    lines.extend([
        "",
        "## Methodological Notes",
        "",
        "**Evidence coverage metric**:",
        "- Extracts source operands from gold program (excludes constants, intermediate refs, years)",
        "- Normalizes numeric forms: 14,316 ↔ 14316, $10.2 ↔ 10.2",
        "- Coverage = fraction of source operands present in rendered context",
        "",
        "**Why this metric**:",
        "- Character retention (52.8% in Stage 34) does not equal evidence retention",
        "- Operand coverage directly measures reasoning prerequisite",
        "- Normalized forms prevent false negatives from formatting differences",
        "",
        "**Zero API cost**: All analysis deterministic offline on cached data.",
        ""
    ])

    output_path.write_text('\n'.join(lines))
    print(f"\nReport written to {output_path}")


def main():
    """Execute ablation and generate report."""
    cache_path = Path('/home/tiantian/keyan/pilot/multibench/output/multihiertt/multihiertt_four_arm_dry_run_repaired_cache.jsonl')
    val_parquet = Path('/home/tiantian/keyan/data/multihiertt/raw/validation.parquet')
    output_path = Path('/home/tiantian/keyan/pilot/CONTEXT_ABLATION_REPORT.md')

    print("=" * 70)
    print("Context Representation Ablation Experiment")
    print("=" * 70)

    results = run_ablation(cache_path, val_parquet)
    generate_report(results, output_path)

    print("\n" + "=" * 70)
    print("Ablation complete. See CONTEXT_ABLATION_REPORT.md for full results.")
    print("=" * 70)


if __name__ == '__main__':
    main()
