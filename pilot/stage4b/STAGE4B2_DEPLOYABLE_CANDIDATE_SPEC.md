# Stage 4B.2 Deployable Candidate Freeze

Router: `stage4b2_sample_se_deployable_candidate`

Status: candidate freeze only, not confirmatory evidence.

Selection data: the existing 250-query development subset.

Selection procedure:

- annual-report grouped inner CV on all development data
- paired gain over Always Both
- sample standard error (`ddof=1`)
- explicit Always Both candidate
- conservative one-SE tie-breaking
- original Stage 4B feature sets, architectures, thresholds, and lambdas only

Selected candidate:

```json
{
  "architecture": "flat_delta",
  "feature_set": "existing_meta_plus_interaction",
  "threshold": 0.5,
  "lambda": null,
  "mean_utility": 0.7482947663670555,
  "se_utility": 0.03980903852328979,
  "mean_gain": 0.0013705616115254893,
  "se_gain": 0.005809644135436938,
  "coverage": 0.031889462612354175
}
```

Current sample-SE nested OOF performance:

- expected gain vs Both: -0.002667
- deviation coverage: 0.052
- cluster CI: [-0.008369079849513026, 0.0]

This candidate must not be modified based on future holdout results.
