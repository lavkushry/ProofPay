"""Trusted measurement semantics shared by execution and evidence ingestion."""

ERROR_CODES = {"CHECK_TIMEOUT", "CHECK_UNAVAILABLE", "RUN_TIMEOUT", "ARTIFACT_MISMATCH", "RUNNER_ERROR"}


class ObservationError(ValueError):
    pass


def api_schema_valid(body):
    return (isinstance(body, dict) and set(body)=={"status", "schema", "total_cents", "currency"}
            and type(body["status"]) is int and body["status"]==200
            and body["schema"]=="cart_total_response_v1" and type(body["total_cents"]) is int
            and 0 <= body["total_cents"] <= 100000000 and body["currency"]=="USD")


def measured_outcome(template, measurement, facts):
    """Missing or contradictory measurements cannot be labeled as passing."""
    if not isinstance(measurement, dict):
        raise ObservationError("Measurement must be an object")
    if set(measurement)=={"error_code"}:
        if measurement["error_code"] not in ERROR_CODES:
            raise ObservationError("Unknown execution error")
        return "error"
    shapes = {
        "viewport_no_horizontal_overflow": {"viewport_width": int, "scroll_width": int, "overflow_px": int},
        "cart_total_unchanged": {"total_cents": int, "currency": str, "baseline_total_cents": int},
        "keyboard_checkout_reachable": {"control_ref": str, "reached": bool, "tabs": int, "focused_id": str},
        "keyboard_activation": {"control_ref": str, "key": str, "reached": bool, "activated": bool},
        "accessible_control_name": {"control_ref": str, "expected_name": str, "name_matches": bool, "aria_snapshot": str},
        "api_status": {"status_code": int, "expected_status": int},
        "api_schema": {"status_code": int, "schema_ref": str, "response": (dict, type(None))},
        "api_total_matches_fixture": {"status_code": int, "baseline_total_cents": int, "response": (dict, type(None))},
    }
    shape = shapes.get(template)
    if shape is None or set(measurement) != set(shape):
        raise ObservationError("Unknown template or measurement fields")
    if any(type(measurement[k]) not in (t if isinstance(t, tuple) else (t,)) for k, t in shape.items()):
        raise ObservationError("Measurement types are invalid")
    m = measurement
    if "control_ref" in m and m["control_ref"] != facts.control_ref:
        raise ObservationError("Control does not match the trusted fixture")
    if "status_code" in m and not 100 <= m["status_code"] <= 599:
        raise ObservationError("HTTP status is invalid")
    if "baseline_total_cents" in m and m["baseline_total_cents"] != facts.total_cents:
        raise ObservationError("Baseline does not match trusted facts")
    if template=="viewport_no_horizontal_overflow":
        if m["viewport_width"] != facts.supported_widths[0] or m["scroll_width"] < 0 or m["overflow_px"] != max(0, m["scroll_width"]-m["viewport_width"]):
            raise ObservationError("Viewport observation is inconsistent")
        passed = m["overflow_px"]==0
    elif template=="cart_total_unchanged":
        if m["total_cents"] < 0:
            raise ObservationError("Cart amount is invalid")
        passed = m["total_cents"]==facts.total_cents and m["currency"]==facts.currency
    elif template=="keyboard_checkout_reachable":
        if not 1 <= m["tabs"] <= 20 or m["reached"] != (m["focused_id"]==facts.control_dom_id):
            raise ObservationError("Keyboard reachability is inconsistent")
        passed = m["reached"]
    elif template=="keyboard_activation":
        if m["key"]!="Enter" or (m["activated"] and not m["reached"]):
            raise ObservationError("Keyboard activation is inconsistent")
        passed = m["reached"] and m["activated"]
    elif template=="accessible_control_name":
        if m["expected_name"]!=facts.accessible_name or len(m["aria_snapshot"]) > 2000:
            raise ObservationError("Accessible-name observation is invalid")
        passed = m["name_matches"]
    elif template=="api_status":
        if m["expected_status"]!=200:
            raise ObservationError("Expected status is not trusted")
        passed = m["status_code"]==200
    elif template=="api_schema":
        if m["schema_ref"]!=facts.schema_ref:
            raise ObservationError("Schema reference is not trusted")
        passed = m["status_code"]==200 and api_schema_valid(m["response"])
    else:
        body = m["response"]
        passed = (m["status_code"]==200 and api_schema_valid(body)
                  and body["total_cents"]==facts.total_cents and body["currency"]==facts.currency)
    return "pass" if passed else "fail"


def provenance(job, check):
    return {**{k: job[k] for k in ("task_id", "delivery_id", "mandate_version_id", "mandate_digest",
             "artifact_version_id", "artifact_digest")}, "run_id": job["job_id"],
            "check_id": check["check_id"], "template_type": check["template_type"]}
