"""Build paired Case(E) + Strategy(E) memory for abstraction feasibility study.

Key requirements:
1. Each Strategy(E) abstracts from SINGLE Case(E), not aggregated
2. Both share same source_experience_id
3. Stratified sampling: top-15 structs, company diversity, complexity range
4. QC abstraction quality: leakage, structural preservation, hallucination, degeneracy
"""
import json
import os
import random
from collections import defaultdict, Counter
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Seed for reproducibility
random.seed(42)

def load_case_memory() -> List[Dict[str, Any]]:
    """Load existing case memory."""
    with open(os.path.join(ROOT, "pilot/output/case_memory.json")) as f:
        return json.load(f)

def stratified_sample_sources(
    cases: List[Dict[str, Any]],
    top_n_structs: int = 15,
    samples_per_struct: int = 6,
) -> List[Dict[str, Any]]:
    """Stratified sampling from top-N structs with company diversity.

    Args:
        cases: Case memory entries
        top_n_structs: Number of top struct patterns to sample from
        samples_per_struct: Target samples per struct

    Returns:
        Sampled source experiences
    """
    # Count structs
    struct_counts = Counter()
    for case in cases:
        struct = tuple(case['struct'])
        struct_counts[struct] += 1

    # Get top-N structs
    top_structs = [struct for struct, _ in struct_counts.most_common(top_n_structs)]

    # Group cases by struct
    cases_by_struct = defaultdict(list)
    for case in cases:
        struct = tuple(case['struct'])
        if struct in top_structs:
            cases_by_struct[struct].append(case)

    # Stratified sampling with company diversity
    selected = []
    for struct in top_structs:
        candidates = cases_by_struct[struct]

        # Group by company
        by_company = defaultdict(list)
        for case in candidates:
            by_company[case['company']].append(case)

        # Sample diverse companies first, then fill from popular companies
        sampled_for_struct = []
        companies = list(by_company.keys())
        random.shuffle(companies)

        # One sample per company until target reached
        for company in companies:
            if len(sampled_for_struct) >= samples_per_struct:
                break
            sample = random.choice(by_company[company])
            sampled_for_struct.append(sample)

        selected.extend(sampled_for_struct)

    print(f"Stratified sampling: {len(selected)} experiences from {top_n_structs} structs")
    return selected

def create_abstraction_prompt(case: Dict[str, Any]) -> str:
    """Create prompt for abstracting single case into strategy.

    Key constraints:
    - Remove company name, year, specific values, entity names
    - Preserve operation sequence and reasoning structure
    - Add operand role bindings (V1=new_value, V2=old_value, etc.)
    - Maintain semantic reasoning guidance
    - No hallucination of operations not in source
    """
    prompt = f"""You are creating an ABSTRACT STRATEGY from a single concrete financial reasoning example.

## SOURCE CASE

Question: {case['question']}
Facts: {'; '.join(case['gold_facts'])}
Program: {case['program']}
Operations: {case['struct']}
Answer: {case['answer']}

## ABSTRACTION REQUIREMENTS

Transform this SINGLE example into an abstract strategy by:

1. **Remove instance-specific details**:
   - Company name: {case['company']}
   - Report/year references
   - Specific numerical values
   - Entity names, table row labels

2. **Preserve reasoning structure**:
   - Operation sequence: {case['struct']}
   - Semantic pattern (what problem type this solves)
   - Reasoning steps and their purpose

3. **Add operand role bindings**:
   - Define semantic roles for each operand (e.g., V1=numerator, V2=denominator)
   - Specify unit conventions
   - Describe how to locate operands in context

4. **No hallucination**:
   - Do NOT add operations not in source program
   - Do NOT generalize beyond what this single example demonstrates
   - Do NOT merge patterns from other examples

5. **Avoid degeneracy**:
   - NOT: "find relevant values and calculate"
   - YES: Specific reasoning guidance about WHAT to calculate and WHY

## OUTPUT FORMAT (JSON)

{{
  "strategy_name": "Short name for this reasoning pattern",
  "problem_pattern": "Abstract description of problem type (no company/year/values)",
  "operation_sequence": {case['struct']},
  "operand_roles": {{
    "role_name": "semantic description and how to locate"
  }},
  "reasoning_steps": [
    "Step 1: ...",
    "Step 2: ..."
  ],
  "formula_template": "Abstract formula using role names",
  "units_convention": "How to handle units/scale",
  "example_question_pattern": "Abstract question pattern (no specifics)"
}}

Output valid JSON only, no extra text.
"""
    return prompt

def main():
    print("=" * 80)
    print("STAGE 36: Paired Abstraction Memory Construction")
    print("=" * 80)
    print()

    # Load cases
    cases = load_case_memory()
    print(f"Loaded {len(cases)} case memory entries")
    print()

    # Stratified sampling
    print("Sampling source experiences...")
    selected_sources = stratified_sample_sources(
        cases,
        top_n_structs=15,
        samples_per_struct=6
    )
    print()

    # Create paired memory structure
    paired_memory = []
    for i, source_case in enumerate(selected_sources):
        source_id = f"E{i+1:03d}"

        # Case(E): Direct copy with source_id
        case_entry = {
            "source_experience_id": source_id,
            "representation": "case",
            **source_case
        }

        paired_memory.append(case_entry)

    # Save source experiences (Case side) first
    output_dir = os.path.join(ROOT, "pilot/stage36_paired_abstraction")
    os.makedirs(output_dir, exist_ok=True)

    source_file = os.path.join(output_dir, "paired_sources.json")
    with open(source_file, 'w') as f:
        json.dump(paired_memory, f, indent=2)

    print(f"Saved {len(paired_memory)} source experiences to {source_file}")
    print()

    # Save abstraction prompts for manual review/LLM generation
    prompts_file = os.path.join(output_dir, "abstraction_prompts.jsonl")
    with open(prompts_file, 'w') as f:
        for entry in paired_memory:
            prompt = create_abstraction_prompt(entry)
            f.write(json.dumps({
                "source_experience_id": entry["source_experience_id"],
                "prompt": prompt
            }) + '\n')

    print(f"Saved {len(paired_memory)} abstraction prompts to {prompts_file}")
    print()

    # Summary statistics
    struct_dist = Counter(tuple(e['struct']) for e in paired_memory)
    company_dist = Counter(e['company'] for e in paired_memory)
    complexity_dist = Counter(e['n_steps'] for e in paired_memory)

    print("Sampling summary:")
    print(f"  Total source experiences: {len(paired_memory)}")
    print(f"  Unique structs: {len(struct_dist)}")
    print(f"  Unique companies: {len(company_dist)}")
    print(f"  Complexity range: {min(complexity_dist.keys())}-{max(complexity_dist.keys())} steps")
    print()
    print("Top structs sampled:")
    for struct, count in struct_dist.most_common(10):
        print(f"    {str(struct):40s} {count:2d}")
    print()

    print("Next step: Run LLM abstraction and QC")
    print("  Script: pilot/stage36_paired_abstraction/generate_abstractions.py")

if __name__ == "__main__":
    main()
