# Runtime-Normalized Stability Final Audit

Date: 2026-08-16

Scope: audit runtime identity, repair cache/provenance and GroupKFold leakage, run the minimum necessary normalized replicates, and test whether query-level memory marginal utility is repeatable and transferable under a fixed effective runtime. No selector development was performed.

## 1. Runtime Identity Audit

DeepSeek official documentation says that after the V4 API release, the current model names are `deepseek-v4-pro` and `deepseek-v4-flash`, available through OpenAI ChatCompletions and Anthropic-compatible APIs. The same update says legacy aliases `deepseek-chat` and `deepseek-reasoner` point to `deepseek-v4-flash` non-thinking and thinking modes during the transition period. See:

- https://api-docs.deepseek.com/updates/
- https://api-docs.deepseek.com/news/news260424/
- https://api-docs.deepseek.com/zh-cn/guides/reasoning_model

Therefore, alias differences and endpoint differences should not automatically be interpreted as underlying model differences. The correct distinction is:

- model alias: `DeepSeek-V4-flash[1m]` vs `deepseek-chat` vs `deepseek-v4-flash`
- API path: Anthropic-compatible vs OpenAI-compatible ChatCompletions
- effective model: the actual model/version/fingerprint returned by the provider

Historical artifacts do not fully prove effective runtime identity:

| Run | Requested / inferred model | Backend | Response model/version saved? | Audit judgment |
|---|---|---|---|---|
| `stage2_old` | `DeepSeek-V4-flash[1m]` | Anthropic-compatible | no | provenance insufficient |
| `r1` | `deepseek-chat` inferred from then-current fallback | OpenAI-compatible | no | provenance insufficient |
| `r2` | `deepseek-chat` inferred from then-current fallback | OpenAI-compatible | no | provenance insufficient |

Interpretation: based on DeepSeek docs, `r1/r2` likely used the V4-Flash non-thinking model family, and `stage2_old` likely used the same family through an Anthropic-compatible path. But the artifacts do not store response-level model/version/fingerprint, so they cannot be treated as strict same-runtime replicates.

Decision: run the minimum strict replacement set, `rn1/rn2/rn3`, rather than mechanically rerunning the full 492-query experiment.

## 2. Cache / Provenance Fixes

New code changes:

- `pilot/llm.py`
  - default DeepSeek fallback now requests `deepseek-v4-flash`, not legacy `deepseek-chat`
  - OpenAI-compatible calls explicitly send `thinking: {"type": "disabled"}`
  - `call_once_with_metadata` returns response text plus runtime metadata
  - saved runtime includes provider, backend, endpoint, requested model, response/effective model, system fingerprint, thinking mode, temperature, and max tokens
- `pilot/stage3/stability_run.py`
  - cache version bumped to `stability_full_doc_prog_v2_runtime_normalized`
  - cache key includes runtime request, endpoint/backend, prompt, arm/mode/sample id, retrieval config, memory config, thinking mode, temperature, and max tokens
  - output artifact stores `runtime_request`, `retrieval_config`, `memory_config`, `prompt_config`, and per-call `runtime_by_call`
- `pilot/stage2_official/run_official.py`
  - cache key now includes runtime, retrieval config, and memory config for future Stage 2 runs

For `rn1/rn2/rn3`, every one of the 3000 calls saved:

```json
{
  "provider": "DeepSeek",
  "backend": "deepseek_openai_compatible",
  "endpoint": "https://api.deepseek.com/chat/completions",
  "requested_model": "deepseek-v4-flash",
  "effective_model": "deepseek-v4-flash",
  "response_model": "deepseek-v4-flash",
  "model_version": "a26a7955944dc5c60445bff77fac9c8e",
  "system_fingerprint": "a26a7955944dc5c60445bff77fac9c8e",
  "thinking_mode": false,
  "temperature": 0.0,
  "max_tokens": 600
}
```

Thus `rn1/rn2/rn3` can be treated as strict same-runtime replicates.

## 3. Leakage Fixes

`pilot/stage3/run_selector_baselines.py` was fixed so fold-level arm priors are computed only from `train_idx`. These priors are used only for probability tie-breaking inside that fold. I also changed random CV to plain seeded KFold rather than label-stratified folds, so fold construction does not depend on full-dataset preferred labels.

Leakage-fixed selector audit:

| CV | Best model | Accuracy | Gain vs Best Fixed | Gap Recovery |
|---|---|---:|---:|---:|
| random KFold, no-leak | query_retrieved_repr/mlp | 0.7378 | +0.0122 | 0.1304 |
| report GroupKFold, no-leak | query_retrieval_meta/rf | 0.7317 | +0.0061 | 0.0652 |

This reinforces the earlier conclusion: current query/retrieval metadata selectors are weak. The stability evidence below supports moving to a marginal-utility framing, not resurrecting four-arm independent correctness classification.

## 4. Same-Runtime Stability

Accepted primary replicates: `rn1`, `rn2`, `rn3`.

Sample: deterministic 250 of official dev[:492], selected by SHA-256 of `stage3-stability-v1|{sample_index}|{sample_id}`. Grounding, retrieval, memory, prompts, evaluator, temperature, max tokens, endpoint, model, and fingerprint are fixed.

Per-arm correctness agreement:

| Arm | Agreement |
|---|---:|
| None | 0.9787 |
| Case | 0.9920 |
| Strategy | 0.9840 |
| Both | 0.9920 |

