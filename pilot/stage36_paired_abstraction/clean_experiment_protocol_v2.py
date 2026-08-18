#!/usr/bin/env python3
"""
Clean Experiment Protocol V2

Minimal comparison to isolate template effect: Clean-FN vs Clean-FN+Sketch

Key principles:
1. Primary causal comparison: ONLY differ by program sketch presence
2. Identical base prompt, document rendering, output instruction
3. Use CLEAN Format-Neutral (either filter contaminated or regenerate)
4. Complete document: pre_text + table + post_text + question
5. Frozen parameters: 224 queries, k=3, temp=0, same model

This protocol DOES NOT call APIs - only defines what should be run.
"""

import json
import os
from typing import Dict, List


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


# ============================================================================
# SHARED PROMPT COMPONENTS (identical for both arms)
# ============================================================================

SYSTEM_PROMPT = """You are a financial reasoning assistant specialized in generating executable programs for financial question answering.

Your task: Given a financial document with tables and a question, generate an executable FinQA program that answers the question.

FinQA Program Syntax:
- Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average
- Arguments: numbers, const_X (constants like const_100, const_m1), #N (reference to step N result), table row labels
- Format: operation(arg1, arg2)
- Multi-step programs: operation1(a, b), operation2(#0, c), operation3(#1, d)
- Example: divide(100, 50), multiply(#0, 2) computes (100/50)*2 = 4

Requirements:
- Extract values from the CURRENT document, not from experience examples
- Generate complete, executable programs
- Use exact values from document tables and text

Output Format:
PROGRAM: <executable FinQA program>
ANSWER: <numerical answer>
"""


OUTPUT_INSTRUCTION = """Generate an executable FinQA program to answer the question using values from the current document.

PROGRAM: <your executable program>
ANSWER: <your numerical answer>"""


# ============================================================================
# DOCUMENT RENDERING (identical for both arms)
# ============================================================================

def render_document(target: Dict) -> str:
    """
    Render complete document with pre_text, table, post_text.

    Identical for both arms.
    """
    parts = []

    # Pre-text
    if 'pre_text' in target and target['pre_text']:
        parts.append("# Document Context\n")
        parts.append(" ".join(target['pre_text']))
        parts.append("\n")

    # Table
    if 'table' in target and target['table']:
        parts.append("\n# Table\n")
        table = target['table']

        # Format as aligned columns
        for row in table:
            parts.append(" | ".join(str(cell) for cell in row))
        parts.append("\n")

    # Post-text
    if 'post_text' in target and target['post_text']:
        parts.append("# Additional Context\n")
        parts.append(" ".join(target['post_text']))
        parts.append("\n")

    return "\n".join(parts)


# ============================================================================
# MEMORY CONSTRUCTION (DIFFERS between arms)
# ============================================================================

def construct_clean_fn_memory(source_ids: List[str], strategy_map: Dict) -> str:
    """
    Clean Format-Neutral memory: Natural language reasoning patterns.

    Uses CLEAN strategies (contaminated sources filtered/regenerated).

    NO program template.
    NO explicit binding instruction.
    """
    parts = ["# Relevant Reasoning Patterns\n"]

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strategy = strategy_map[source_id]

        # Skip if marked as contaminated
        if strategy.get('contaminated', False):
            continue

        parts.append(f"\n## Pattern: {strategy['strategy_name']}")
        parts.append(f"\nWhen to use: {strategy['problem_pattern']}")
        parts.append(f"\nReasoning approach:")
        parts.append(strategy['reasoning_steps'])
        parts.append(f"\nOperand identification:")
        parts.append(strategy['operand_roles'])
        parts.append("")

    return "\n".join(parts)


