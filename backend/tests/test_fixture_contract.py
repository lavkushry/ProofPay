from fastapi.testclient import TestClient

from fixture.app import app
from fixture_contract.registry import load_contract


def test_reviewed_fixture_manifest_and_versioned_routes():
    contract = load_contract()
    client = TestClient(app)
    manifest = client.get("/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["digest"] == contract.digest
    for artifact in contract.artifacts:
        source = client.get(f"/versions/{artifact.artifact_ref}/source")
        assert source.status_code == 200
        assert source.headers["x-artifact-digest"] == artifact.digest
    assert client.get("/versions/checkout_mobile_broken/checkout").status_code == 200
    assert client.get("/versions/checkout_api_broken/api/cart-total").status_code == 500
    assert client.get("/versions/checkout_api_fixed/api/cart-total").json() == {
        "status": 200, "schema": "cart_total_response_v1", "total_cents": 4200, "currency": "USD"
    }
    assert client.get("/versions/checkout_mobile_fixed/api/cart-total").status_code == 404
