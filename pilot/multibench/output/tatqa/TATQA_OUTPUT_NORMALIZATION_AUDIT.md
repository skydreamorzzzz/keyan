# TAT-QA Output Normalization Audit

Date: 2026-08-16

Scope: evaluation-only audit over frozen TAT-QA four-arm dry-run raw outputs. No LLM/API calls, no prompt/retrieval/memory changes.

## Canonicalization Contract

- Strip currency symbols and comma separators only from pure numeric predictions.
- Split embedded thousand/million/billion/percent scale tokens from pure numeric predictions.
- Remove duplicate embedded scale when it matches the independent pred_scale.
- Preserve textual span and multi-span answers containing non-scale words.

Changed predictions: 52 / 120.
Change tags: `{'numeric_format': 52, 'duplicate_scale_removed': 23, 'embedded_scale:million': 14, 'embedded_scale:percent': 9}`.

## Raw vs Canonicalized Metrics

| Arm | Raw EM | Canon EM | Delta EM | Raw F1 | Canon F1 | Delta F1 |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 0.567 | 0.667 | +0.100 | 0.685 | 0.785 | +0.100 |
| `case` | 0.533 | 0.667 | +0.133 | 0.620 | 0.753 | +0.133 |
| `strategy` | 0.533 | 0.633 | +0.100 | 0.662 | 0.762 | +0.100 |
| `both` | 0.500 | 0.633 | +0.133 | 0.592 | 0.725 | +0.133 |

## Correctness Flips

- Flip counts: `{'improved': 14}`.
- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3` arm=`none` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$191.7 million', 'scale': 'million'} -> ['191.7', 'million'] gold=['$191.7 million'] scale=none
- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3` arm=`case` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$191.7 million', 'scale': 'million'} -> ['191.7', 'million'] gold=['$191.7 million'] scale=none
- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3` arm=`strategy` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$191.7 million', 'scale': 'million'} -> ['191.7', 'million'] gold=['$191.7 million'] scale=none
- `tatqa:dev:06e79509-49d3-47c4-94a9-1ca382cb11c3` arm=`both` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$191.7 million', 'scale': 'million'} -> ['191.7', 'million'] gold=['$191.7 million'] scale=none
- `tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af` arm=`case` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$16.9 million', 'scale': 'million'} -> ['16.9', 'million'] gold=['$16.9 million'] scale=none
- `tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af` arm=`strategy` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$16.9 million', 'scale': 'million'} -> ['16.9', 'million'] gold=['$16.9 million'] scale=none
- `tatqa:dev:f1eedc55-cc96-4574-b82b-e6f17cf176af` arm=`both` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$16.9 million', 'scale': 'million'} -> ['16.9', 'million'] gold=['$16.9 million'] scale=none
- `tatqa:dev:03f232b9-a78e-42d0-b555-c801eaac577d` arm=`none` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$46.4 million', 'scale': 'million'} -> ['46.4', 'million'] gold=['$46.4 million'] scale=none
- `tatqa:dev:03f232b9-a78e-42d0-b555-c801eaac577d` arm=`case` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$46.4 million', 'scale': 'million'} -> ['46.4', 'million'] gold=['$46.4 million'] scale=none
- `tatqa:dev:03f232b9-a78e-42d0-b555-c801eaac577d` arm=`both` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$46.4 million', 'scale': 'million'} -> ['46.4', 'million'] gold=['$46.4 million'] scale=none
- `tatqa:dev:9e5d65f8-9015-40a0-a35f-361b9b7c753d` arm=`none` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$1.1 million', 'scale': 'million'} -> ['1.1', 'million'] gold=['$1.1 million'] scale=none
- `tatqa:dev:9e5d65f8-9015-40a0-a35f-361b9b7c753d` arm=`case` improved raw=(0,0.00) canon=(1,1.00) tags=['duplicate_scale_removed', 'embedded_scale:million', 'numeric_format'] pred={'answer': '$1.1 million', 'scale': 'million'} -> ['1.1', 'million'] gold=['$1.1 million'] scale=none

## Memory Effect Events

| Event | Raw | Canonicalized |
|---|---:|---:|
| `case_only` | 0 | 0 |
| `strategy_only` | 1 | 0 |
| `none_only` | 0 | 0 |
| `both_only` | 0 | 0 |
| `none_gt_both` | 2 | 2 |
| `case_gt_both` | 1 | 1 |
| `strategy_gt_both` | 2 | 1 |

## Interpretation

- Canonicalization is intentionally conservative: it changes only pure numeric/currency answers with optional scale tokens.
- Textual span and multi-span predictions containing ordinary words are preserved.
- The audit measures whether dry-run memory effects were artifacts of answer/scale formatting before any new experiment is run.

## Decision

Decision: `FREEZE EVALUATION CONTRACT`.