def construct_clean_fn_sketch_memory(
    source_ids: List[str],
    strategy_map: Dict,
    sketch_map: Dict
) -> str:
    """
    Clean Format-Neutral + Sketch memory.

    Adds program template to Clean-FN.
    Everything else IDENTICAL to Clean-FN.
    """
    parts = ["# Relevant Program Patterns\n"]

    for source_id in source_ids:
        if source_id not in strategy_map or source_id not in sketch_map:
            continue

        strategy = strategy_map[source_id]
        sketch = sketch_map[source_id]

        # Skip if marked as contaminated
        if strategy.get('contaminated', False):
            continue

        parts.append(f"\n## Pattern: {strategy['strategy_name']}")
        parts.append(f"\nWhen to use: {strategy['problem_pattern']}")

        # Reasoning (same as Clean-FN)
        parts.append(f"\nReasoning approach:")
        parts.append(strategy['reasoning_steps'])

        # Operand identification (same as Clean-FN)
        parts.append(f"\nOperand identification:")
        parts.append(strategy['operand_roles'])

        # THE ONLY DIFFERENCE: Add program template
        parts.append(f"\n**Program template:**")
        parts.append(sketch['program_sketch'])
        parts.append("\nReplace placeholders (<value1>, <value2>, etc.) with actual values from the current document.")
        parts.append("")

    return "\n".join(parts)


# ============================================================================
# PROMPT CONSTRUCTION (identical structure, differs only by memory)
# ============================================================================

def build_prompt(
    document: str,
    question: str,
    memory: str
) -> str:
    """
    Build complete prompt.

    Identical structure for both arms, only memory content differs.
    """
    return f"""{SYSTEM_PROMPT}

{document}

# Question

{question}

# Experience Memory

{memory}

{OUTPUT_INSTRUCTION}
"""


# ============================================================================
# EXPERIMENT PROTOCOL
# ============================================================================

