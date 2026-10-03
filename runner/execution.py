"""Actual HTTP and Chromium observations of verified, reviewed fixture bytes."""

import asyncio
import base64
import hashlib
import re
from datetime import datetime, timezone

import httpx

from fixture_contract.observations import measured_outcome, provenance
from fixture_contract.registry import decode_json
from runner.contracts import RunnerViolation, validate_job


def stamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch(client, url):
    async with client.stream("GET", url) as response:
        if 300<=response.status_code<400:
            raise RunnerViolation("Fixture redirect is forbidden")
        if response.headers.get("Content-Encoding", "identity")!="identity":
            raise RunnerViolation("Compressed fixture responses are not accepted")
        data = bytearray()
        async for part in response.aiter_bytes():
            if len(data)+len(part)>262144:
                raise RunnerViolation("Fixture response exceeds limit")
            data.extend(part)
        return response.status_code, response.headers, bytes(data)


async def reach(page, control_id):
    for tabs in range(1, 21):
        await page.keyboard.press("Tab")
        focused = await page.evaluate("document.activeElement.id")
        if focused==control_id:
            return True, tabs, focused
    return False, 20, focused


async def browser_measure(page, template, facts):
    from playwright.async_api import expect
    control = page.locator(f"#{facts.control_dom_id}")
    if template=="viewport_no_horizontal_overflow":
        width = await page.evaluate("window.innerWidth")
        scroll = await page.evaluate("document.documentElement.scrollWidth")
        return {"viewport_width": width, "scroll_width": scroll, "overflow_px": max(0, scroll-width)}
    if template=="cart_total_unchanged":
        total = (await page.locator(".total-row span").last.inner_text()).strip()
        if not re.fullmatch(r"\$(0|[1-9][0-9]*)\.[0-9]{2}", total):
            raise RunnerViolation("Checkout total is unavailable")
        dollars, cents = total[1:].split(".")
        return {"total_cents": int(dollars)*100+int(cents), "currency": "USD", "baseline_total_cents": facts.total_cents}
    if template=="keyboard_checkout_reachable":
        reached, tabs, focused = await reach(page, facts.control_dom_id)
        return {"control_ref": facts.control_ref, "reached": reached, "tabs": tabs, "focused_id": focused}
    if template=="keyboard_activation":
        reached, _, _ = await reach(page, facts.control_dom_id)
        if reached:
            await page.keyboard.press("Enter")
        activated = await page.locator(f"#{facts.target_dom_id}").get_attribute("data-activated")
        return {"control_ref": facts.control_ref, "key": "Enter", "reached": reached, "activated": activated=="true"}
    if template=="accessible_control_name":
        snapshot = await control.aria_snapshot(timeout=2000)
        try:
            await expect(control).to_have_accessible_name(facts.accessible_name, timeout=500)
            matches = True
        except AssertionError:
            matches = False
        return {"control_ref": facts.control_ref, "expected_name": facts.accessible_name,
                "name_matches": matches, "aria_snapshot": snapshot[:2000]}
    raise RunnerViolation("Unknown browser template")


def result(job, check, measurement, facts, indexes=None):
    return {"check_id": check["check_id"], "outcome": measured_outcome(check["template_type"], measurement, facts),
            "observations": {"provenance": provenance(job, check), "measurement": measurement},
            "screenshot_indexes": indexes or [], "completed_at": stamp()}


