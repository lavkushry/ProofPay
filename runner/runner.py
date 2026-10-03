"""Credential-scoped polling; execution receives no API or financial keys."""

import asyncio
import json
import os
import signal
import socket

import httpx

from runner.contracts import RunnerViolation, origin
from runner.execution import execute


class LeaseLost(Exception):
    pass


async def heartbeat(client, job):
    while True:
        await asyncio.sleep(10)
        response = await client.post(f"/internal/runner/jobs/{job['job_id']}/heartbeat", json={"lease_token": job["lease_token"]})
        if response.status_code!=204:
            raise LeaseLost()


async def process(client, job, fixture_url):
    async def work():
        body = await execute(job, fixture_url)
        # Lost HTTP acknowledgements replay exact completion bytes and run identity.
        for attempt in range(3):
            try:
                response = await client.post(f"/internal/runner/jobs/{job['job_id']}/complete", json=body)
                if response.status_code==200:
                    return response.json()
                if response.status_code in {401, 403, 409, 422}:
                    raise LeaseLost()
            except httpx.HTTPError:
                pass
            await asyncio.sleep(min(2**attempt, 4))
        raise LeaseLost()
    task = asyncio.create_task(work())
    pulse = asyncio.create_task(heartbeat(client, job))
    try:
        done, _ = await asyncio.wait({task, pulse}, return_when=asyncio.FIRST_COMPLETED)
        if pulse in done:
            await pulse
        return await task
    finally:
        task.cancel()
        pulse.cancel()
        await asyncio.gather(task, pulse, return_exceptions=True)


async def main():
    token = os.environ.get("RUNNER_SERVICE_TOKEN", "")
    if len(token.encode())<32:
        raise SystemExit("Configure a distinct runner service credential of at least 32 bytes.")
    api_url = origin(os.environ.get("API_URL", "http://api:8000"))
    fixture_url = origin(os.environ.get("FIXTURE_URL", "http://fixture:8080"))
    worker_id = os.environ.get("RUNNER_WORKER_ID", socket.gethostname())
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stopping.set)
    async with httpx.AsyncClient(base_url=api_url, headers={"Authorization": f"Bearer {token}"},
        timeout=10, follow_redirects=False, trust_env=False) as client:
        while not stopping.is_set():
            try:
                response = await client.post("/internal/runner/jobs/claim", json={"worker_id": worker_id})
                if response.status_code==200:
                    job = response.json()
                    completed = await process(client, job, fixture_url)
                    print(json.dumps({"event": "verification_recorded", "job_id": job["job_id"], "state": completed["state"]}), flush=True)
                    continue
                if response.status_code in {401, 403}:
                    raise SystemExit("Runner service authentication was rejected.")
            except (httpx.HTTPError, LeaseLost, RunnerViolation, ValueError):
                print('{"event":"runner_retry_or_hold"}', flush=True)
            try:
                await asyncio.wait_for(stopping.wait(), timeout=2)
            except TimeoutError:
                pass


if __name__=="__main__":
    asyncio.run(main())
