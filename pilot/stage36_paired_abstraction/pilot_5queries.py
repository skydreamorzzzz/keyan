"""Quick 5-query pilot to verify experiment setup before full run."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

# Import main experiment functions
from pilot.stage36_paired_abstraction.downstream_experiment import (
    load_experiment_data,
    execute_arm,
    analyze_transitions,
    correlate_with_diagnostics
)

def main():
    print("=" * 80)
    print("STAGE 36: 5-Query Pilot")
    print("=" * 80)
    print()

    # Load data
    print("Loading experiment data...")
    data = load_experiment_data()
    print()

    # Select first 5 targets
    pilot_targets = data["targets"][:5]
    pilot_retrieval = [r for r in data["retrieval_cache"] if r["target_id"] in [t["id"] for t in pilot_targets]]

    print(f"Running pilot with {len(pilot_targets)} queries")
    print()

    # Execute each arm on pilot sample
    all_results = {}

    for arm_name in ["None", "Case", "Strategy", "Paired"]:
        print(f"--- {arm_name} Arm ---")
        results = execute_arm(
            arm_name,
            pilot_targets,
            pilot_retrieval,
            data["cases"],
            data["strategies"]
        )
        all_results[arm_name] = results

        # Save pilot results
        output_file = os.path.join(
            ROOT,
            f"pilot/stage36_paired_abstraction/pilot_{arm_name.lower()}.json"
        )
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print()

    # Quick summary
    print("=" * 80)
    print("PILOT SUMMARY")
    print("=" * 80)
    print()

    for arm_name, results in all_results.items():
        n_correct = sum(r["exact_match"] for r in results)
        print(f"{arm_name:12s}: {n_correct}/{len(results)} correct")

    print()
    print("✓ Pilot complete. Check results before running full 30-query experiment.")

if __name__ == "__main__":
    main()
