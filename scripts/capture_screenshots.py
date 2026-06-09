"""Capture dashboard screenshots for the blog using the system Chrome via Playwright.

Usage: python scripts/capture_screenshots.py
Requires the Streamlit app running on http://localhost:8502 and the databases up.
Writes PNGs into screenshots/.
"""
import pathlib
import time

from playwright.sync_api import sync_playwright

URL = "http://localhost:8502"
OUT = pathlib.Path(__file__).resolve().parent.parent / "screenshots"
OUT.mkdir(exist_ok=True)
VIEWPORT = {"width": 1440, "height": 1024}


def click_button(page, text):
    page.locator("button", has_text=text).first.click()
    page.wait_for_timeout(1800)


def shot(page, name):
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / name), full_page=True)
    print("saved", name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(3500)  # let the worker backfill and charts render

        shot(page, "01-dashboard-dark.png")

        click_button(page, "Correct MSFT price")
        shot(page, "02-sql-preview-selected.png")

        click_button(page, "Run selected SQL")
        page.wait_for_timeout(4000)  # wait for CDC to propagate to ClickHouse
        shot(page, "03-after-run-cdc.png")

        # Light mode
        page.get_by_text("Light mode").click()
        page.wait_for_timeout(1800)
        shot(page, "04-dashboard-light.png")
        # back to dark
        page.get_by_text("Light mode").click()
        page.wait_for_timeout(1500)

        # Analytics / events tab
        page.get_by_role("tab", name="Analytics").click()
        page.wait_for_timeout(1500)
        shot(page, "05-analytics-events.png")

        # restore baseline so the demo data is clean
        click_button(page, "Reload baseline")
        page.wait_for_timeout(4000)
        print("baseline reloaded")

        browser.close()


if __name__ == "__main__":
    main()
