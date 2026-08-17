# MultiHiertt Source

Dataset: MultiHiertt, ACL 2022, numerical reasoning over multiple hierarchical financial tables and text.

Primary/official repository:
- https://github.com/psunlpgroup/MultiHiertt

Official paper:
- https://aclanthology.org/2022.acl-long.454/

Downloaded annotation files used in this repo:
- Hugging Face parquet repackaging: https://huggingface.co/datasets/bevaya/MultiHiertt
- Reason: the official GitHub points to JSON data via Google Drive, while this Hugging Face mirror packages only the annotation data in documented parquet form without model checkpoints.

Files:
- `data/multihiertt/raw/train.parquet` from https://huggingface.co/api/datasets/bevaya/MultiHiertt/parquet/default/train/0.parquet rows=7830 bytes=152439307 md5=197aa33da73685d87316203fd2cd28fc
- `data/multihiertt/raw/validation.parquet` from https://huggingface.co/api/datasets/bevaya/MultiHiertt/parquet/default/validation/0.parquet rows=1044 bytes=20464413 md5=8ba78b5c9a19b37edaf9f009613c1df3

License/provenance notes:
- QA annotations and official code are MIT licensed in the official GitHub repository.
- Underlying table data originates from FinTabNet / public SEC filings; see the Hugging Face dataset card for CDLA-Permissive-1.0 notes.

Large raw parquet files are intentionally ignored by git because the train parquet is larger than normal GitHub file-size limits. Re-run `pilot/multibench/multihiertt_ingest.py` after downloading them to regenerate processed JSONL and audit artifacts.
