"""Exercise fresh Compose services and the unfinished-workflow boundary."""

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid


def request(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read()


def run(web_url, fixture_url):
    status, body = request(f"{web_url}/readyz")
    assert status == 200 and json.loads(body)["database"] == "connected"
    status, body = request(f"{web_url}/api/v1/tasks")
    assert status == 200 and isinstance(json.loads(body), list)
    status, body = request(f"{web_url}/api/v1/sessions/me")
    assert status == 200 and json.loads(body)["display_name"] == "Sarah (Agency Owner)"
    status, body = request(f"{web_url}/contractor/tasks")
    assert status == 200 and b'<div id="root">' in body
    for version in ("broken", "fixed"):
        status, body = request(f"{fixture_url}/checkout-{version}")
        assert status == 200 and b"checkout_pay" in body
    status, body = request(f"{web_url}/api/v1/deliveries/submit", {
        "task_id": str(uuid.uuid4()), "artifact_ref": "checkout_mobile_fixed", "claim": "Fixed",
    })
    assert status == 503 and json.loads(body)["detail"]["code"] == "WORKFLOW_UNAVAILABLE"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-url", default="http://localhost:3000")
    parser.add_argument("--fixture-url", default="http://localhost:8080")
    args = parser.parse_args()
    for attempt in range(20):
        try:
            run(args.web_url.rstrip("/"), args.fixture_url.rstrip("/"))
            print("PASS: PostgreSQL readiness, base seed, nginx API proxy/SPA fallback, fixture and delivery hold.")
            break
        except (AssertionError, OSError, ValueError):
            if attempt == 19:
                raise
            time.sleep(1)
