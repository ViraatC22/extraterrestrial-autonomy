"""WebGL lifecycle stress test for Mission Control.

Switches repeatedly between presentation mode, focus mode, layers, cameras and
paired replay, and counts WebGL contexts created and lost on every page. A
healthy run creates one context per page load (two in development, where
React's strict mode mounts twice) and loses none.

Needs the engine (:8000) and the web app running; uses the system Chrome.

    python review/stress_webgl.py [--base http://localhost:3000] [--cycles 20]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "webgl_stress_result.json"
API = "http://127.0.0.1:8000"

COUNTER = """
window.__webgl = {created: 0, lost: 0};
const original = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
  const ctx = original.call(this, type, ...rest);
  if (ctx && (type === "webgl2" || type === "webgl") && !this.__counted) {
    this.__counted = true;
    window.__webgl.created += 1;
    this.addEventListener("webglcontextlost", () => { window.__webgl.lost += 1; });
  }
  return ctx;
};
"""


def press(page, name: str, exact: bool = True, wait: int = 300) -> None:
    """Click a control. Forced: under software rendering, heavy frames make
    Playwright's "element is stable" check time out, and this test is about
    GPU lifecycle, not click timing."""
    page.get_by_role("button", name=name, exact=exact).first.click(force=True)
    page.wait_for_timeout(wait)


def counts(page) -> dict:
    return page.evaluate("({...window.__webgl})")


def discordant_seed() -> int:
    with urllib.request.urlopen(f"{API}/results") as response:
        points = json.load(response)["paired_points"]
    return next(
        p["seed"]
        for p in points
        if p["condition"] == "mars_faults" and p["success_treatment"] != p["success_control"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3000")
    parser.add_argument("--cycles", type=int, default=20)
    args = parser.parse_args()
    pages = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(COUNTER)

        page.goto(args.base + "/")
        page.get_by_role("button", name="launch mission").click()
        page.get_by_role("button", name="PRESENT").wait_for(timeout=120_000)
        page.wait_for_timeout(3000)
        for cycle in range(args.cycles):
            press(page, "PRESENT", wait=500)
            for key in ("2", "4", "5", "l", "l", "l", "1"):
                page.keyboard.press(key)
                page.wait_for_timeout(250)
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            press(page, "FOCUS")
            press(page, "PANELS")
            for name in (
                "KNOWLEDGE",
                "RISK",
                "ERROR",
                "SURFACE",
                "PLANNER",
                "NAV CAM",
                "CHASE",
                "ORBIT",
            ):
                press(page, name, wait=250)
            print(f"cycle {cycle + 1}: {counts(page)}", flush=True)
        pages.append(
            {"page": "mission control, one mission", "cycles": args.cycles, **counts(page)}
        )

        seed = discordant_seed()
        page.goto(f"{args.base}/?paired=mars_faults:{seed}")
        page.get_by_text("PAIRED REPLAY").first.wait_for(timeout=120_000)
        page.wait_for_timeout(4000)
        for _ in range(max(4, args.cycles // 2)):
            press(page, "FIXED:", exact=False, wait=1500)
            press(page, "ADAPTIVE:", exact=False, wait=1500)
            press(page, "PRESENT", wait=400)
            page.keyboard.press("t")
            page.wait_for_timeout(1200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        pages.append({"page": f"paired replay mars_faults:{seed}", **counts(page)})
        browser.close()

    total_lost = sum(p["lost"] for p in pages)
    result = {
        "base": args.base,
        "pages": pages,
        "contexts_lost": total_lost,
        "max_contexts_per_page": max(p["created"] for p in pages),
        "passed": total_lost == 0 and max(p["created"] for p in pages) <= 2,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
