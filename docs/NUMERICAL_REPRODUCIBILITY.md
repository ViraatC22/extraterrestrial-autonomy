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

## 3. Changes (engine v2 only; v1 is untouched so Study 1 still reproduces)

1. **Canonical terrain.** Continuous terrain fields are rounded to 9 decimal places right
   after generation (`environments.canonicalize`). Platform noise is ~1e-15; the smallest
   physically meaningful difference (slope-sensor noise, 1.2 degrees) is ~1. Nine decimals
   is about six orders of magnitude from each, so the rounding removes platform noise without
   changing the terrain. The tolerance was set from these magnitudes, not tuned on results.
2. **Deterministic candidate ranking.** Two targets whose utilities differ by less than a
   relative 1e-9 are tied, and the lower target id wins (`MissionManager._better`). The same
   reasoning sets 1e-9: far above floating-point noise, far below any utility difference that
   could matter (utilities differ by percents).

Results after these changes: section 4.
