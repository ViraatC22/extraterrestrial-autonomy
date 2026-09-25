"""Regenerate every screenshot in review/screenshots/.

Needs both servers running (engine on :8000, web on :3000) and Google Chrome.
Uses the system Chrome through Playwright, so there is no browser download.

    python review/capture_screenshots.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "screenshots"
BASE = "http://localhost:3000"
VIEW = {"width": 1600, "height": 1000}


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("saved", name)


def scroll(page, y):
    page.evaluate(f"document.querySelector('main .overflow-y-auto').scrollTop = {y}")
    page.wait_for_timeout(700)


def main():
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = browser.new_page(viewport=VIEW)

        # Mission Control
        page.goto(BASE + "/")
        page.wait_for_timeout(4000)
        page.get_by_role("button", name="launch mission").click()
        page.wait_for_timeout(16000)
        page.locator('input[type="range"]').last.fill("20")
        page.wait_for_timeout(2500)
        shot(page, "01_mission_control_surface")
        for cam, name in (("CHASE", "02_camera_chase"), ("ROVER POV", "03_camera_rover_pov"),
                          ("PLANNER", "04_camera_planner_candidate_routes")):
            page.get_by_role("button", name=cam, exact=True).click()
            page.wait_for_timeout(3500)
            shot(page, name)
        page.get_by_role("button", name="TOP DOWN", exact=True).click()
        page.wait_for_timeout(3000)
        for layer, name in (("KNOWLEDGE", "05_layer_knowledge"), ("ERROR", "06_layer_belief_error"),
                            ("RISK", "07_layer_risk")):
            page.get_by_role("button", name=layer, exact=True).click()
            page.wait_for_timeout(2500)
            shot(page, name)
        page.mouse.move(800, 520)
        page.wait_for_timeout(1500)
        shot(page, "08_terrain_probe")
        page.get_by_role("button", name="PRESENT").click()
        page.wait_for_timeout(1500)
        page.keyboard.press("2")
        page.wait_for_timeout(3000)
        shot(page, "09_presentation_mode")
        page.keyboard.press("Escape")

        # Autonomy Inspector
        page.goto(BASE + "/inspector")
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="evaluate").click()
        page.wait_for_timeout(12000)
        shot(page, "10_autonomy_inspector")

        # Experiments
        page.goto(BASE + "/experiments")
        page.wait_for_timeout(8000)
        shot(page, "11_experiments_intervals")
        scroll(page, 1250)
        shot(page, "12_experiments_pareto_forest_seeds")

        # Failure Analysis and a case-study replay
        page.goto(BASE + "/failures")
        page.get_by_role("link", name="REPLAY IN MISSION CONTROL").first.wait_for(timeout=180000)
        page.wait_for_timeout(1000)
        shot(page, "13_failure_case_studies")
        page.get_by_role("link", name="REPLAY IN MISSION CONTROL").first.click()
        page.get_by_text("Replay of a mission from the completed confirmatory run").wait_for(
            timeout=120000
        )
        page.wait_for_timeout(6000)
        shot(page, "14_case_study_replay")

        # Scenario Lab
        page.goto(BASE + "/scenario")
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="run sweep").click()
        page.get_by_role("button", name="run sweep").wait_for(timeout=600000)
        page.wait_for_timeout(1000)
        shot(page, "15_scenario_lab_sensitivity")

        browser.close()


if __name__ == "__main__":
    main()