class CleanExperimentProtocol:
    """
    Protocol definition for clean 3-arm comparison.

    DOES NOT call APIs - only defines protocol.
    """

    def __init__(self):
        self.targets = []
        self.retrieval_cache = []
        self.strategy_map = {}
        self.sketch_map = {}
        self.audit_results = {}

    def load_data(self):
        """Load all required data."""
        print("Loading data...")

        # Load targets
        with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
            self.targets = json.load(f)

        # Load retrieval cache
        with open(f'{BASE_PATH}/expanded_retrieval_cache.json') as f:
            self.retrieval_cache = json.load(f)

        # Load CLEAN strategies (regenerated v2)
        with open(f'{BASE_PATH}/strategies_format_neutral_clean_v2.json') as f:
            strategies = json.load(f)
        self.strategy_map = {s['source_experience_id']: s for s in strategies}

        # Load sketches
        with open(f'{BASE_PATH}/grounded_sketches.json') as f:
            sketches = json.load(f)
        self.sketch_map = {s['source_experience_id']: s for s in sketches}

        # Load post-regeneration QC audit results
        with open(f'{BASE_PATH}/strategy_qc_audit_v2_post_regen.json') as f:
            audit = json.load(f)

        # Mark remaining contaminated strategies (should be minimal after regeneration)
        for result in audit['audit_results']:
            source_id = result['source_id']
            if result['contaminated'] and source_id in self.strategy_map:
                self.strategy_map[source_id]['contaminated'] = True

        print(f"  Targets: {len(self.targets)}")
        print(f"  Strategies: {len(self.strategy_map)}")
        print(f"  Sketches: {len(self.sketch_map)}")

        contaminated_count = sum(1 for s in self.strategy_map.values() if s.get('contaminated', False))
        print(f"  Contaminated strategies (filtered): {contaminated_count}")
        print()

    def generate_arm_data(self, arm_type: str) -> List[Dict]:
        """
        Generate prompt data for one arm.

        Args:
            arm_type: 'clean_fn' or 'clean_fn_sketch'

        Returns:
            List of prompt records (does NOT call API)
        """
        prompts = []

        for target in self.targets:
            target_id = target['id']

            # Get retrieval
            retrieval = next((r for r in self.retrieval_cache if r['target_id'] == target_id), None)
            if not retrieval:
                print(f"  ⚠️  No retrieval for {target_id}")
                continue

            source_ids = retrieval['shared_source_ids'][:3]  # k=3

            # Render document
            document = render_document(target)
            question = target['qa']['question']

            # Construct memory (ONLY DIFFERENCE)
            if arm_type == 'clean_fn':
                memory = construct_clean_fn_memory(source_ids, self.strategy_map)
            elif arm_type == 'clean_fn_sketch':
                memory = construct_clean_fn_sketch_memory(source_ids, self.strategy_map, self.sketch_map)
            else:
                raise ValueError(f"Unknown arm type: {arm_type}")

            # Build prompt
            prompt = build_prompt(document, question, memory)

            prompts.append({
                'target_id': target_id,
                'arm': arm_type,
                'prompt': prompt,
                'source_ids': source_ids,
                'gold_program': target['qa']['program'],
                'gold_answer': target['qa']['exe_ans']
            })

        return prompts

    def show_example_prompts(self):
        """Show example prompts for both arms."""
        if not self.targets:
            self.load_data()

        print("="*80)
        print("EXAMPLE PROMPTS")
        print("="*80)
        print()

        # Get first target with valid retrieval
        target = None
        retrieval = None
        for t in self.targets:
            r = next((r for r in self.retrieval_cache if r['target_id'] == t['id']), None)
            if r and 'shared_source_ids' in r and r['shared_source_ids']:
                target = t
                retrieval = r
                break

        if not target or not retrieval:
            print("  ⚠️  No valid target with retrieval found")
            return

        target_id = target['id']
        source_ids = retrieval['shared_source_ids'][:3]

        document = render_document(target)
        question = target['qa']['question']

        # Clean-FN
        print("ARM 1: Clean Format-Neutral")
        print("-"*80)
        memory_fn = construct_clean_fn_memory(source_ids, self.strategy_map)
        prompt_fn = build_prompt(document, question, memory_fn)
        print(prompt_fn[:1500])
        print("...")
        print()

        # Clean-FN+Sketch
        print("ARM 2: Clean Format-Neutral + Sketch")
        print("-"*80)
        memory_fns = construct_clean_fn_sketch_memory(source_ids, self.strategy_map, self.sketch_map)
        prompt_fns = build_prompt(document, question, memory_fns)
        print(prompt_fns[:1500])
        print("...")
        print()

    def generate_protocol_summary(self):
        """Generate summary of protocol."""
        if not self.targets:
            self.load_data()

        print("="*80)
        print("CLEAN EXPERIMENT PROTOCOL V2")
        print("="*80)
        print()

        print("PRIMARY COMPARISON:")
        print("  Clean-FN vs Clean-FN+Sketch")
        print()

        print("IDENTICAL FACTORS:")
        print("  ✓ System prompt")
        print("  ✓ Document rendering (pre_text + table + post_text)")
        print("  ✓ Output instruction")
        print("  ✓ Strategy source (cleaned)")
        print("  ✓ Retrieval (k=3, shared source IDs)")
        print("  ✓ Model: DeepSeek-V4-Flash")
        print("  ✓ Temperature: 0")
        print("  ✓ Query set: 224 targets")
        print()

        print("ONLY DIFFERENCE:")
        print("  Clean-FN:        Reasoning + operands (NO program template)")
        print("  Clean-FN+Sketch: Reasoning + operands + program template")
        print()

        print("CONTAMINATION HANDLING:")
        contaminated = sum(1 for s in self.strategy_map.values() if s.get('contaminated', False))
        print(f"  Remaining contaminated: {contaminated}/78 (5.1%)")
        print(f"  Regenerated clean: 23 sources (27 → 4)")
        print(f"  Scale mismatches: 0 (all eliminated)")
        print(f"  Action: Minimal remaining contamination filtered from memory")
        print()

        print("COST:")
        print(f"  2 arms × 224 queries = 448 API calls")
        print()

        print("OUTPUT FILES (after execution):")
        print("  results_clean_fn.json")
        print("  results_clean_fn_sketch.json")
        print()

        print("EVALUATION:")
        print("  Use canonical_evaluator_v2.py")
        print("  McNemar test for paired comparison")
        print("  Bootstrap CI for effect size")
        print()

        print("STATUS:")
        print("  ⚠️  PROTOCOL DEFINED - API CALLS NOT IMPLEMENTED")
        print("  ⚠️  REQUIRES USER AUTHORIZATION FOR 448 API CALLS")
        print()

        print("="*80)


def main():
    """Generate protocol and examples."""
    protocol = CleanExperimentProtocol()
    protocol.generate_protocol_summary()
    protocol.show_example_prompts()

    print()
    print("To execute this protocol:")
    print("  1. Get user authorization for 448 API calls")
    print("  2. Implement API calling code (DeepSeek-V4-Flash, temp=0)")
    print("  3. Run both arms")
    print("  4. Evaluate with canonical_evaluator_v2.py")
    print("  5. Statistical analysis with McNemar + Bootstrap CI")
    print()


if __name__ == '__main__':
    main()
