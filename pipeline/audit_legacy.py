"""Read-only forensic check of the known Stage36 index-mapping defect."""
import json
from pathlib import Path
import numpy as np
from pipeline.common import ROOT, write_json

def main():
    base=ROOT/"pilot/stage36_paired_abstraction"; paired=json.load(open(base/"paired_sources.json")); clean=json.load(open(base/"cases_clean.json")); vec=np.load(base/"source_embeddings.npy")
    mismatches=[]
    for index, clean_row in enumerate(clean):
        paired_id=paired[index]["source_experience_id"] if index<len(paired) else None
        if paired_id!=clean_row["source_experience_id"]: mismatches.append({"row":index,"embedding_source_id":clean_row["source_experience_id"],"retrieval_mapped_source_id":paired_id})
    report={"legacy_source_embeddings_rows":int(vec.shape[0]),"legacy_clean_sources":len(clean),"legacy_paired_sources":len(paired),"index_mapping_mismatch":bool(mismatches),"mismatched_rows":len(mismatches),"first_mismatches":mismatches[:10],"finding":"INVALID: expanded retrieval maps embedding rows through a different source ordering." if mismatches else "no mismatch observed"}
    write_json(ROOT/"artifacts/finqa_v1/legacy_audit.json",report); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
