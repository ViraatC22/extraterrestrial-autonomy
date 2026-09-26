"""Rebuild every generated paper asset from stored artifacts; record provenance.

    python scripts/build_all_figures.py           # rebuild + write paper/PROVENANCE.yaml
    python scripts/build_all_figures.py --check   # verify files still match PROVENANCE.yaml

Each step reads committed artifacts only - no step runs a simulation - so the
whole rebuild takes seconds and cannot touch held-out data. Study 1's result
tables are locked (data/results/v1_LOCK.json); its step recomputes and
verifies them instead of writing them.

PROVENANCE.yaml maps every generated file, and every macro the paper uses, to
the script that made it, that script's hash, the input files and their hashes,
and the commit. `--check` (and tests/test_paper_provenance.py) fails if a file
changed without a rebuild, or a macro the paper uses has no recorded source.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "paper" / "PROVENANCE.yaml"
PAPER = ROOT / "paper" / "exonaut.tex"

STEPS = [
    {
        "id": "study1_assets",
        "script": "scripts/make_exonaut_paper_assets.py",
        "args": [],
        "inputs": ["data/results/exonaut_main.csv", "data/results/exonaut_main.metadata.json"],
        "outputs": [
            "paper/tables/exonaut_main_macros.tex",
            "paper/tables/exonaut_main_descriptive.tex",
            "paper/tables/exonaut_main_primary.tex",
            "paper/tables/exonaut_main_secondary.tex",
            "paper/tables/exonaut_main_gap.tex",
            "paper/figures/exonaut_main_outcomes.pdf",
            "paper/figures/exonaut_main_terminations.pdf",
        ],
    },
    {
        "id": "study1_audit_macros",
        "script": "scripts/audit_confirmatory.py",
        "args": ["--render"],
        "inputs": [
            "data/results/audit_fault_exposure.csv",
            "data/results/audit_learner_calibration.csv",
            "data/results/exonaut_main.csv",
        ],
        "outputs": ["paper/tables/exonaut_audit_macros.tex"],
    },
    {
        "id": "calibration",
        "script": "scripts/calibration_paper_assets.py",
        "args": [],
        "inputs": [
            "data/validation/calibration/diagnose_coverage.csv",
            "data/validation/calibration/diagnose_predictive.csv",
            "data/validation/calibration/summary.json",
            "data/validation/calibration/fit.json",
            "data/validation/calibration/evaluate_coverage.csv",
            "data/validation/calibration/evaluate_coverage_by_class.csv",
            "data/validation/calibration/evaluate_predictive.csv",
            "data/validation/calibration/selection.json",
        ],
        "outputs": [
            "paper/tables/exonaut_calibration_macros.tex",
            "paper/figures/v2_calibration_curve.pdf",
            "paper/figures/v2_calibration_by_class.pdf",
            "data/validation/calibration/RESULTS.md",
        ],
    },
    {
        "id": "power",
        "script": "scripts/power_analysis.py",
        "args": ["analyze"],
        "inputs": ["data/validation/power_analysis/validation_missions.csv"],
        "outputs": [
            "paper/tables/exonaut_power_macros.tex",
            "paper/figures/v2_power_curve.pdf",
            "data/validation/power_analysis/power_summary.json",
            "data/validation/power_analysis/power_grid.csv",
            "data/validation/power_analysis/sample_size_table.csv",
            "data/validation/power_analysis/RESULTS.md",
        ],
    },
    {
        "id": "exploration_v2",
        "script": "scripts/analyze_exploration.py",
        "args": [],
        "inputs": ["data/results/exploration_v2_validation.csv"],
        "outputs": ["docs/EXPLORATION_V2.md", "data/results/exploration_v2_summary.json"],
    },
]


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def git_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip()


def paper_macros() -> dict[str, str]:
    """Macro name -> the generated file that defines it."""
    defined = {}
    for step in STEPS:
        for rel in step["outputs"]:
            path = ROOT / rel
            if path.suffix == ".tex" and path.exists():
                for name in re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", path.read_text()):
                    defined[name] = rel
    used = set(re.findall(r"\\([A-Z][A-Za-z]+)", PAPER.read_text()))
    return {name: defined[name] for name in sorted(used) if name in defined}


def undefined_paper_macros() -> list[str]:
    """Capitalised macros the paper uses that no generator defines (typos or stale)."""
    text = PAPER.read_text()
    local = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text))
    used = set(re.findall(r"\\((?:Main|Audit|Cal|Pow|Pilot)[A-Za-z]+)", text))
    defined = set(paper_macros()) | local
    return sorted(used - defined)


def record() -> dict:
    commit = git_commit()
    entries = []
    for step in STEPS:
        entries.append(
            {
                "step": step["id"],
                "command": " ".join(["python", step["script"], *step["args"]]),
                "script_sha256": sha(ROOT / step["script"]),
                "inputs": {rel: sha(ROOT / rel) for rel in step["inputs"]},
                "outputs": {rel: sha(ROOT / rel) for rel in step["outputs"]},
            }
        )
    return {
        "generated_at_commit": commit,
        "note": (
            "Every generated file the paper uses, with the script, inputs and hashes that "
            "produced it. Regenerate with: python scripts/build_all_figures.py"
        ),
        "steps": entries,
        "paper_macros": paper_macros(),
        "figures_in_paper": sorted(
            set(re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", PAPER.read_text()))
        ),
    }


def check() -> list[str]:
    recorded = yaml.safe_load(PROVENANCE.read_text())
    problems = []
    for step in recorded["steps"]:
        for kind in ("inputs", "outputs"):
            for rel, digest in step[kind].items():
                if sha(ROOT / rel) != digest:
                    problems.append(
                        f"{step['step']}: {kind[:-1]} {rel} changed since the last rebuild"
                    )
        if sha(ROOT / step["command"].split()[1]) != step["script_sha256"]:
            problems.append(f"{step['step']}: script changed since the last rebuild")
    for name in undefined_paper_macros():
        problems.append(f"paper uses \\{name}, which no generator defines")
    for fig in recorded["figures_in_paper"]:
        rel = f"paper/{fig}"
        if not any(rel in s["outputs"] for s in recorded["steps"]):
            problems.append(f"figure {rel} is not produced by any step")
    return problems


def main() -> int:
    if "--check" in sys.argv:
        problems = check()
        print("\n".join(problems) if problems else "provenance OK")
        return 1 if problems else 0
    for step in STEPS:
        missing = [rel for rel in step["inputs"] if not (ROOT / rel).exists()]
        if missing:
            print(f"skip {step['id']}: missing inputs {missing}")
            continue
        print(f"== {step['id']}")
        subprocess.run([sys.executable, step["script"], *step["args"]], cwd=ROOT, check=True)
    PROVENANCE.write_text(yaml.safe_dump(record(), sort_keys=False, width=100))
    print(f"wrote {PROVENANCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
