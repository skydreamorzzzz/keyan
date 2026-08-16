# Vendored TAT-QA Official Evaluator

Downloaded: 2026-08-16

Source repository: https://github.com/NExTplusplus/tat-qa

Files:

- `tatqa_metric.py` from `https://raw.githubusercontent.com/NExTplusplus/tat-qa/master/tatqa_metric.py`
- `tatqa_utils.py` from `https://raw.githubusercontent.com/NExTplusplus/tat-qa/master/tatqa_utils.py`

Local compatibility note:

- `tatqa_metric.py` has a minimal import guard around `pandas`. Core EM/F1/scale computation does not require pandas; pandas is only used by optional detail pivot-table helpers. In environments without pandas, those helpers return `None`.

Metric semantics are otherwise delegated to the official `TaTQAEmAndF1` implementation.
