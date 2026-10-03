"""One reviewed fixture application, with immutable broken/corrected artifact paths."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from fixture_contract.registry import artifact_bytes, decode_json, load_contract

app = FastAPI(title="ProofPay Checkout Fixture")
contract = load_contract()


def resolve(reference):
    artifact = contract.artifact(reference)
    if artifact is None:
        raise HTTPException(404, "Unknown fixture version")
    return artifact


@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>ProofPay Fixture Service</h1><p>Reviewed checkout artifacts for three acceptance families.</p>"


@app.get("/manifest")
async def manifest():
    return {"digest": contract.digest, "manifest": contract.model_dump(mode="json")}


@app.get("/versions/{artifact_ref}/source")
async def source(artifact_ref: str):
    artifact = resolve(artifact_ref)
    media = "application/json" if artifact.family == "api_endpoint" else "text/html"
    return Response(artifact_bytes(contract, artifact_ref), media_type=media,
                    headers={"X-Artifact-Digest": artifact.digest})


@app.get("/versions/{artifact_ref}/checkout", response_class=HTMLResponse)
async def versioned_checkout(artifact_ref: str):
    artifact = resolve(artifact_ref)
    if artifact.family == "api_endpoint":
        raise HTTPException(404, "Checkout HTML is not available for this artifact family")
    return Response(artifact_bytes(contract, artifact_ref), media_type="text/html",
                    headers={"X-Artifact-Digest": artifact.digest})


@app.get("/versions/{artifact_ref}/api/cart-total")
async def versioned_cart_total(artifact_ref: str):
    artifact = resolve(artifact_ref)
    if artifact.family != "api_endpoint":
        raise HTTPException(404, "API response is not available for this artifact family")
    response = decode_json(artifact_bytes(contract, artifact_ref))
    return JSONResponse(response["body"], status_code=response["status_code"],
                        headers={"X-Artifact-Digest": artifact.digest})


@app.get("/checkout-broken", response_class=HTMLResponse)
async def checkout_broken():
    return Response(artifact_bytes(contract, "checkout_mobile_broken"), media_type="text/html")


@app.get("/checkout-fixed", response_class=HTMLResponse)
async def checkout_fixed():
    return Response(artifact_bytes(contract, "checkout_mobile_fixed"), media_type="text/html")


@app.get("/api/cart-total")
async def cart_total():
    return decode_json(artifact_bytes(contract, "checkout_api_fixed"))["body"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fixture.app:app", host="0.0.0.0", port=8080)
