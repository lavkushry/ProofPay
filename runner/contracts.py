"""Independent runner validation of server job targets and approved templates."""

import uuid
from urllib.parse import urlsplit

from fixture_contract.registry import canonical_bytes, load_contract


class RunnerViolation(ValueError):
    pass


def origin(value):
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}:
        raise RunnerViolation("Invalid service origin")
    return value.rstrip("/")


def validate_job(job, fixture_origin):
    keys = {"job_id", "lease_token", "lease_until", "task_id", "delivery_id", "mandate_version_id", "mandate_digest",
            "artifact_version_id", "artifact_digest", "fixture_url", "checks"}
    if not isinstance(job, dict) or set(job)!=keys:
        raise RunnerViolation("Invalid job fields")
    for key in ("job_id", "lease_token", "task_id", "delivery_id", "mandate_version_id", "artifact_version_id"):
        uuid.UUID(job[key])
    base = origin(fixture_origin)
    contract = load_contract()
    artifact = next((a for a in contract.artifacts if job["fixture_url"]==base+a.relative_path), None)
    if artifact is None or artifact.digest!=job["artifact_digest"]:
        raise RunnerViolation("Unknown fixture artifact or digest")
    expected = [{"check_id": f"C0{i}", "template_type": t.template_type, "params": t.params,
                 "compiled_by": "ai", "approved": True} for i, t in enumerate(contract.family(artifact.family).templates, 1)]
    if canonical_bytes(job["checks"])!=canonical_bytes(expected):
        raise RunnerViolation("Unknown approved template or parameters")
    return contract, artifact
