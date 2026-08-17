# MultiHiertt Evaluator Audit

Date: 2026-08-17

Scope: official-compatible evaluator only. No LLM/API calls, memory construction, retrieval, four-arm experiment, or prompt execution.

## Source / Compatibility

- Official reference: `psunlpgroup/MultiHiertt/evaluate.py`.
- Project wrapper: `pilot/multibench/multihiertt_evaluator.py`.
- Vendored official subset: `pilot/multibench/official_multihiertt/`.
- The wrapper delegates span scoring, program tokenization, program execution, and mixed span/program numerical tolerance to official-compatible functions.

## Compatibility Normalization

- Prediction dicts may use predicted_ans/predicted_answer/answer/prediction for answer text.
- Prediction dicts may use predicted_program/program/pred_program for program text.
- Raw program strings are tokenized with official program_tokenization before official execution.
- Numeric/list prediction values are cast to strings only before official span metric.
- Official str_to_num semantics are preserved, including removing $, comma, percent sign, and hyphen.
- Answer-only predictions for program gold are compared to official gold program execution using official mixed span/program numeric tolerance.

Important official semantics retained: `str_to_num` strips `$`, `,`, `%`, and `-`. This means negative signs are not distinguished by the official numeric parser; this is recorded as a compatibility risk rather than silently corrected.

## Gold Prediction Self-Check

| Split | Count | EM | F1 | Program | Span | Invalid programs | Gold failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| `train` | 7830 | 1.000 | 1.000 | 6306 | 1524 | 0 | 0 |
| `validation` | 1044 | 1.000 | 1.000 | 842 | 202 | 0 | 0 |

## Unit Test Coverage

- Program execution: add/subtract/divide tokenized program equality.
- Numeric normalization: currency/comma/percent behavior inherited from official `str_to_num`.
- Negative-number compatibility risk: official parser removes hyphen.
- Span and multi-span exact/F1 behavior.

## Decision

Decision: `EVALUATOR FROZEN`.