async def execute(job, fixture_origin):
    from playwright.async_api import Error as PlaywrightError

    contract, artifact = validate_job(job, fixture_origin)
    output = {"lease_token": job["lease_token"], "artifact_digest": job["artifact_digest"],
              "mandate_digest": job["mandate_digest"], "results": [], "screenshots": []}
    try:
        async with asyncio.timeout(30):
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False,
                headers={"Accept-Encoding": "identity"}) as client:
                status, headers, source = await fetch(client, job["fixture_url"]+"/source")
                if status!=200 or hashlib.sha256(source).hexdigest()!=artifact.digest:
                    raise RunnerViolation("Fixture source differs from the approved artifact")
                if artifact.family=="api_endpoint":
                    expected = decode_json(source)
                    status, headers, body = await fetch(client, job["fixture_url"]+contract.facts.endpoint_path)
                    parsed = decode_json(body)
                    if status!=expected["status_code"] or parsed!=expected["body"] or headers.get("X-Artifact-Digest")!=artifact.digest:
                        raise RunnerViolation("API observation differs from its artifact")
                    for check in job["checks"]:
                        template = check["template_type"]
                        if template=="api_status":
                            measured = {"status_code": status, "expected_status": check["params"]["expected_status"]}
                        elif template=="api_schema":
                            measured = {"status_code": status, "schema_ref": contract.facts.schema_ref, "response": parsed}
                        elif template=="api_total_matches_fixture":
                            measured = {"status_code": status, "baseline_total_cents": contract.facts.total_cents, "response": parsed}
                        else:
                            raise RunnerViolation("Unknown API template")
                        output["results"].append(result(job, check, measured, contract.facts))
                else:
                    checkout = job["fixture_url"]+"/checkout"
                    status, headers, html = await fetch(client, checkout)
                    if status!=200 or hashlib.sha256(html).hexdigest()!=artifact.digest or headers.get("X-Artifact-Digest")!=artifact.digest:
                        raise RunnerViolation("Checkout observation differs from its artifact")
                    await execute_browser(job, contract, checkout, html, output)
        return output
    except TimeoutError:
        code = "RUN_TIMEOUT"
    except RunnerViolation:
        code = "ARTIFACT_MISMATCH"
    except (httpx.HTTPError, ValueError):
        code = "CHECK_UNAVAILABLE"
    except PlaywrightError:
        code = "RUNNER_ERROR"
    # A failed setup/runtime never inherits partial passing results.
    output["screenshots"] = []
    output["results"] = [result(job, c, {"error_code": code}, contract.facts) for c in job["checks"]]
    return output


async def execute_browser(job, contract, url, html, output):
    from playwright.async_api import Error, TimeoutError as PlaywrightTimeout, async_playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--disable-background-networking", "--disable-component-update"])
        try:
            context = await browser.new_context(viewport={"width": 320, "height": 640}, device_scale_factor=1,
                service_workers="block", accept_downloads=False)
            context.set_default_timeout(3000)
            async def route(request_route):
                request = request_route.request
                if request.url==url and request.method=="GET" and request.is_navigation_request():
                    # Render the bytes just fetched and verified over HTTP, eliminating a second-fetch race.
                    await request_route.fulfill(status=200, content_type="text/html", body=html)
                else:
                    await request_route.abort()
            async def websocket(ws):
                await ws.close()
            await context.route("**/*", route)
            await context.route_web_socket("**/*", websocket)
            for check in job["checks"]:
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="load", timeout=5000)
                    measurement = await browser_measure(page, check["template_type"], contract.facts)
                    data = await page.screenshot(type="png", animations="disabled")
                    if len(data)>524288:
                        raise RunnerViolation("Screenshot exceeds limit")
                    index = len(output["screenshots"])
                    output["screenshots"].append({"check_id": check["check_id"], "media_type": "image/png",
                        "sha256": hashlib.sha256(data).hexdigest(), "data_base64": base64.b64encode(data).decode()})
                    output["results"].append(result(job, check, measurement, contract.facts, [index]))
                except PlaywrightTimeout:
                    output["results"].append(result(job, check, {"error_code": "CHECK_TIMEOUT"}, contract.facts))
                except Error:
                    output["results"].append(result(job, check, {"error_code": "CHECK_UNAVAILABLE"}, contract.facts))
                finally:
                    await page.close()
            await context.close()
        finally:
            await browser.close()
