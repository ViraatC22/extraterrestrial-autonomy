# Study 2 (v2) freeze checklist

**No v2 confirmatory data may be generated until every box below is checked, each check is
committed, and `docs/PREREGISTRATION_V2.md` exists.** The terrain generator enforces the last
part: it refuses every seed in the v2 confirmatory pools unless that file exists and the run is
authorized with its SHA-256 (`EXONAUT_AUTHORIZE_V2_CONFIRMATORY`). Every attempt is logged.

Status on 2026-09-26: **BLOCKED** (calibration not accepted; owner decisions pending).

| # | Item | Status | Evidence / what is missing |
|---|---|---|---|
| 1 | **Calibration accepted** | ☐ blocked | Pre-specified rule: NOT ACCEPTED (`CALIBRATION_AUDIT.md` §4). Owner must choose option A, B or C (§5) and the choice must be logged. |
| 2 | Simulator validation passed | ☑ | `SIMULATOR_VALIDATION.md`; all checklist tests pass. Re-run on the freeze commit. |
| 3 | Hypotheses frozen | ☐ | Draft: `V2_HYPOTHESES_DRAFT.md`. Owner to confirm two-sided H1/H2 and the secondary family. |
| 4 | Outcomes and tiers frozen | ☐ | Draft table in `V2_HYPOTHESES_DRAFT.md`. |
| 5 | Statistical tests frozen | ☐ | McNemar exact (primary), paired t + Wilcoxon (secondary). The paired interval for the success difference must be chosen and, if not the v1 t interval, implemented and tested. |
| 6 | Multiplicity plan frozen | ☐ | One primary test (no correction); Holm across the secondary family. |
| 7 | Sample size frozen | ☐ | `POWER_ANALYSIS.md` gives n for each leading calibration candidate; the one matching item 1 applies. Owner to confirm the minimum effect of interest. |
| 8 | Seed manifests frozen | ☑ | `data/splits/v2/seed_manifest.json`, checksum verified by `tests/test_v2_protocol.py`; confirmatory pools disjoint from every v1 split. |
| 9 | Held-out access log clean | ☐ check at freeze | `data/splits/heldout_access_log.jsonl` must show no v2 confirmatory seed (and should show no unused v1 held-out seed used for development). As of this commit the file does not exist: nothing has been logged. |
| 10 | Paper methods updated | ☐ | The paper's Study 2 section describes the planned design without results; it must be updated to the frozen choices. |
| 11 | Code commit tagged | ☐ | Tag the freeze commit (e.g. `study2-freeze`); the run's metadata must record it. |
| 12 | Configs checksummed | ☐ | A v2 design file (like `experiments/configs/exonaut_main.json`) with its digest recorded in the plan. |
| 13 | Raw-output schema frozen | ☐ | Column list of the v2 results table fixed in the plan (the v1 schema plus `epistemic_scale`, `class_assignment`, and the calibration descriptives). |
| 14 | v1 still reproduces | ☑ (re-run at freeze) | `scripts/verify_v1_reproduction.py`; `tests/test_v1_lock.py`. |

## After every box is checked

1. Write `docs/PREREGISTRATION_V2.md` from the frozen drafts; commit and tag.
2. Record the checklist evidence (commit hashes) in this file.
3. Authorize the single run with the plan's hash, run it once, and report every pre-specified
   outcome, whatever it shows.
