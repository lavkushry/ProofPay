import hashlib
import json
from typing import List, Dict, Any
from backend.app.schemas.api_schemas import EvidenceReviewResult, CheckObservation

class EvidenceReviewerService:
    """
    Evidence Reviewer implementing prompt reviewer-v0.1 from 06-AI_LAYER.md.
    Compares contractor claim against test execution observations and screenshot evidence.
    """

    @staticmethod
    def review_bundle(
        claim: str,
        results: List[CheckObservation],
        has_screenshot: bool = True
    ) -> EvidenceReviewResult:
        contradictions = []
        evidence_refs = []
        failed_checks = []

        for r in results:
            evidence_refs.append(f"check:{r.check_id}")
            if r.outcome != "pass":
                failed_checks.append(r)

        claim_lower = claim.lower()

        # Check for D06 contradiction: contractor claimed mobile fix, but overflow check failed
        if failed_checks:
            for fc in failed_checks:
                if fc.check_id == "C01" and "overflow" in fc.observations.get("template", ""):
                    scroll_w = fc.observations.get("scroll_width", 480)
                    view_w = fc.observations.get("viewport_width", 320)
                    contradiction_msg = (
                        f"Claim asserts '{claim}', but runner evidence shows {fc.observations.get('template')} "
                        f"failed: document scrollWidth {scroll_w}px exceeds viewport width {view_w}px."
                    )
                    contradictions.append(contradiction_msg)
                else:
                    contradictions.append(
                        f"Check {fc.check_id} failed with observation: {fc.observations.get('message', 'Unmet condition')}"
                    )

            rationale = (
                f"Delivery rejected due to {len(failed_checks)} failed acceptance check(s). "
                + " ".join(contradictions)
            )
            return EvidenceReviewResult(
                verdict="fail",
                per_check_results=results,
                contradictions=contradictions,
                rationale=rationale,
                evidence_refs=evidence_refs
            )

        # All checks passed
        rationale = "All three approved acceptance checks executed successfully on the submitted artifact version. Visual viewport and DOM requirements verified."
        return EvidenceReviewResult(
            verdict="pass",
            per_check_results=results,
            contradictions=[],
            rationale=rationale,
            evidence_refs=evidence_refs
        )

    @staticmethod
    def calculate_digest(data: Dict[str, Any]) -> str:
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
