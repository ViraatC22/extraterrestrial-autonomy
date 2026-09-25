"""Regenerate every screenshot in review/screenshots/.

Needs both servers running (API on :8000, web on :3000) and Google Chrome
installed. Uses the system Chrome via Playwright, so no browser download.

    python review/capture_screenshots.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "screenshots"
BASE = "http://localhost:3000"
VIEW = {"width": 1600, "height": 1000}


def shot(page, name, full_page=False):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full_page)
    print("saved", name)


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport=VIEW)

        # 1. Mission Control, idle then launched
        page.goto(BASE + "/")
        page.wait_for_timeout(4000)
        shot(page, "01_mission_control_idle")
        page.get_by_role("button", name="launch mission").click()
        page.wait_for_timeout(14000)
        shot(page, "02_mission_control_launched")
        for layer in ("SLOPE", "LIGHT"):
            button = page.get_by_role("button", name=layer, exact=True)
            if button.count():
                button.first.click()
                page.wait_for_timeout(2500)
                shot(page, f"03_mission_control_layer_{layer.lower()}")

        # 2. Autonomy Inspector, after evaluation
        page.goto(BASE + "/inspector")
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="evaluate").click()
        page.wait_for_timeout(12000)
        shot(page, "04_autonomy_inspector", full_page=True)

        # 3. Experiments and Failure Analysis (read committed results)
        page.goto(BASE + "/experiments")
        page.wait_for_timeout(5000)
        shot(page, "05_experiments", full_page=True)
        page.goto(BASE + "/failures")
        page.wait_for_timeout(5000)
        shot(page, "06_failure_analysis", full_page=True)

        # 4. Scenario Lab, before and after a small sweep
        page.goto(BASE + "/scenario")
        page.wait_for_timeout(3000)
        slider = page.locator('input[type="range"]').first
        slider.fill("2")  # 2 missions per point keeps the capture quick
        shot(page, "07_scenario_lab_setup")
        page.get_by_role("button", name="run sweep").click()
        # Result rows only render once the whole sweep has finished.
        page.wait_for_selector("text=% success", timeout=300000)
        page.wait_for_timeout(1500)
        shot(page, "08_scenario_lab_results", full_page=True)

        browser.close()


if __name__ == "__main__":
    main()
