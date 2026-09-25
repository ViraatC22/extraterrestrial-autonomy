# Results

Generated from `data/results/exonaut_main.csv` (750 missions, 50 seeds per
condition, held-out `test` and `ood` splits). Regenerate with
`python scripts/make_exonaut_paper_assets.py`; the authoritative tables live in
`paper/tables/`.

## Outcomes

| Condition | Planner | Success | Science frac. | Immob. | Energy out |
|---|---|---:|---:|---:|---:|
| Moon (in-dist) | Distance-only A* | 0.66 | 0.659 | 0 | 12 |
| Moon (in-dist) | Fixed risk-aware | 0.90 | 0.788 | 0 | 4 |
| Moon (in-dist) | Adaptive risk-aware | 0.92 | 0.829 | 0 | 3 |
| Mars OOD | Distance-only A* | 0.48 | 0.101 | 7 | 18 |
| Mars OOD | Fixed risk-aware | 0.34 | 0.173 | 6 | 21 |
| Mars OOD | Adaptive risk-aware | 0.34 | 0.158 | 7 | 20 |
| Mars, 1.5× dispersion | Distance-only A* | 0.44 | 0.081 | 8 | 20 |
| Mars, 1.5× dispersion | Fixed risk-aware | 0.22 | 0.162 | 8 | 27 |
| Mars, 1.5× dispersion | Adaptive risk-aware | 0.36 | 0.132 | 7 | 22 |
| Mars, faults | Distance-only A* | 0.40 | 0.074 | 9 | 20 |
| Mars, faults | Fixed risk-aware | 0.26 | 0.168 | 9 | 24 |
| Mars, faults | Adaptive risk-aware | 0.46 | 0.146 | 8 | 17 |
| Mars, comm delay | Distance-only A* | 0.54 | 0.107 | 3 | 19 |
| Mars, comm delay | Fixed risk-aware | 0.28 | 0.200 | 4 | 26 |
| Mars, comm delay | Adaptive risk-aware | 0.44 | 0.156 | 2 | 23 |

## Primary contrasts (adaptive vs fixed risk-aware)

Paired within condition and seed; Holm-corrected across the ten-member family.

| Condition | Outcome | Δ | 95% CI | p_Holm |
|---|---|---:|---|---:|
| Mars, faults | success | **+0.200** | [+0.085, +0.315] | **0.020** ✻ |
| Mars, comm delay | success | +0.160 | [+0.004, +0.316] | 0.461 |
| Mars, 1.5× dispersion | success | +0.140 | [−0.001, +0.281] | 0.461 |
| Mars OOD | success | +0.000 | [−0.128, +0.128] | 1.000 |
| Moon | success | +0.020 | [−0.071, +0.111] | 1.000 |
| Moon | science fraction | +0.040 | [+0.002, +0.079] | 0.326 |
| Mars, comm delay | science fraction | −0.044 | [−0.085, −0.002] | 0.326 |
| Mars, 1.5× dispersion | science fraction | −0.030 | [−0.059, −0.002] | 0.326 |
| Mars, faults | science fraction | −0.022 | [−0.050, +0.005] | 0.461 |
| Mars OOD | science fraction | −0.015 | [−0.051, +0.022] | 1.000 |

Bootstrap (BCa, 10,000 resamples, blocks resampled to preserve pairing) agrees
closely with the t-intervals throughout, so the parametric assumptions are not
driving the conclusions.

## Verdict against the stated hypotheses

- **H1 — supported.** Lunar parity (0.92 vs 0.90, five discordant seeds of 50).
- **H2 — not supported.** Martian science fraction moved *against* the
  hypothesis (−0.015, p = 1.000) and Martian success was exactly tied, five
  discordant seeds each way. The validation-set advantage of +0.125 to +0.167
  did not replicate on held-out seeds.
- **H3 — not supported as stated.** Success in the "hardware faults" condition
  rose 0.26 → 0.46 (the only contrast surviving Holm correction). But a post-hoc
  audit shows faults fired in only 16% of adaptive and 26% of fixed missions,
  and in neither mission on 5 of the 10 discordant seeds. It is not evidence
  of fault tolerance. See `scripts/audit_confirmatory.py`.
- **H4 —** reported descriptively in the tables.

## Two findings worth stating plainly

**Adaptation buys survival, not science.** Across every Martian condition
success rises while science fraction falls slightly. This follows from the
1/(1−slip) term in the locomotion cost: a corrected slip belief corrects the
energy estimate, so the robot turns back in time — which saves the rover and
costs the last target.

**The uninformed planner often survives best.** Distance-only A* had the
highest Martian success rate in three of four conditions while returning the
least science, with roughly half the ground interventions of the risk-aware
planners. Risk-averse routing is expensive when nearly all ground is
hazardous, and the current objective charges nothing for the extra distance
and exposure that caution incurs. This is a limitation of the formulation, not
an incidental result.
