# app/payments.py
import os
import time
import base64
import requests
from typing import Optional

WATA_BASE_URL = os.getenv("WATA_BASE_URL", "https://api-sandbox.wata.pro/api/h2h").rstrip("/")
WATA_TOKEN    = os.getenv("WATA_TOKEN")
APP_BASE_URL  = os.getenv("APP_BASE_URL", os.getenv("BASE_URL", "")).rstrip("/")
MODE          = os.getenv("PAYMENTS_MODE", "real").lower()  # 'real' | 'mock'

PUBLIC_KEY_URL = os.getenv("WATA_PUBLIC_KEY_URL", f"{WATA_BASE_URL}/public-key")

# ── Public key cache ──────────────────────────────────────────────────────────
_PUBKEY_CACHE = {"pem": None, "ts": 0.0}
_PUBKEY_TTL   = 600.0  # 10 минут


def _fetch_public_key_pem() -> str:
    now = time.time()
    if _PUBKEY_CACHE["pem"] and (now - _PUBKEY_CACHE["ts"] < _PUBKEY_TTL):
        return _PUBKEY_CACHE["pem"]

    resp = requests.get(PUBLIC_KEY_URL, headers={"Content-Type": "application/json"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    pem = data.get("value") or ""
    if not pem.startswith("-----BEGIN PUBLIC KEY-----"):
        raise ValueError("Invalid public key PEM from WATA")
    _PUBKEY_CACHE["pem"] = pem
    _PUBKEY_CACHE["ts"] = now
    return pem


def verify_signature(raw_body: bytes, signature_b64: str) -> bool:
    """
    Проверка X-Signature (RSA+SHA512) входящего webhook’а WATA.
    В mock-режиме всегда True.
    """
    if MODE == "mock":
        return True

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pem = _fetch_public_key_pem()
        public_key = serialization.load_pem_public_key(pem.encode("utf-8"))
        signature  = base64.b64decode(signature_b64)

        public_key.verify(
            signature,
            raw_body,
            padding.PKCS1v15(),
            hashes.SHA512(),
        )
        return True
    except Exception:
        return False


def create_invoice(
    user_id: int,
    amount: float,
    plan: str,
    success_url: Optional[str] = None,
    fail_url: Optional[str] = None,
    order_id: Optional[str] = None
) -> dict:
    """
    Создание платёжной ссылки через WATA.
    В mock-режиме возвращает ссылку на вашу заглушку /testpay.
    """
    # MOCK: без токена или явно включен mock → своя тестовая ссылка
    if MODE == "mock" or not WATA_TOKEN:
        if not APP_BASE_URL:
            raise RuntimeError("APP_BASE_URL or BASE_URL is required in mock mode")
        link = (
            f"{APP_BASE_URL}/testpay"
            f"?user_id={user_id}&plan={plan}&amount={amount:.2f}&orderId={order_id or user_id}"
        )
        return {"id": "mock", "url": link, "status": "Opened"}

    # REAL: sandbox/prod WATA
    url = f"{WATA_BASE_URL}/links"
    payload = {
        "amount": float(f"{amount:.2f}"),
        "currency": "RUB",
        "description": f"{plan} user {user_id}",
        "orderId": str(order_id or user_id),
    }
    if success_url:
        payload["successRedirectUrl"] = success_url
    if fail_url:
        payload["failRedirectUrl"] = fail_url

    headers = {
        "Authorization": f"Bearer {WATA_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise requests.HTTPError(f"{resp.status_code} {resp.reason} at {url} -> {detail}", response=resp)

    return resp.json()
