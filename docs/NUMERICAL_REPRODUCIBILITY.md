# Numerical reproducibility across platforms (Study 2 engine)

Why this exists: Study 1 reproduces bit for bit only on the machine that generated it
(macOS, arm64). On Linux x86-64, 78 of 750 missions differed and 18 changed outcome, although
every inferential conclusion held (`RESEARCH_LOG.md`, 2026-09-26). Study 2 should not carry
that forward knowingly. Everything below used **validation seeds only** (200000-200199, both
bodies, both planners: 800 missions per run), with the Study 2 configuration (engine v2,
confusion-aware learner M3). Harness: `scripts/numerical_reproducibility.py`; the Linux runs
are the GitHub workflow "numerical reproducibility (Linux)". Raw per-mission fingerprints
(terrain hashes, full paths, every decision's P(fail) as exact hex floats):
`data/validation/numerics/`.

## 1. Where can floating-point noise change a decision?

Every branch in the engine that compares floats, by kind:

| Location | Comparison | Kind | Exposure |
|---|---|---|---|
| `planners/base.py` A* | heap order `(f, g, cell)`; `new_cost < best_cost` | ranking of path costs | equal-cost paths are common on an 8-connected grid; ties on exact equality fall to `g` then cell coordinates (deterministic), but values that are only *nearly* equal because of platform noise are ordered by the noise |
| `mission_manager.select_objective` | `utility > best` | ranking of candidates | near-ties decided by noise (v1) |
| `mission_manager.select_objective` | `p_failure > risk_budget` | threshold | flips only if P(fail) lies within noise of ε |
| `world_model.believed_traversable` | `hazard_prob >= threshold`, `slope <= max_slope` | threshold | believed slope is a noisy reading; flips only within noise of the limit |
| `vehicle.attempt_move` | `slope > max_slope`, `slip >= 0.80`, `charge < amount` | threshold | as above |
| `mission_manager` | `charge_fraction >= resume` | threshold | as above |
| `risk._normal_sf` | `erfc` (maths library) | value | last-bit differences between libraries feed every risk term |
| M3 learner | `np.exp` in the mixture responsibility | value | vectorised `exp` implementations differ by platform |
| terrain generators | `sin`, `cos`, `arctan`, `exp` | value | every continuous terrain field |

Thresholds cannot be made immune by a tolerance band - a value near the edge of a band
straddles it just as it straddles the threshold - but they flip only when a value lands
within ~1e-15 of the threshold, which is rare. Rankings of *mathematically equal or
near-equal* quantities are different: they are common, and platform noise decides them every
time. Value differences are the root: if every input to a decision is bit-identical, every
comparison is.

## 2. Baseline (before any change)

`data/validation/numerics/baseline_summary.json`:

- Terrain: **0 of 800** maps had bit-identical continuous fields; **800 of 800** had
  identical classes and hazards. The generators' maths-library calls differ in the last bits.
- 194 missions fully identical (path, every decision value, energy); 661 same path;
  787 same termination; 13 success flips.
- Mars effect (adaptive - fixed success): +0.070 on macOS, +0.060 on Linux.

## 3. Changes, in the order made (engine v2 only; v1 untouched)

Each round was measured on all 800 validation missions on both platforms
(`data/validation/numerics/<round>_summary.json`).

| Round | Change | Terrain bit-identical | Same path | Same outcome | Success flips |
|---|---|---|---|---|---|
| baseline | none | 0 | 661 | 787 | 13 |
| canonical | terrain rounded to 9 decimals; utility ties within 1e-9 (relative) go to the lower target id | 0 (harness then hashed raw terrain) | 731 | 795 | 4 |
| deterministic | exp, erfc, hypot from IEEE-exact operations (`exonaut.numerics`) | 796 | 774 | 798 | 1 |
| fsum | exactly rounded reductions (math.fsum); terrain rounded to 6 decimals | 800 | 772 | 796 | 3 |
| final | integer powers by repeated multiplication (Python's `**` calls the platform `pow`) | see section 4 | | | |

Tolerances were set from magnitudes, not outcomes: platform noise is ~1e-15 relative; the
smallest physically meaningful differences are ~1 (slope-sensor noise 1.2 degrees) and utility
gaps are percents. The move from 9 to 6 decimals followed a calculation of the chance that a
value lies within platform noise of a rounding boundary (~2e-15 / 10^-d per value, ~16,000
values per map: ~3% of maps at d = 9, which matched the 4 of 800 measured; ~3e-5 at d = 6).

**Stopping rule, written and committed before the final round's results were seen:** the
final round is the last numerical iteration. More rounds would start to become their own source
of researcher degrees of freedom. Whatever it shows, Study 2 is frozen with the rule in
section 5.

## 5. Rule for Study 2 (pre-specified here, before the final round's results)

- **Canonical platform.** The confirmatory results of Study 2 are those produced on macOS,
  arm64 (the development machine), Python 3.13, with the pinned libraries in
  `requirements-lock.txt`. These are the numbers reported and tested.
- **Cross-platform check.** The same confirmatory run is repeated once on Linux x86-64 (the
  GitHub workflow), with the same code and libraries. The primary conclusion is declared
  **platform-robust** if (a) the primary test's reject / do-not-reject decision is the same on
  both platforms, and (b) the two primary estimates (difference in Mars success) differ by no
  more than **0.05**, half the minimum effect of interest - a difference smaller than that
  could not change the practical reading of the result. Mission-level identity is reported
  descriptively. If either condition fails, the canonical result is still the one reported,
  and the paper says plainly that it is not platform-robust.
- The canonical-platform rule applies even if the final round reaches full identity, since
  identity on validation missions does not guarantee it on new terrain.
