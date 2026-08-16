# Stage 4B.1: Protocol Repair & Re-audit

Date: 2026-08-16

## Scope

This re-audit fixes Stage 4B protocol defects and reruns only the existing `rn1/rn2/rn3` development data. No API calls were made, no new features were added, and the model/formulation/threshold/lambda grids were not expanded.

## Repairs

1. `evaluate_realized_by_replicate()`
   - Replaced `statistics.mean(np.array(...))` with explicit float numpy arrays.
   - `gain_vs_both` is now computed as `policy_accuracy - both_accuracy`.
   - `paired_gain_vs_both` is also saved as a diagnostic and matches the accuracy difference.

2. Inner-CV selection
   - Candidate selection now uses paired validation gain over Always Both, not absolute validation accuracy.
   - Each inner fold computes:

     ```text
     gain = policy_accuracy - both_accuracy
     ```

   - Conservative one-SE selection is applied to mean paired gain and SE.
   - `Always Both` is an explicit candidate with gain `0` and coverage `0`.
   - Ties / one-SE ambiguity still prefer lower coverage and the Always Both candidate.

3. Hierarchical Case gate
   - If the best fallback arm is `Case` but gate confidence is below the stricter Case threshold, the router now abstains to `Both`.
   - It no longer silently switches to the second-best deviation arm.

4. Cache provenance
   - Loading an existing stability cache now validates every record's runtime provenance.
   - Cache hits also validate runtime/fingerprint before returning.
   - Missing runtime provenance or runtime drift fails immediately.
   - The Stage 4B holdout cache loader was similarly hardened.

5. Tests
   - Added `pilot/tests/test_stage4b_protocol.py`.
   - Tests cover realized gain arithmetic, paired-gain conservative selection, Case abstention behavior, and cache runtime drift checks.

## Fully Nested OOF Result

Protocol remains:

- outer annual-report GroupKFold
- inner annual-report GroupKFold on outer-train only
- original Stage 4B feature sets
- original architectures
- original threshold/lambda grids
- no new API features

Corrected fully nested OOF result:

| Metric | Value |
|---|---:|
| Always Both expected accuracy | 0.7467 |
| Nested policy expected accuracy | 0.7520 |
| Expected gain vs Both | +0.0053 |
| Oracle | 0.8387 |
| Oracle gap recovery | 5.8% |
| Deviation coverage | 5.6% |
| Deviation count | 14 / 250 |
| Beneficial deviations | 2 |
| Harmful deviations | 1 |
| Neutral deviations | 11 |
| Annual-report cluster 95% CI | [-0.0054, 0.0192] |

Action distribution:

| Action | Count |
|---|---:|
| Both | 236 |
| None | 8 |
| Case | 5 |
| Strategy | 1 |

Fold selections:

| Fold | Architecture | Feature set | Threshold | Lambda | Inner mean gain | Inner SE | Inner coverage |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | flat_delta | synthetic_interaction | 0.05 | n/a | 0.0100 | 0.0041 | 0.1661 |
| 2 | hierarchical | synthetic_interaction | 0.80 | n/a | 0.0017 | 0.0059 | 0.0400 |
| 3 | flat_delta | existing_meta_plus_compatibility | 0.33 | n/a | 0.0101 | 0.0104 | 0.1250 |
| 4 | gain_harm | synthetic_interaction | 0.50 | 1.0 | 0.0150 | 0.0001 | 0.0598 |
| 5 | flat_delta | synthetic_interaction | 0.20 | n/a | 0.0100 | 0.0041 | 0.0150 |

Interpretation: after repair, the fully nested policy no longer collapses to Both. However, the gain is small, the annual-report cluster CI crosses zero, and most deviations are neutral.

## Corrected Realized Gain by Replicate

The realized gain bug materially affected Stage 4B reporting. Corrected realized results:

| Replicate | Policy accuracy | Both accuracy | Gain |
|---|---:|---:|---:|
| rn1 | 0.7560 | 0.7480 | +0.0080 |
| rn2 | 0.7480 | 0.7440 | +0.0040 |
| rn3 | 0.7520 | 0.7480 | +0.0040 |

Mean realized gain: +0.0053. Range: 0.0040.

This is directionally consistent across the three existing replicates, but still small.

## Fixed Candidate Audit

Each fixed candidate now competes with the explicit Always Both candidate during inner selection. These remain exploratory audits, not a new search.

| Candidate | Expected gain | Coverage | Beneficial | Harmful | Neutral | Cluster 95% CI | Mean realized gain |
|---|---:|---:|---:|---:|---:|---:|---:|
| flat_delta + compatibility | -0.0067 | 4.8% | 1 | 3 | 8 | [-0.0256, 0.0083] | -0.0067 |
| hierarchical + compatibility | +0.0000 | 2.4% | 1 | 1 | 4 | [-0.0117, 0.0121] | +0.0000 |
| hierarchical + synthetic interaction | -0.0027 | 0.8% | 0 | 1 | 1 | [-0.0084, 0.0000] | -0.0027 |
| gain_harm + synthetic interaction | +0.0013 | 5.2% | 1 | 1 | 11 | [-0.0079, 0.0117] | +0.0013 |

No fixed candidate provides confirmatory evidence. The fully nested mixed policy is the strongest repaired result, but it still has weak statistical support.

## What Changed Relative to Stage 4B

Stage 4B's conclusion that the policy "collapsed to Both" was partly an artifact of the selection protocol:

- one-SE was applied to absolute accuracy instead of paired gain;
- Always Both was not explicitly represented as a candidate;
- realized gain reporting was numerically broken.

After repair:

- the main nested policy does make sparse deviations;
- realized gains are nonzero and consistently positive across rn1/rn2/rn3;
- the gain remains too small and uncertain to count as confirmed.

## Limitations

- This is still the same 250-query development subset.
- No fresh holdout was rerun.
- Positive deviations remain sparse: only 2 beneficial expected deviations in the repaired nested OOF policy.
- Most deviations are neutral, so the signal may still be weakly tied to accuracy while more relevant for memory-cost tradeoff in a future pre-registered test.
- The fixed candidate audit does not rescue a robust architecture-specific claim.

## Final Judgment

**SIGNAL SURVIVES BUT NOT CONFIRMED**

The Stage 4B negative result should be softened. The repaired protocol shows a small, directionally consistent learnability signal under fully nested annual-report CV:

```text
expected gain = +0.53pp
rn1/rn2/rn3 gains = +0.80pp / +0.40pp / +0.40pp
coverage = 5.6%
cluster CI crosses 0
```

This is not enough to proceed as a confirmed router result. It does justify treating the Stage 4B collapse-to-Both conclusion as a protocol artifact and motivates a future pre-registered confirmation only after improving observability or defining an explicit accuracy-memory objective.
