# TAT-QA Evaluator Audit

Date: 2026-08-16

Scope: evaluation layer only. No LLM calls, no Case/Strategy Memory construction, no four-arm experiments, no router design.

## Source And Compatibility

The evaluator reuses the official TAT-QA implementation:

- Official entry point: `tatqa_eval.py`
- Official metric implementation: `tatqa_metric.py`
- Official utility implementation: `tatqa_utils.py`
- Source repository: https://github.com/NExTplusplus/tat-qa
- Raw files vendored under: `pilot/multibench/official_tatqa/`

Project wrapper:

- `pilot/multibench/tatqa_evaluator.py`

The wrapper calls the official `TaTQAEmAndF1` metric. It accepts the official prediction format:

```json
{
  "question_uid": ["answer", "scale"]
}
```

It also accepts a project-friendly dict form:

```json
{
  "question_uid": {"answer": "...", "scale": "..."}
}
```

The only input-normalization compatibility layer is scalar numeric prediction conversion to strings before calling the official metric. This is necessary because the official metric treats Python numeric `0` as missing via `if not prediction`, while official JSON examples represent predicted answers as strings. Without this wrapper normalization, gold-as-prediction fails on zero-valued arithmetic answers.

## Metric Behavior

Official metric behavior preserved:

- span / multi-span: normalized DROP-style EM/F1 with optimal multi-span alignment.
- arithmetic: answer and scale are converted through official `get_answer_str`; F1 is set equal to EM for arithmetic.
- count: answer is stringified as integer; F1 is set equal to EM.
- scale: exact scale match is tracked separately as `scale_score`.
- percent: official special case allows decimal predictions such as `0.046` to match gold `4.6` with `scale="percent"` for answer EM/F1, while scale score remains incorrect if predicted scale is empty.

## Gold Self-Check

Command:

```bash
python pilot/multibench/tatqa_evaluator.py --self-check --splits train dev
```

Result:

| Split | Count | EM | F1 | Scale score | Gold-prediction failures |
|---|---:|---:|---:|---:|---:|
| train | 13215 | 1.0000 | 1.0000 | 1.0000 | 0 |
| dev | 1668 | 1.0000 | 1.0000 | 1.0000 | 0 |

Machine-readable output:

- `pilot/multibench/output/tatqa/tatqa_evaluator_self_check.json`

Before numeric-zero normalization, gold-as-prediction produced 55 train failures and 5 dev failures, all zero-valued arithmetic answers. That was traced to the official metric's Python truthiness check, not to dataset parsing.

## Unit Tests

Command:

```bash
python -m unittest pilot.tests.test_tatqa_evaluator
```

Result: 6 tests passed.

Coverage:

- numeric `0` answer is not treated as missing by the wrapper;
- comma-formatted numbers match numeric gold;
- percent decimal prediction special case;
- scale mismatch blocks EM when appropriate;
- multi-span answer order invariance;
- project dict prediction format.

## Known Differences / Risks

- The vendored official `tatqa_utils.py` emits Python 3.13 `SyntaxWarning` messages for non-raw regex strings. The warnings do not affect metric results.
- The evaluator does not execute TAT-QA derivations. It evaluates final answer + scale using the official answer metric.
- Public TAT-QA test has no gold answers in the downloaded file, so self-check and local evaluation are limited to train/dev unless a gold test file is obtained.
- Arithmetic predictions should provide the final answer, not a derivation. A future program-execution layer would be separate from this official answer metric.

## Decision

The TAT-QA evaluator is ready for the next ingestion-stage work:

- build TAT-QA Case Memory from train;
- design Strategy extraction only after deciding how to represent derivations;
- run any future memory experiments against this evaluator, not ad hoc matching.
