"""Manual browser proof for the runtime preview, separate from business evidence."""

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def run(web_url, fixture_url, output):
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(web_url)
        expect(page.get_by_role("heading", name="Workspace access")).to_be_visible()
        page.screenshot(path=str(output / "session-login.png"), full_page=True)
        page.get_by_label("Access code").fill("rejected-test-code")
        page.get_by_role("button", name="Enter workspace").click()
        expect(page.get_by_role("alert")).to_contain_text("Access code is invalid")
        page.get_by_label("Access code").fill(os.environ.get("DEMO_JUDGE_ACCESS_CODE", "local-judge-access"))
        page.get_by_role("button", name="Enter workspace").click()
        expect(page.get_by_role("status")).to_contain_text("awaiting implementation")
        expect(page.get_by_role("heading", name="Agency Delivery Review Queue")).to_be_visible()
        page.screenshot(path=str(output / "runtime-preview.png"), full_page=True)
        page.get_by_role("button", name="Brief Composer & Compiler").click()
        with page.expect_response(lambda response: response.url.endswith("/api/v1/briefs")) as response:
            page.get_by_role("button", name="Compile Checks via AI", exact=False).click()
        assert response.value.status == 503
        expect(page.get_by_role("alert")).to_contain_text("No work or payment was created")
        page.screenshot(path=str(output / "workflow-hold.png"), full_page=True)
        page.get_by_role("button", name="Maya", exact=True).click()
        expect(page.get_by_role("button", name="Contractor Portal", exact=True)).to_be_visible()
        expect(page.get_by_text("Judge · Contractor Maya", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Brief Composer & Compiler")).to_have_count(0)
        page.get_by_role("button", name="Leo", exact=True).click()
        expect(page.get_by_text("Judge · Contractor Leo", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="Contractor Submission Portal (Leo Vance)")).to_be_visible()
        page.screenshot(path=str(output / "session-contractor.png"), full_page=True)
        page.reload()
        expect(page.get_by_text("Judge · Contractor Leo", exact=True)).to_be_visible()
        page.get_by_role("button", name="Sign out").click()
        expect(page.get_by_role("heading", name="Workspace access")).to_be_visible()
        assert page.request.get(web_url + "/api/session").status == 401
        page.get_by_label("Access code").fill(os.environ.get("DEMO_OWNER_ACCESS_CODE", "local-owner-access"))
        page.get_by_role("button", name="Enter workspace").click()
        expect(page.get_by_role("heading", name="Agency Delivery Review Queue")).to_be_visible()
        expect(page.get_by_role("button", name="Maya", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Judge Demo Controller", exact=False)).to_have_count(0)

        mobile = browser.new_page(viewport={"width": 320, "height": 640})
        observations = {}
        for version in ("broken", "fixed"):
            mobile.goto(f"{fixture_url}/checkout-{version}")
            width = mobile.evaluate("document.documentElement.scrollWidth")
            observations[version] = {"viewport_width": 320, "scroll_width": width}
            assert (width > 320) if version == "broken" else (width == 320)
            mobile.screenshot(path=str(output / f"fixture-{version}.png"), full_page=True)
        (output / "fixture-observations.json").write_text(json.dumps(observations, indent=2) + "\n")
        browser.close()
        print("PASS: actual Chromium sign-in, judge/owner scope, restore/logout, workflow hold and fixture overflow.")
        print(json.dumps(observations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-url", default="http://localhost:3000")
    parser.add_argument("--fixture-url", default="http://localhost:8080")
    parser.add_argument("--output-dir", default="/screenshots")
    args = parser.parse_args()
    run(args.web_url, args.fixture_url, Path(args.output_dir))
