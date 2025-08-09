# app/payments.py
import os
import requests

WATA_BASE_URL = os.getenv("WATA_BASE_URL", "https://api-sandbox.wata.pro/api/h2h").rstrip("/")
WATA_TOKEN    = os.getenv("WATA_TOKEN")
APP_BASE_URL  = os.getenv("APP_BASE_URL", "").rstrip("/")
MODE          = os.getenv("PAYMENTS_MODE", "real")  # 'real' | 'mock'

def create_invoice(user_id: int, amount: float, plan: str,
                   success_url: str | None = None,
                   fail_url: str | None = None,
                   order_id: str | None = None) -> dict:
    # MOCK: без токена или явно включен mock — отдаём тестовую ссылку
    if MODE == "mock" or not WATA_TOKEN:
        if not APP_BASE_URL:
            raise RuntimeError("APP_BASE_URL is required in mock mode")
        link = f"{APP_BASE_URL}/testpay?user_id={user_id}&plan={plan}&amount={amount:.2f}&orderId={order_id or user_id}"
        return {"id": "mock", "url": link, "status": "Opened"}

    # REAL: sandbox/prod WATA
    url = f"{WATA_BASE_URL}/links"
    payload = {
        "amount": float(f"{amount:.2f}"),
        "currency": "RUB",
        "description": f"{plan} user {user_id}",
        "orderId": str(order_id or user_id),
    }
    if success_url: payload["successRedirectUrl"] = success_url
    if fail_url:    payload["failRedirectUrl"]    = fail_url

    headers = {
        "Authorization": f"Bearer {WATA_TOKEN}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code >= 400:
        try: detail = resp.json()
        except Exception: detail = resp.text
        raise requests.HTTPError(f"{resp.status_code} {resp.reason} at {url} -> {detail}", response=resp)
    return resp.json()