Overall correctness agreement is high, but this is not sufficient by itself: selector-relevant stability depends on preference events where arms differ.

Same-runtime one-shot and expected metrics:

| Replicate | None | Case | Strategy | Both | Best Fixed | Oracle | Gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rn1` | 0.692 | 0.716 | 0.700 | 0.748 | 0.748 | 0.836 | 0.088 |
| `rn2` | 0.688 | 0.716 | 0.704 | 0.744 | 0.744 | 0.836 | 0.092 |
| `rn3` | 0.700 | 0.716 | 0.712 | 0.748 | 0.748 | 0.844 | 0.096 |
| expected | 0.693 | 0.716 | 0.705 | 0.747 | 0.747 | 0.839 | 0.092 |

The normalized expected oracle gap remains 9.2pp on the 250-query subset.

## 5. Preference-Event Stability

Counts are over 250 queries. `positive_any_run` means the event occurred in at least one of `rn1/rn2/rn3`.

| Event | any run | >=2/3 runs | 3/3 runs | >=2 rate among any | 3/3 rate among any |
|---|---:|---:|---:|---:|---:|
| Case > Strategy | 26 | 23 | 19 | 0.885 | 0.731 |
| Strategy > Case | 21 | 20 | 19 | 0.952 | 0.905 |
| Case > Both | 6 | 5 | 5 | 0.833 | 0.833 |
| Strategy > Both | 12 | 12 | 10 | 1.000 | 0.833 |

The events are not frequent, because Both is the best fixed arm. But when single-memory arms beat another candidate, especially Strategy > Case and Strategy > Both, the signs are highly repeatable under fixed runtime.

## 6. Held-Out Preference Transfer

Protocol:

- train preference from two runs only
- evaluate on the third run only
- no held-out labels are used for preference construction, thresholding, prior/tie-breaking, or arm selection
- Best Fixed and Oracle are evaluation baselines computed on the held-out run

| Held-out | Train runs | Policy acc. | Best Fixed | Oracle | Gain | Gap recovered |
|---|---|---:|---:|---:|---:|---:|
| `rn1` | `rn2+rn3` | 0.832 | 0.748 | 0.836 | +0.084 | 0.955 |
| `rn2` | `rn1+rn3` | 0.836 | 0.744 | 0.836 | +0.092 | 1.000 |
| `rn3` | `rn1+rn2` | 0.840 | 0.748 | 0.844 | +0.092 | 0.958 |
| mean | - | 0.836 | 0.747 | 0.839 | +0.089 | - |

Choice distributions are dominated by Both but include targeted deviations:

- `rn1` held out: Both 226, Case 6, None 7, Strategy 11
- `rn2` held out: Both 226, Case 6, None 8, Strategy 10
- `rn3` held out: Both 227, Case 5, None 8, Strategy 10

This supports the next-stage framing: Both should be the default action, and the router should estimate relative marginal utility/confidence for deviating to Case, Strategy, or None.

## 7. Paired Bootstrap Confidence Intervals

Bootstrap method:

- paired percentile bootstrap over queries
- statistic: mean of `policy_correct_i - best_fixed_arm_correct_i`
- 10,000 bootstrap resamples
- seed: 20260816
- fixed arm is the held-out run's Best Fixed arm, used as the evaluation baseline

| Held-out | Point gain | 95% CI |
|---|---:|---:|
| `rn1` | +0.084 | [0.052, 0.120] |
| `rn2` | +0.092 | [0.056, 0.132] |
| `rn3` | +0.092 | [0.056, 0.132] |

Pooled over held-out run/query observations:

- point gain: +0.0893
- 95% CI: [0.0693, 0.1093]

The fold-level CIs are primary because queries recur across runs; the pooled CI is a compact summary, not an independence claim.

## 8. Interpretation / Limitations

What is now supported:

- Under fixed `deepseek-v4-flash` non-thinking runtime, query-level memory marginal utility exhibits repeatable and transferable heterogeneity.
- The normalized oracle gap remains large on the fixed 250-query subset: expected gap 9.2pp.
- Two-run preference estimates transfer to a held-out run with consistently positive paired-bootstrap CIs.
- The effect is not explained by evaluator tolerance, cache reuse, report-sibling selector leakage, or exact train-question duplicates from earlier audits.

What is not supported:

- A precise variance decomposition such as "7pp stable heterogeneity + 1-2pp noise." The current evidence supports repeatability and transferability, not a clean variance attribution.
- Treating `stage2_old/r1/r2` as strict same-runtime replicates. Their outputs remain useful as secondary evidence, but their artifacts lack response-level effective model/version metadata.
- A four-arm independent correctness selector. Existing low-cost selectors remain weak under leakage-controlled GroupKFold.

Secondary runtime-path observation:

`stage2_old/r1/r2` show the same qualitative transfer pattern despite likely different API paths and incomplete provenance. If DeepSeek's alias mapping applied at those call times, this is consistent with runtime-path robustness within the V4-Flash family. Because response-level metadata was not saved, this remains secondary evidence only.

## 9. Final Decision

**PROCEED TO MARGINAL-UTILITY SELECTOR**

Next-stage direction:

Both as default action + estimate Case/Strategy/None relative marginal utility + confidence gating.

Do not continue the old four-arm independent correctness classifier as the primary method.
