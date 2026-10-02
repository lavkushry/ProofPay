from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ProofPay Checkout Fixture")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BROKEN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Checkout - Store Fixture (Broken)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 16px; background: #f9fafb; }
    /* The Bug: fixed width 480px causes horizontal scrollbar on 320px mobile viewport */
    .checkout-container { width: 480px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    h1 { font-size: 20px; color: #111827; }
    .cart-summary { margin: 16px 0; border-top: 1px solid #e5e7eb; padding-top: 12px; }
    .item-row { display: flex; justify-content: space-between; margin-bottom: 8px; }
    .total-row { display: flex; justify-content: space-between; font-weight: bold; margin-top: 12px; border-top: 2px solid #111827; padding-top: 8px; }
    .pay-btn { display: block; width: 100%; padding: 12px; background: #0070ba; color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
    .pay-btn:focus { outline: 3px solid #2563eb; }
  </style>
</head>
<body>
  <div class="checkout-container" id="checkout">
    <h1>Order Checkout (v1.0.1 - Broken)</h1>
    <div class="cart-summary">
      <div class="item-row"><span>Design System Audit</span><span>$42.00</span></div>
      <div class="total-row"><span>Total</span><span>$42.00</span></div>
    </div>
    <button id="checkout_pay" class="pay-btn" aria-label="Pay now" tabindex="0">Pay now</button>
  </div>
</body>
</html>
"""

FIXED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Checkout - Store Fixture (Corrected)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 16px; background: #f9fafb; box-sizing: border-box; }
    *, *:before, *:after { box-sizing: inherit; }
    /* Fixed: fluid max-width ensures 0px horizontal overflow on 320px viewport */
    .checkout-container { width: 100%; max-width: 480px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    h1 { font-size: 20px; color: #111827; }
    .cart-summary { margin: 16px 0; border-top: 1px solid #e5e7eb; padding-top: 12px; }
    .item-row { display: flex; justify-content: space-between; margin-bottom: 8px; }
    .total-row { display: flex; justify-content: space-between; font-weight: bold; margin-top: 12px; border-top: 2px solid #111827; padding-top: 8px; }
    .pay-btn { display: block; width: 100%; padding: 12px; background: #0070ba; color: white; border: none; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
    .pay-btn:focus { outline: 3px solid #2563eb; }
  </style>
</head>
<body>
  <div class="checkout-container" id="checkout">
    <h1>Order Checkout (v1.0.2 - Fixed)</h1>
    <div class="cart-summary">
      <div class="item-row"><span>Design System Audit</span><span>$42.00</span></div>
      <div class="total-row"><span>Total</span><span>$42.00</span></div>
    </div>
    <button id="checkout_pay" class="pay-btn" aria-label="Pay now" tabindex="0">Pay now</button>
  </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return "<h1>ProofPay Fixture Service</h1><p><a href='/checkout-broken'>Broken Checkout</a> | <a href='/checkout-fixed'>Fixed Checkout</a></p>"

@app.get("/checkout-broken", response_class=HTMLResponse)
async def checkout_broken():
    return BROKEN_HTML

@app.get("/checkout-fixed", response_class=HTMLResponse)
async def checkout_fixed():
    return FIXED_HTML

@app.get("/api/cart-total")
async def cart_total():
    return {
        "status": 200,
        "schema": "cart_total_response_v1",
        "total_cents": 4200,
        "currency": "USD"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fixture.app:app", host="0.0.0.0", port=8080)
