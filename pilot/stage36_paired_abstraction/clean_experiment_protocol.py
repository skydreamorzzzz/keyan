#!/usr/bin/env python3
"""
Clean Experiment Protocol: Case vs Clean-FN vs GS

Minimal 3-arm comparison to isolate template effect.

Key principles:
1. Identical base prompt, document, output instruction
2. Only memory representation differs
3. Case must be re-run (not reused from Stage 37)
4. Use canonical evaluator
5. 224 queries, k=3, DeepSeek-V4-Flash, temp=0
"""

import json
import os
from typing import Dict, List


BASE_PATH = '/home/tiantian/keyan/pilot/stage36_paired_abstraction'


# Shared system prompt (identical for all arms)
SYSTEM_PROMPT = """You are a financial reasoning assistant. Your task is to generate executable programs for financial question answering.

Given:
- A financial document with tables
- A question about the document
- Relevant experience from similar solved problems

Generate:
- An executable FinQA program that answers the question
- The final numerical answer

FinQA Program Syntax:
- Operations: add, subtract, multiply, divide, exp, greater, table_max, table_min, table_sum, table_average
- Arguments: numbers, const_X (e.g. const_100, const_m1), #N (reference to step N result), table row labels
- Format: operation(arg1, arg2)
- Multi-step: operation1(a, b), operation2(#0, c), operation3(#1, d)
- Example: divide(100, 50), multiply(#0, const_100) → result = 200

Requirements:
- Use values from the CURRENT document, not from experience memory
- Generate complete, executable programs
- Output format:
  PROGRAM: <your program>
  ANSWER: <numerical result>
"""


# Output instruction (identical for all arms)
OUTPUT_INSTRUCTION = """
Generate an executable FinQA program that answers this question using values from the current document.

Output format:
PROGRAM: <executable FinQA program>
ANSWER: <numerical answer>
"""


def construct_case_memory(source_ids: List[str], case_map: Dict) -> str:
    """
    Case memory: Concrete solved examples.

    Format:
    - Question
    - Program (gold)
    - Answer (gold)

    No additional instructions.
    """
    memory_parts = ["# Similar solved examples\n"]

    for source_id in source_ids:
        if source_id not in case_map:
            continue

        case = case_map[source_id]
        memory_parts.append(f"\n## Example {source_id}")
        memory_parts.append(f"Question: {case['question']}")
        memory_parts.append(f"Program: {case['program']}")
        memory_parts.append(f"Answer: {case['answer']}\n")

    return "\n".join(memory_parts)


def construct_clean_format_neutral_memory(source_ids: List[str], strategy_map: Dict) -> str:
    """
    Clean Format-Neutral memory: Natural language reasoning.

    Format:
    - Problem pattern
    - Reasoning steps (natural language)
    - Operand roles (natural language)

    No program template.
    No explicit binding instruction beyond base prompt.
    """
    memory_parts = ["# Relevant reasoning patterns\n"]

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strat = strategy_map[source_id]
        memory_parts.append(f"\n## Pattern {source_id}: {strat['strategy_name']}")
        memory_parts.append(f"When to use: {strat['problem_pattern']}")
        memory_parts.append(f"\nReasoning steps:")
        memory_parts.append(strat['reasoning_steps'])
        memory_parts.append(f"\nOperand roles:")
        memory_parts.append(strat['operand_roles'])
        memory_parts.append("")

    return "\n".join(memory_parts)


def construct_grounded_sketch_memory(source_ids: List[str], sketch_map: Dict) -> str:
    """
    Grounded Sketch memory: Program template + operand roles.

    Format:
    - Problem pattern
    - Program template with typed slots
    - Operand descriptions
    - Binding instruction
    """
    memory_parts = ["# Relevant program patterns\n"]

    for source_id in source_ids:
        if source_id not in sketch_map:
            continue

        sketch = sketch_map[source_id]
        memory_parts.append(f"\n## Pattern {source_id}: {sketch['strategy_name']}")
        memory_parts.append(f"When to use: {sketch['problem_pattern']}")
        memory_parts.append(f"\nProgram template:")
        memory_parts.append(sketch['program_sketch'])
        memory_parts.append(f"\nOperand descriptions:")
        memory_parts.append(sketch['operand_bindings'])
        memory_parts.append(f"\nBinding instruction:")
        memory_parts.append("Replace each placeholder (<value1>, <value2>, etc.) with actual values from the current document's table and text.")
        memory_parts.append("")

    return "\n".join(memory_parts)


