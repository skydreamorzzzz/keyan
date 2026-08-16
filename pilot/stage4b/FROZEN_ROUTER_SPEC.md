# Stage 4B Frozen Router Spec

Frozen router: `conservative_no_override_router`

The Stage 4B development protocol was intentionally conservative:

- outer GroupKFold by annual report
- fold-local vectorizer/preprocessing
- inner grouped CV for all model, feature, architecture, threshold, and lambda choices
- one-standard-error rule favoring lower coverage and higher abstention
- default action is `Both`

Under this protocol, the fully nested OOF policy selected zero deviations and exactly matched Always Both. Therefore the only non-optimistic frozen policy is:

```text
for every query:
    choose Both
```

This is a valid frozen router for confirmatory falsification: it prevents reintroducing Stage 4A winner's-curse behavior into holdout evaluation.

No holdout result may be used to:

- re-enable overrides
- change thresholds
- change feature schema
- change model family
- change holdout filtering
- select a different development candidate

The confirmatory holdout test therefore measures:

1. Whether the conservative freeze preserves the Both baseline.
2. Whether there is any accuracy or cost benefit left after removing model-selection optimism.

Expected result: no adaptive gain and no memory-cost reduction, unless later evidence justifies a new pre-registered router.
