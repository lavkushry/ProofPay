import hashlib
import json
from typing import Dict, Any
from backend.app.schemas.api_schemas import CheckProposal, CheckItem

class BriefCompilerService:
    """
    Acceptance Check Compiler implementing prompt compiler-v0.1 from 06-AI_LAYER.md.
    Interprets brief intent and binds strictly to the three allowlisted checks for the supported family.
    """

    @staticmethod
    def compile_brief(family: str, brief_text: str) -> CheckProposal:
        text_lower = brief_text.lower()

        if family == "responsive_css":
            # Check for supported intent or ambiguities
            if "desktop only" in text_lower or "bitcoin" in text_lower:
                return CheckProposal(
                    checks=[],
                    ambiguities=["Unsupported platform or payment requirement in brief."],
                    clarifying_questions=["Please clarify whether checkout needs to support 320px mobile viewport."]
                )
            
            return CheckProposal(
                checks=[
                    CheckItem(
                        check_id="C01",
                        template_type="viewport_no_horizontal_overflow",
                        params={"width": 320, "target_ref": "checkout"},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C02",
                        template_type="cart_total_unchanged",
                        params={"baseline_ref": "fixture_cart_v1"},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C03",
                        template_type="keyboard_checkout_reachable",
                        params={"control_ref": "checkout_pay"},
                        compiled_by="ai",
                        approved=False
                    )
                ],
                ambiguities=[],
                clarifying_questions=[]
            )

        elif family == "api_endpoint":
            return CheckProposal(
                checks=[
                    CheckItem(
                        check_id="C01",
                        template_type="api_status",
                        params={"target_ref": "cart_total", "expected_status": 200},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C02",
                        template_type="api_schema",
                        params={"target_ref": "cart_total", "schema": "cart_total_response_v1"},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C03",
                        template_type="api_total_matches_fixture",
                        params={"target_ref": "cart_total", "baseline_ref": "fixture_cart_v1"},
                        compiled_by="ai",
                        approved=False
                    )
                ],
                ambiguities=[],
                clarifying_questions=[]
            )

        elif family == "keyboard_accessibility":
            return CheckProposal(
                checks=[
                    CheckItem(
                        check_id="C01",
                        template_type="keyboard_checkout_reachable",
                        params={"control_ref": "checkout_pay"},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C02",
                        template_type="keyboard_activation",
                        params={"control_ref": "checkout_pay", "key": "Enter"},
                        compiled_by="ai",
                        approved=False
                    ),
                    CheckItem(
                        check_id="C03",
                        template_type="accessible_control_name",
                        params={"control_ref": "checkout_pay", "name": "checkout_pay_name_v1"},
                        compiled_by="ai",
                        approved=False
                    )
                ],
                ambiguities=[],
                clarifying_questions=[]
            )

        return CheckProposal(
            checks=[],
            ambiguities=[f"Unsupported brief family '{family}'. Must be one of responsive_css, api_endpoint, keyboard_accessibility."],
            clarifying_questions=["Please select one of the three supported brief families."]
        )

    @staticmethod
    def calculate_digest(data: Dict[str, Any]) -> str:
        canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
