# Study 2 (v2) freeze checklist

**No v2 confirmatory data may be generated until every box below is checked, each check is
committed, and `docs/PREREGISTRATION_V2.md` exists.** The terrain generator enforces the last
part: it refuses every seed in the v2 confirmatory pools unless that file exists and the run is
authorized with its SHA-256 (`EXONAUT_AUTHORIZE_V2_CONFIRMATORY`). Every attempt is logged.

Status on 2026-09-27: **FROZEN (revision 2), NOT AUTHORISED.** Every item is checked. The plan
is `docs/PREREGISTRATION_V2.md`; the freeze commit is tagged `study2-freeze-n240`. Revision 1
(tag `study2-freeze`, n = 230) is superseded: its plan hash must not be used. No Study 2
confirmatory seed has been used, and the run has not been authorised.

Plan SHA-256 (revision 2): `8adb1dd7c1fda68631eeb58ea2e2cb6ab0f6ebba6b0d92269fcc6d1d059294cc`

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Calibration decided | ☑ | The pre-specified rule accepted **no** candidate (`CALIBRATION_AUDIT.md` §4); the owner chose option A, the confusion-aware learner M3 (§6; `RESEARCH_LOG.md` 2026-09-27). The rule was not changed; M3's Mars shortfall (95% coverage ≈ 0.72) is disclosed in the plan (§2) and measured descriptively. Commit ae44434. |
| 2 | Simulator validation passed | ☑ | `SIMULATOR_VALIDATION.md`; full test suite passes on the freeze commit. |
| 3 | Hypotheses frozen | ☑ | Plan §4: H1 primary (Mars success), H2, H3a, H3b secondary; all two-sided (owner decision). `V2_HYPOTHESES_DRAFT.md` is marked superseded. |
| 4 | Outcomes and tiers frozen | ☑ | Plan §6 (primary / secondary / descriptive / exploratory / post-hoc). |
| 5 | Statistical tests frozen | ☑ | Plan §5: McNemar exact (H1, H3a); paired t with Wilcoxon alongside (H2, H3b); success difference with Newcombe's hybrid score interval (`analysis.newcombe_paired_ci`, `tests/test_newcombe.py`). |
| 6 | Multiplicity plan frozen | ☑ | Plan §5: one primary test, no correction; Holm across {H2, H3a, H3b}. |
| 7 | Sample size frozen | ☑ | n = **240** per condition: the pre-specified rule (minimum effect 0.10, target power 0.90, upper bound of the validation discordance) applied to the final engine; exact power 0.901 (`data/validation/power_analysis/final_engine_sizing.json`, plan §7). Revision 1's 230 came from the pre-numerics engine and would give 0.888. `tests/test_power_analysis.py` checks the design's n equals the rule's answer. |
| 8 | Seed manifests frozen | ☑ | `data/splits/v2/seed_manifest.json`, checksum `2b24c27d…2479e` in plan header, verified by `tests/test_v2_protocol.py`; confirmatory pools disjoint from every v1 split. |
| 9 | Held-out access log clean | ☑ | `data/splits/heldout_access_log.jsonl` does not exist on the freeze commit: no logged access to any held-out or confirmatory seed. Tests redirect their deliberate probes with `EXONAUT_HELDOUT_LOG`. |
| 10 | Paper methods updated | ☑ | `paper/exonaut.tex` §"Study 2: frozen, not yet executed": design, hypotheses, tests, n and achieved power, numerical-reproducibility rule, protection. No result reported. |
| 11 | Code commit tagged | ☑ | Tag `study2-freeze-n240`. `scripts/run_study2.py` records commit, design digest and plan hash in the results sidecar. |
| 12 | Configs checksummed | ☑ | `experiments/configs/study2.json` (`n_seeds` 240), design digest `d3be0b9ce18a`, recorded in the plan header and checked by the runner. |
| 13 | Raw-output schema frozen | ☑ | Plan §9: columns exactly `RESULT_COLUMNS` in `scripts/run_study2.py`; exercised by the validation dry run (`data/validation/study2_dry_run/`), re-run on the final engine with the revision-2 design. |
| 14 | v1 still reproduces | ☑ | `scripts/verify_v1_reproduction.py`: 750 / 750 exact on macOS arm64 after all engine changes (engine code identical to the freeze commit); `tests/test_v1_lock.py` passes. |
| 15 | Numerical reproducibility | ☑ | `NUMERICAL_REPRODUCIBILITY.md`: five rounds on validation seeds, macOS arm64 vs Linux x86-64; exact identity **not** reached (608 / 800 missions fully identical, 3 success flips). By the rule committed before the final round (51ba075): canonical platform macOS arm64, plus a pre-specified Linux robustness check (same H1 decision, estimates within 0.05). |

## What happens next (not done here)

1. The owner decides whether to authorise the run. Authorising means setting
   `EXONAUT_AUTHORIZE_V2_CONFIRMATORY` to the SHA-256 of `docs/PREREGISTRATION_V2.md`, for the
   single run, and recording that in `RESEARCH_LOG.md`.
2. Run once on the canonical platform from a clean checkout of `study2-freeze-n240`
   (`scripts/run_study2.py`, then `scripts/analyze_study2.py`).
3. Repeat the run on Linux for the robustness check, and report every pre-specified outcome,
   whatever it shows.
