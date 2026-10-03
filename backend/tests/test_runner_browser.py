"""Actual container polling/Chromium/HTTP/PostgreSQL proof; approval uses a model double."""

import hashlib
import json
import os
import socket
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn

from backend.app.config import settings
from backend.app.main import app
from backend.tests.postgres_support import database_factory, graph, pg_engine, postgres_url
from backend.tests.test_workflows import workspace
from backend.tests.test_mandates import approval_workspace
from backend.tests.test_verification import RUNNER_TOKEN, approved_task, submit, verification_workspace
from fixture.app import app as fixture_app

pytestmark = [pytest.mark.postgres, pytest.mark.runner_browser,
              pytest.mark.skipif(os.environ.get("PROOFPAY_RUNNER_BROWSER_TESTS")!="1", reason="Opt in to actual Docker/Chromium proof")]


@contextmanager
def serve(application):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(application, log_level="critical", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+10
    try:
        while not server.started and thread.is_alive() and time.monotonic()<deadline:
            time.sleep(0.02)
        assert server.started, "Actual HTTP service did not start"
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


@pytest.mark.parametrize("family,reference,expected", [
    ("responsive_css", "checkout_mobile_broken", ["fail", "pass", "pass"]),
    ("responsive_css", "checkout_mobile_fixed", ["pass", "pass", "pass"]),
    ("api_endpoint", "checkout_api_broken", ["fail", "fail", "fail"]),
    ("api_endpoint", "checkout_api_fixed", ["pass", "pass", "pass"]),
    ("keyboard_accessibility", "checkout_keyboard_broken", ["fail", "fail", "fail"]),
    ("keyboard_accessibility", "checkout_keyboard_fixed", ["pass", "pass", "pass"]),
])
def test_actual_runner_polls_executes_and_persists(verification_workspace, pg_engine, monkeypatch, family, reference, expected):
    client, _, _, _ = verification_workspace
    with serve(fixture_app) as fixture_url, serve(app) as api_url:
        monkeypatch.setattr(settings, "FIXTURE_URL", fixture_url)
        brief, version, _ = approved_task(verification_workspace, family)
        delivery, _, _ = submit(verification_workspace, pg_engine, brief, version, reference)
        container = "proofpay-runner-proof-"+uuid.uuid4().hex[:12]
        command = ["docker", "run", "--rm", "--name", container, "--network", "host", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "768m", "--cpus", "1", "--pids-limit", "256", "--shm-size", "256m",
            "--tmpfs", "/tmp:size=256m,mode=1777", "--tmpfs", "/home/pwuser/.cache:size=64m,uid=1001,gid=1001",
            "-e", f"API_URL={api_url}", "-e", f"FIXTURE_URL={fixture_url}", "-e", f"RUNNER_SERVICE_TOKEN={RUNNER_TOKEN}",
            "-e", f"RUNNER_WORKER_ID={container}", os.environ.get("PROOFPAY_RUNNER_IMAGE", "proofpay-m3-runner")]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        start = time.monotonic()
        try:
            deadline = start+55
            while time.monotonic()<deadline and process.poll() is None:
                status = client.get(f"/api/jobs/{delivery['verification_job_id']}").json()
                if status["state"] in {"done", "failed", "held"}:
                    break
                time.sleep(0.2)
            else:
                pytest.fail("Runner did not complete the real HTTP job before the acceptance deadline")
            assert status["state"]=="done", status
            public = client.get(f"/api/evidence/{status['result_resource_id']}")
            assert public.status_code==200, public.text
            bundle = public.json()
            assert [r["outcome"] for r in bundle["results"]]==expected
            assert bundle["is_current"] and bundle["run_id"]==delivery["verification_job_id"]
            output = Path("artifacts/verification")
            output.mkdir(parents=True, exist_ok=True)
            for artifact in bundle["artifacts"]:
                data = client.get(artifact["download_path"]).content
                assert hashlib.sha256(data).hexdigest()==artifact["sha256"]
                if artifact["media_type"]=="image/png":
                    (output/f"{reference}-{artifact['check_id']}.png").write_bytes(data)
            (output/f"{reference}.json").write_text(json.dumps({"artifact_ref": reference,
                "approval_model": "explicit-test-double", "runner": "actual-container-http-chromium",
                "elapsed_seconds": round(time.monotonic()-start, 3), "bundle": bundle}, indent=2)+"\n")
            task = client.get(f"/api/tasks/{brief['task_id']}").json()
            assert task["state"]=="verifying" and task["review_required"] and "REVIEW_NOT_IMPLEMENTED" in task["hold_reasons"]
        finally:
            subprocess.run(["docker", "stop", "--time", "3", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=10)
            stdout, stderr = process.communicate(timeout=10)
        assert process.returncode==0, stderr.decode()[-1000:]
        assert b"verification_recorded" in stdout
