"""Ödeme sağlayıcıları (Hafta 9).

GÜVENLİK NOTLARI
- Kart numarası ve CVC veri tabanına, log dosyasına veya oturuma ASLA yazılmaz.
  Yalnızca son 4 hane saklanır. CardDetails nesnesinin __repr__ metodu bile maskelidir.
- Gerçek projelerde kart bilgisi sunucumuza hiç gelmez: sağlayıcının ödeme sayfası veya
  JavaScript bileşeni kartı "token"a çevirir (PCI DSS uyumu). Bu ders projesinde yalnızca
  TEST kartları kullanıldığı için form sunucumuza geliyor.
- Idempotency anahtarı: Aynı anahtarla gelen ikinci istek kartı tekrar çekmez,
  ilk sonucun aynısını döndürür. Zaman aşımında "çekildi mi, çekilmedi mi?"
  bilinmediğinden, aynı anahtarla tekrar denemek çift çekimi önler.
- İstek imzası (HMAC-SHA256): Gövde, gizli anahtarla imzalanır; yolda değiştirilirse
  sağlayıcı imzayı doğrulayamaz ve reddeder.
"""
import hashlib
import hmac
import json
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from flask import current_app

from app.integrations.errors import ConfigurationError, ExternalServiceError, ExternalTimeout
from app.integrations.http_client import ApiClient


@dataclass(frozen=True)
class CardDetails:
    holder: str
    number: str = field(repr=False)
    exp_month: int = field(repr=False)
    exp_year: int = field(repr=False)
    cvc: str = field(repr=False)

    @property
    def last4(self):
        return self.number[-4:]

    def __repr__(self):
        return f"CardDetails(holder={self.holder!r}, number=**** **** **** {self.last4})"


@dataclass(frozen=True)
class ChargeResult:
    success: bool
    transaction_ref: "str | None" = None
    error_code: "str | None" = None
    message: str = ""


@dataclass(frozen=True)
class RefundResult:
    success: bool
    refund_ref: "str | None" = None
    message: str = ""


# Sağlayıcı hata kodlarının kullanıcıya gösterilecek Türkçe karşılıkları
ERROR_MESSAGES = {
    "card_declined": "Kartınız bankanız tarafından reddedildi.",
    "insufficient_funds": "Kartınızın limiti yetersiz.",
    "expired_card": "Kartınızın son kullanma tarihi geçmiş.",
    "incorrect_cvc": "Güvenlik kodu (CVC) hatalı.",
    "card_not_supported": "Bu kart test ortamında desteklenmiyor. Sayfadaki test kartlarından birini kullanın.",
}


def error_message(code):
    return ERROR_MESSAGES.get(code, "Ödeme tamamlanamadı. Lütfen tekrar deneyin.")


class PaymentGateway(ABC):
    name = "unknown"

    @abstractmethod
    def charge(self, amount, currency, card, idempotency_key, description=""):
        """Karttan tahsilat yapar ve ChargeResult döndürür; ağ sorunlarında IntegrationError fırlatır."""

    @abstractmethod
    def refund(self, transaction_ref, amount, idempotency_key):
        """Tahsilatı iade eder ve RefundResult döndürür."""


# --- 1) Sahte (test) sağlayıcı ---------------------------------------------------------------

