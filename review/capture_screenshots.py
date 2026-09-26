"""Regenerate the app screenshots in review/screenshots/.

Needs both servers running (engine on :8000, web on :3000) and Google Chrome.
Uses the system Chrome through Playwright, so there is no browser download.
The model renders (model_*.png) come from scripts/build_vehicle_models.py and
are left alone.

    python review/capture_screenshots.py
"""

import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "screenshots"
BASE = "http://localhost:3000"
API = "http://127.0.0.1:8000"
VIEW = {"width": 1600, "height": 1000}


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("saved", name)


def scroll(page, y, which=0):
    page.evaluate(f"document.querySelectorAll('main .overflow-y-auto')[{which}].scrollTop = {y}")
    page.wait_for_timeout(700)


def camera(page, name, wait=3500):
    page.get_by_role("button", name=name, exact=True).click()
    page.wait_for_timeout(wait)


def seek(page, frame):
    timeline = page.locator('input[type="range"]').last
    top = int(timeline.get_attribute("max") or 0)
    timeline.fill(str(min(frame, top)))
    page.wait_for_timeout(2500)


def discordant_seed(condition="mars_faults"):
    """A seed where only the adaptive planner returned, having collected some
    science (so there is driving to show), from the committed results. This
    only picks an illustration of the replay feature; it is not a result."""
    with urllib.request.urlopen(f"{API}/results") as response:
        points = json.load(response)["paired_points"]
    for p in points:
        if (
            p["condition"] == condition
            and p["success_treatment"]
            and not p["success_control"]
            and p["science_treatment"] > 0
        ):
            return p["seed"]
    return points[0]["seed"]


def main():
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("[0-9]*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport=VIEW)

        # Mission Control: a default mission part-way through
        page.goto(BASE + "/")
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="launch mission").click()
        page.wait_for_timeout(16000)
        seek(page, 20)
        shot(page, "01_mission_control_surface")
        camera(page, "CHASE")
        shot(page, "02_camera_chase")
        camera(page, "NAV CAM")
        shot(page, "03_camera_navcam")
        camera(page, "TOP DOWN", 3000)
        for layer, name in (
            ("KNOWLEDGE", "05_layer_knowledge"),
            ("ERROR", "06_layer_belief_error"),
            ("RISK", "07_layer_risk_with_budget"),
        ):
            page.get_by_role("button", name=layer, exact=True).click()
            page.wait_for_timeout(2500)
            shot(page, name)
        page.mouse.click(760, 480)
        page.wait_for_timeout(800)
        page.mouse.click(900, 600)
        page.wait_for_timeout(2500)
        shot(page, "08_terrain_probe_compare")
        page.get_by_role("button", name="CLEAR PINS").click()
        page.get_by_role("button", name="SURFACE", exact=True).click()
        page.get_by_role("button", name="FOCUS").click()
        camera(page, "ORBIT", 2500)
        shot(page, "10_focus_mode")
        page.get_by_role("button", name="PANELS").click()
        page.get_by_role("button", name="PRESENT").click()
        page.wait_for_timeout(1500)
        page.keyboard.press("2")
        page.wait_for_timeout(3000)
        shot(page, "09_presentation_mode")
        page.keyboard.press("Escape")

        # Demonstration mission at its adaptation event, in planner view
        page.goto(BASE + "/?demo=1")
        page.get_by_text("DEMONSTRATION CASE").first.wait_for(timeout=60000)
        page.wait_for_timeout(5000)
        with urllib.request.urlopen(f"{API}/demo-mission") as response:
            event_frame = json.load(response)["chosen"]["event_frame"]
        seek(page, event_frame)
        page.wait_for_timeout(1500)
        shot(page, "04_demo_mission_planner_view")

        # Paired replay of a committed confirmatory seed
        seed = discordant_seed()
        page.goto(BASE + f"/?paired=mars_faults:{seed}")
        page.get_by_text("PAIRED REPLAY").first.wait_for(timeout=120000)
        page.wait_for_timeout(6000)
        seek(page, 60)
        shot(page, "11_paired_replay_adaptive")
        page.get_by_role("button", name="FIXED:").click()
        page.wait_for_timeout(6000)
        shot(page, "12_paired_replay_fixed")

        # Autonomy Inspector, with one calculation opened
        page.goto(BASE + "/inspector")
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="evaluate").click()
        page.get_by_text("SHOW CALCULATION").first.wait_for(timeout=60000)
        page.get_by_text("SHOW CALCULATION").first.click()
        page.wait_for_timeout(800)
        scroll(page, 420, which=1)
        shot(page, "13_autonomy_inspector_calculation")

        # Experiments
        page.goto(BASE + "/experiments")
        page.wait_for_timeout(8000)
        shot(page, "14_experiments_tiers_intervals")
        scroll(page, 900)
        shot(page, "15_experiments_effects_seeds")
        scroll(page, 1900)
        shot(page, "16_experiments_secondary")

        # Failure Analysis and a case-study replay
        page.goto(BASE + "/failures")
        page.get_by_role("link", name="REPLAY IN MISSION CONTROL").first.wait_for(timeout=180000)
        page.wait_for_timeout(1000)
        shot(page, "17_failure_case_studies")
        page.get_by_role("link", name="REPLAY IN MISSION CONTROL").first.click()
        page.get_by_text("Replay of a mission from the completed confirmatory run").wait_for(
            timeout=120000
        )
        page.wait_for_timeout(6000)
        shot(page, "18_case_study_replay")

        # Scenario Lab
        page.goto(BASE + "/scenario")
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="run sweep").click()
        page.get_by_role("button", name="run sweep").wait_for(timeout=600000)
        page.wait_for_timeout(1000)
        shot(page, "19_scenario_lab_sensitivity")

        browser.close()


if __name__ == "__main__":
    main()
