from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from backend.app.services.auth import require_owner

router = APIRouter(prefix="/api/v1/catalog", tags=["Catalog"])

@router.get("/families")
async def list_supported_families() -> List[Dict[str, Any]]:
    return [
        {
            "family": "responsive_css",
            "name": "Responsive CSS & Mobile Layout",
            "description": "Ensure checkout fits a 320px viewport without horizontal overflow while keeping cart total and keyboard navigation working.",
            "target_fixture": "checkout_fixture",
            "templates": ["viewport_no_horizontal_overflow", "cart_total_unchanged", "keyboard_checkout_reachable"]
        },
        {
            "family": "api_endpoint",
            "name": "API Endpoint Repair",
            "description": "Verify cart-total endpoint returns HTTP 200, valid schema, and exact calculated total.",
            "target_fixture": "checkout_fixture",
            "templates": ["api_status", "api_schema", "api_total_matches_fixture"]
        },
        {
            "family": "keyboard_accessibility",
            "name": "Keyboard Accessibility",
            "description": "Ensure payment button can be reached via Tab, activated via Enter, and has an accessible name.",
            "target_fixture": "checkout_fixture",
            "templates": ["keyboard_checkout_reachable", "keyboard_activation", "accessible_control_name"]
        }
    ]

@router.get("/recipients", dependencies=[Depends(require_owner)])
async def list_contractors() -> List[Dict[str, Any]]:
    return [
        {
            "recipient_ref": "contractor_maya",
            "display_name": "Maya Lin (Frontend Specialist)",
            "currency": "USD"
        },
        {
            "recipient_ref": "contractor_leo",
            "display_name": "Leo Vance (Fullstack Contractor)",
            "currency": "USD"
        }
    ]

@router.get("/artifacts")
async def list_artifacts() -> List[Dict[str, Any]]:
    return [
        {
            "artifact_ref": "checkout_mobile_broken",
            "name": "v1.0.1-broken (Fixed width checkout, overflows at 320px)",
            "version": "1.0.1",
            "is_corrected": False
        },
        {
            "artifact_ref": "checkout_mobile_fixed",
            "name": "v1.0.2-corrected (Fluid width checkout, fits 320px cleanly)",
            "version": "1.0.2",
            "is_corrected": True
        }
    ]