class MockPaymentGateway(PaymentGateway):
    """İnternete çıkmayan test sağlayıcısı. Sonucu kart numarası belirler (gerçek sandbox'lardaki gibi)."""

    name = "mock"

    TEST_CARDS = {
        "4111111111111111": ("success", "Başarılı ödeme"),
        "5555555555554444": ("success", "Başarılı ödeme (Mastercard)"),
        "4000000000000002": ("card_declined", "Kart reddedilir"),
        "4000000000009995": ("insufficient_funds", "Yetersiz bakiye"),
        "4000000000000119": ("timeout", "Ödeme alınır ama yanıt gelmez (zaman aşımı benzetimi)"),
    }

    def __init__(self):
        self._charges = {}        # idempotency_key -> ChargeResult
        self._transactions = {}   # transaction_ref -> tutar
        self._refunds = {}        # idempotency_key -> RefundResult
        self._lock = threading.Lock()
        self.charge_calls = 0     # testlerde kaç gerçek çekim yapıldığını görmek için

    def charge(self, amount, currency, card, idempotency_key, description=""):
        with self._lock:
            if idempotency_key in self._charges:      # Aynı istek tekrar geldi: kartı tekrar ÇEKME
                return self._charges[idempotency_key]

            behaviour = self.TEST_CARDS.get(card.number, ("card_not_supported", ""))[0]
            if behaviour in ("success", "timeout"):
                self.charge_calls += 1
                ref = f"mock_tx_{uuid.uuid4().hex[:16]}"
                self._transactions[ref] = Decimal(amount)
                result = ChargeResult(True, transaction_ref=ref, message="Ödeme onaylandı.")
            else:
                result = ChargeResult(False, error_code=behaviour, message=error_message(behaviour))
            self._charges[idempotency_key] = result

        if behaviour == "timeout":
            # Para çekildi ama yanıt "yolda kayboldu": istemci sonucu bilmiyor
            raise ExternalTimeout("Ödeme sağlayıcısı zamanında yanıt vermedi.", service=self.name)
        return result

    def refund(self, transaction_ref, amount, idempotency_key):
        with self._lock:
            if idempotency_key in self._refunds:
                return self._refunds[idempotency_key]
            # Sunucu yeniden başlayınca bellek sıfırlanır; gerçek bir sağlayıcı işlemleri kalıcı tuttuğu
            # için "mock_tx_" ile başlayan her işlemi bilinen işlem sayıyoruz.
            if transaction_ref not in self._transactions and not str(transaction_ref).startswith("mock_tx_"):
                result = RefundResult(False, message="İşlem bulunamadı.")
            else:
                result = RefundResult(True, refund_ref=f"mock_rf_{uuid.uuid4().hex[:16]}", message="İade edildi.")
            self._refunds[idempotency_key] = result
            return result


# --- 2) Gerçek / sandbox HTTP sağlayıcı (adaptör) ---------------------------------------------

class HttpPaymentGateway(PaymentGateway):
    """Genel REST ödeme API'si adaptörü.

    POST {PAYMENT_API_URL}/charges   -> {"id": "...", "status": "succeeded" | "failed", "error": {"code": "..."}}
    POST {PAYMENT_API_URL}/refunds   -> {"id": "...", "status": "succeeded" | "failed"}
    Gerçek sağlayıcıların (iyzico, PayTR, Stripe...) alan adları farklıdır; bu sınıf onlara göre uyarlanır.
    """

    name = "http"

    def __init__(self, client, secret_key):
        self.client = client
        self._secret = (secret_key or "").encode()

    def _signed_post(self, path, payload, idempotency_key):
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()
        return self.client.request("POST", path, data=body, headers={
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "X-Signature": signature,
        })

    def charge(self, amount, currency, card, idempotency_key, description=""):
        response = self._signed_post("/charges", {
            "amount": str(Decimal(amount).quantize(Decimal("0.01"))),
            "currency": currency,
            "description": description,
            "card": {"holder": card.holder, "number": card.number, "exp_month": card.exp_month,
                     "exp_year": card.exp_year, "cvc": card.cvc},
        }, idempotency_key)

        status = response.get("status")
        if status == "succeeded" and response.get("id"):
            return ChargeResult(True, transaction_ref=str(response["id"]), message="Ödeme onaylandı.")
        if status == "failed":
            code = (response.get("error") or {}).get("code", "card_declined")
            return ChargeResult(False, error_code=code, message=error_message(code))
        raise ExternalServiceError("Ödeme sağlayıcısı anlaşılmayan bir yanıt verdi.", service=self.name)

    def refund(self, transaction_ref, amount, idempotency_key):
        response = self._signed_post("/refunds", {
            "charge_id": transaction_ref, "amount": str(Decimal(amount).quantize(Decimal("0.01"))),
        }, idempotency_key)
        if response.get("status") == "succeeded":
            return RefundResult(True, refund_ref=str(response.get("id")), message="İade edildi.")
        return RefundResult(False, message="İade reddedildi.")


# --- Seçici -------------------------------------------------------------------------------------

def get_payment_gateway():
    cached = current_app.extensions.get("payment_gateway")
    if cached is not None:
        return cached

    config = current_app.config
    if config["USE_MOCK_APIS"]:
        gateway = MockPaymentGateway()
    else:
        if not (config["PAYMENT_API_URL"] and config["PAYMENT_API_KEY"] and config["PAYMENT_SECRET_KEY"]):
            raise ConfigurationError("Ödeme API adresi veya anahtarları tanımlı değil (.env).", service="payment")
        client = ApiClient(config["PAYMENT_API_URL"], config["PAYMENT_API_KEY"], name="payment",
                           timeout=config["PAYMENT_API_TIMEOUT"],
                           max_retries=1)  # Idempotency anahtarı olduğu için tekrar denemek güvenli
        gateway = HttpPaymentGateway(client, config["PAYMENT_SECRET_KEY"])

    current_app.extensions["payment_gateway"] = gateway
    return gateway
