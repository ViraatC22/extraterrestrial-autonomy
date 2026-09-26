# Study 2 sample size: formal power analysis (validation seeds only)

Generated results: `data/validation/power_analysis/RESULTS.md` (tables),
`power_summary.json`, `power_grid.csv`, `sample_size_table.csv`, and the figure
`paper/figures/v2_power_curve.pdf`. Script: `scripts/power_analysis.py`. Tests:
`tests/test_power_analysis.py`. No v1 held-out or v2 confirmatory seed was used.

## The test being powered

The planned primary test (`V2_HYPOTHESES_DRAFT.md`) is McNemar's exact test, two-sided,
α = 0.05, on mission success in the Mars condition, with fixed and adaptive planners paired
by seed. There is one primary test, so no multiplicity correction applies to it; the
secondary family (Holm-corrected) is not powered, and its detectable effect at the chosen n
is reported instead.

For matched pairs, write p10 = P(only adaptive succeeds) and p01 = P(only fixed succeeds).

- **Effect** Δ = p10 - p01: the difference in success probability.
- **Discordance** ψ = p10 + p01: how often the planners disagree. Only discordant pairs
  carry information, so the same Δ needs more seeds when ψ is large.

## Choices, and why

| Quantity | Value | Basis |
|---|---|---|
| α | 0.05, two-sided | as in Study 1; no directional hypothesis (see the draft) |
| Target power | 0.90 | preferred over 0.80 because Study 2 is a single confirmatory attempt and a null result should be informative |
| Minimum effect of interest Δ | 0.10 | fixed before looking at the validation outcomes: a change of one mission in ten in safe-return probability. This is a judgement, not a derived quantity: given the model's simplifications (Limitations in the paper), we would not base a design conclusion on a smaller difference. Sensitivity: 0.05, 0.075, 0.125, 0.15 |
| Discordance ψ | estimated on validation, then its one-sided 90% upper Wilson bound | ψ is a nuisance parameter; using an upper bound guards against under-powering if validation happened to show unusually few disagreements |
| Estimated Δ on validation | recorded, **not used** | sizing a study on its own pilot effect is how optimistic studies get planned |

Power is computed **exactly**: sum over the binomial distribution of the number of discordant
pairs D ~ Bin(n, ψ), and for each D over the count favouring the adaptive planner,
W ~ Bin(D, (ψ + Δ) / 2ψ), of the probability that the analysis code's own test rejects. The
rejection rule is checked against `scipy.stats.binomtest` - the function the analysis code
calls - for every D up to 120, and exact power is checked against Monte Carlo simulation.

## Which calibration method?

ψ depends on how the planners behave, which depends on the calibration method, and no
method has been accepted (`CALIBRATION_AUDIT.md`). The analysis is therefore run for the two
leading candidates - M3 (confusion-aware learner) and M2a (Moon-fit uncertainty scale) - on
all 200 validation seeds per body, and the n that applies is the one matching the owner's
calibration decision.

## Results

Full tables: `data/validation/power_analysis/RESULTS.md` (generated). Key numbers, from
`power_summary.json` and `sample_size_table.csv`:

| | M3 (confusion-aware) | M2a (Moon-fit scale) |
|---|---|---|
| Validation seeds (Mars) | 200 | 200 |
| Discordant pairs (only adaptive / only fixed) | 24 / 10 | 21 / 19 |
| Discordance ψ: point, upper bound | 0.170, 0.207 | 0.200, 0.239 |
| **n for power 0.90 at Δ = 0.10** | **230** | **260** |
| Exact / simulated power at that n | 0.912 / 0.915 | 0.903 / 0.901 |
| n for Δ = 0.05 (power 0.90) | 900 | more than 1,000 (not reachable with one pool) |
| Science fraction: difference detectable with 80% power at that n | 0.012 | 0.013 |

**Recommendation.** Freeze n at the value matching the calibration decision: 230 matched
seeds if M3 is chosen, 260 if M2a. Both fit comfortably in the 1,000-seed confirmatory pools.
If the owner wants power for effects as small as 0.05, the study would need 900 seeds (M3)
or cannot be run from one pool (M2a), and the plan should say which effect sizes it is not
designed to detect.

Two cautions. The validation differences (+0.07 for M3, +0.01 for M2a) were not used to size
the study and are not evidence: they come from development seeds that also shaped the method.
And the Moon condition (secondary) is not powered: success there is near ceiling for both
planners, so it can only detect a large harm.
