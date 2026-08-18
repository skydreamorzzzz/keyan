"""Merge pilot and expanded retrieval caches, then update expanded_sample_queries.json."""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Load pilot retrieval cache (30 queries)
pilot_cache_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/retrieval_cache.json")
with open(pilot_cache_file) as f:
    pilot_cache = json.load(f)

# Load expanded retrieval cache (194 queries)
expanded_cache_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/expanded_retrieval_cache.json")
with open(expanded_cache_file) as f:
    expanded_cache = json.load(f)

# Merge caches
full_cache = pilot_cache + expanded_cache

print(f"Merged retrieval cache: {len(pilot_cache)} pilot + {len(expanded_cache)} expanded = {len(full_cache)} total")
print()

# Create mapping: target_id -> shared_source_ids
retrieval_map = {entry["target_id"]: entry["shared_source_ids"] for entry in full_cache}

# Load expanded sample queries
expanded_file = os.path.join(ROOT, "pilot/stage36_paired_abstraction/expanded_sample_queries.json")
with open(expanded_file) as f:
    expanded_queries = json.load(f)

print(f"Loaded {len(expanded_queries)} expanded sample queries")
print()

# Update each query with shared_source_ids
updated_count = 0
for query in expanded_queries:
    target_id = query["id"]
    if target_id in retrieval_map:
        query["shared_source_ids"] = retrieval_map[target_id]
        updated_count += 1

print(f"Updated {updated_count}/{len(expanded_queries)} queries with shared_source_ids")
print()

# Save updated expanded sample
with open(expanded_file, 'w') as f:
    json.dump(expanded_queries, f, indent=2)

print(f"✓ Updated {expanded_file} with retrieval metadata")
print()

# Validation: Check coverage
missing = [q["id"] for q in expanded_queries if "shared_source_ids" not in q]
if missing:
    print(f"✗ {len(missing)} queries still missing shared_source_ids: {missing[:5]}")
else:
    print(f"✓ All {len(expanded_queries)} queries have shared_source_ids")