def build_prompt(
    document_text: str,
    table: List[List],
    question: str,
    memory_text: str
) -> str:
    """
    Build complete prompt with consistent structure.

    Structure:
    1. System prompt
    2. Document
    3. Table
    4. Memory
    5. Question
    6. Output instruction
    """
    # Format table
    table_str = "\n".join([" | ".join(map(str, row)) for row in table])

    prompt = f"""{SYSTEM_PROMPT}

# Current Document

{document_text}

# Table

{table_str}

# Experience Memory

{memory_text}

# Question

{question}

{OUTPUT_INSTRUCTION}
"""

    return prompt


class CleanExperimentRunner:
    """
    Runner for clean 3-arm experiment.

    NOT IMPLEMENTED: API calling logic (requires user authorization)

    This class defines the protocol but does not execute.
    """

    def __init__(self, api_key: str = None, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.temperature = 0.0

    def load_data(self):
        """Load targets, sources, retrieval cache."""
        # Load targets
        with open(f'{BASE_PATH}/expanded_sample_queries.json') as f:
            self.targets = json.load(f)

        # Load retrieval cache
        with open(f'{BASE_PATH}/expanded_retrieval_cache.json') as f:
            self.retrieval_cache = json.load(f)

        # Load sources
        with open(f'{BASE_PATH}/paired_sources.json') as f:
            sources = json.load(f)
        self.case_map = {s['source_experience_id']: s for s in sources}

        # Load abstractions
        # For Clean-FN: need to create from case if not exists
        # For GS: use grounded_sketches.json
        with open(f'{BASE_PATH}/grounded_sketches.json') as f:
            sketches = json.load(f)
        self.sketch_map = {s['source_experience_id']: s for s in sketches}

        print(f"Loaded {len(self.targets)} targets")
        print(f"Loaded {len(self.case_map)} case sources")
        print(f"Loaded {len(self.sketch_map)} grounded sketches")

    def run_arm(self, arm_name: str, arm_type: str):
        """
        Run one arm (NOT IMPLEMENTED - requires API authorization).

        Args:
            arm_name: Display name for arm
            arm_type: 'case' | 'clean_fn' | 'gs'
        """
        print(f"\n{'='*80}")
        print(f"ARM: {arm_name}")
        print(f"{'='*80}")
        print()
        print("⚠️  API calling NOT IMPLEMENTED")
        print("⚠️  This runner only defines the protocol")
        print()
        print("To run this arm:")
        print(f"  1. Get user authorization for {len(self.targets)} API calls")
        print(f"  2. Implement API calling logic with DeepSeek-V4-Flash")
        print(f"  3. Save responses to: results_{arm_type}_clean.json")
        print(f"  4. Use canonical_evaluator.py to evaluate")

        # Show example prompt for first query
        if len(self.targets) > 0:
            target = self.targets[0]
            retrieval = next((r for r in self.retrieval_cache if r['target_id'] == target['id']), None)

            if retrieval:
                source_ids = retrieval['shared_source_ids'][:3]

                # Construct memory based on arm type
                if arm_type == 'case':
                    memory = construct_case_memory(source_ids, self.case_map)
                elif arm_type == 'clean_fn':
                    # For clean FN, we need strategy abstractions
                    # If not available, skip or create minimal ones
                    memory = "# Clean Format-Neutral memory (to be created)"
                elif arm_type == 'gs':
                    memory = construct_grounded_sketch_memory(source_ids, self.sketch_map)
                else:
                    memory = ""

                # Build prompt
                prompt = build_prompt(
                    document_text=" ".join(target.get('pre_text', [])),
                    table=target.get('table', []),
                    question=target['qa']['question'],
                    memory_text=memory
                )

                print("\nExample prompt for first query:")
                print("-" * 80)
                print(prompt[:1000])
                print("...")
                print("-" * 80)

    def run_all_arms(self):
        """Run all three arms (protocol definition only)."""
        self.load_data()

        arms = [
            ('Case', 'case'),
            ('Clean Format-Neutral', 'clean_fn'),
            ('Grounded Sketch', 'gs'),
        ]

        for arm_name, arm_type in arms:
            self.run_arm(arm_name, arm_type)

        print(f"\n{'='*80}")
        print("CLEAN EXPERIMENT PROTOCOL DEFINED")
        print(f"{'='*80}")
        print()
        print("Total cost: 3 arms × 224 queries = 672 API calls")
        print()
        print("Next steps:")
        print("  1. Get user authorization")
        print("  2. Implement API calling")
        print("  3. Run experiment")
        print("  4. Evaluate with canonical_evaluator.py")
        print("  5. Statistical analysis with paired tests")


def main():
    """Define protocol (does not call API)."""
    print("="*80)
    print("CLEAN EXPERIMENT PROTOCOL")
    print("="*80)
    print()
    print("This script defines the protocol but does NOT call APIs.")
    print("User authorization required before execution.")
    print()

    runner = CleanExperimentRunner()
    runner.run_all_arms()


if __name__ == '__main__':
    main()
