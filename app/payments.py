import os
import base64
import requests

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# WATA API settings from environment
API_BASE_URL = os.getenv("WATA_API_BASE_URL", "https://api.wata.pro/api/h2h")
ACCESS_TOKEN = os.getenv("WATA_ACCESS_TOKEN")
CURRENCY = os.getenv("WATA_CURRENCY", "RUB")

# Load and cache public key for webhook signature verification
def _load_public_key():
    """
    Загружает публичный ключ от WATA для проверки подписи уведомлений.
    Возвращает объект публичного ключа.
    """
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    resp = requests.get(f"{API_BASE_URL}/public-key", headers=headers)
    resp.raise_for_status()
    pem = resp.json().get("value")
    return serialization.load_pem_public_key(pem.encode())

_public_key = _load_public_key()


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """
    Проверяет подпись уведомления WATA по RSA SHA512.
    :param raw_body: байты тела запроса
    :param signature: подпись из заголовка X-Signature (base64)
    :return: True, если подпись валидна
    """
    try:
        sig_bytes = base64.b64decode(signature)
        _public_key.verify(
            sig_bytes,
            raw_body,
            padding.PKCS1v15(),
            hashes.SHA512()
        )
        return True
    except Exception:
        return False


def create_invoice(user_id: int, amount: float, plan: str, base_url: str) -> dict:
    """
    Создает платёжную ссылку в WATA.
    :param user_id: Telegram user id
    :param amount: сумма к оплате
    :param plan: описание плана (например, "Месяц")
    :param base_url: URL приложения для редиректов
    :return: JSON-ответ от WATA API с ключём 'url'
    """
    payload = {
        "amount": float(amount),
        "currency": CURRENCY,
        "description": f"{plan} подписка для user {user_id}",
        "orderId": str(user_id),
        "successRedirectUrl": f"{base_url}/success?user_id={user_id}&plan={plan}",
        "failRedirectUrl": f"{base_url}/fail?user_id={user_id}&plan={plan}"
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    resp = requests.post(f"{API_BASE_URL}/links", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()
