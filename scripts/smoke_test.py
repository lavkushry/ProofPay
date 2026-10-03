"""Exercise Compose readiness, session authority, proxying and workflow holds."""

import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
import uuid


def request(url, body=None, *, method=None, headers=None, opener=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = (opener or urllib.request.build_opener()).open(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.read()


def run(web_url, fixture_url):
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path, body=None, **kwargs):
        return request(web_url + path, body, opener=opener, **kwargs)
    status, body = call("/readyz")
    assert status == 200 and json.loads(body)["database"] == "connected"
    assert call("/api/v1/tasks")[0] == 401
    status, body = call("/api/session", {"access_code": os.environ.get("DEMO_JUDGE_ACCESS_CODE", "local-judge-access"), "persona": "owner"})
    assert status == 201
    session = json.loads(body)
    assert session["role"] == "owner" and session["is_judge"]
    status, body = call("/api/v1/tasks")
    assert status == 200 and isinstance(json.loads(body), list)
    assert call("/contractor/tasks")[0] == 200
    for version in ("broken", "fixed"):
        status, body = request(f"{fixture_url}/checkout-{version}")
        assert status == 200 and b"checkout_pay" in body
    status, body = call("/api/v1/deliveries/submit", {
        "task_id": str(uuid.uuid4()), "artifact_ref": "checkout_mobile_fixed", "claim": "Fixed",
    }, headers={"X-CSRF-Token": session["csrf_token"], "Idempotency-Key": str(uuid.uuid4())})
    assert status == 503 and json.loads(body)["code"] == "WORKFLOW_UNAVAILABLE"
    status, body = call("/api/judge/role", {"persona": "contractor_leo"}, headers={"X-CSRF-Token": session["csrf_token"]})
    assert status == 200
    rotated = json.loads(body)
    assert rotated["role"] == "contractor" and rotated["principal_id"] == session["principal_id"]
    assert call("/api/v1/catalog/recipients")[0] == 403
    assert call("/api/session", method="DELETE", headers={"X-CSRF-Token": rotated["csrf_token"]})[0] == 204
    assert call("/api/v1/tasks")[0] == 401


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-url", default="http://localhost:3000")
    parser.add_argument("--fixture-url", default="http://localhost:8080")
    args = parser.parse_args()
    for attempt in range(20):
        try:
            run(args.web_url.rstrip("/"), args.fixture_url.rstrip("/"))
            print("PASS: readiness, session/CSRF/persona/logout, API proxy, fixtures and workflow hold.")
            break
        except (AssertionError, OSError, ValueError):
            if attempt == 19:
                raise
            time.sleep(1)
