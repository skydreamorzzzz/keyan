#!/usr/bin/env python3
"""
Stage 39: Arm-Specific Memory Constructors
"""

def construct_case_memory(source_ids, case_map):
    """Case: concrete solved examples."""

    memory_parts = ["Similar solved examples:"]

    for source_id in source_ids:
        if source_id not in case_map:
            continue

        case = case_map[source_id]

        memory_parts.append(f"\nExample {source_id}:")
        memory_parts.append(f"Question: {case['question']}")
        memory_parts.append(f"Program: {case['program']}")
        memory_parts.append(f"Answer: {case['answer']}")
        memory_parts.append("")

    return "\n".join(memory_parts)


def construct_format_neutral_memory(source_ids, strategy_map):
    """Format-Neutral Strategy: natural language reasoning."""

    memory_parts = ["Relevant reasoning patterns:"]

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strat = strategy_map[source_id]

        memory_parts.append(f"\nPattern {source_id}: {strat['strategy_name']}")
        memory_parts.append(f"When to use: {strat['problem_pattern']}")
        memory_parts.append(f"\nReasoning steps:\n{strat['reasoning_steps']}")
        memory_parts.append(f"\nOperand roles:\n{strat['operand_roles']}")

        if strat.get('formula_template'):
            memory_parts.append(f"Formula: {strat['formula_template']}")

        memory_parts.append("")

    return "\n".join(memory_parts)


def construct_format_neutral_with_binding_memory(source_ids, strategy_map):
    """Format-Neutral Strategy + explicit binding instruction."""

    memory_parts = ["Relevant reasoning patterns:"]

    for source_id in source_ids:
        if source_id not in strategy_map:
            continue

        strat = strategy_map[source_id]

        memory_parts.append(f"\nPattern {source_id}: {strat['strategy_name']}")
        memory_parts.append(f"When to use: {strat['problem_pattern']}")
        memory_parts.append(f"\nReasoning steps:\n{strat['reasoning_steps']}")
        memory_parts.append(f"\nOperand roles:\n{strat['operand_roles']}")

        if strat.get('formula_template'):
            memory_parts.append(f"Formula: {strat['formula_template']}")

        # Explicit binding instruction
        memory_parts.append("""
Binding instruction:
1. Read the question to identify the target metric
2. Find the relevant column(s) in the table
3. Identify the relevant row(s) based on time period or other criteria
4. Extract concrete values for each operand role
5. Construct a fully executable FinQA program with these concrete values""")

        memory_parts.append("")

    return "\n".join(memory_parts)


def construct_grounded_sketch_memory(source_ids, sketch_map):
    """Grounded Sketch: program template + binding instructions."""

    memory_parts = ["Relevant program patterns:"]

    for source_id in source_ids:
        if source_id not in sketch_map:
            continue

        sketch = sketch_map[source_id]

        memory_parts.append(f"\nPattern {source_id}: {sketch['strategy_name']}")
        memory_parts.append(f"When to use: {sketch['problem_pattern']}")
        memory_parts.append(f"\nProgram sketch:\n{sketch['program_sketch']}")
        memory_parts.append(f"\nOperand bindings:\n{sketch['operand_bindings']}")
        memory_parts.append(f"\n{sketch['binding_instruction']}")
        memory_parts.append("")

    return "\n".join(memory_parts)
