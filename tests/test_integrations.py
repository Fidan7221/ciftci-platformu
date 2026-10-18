"""Hafta 9 testleri: harici API katmanı (app/integrations/).

HİÇBİR TEST GERÇEK BİR SUNUCUYA İSTEK ATMAZ. requests oturumu unittest.mock ile
taklit edilir; böylece zaman aşımı, 500, 429 gibi durumlar istenildiği an üretilebilir
ve testler internet olmadan, saniyeler içinde çalışır.

Çalıştırma: pytest -v tests/test_integrations.py
"""
import hashlib
import hmac
import json
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import requests

from app.integrations.errors import (
    ConfigurationError, ExternalServiceError, ExternalTimeout, RateLimitExceeded,
)
from app.integrations.http_client import ApiClient
from app.integrations.payment_gateway import (
    CardDetails, HttpPaymentGateway, MockPaymentGateway, get_payment_gateway,
)
from app.integrations.price_api import HttpPriceProvider, MockPriceProvider, get_price_provider
from app.utils.rate_limit import RateLimiter

SECRET_KEY = "test-gizli-anahtar-123"


def fake_response(status=200, payload=None, headers=None, bad_json=False):
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    if bad_json:
        response.json.side_effect = ValueError("bozuk")
    else:
        response.json.return_value = payload if payload is not None else {}
    return response


def make_client(*results, **kwargs):
    """results: sırayla dönecek yanıtlar veya fırlatılacak hatalar."""
    session = MagicMock()
    session.request.side_effect = list(results)
    sleeps = []
    client = ApiClient("https://api.ornek.com/v1", kwargs.pop("api_key", SECRET_KEY), name="test",
                       session=session, sleep=sleeps.append, **kwargs)
    return client, session, sleeps


def card(number="4111111111111111"):
    return CardDetails(holder="Test Kişi", number=number, exp_month=12, exp_year=2099, cvc="123")


# --- 1. Ortak HTTP istemcisi ---------------------------------------------------------------

def test_successful_json_request_sends_key_in_header_not_url():
    client, session, _ = make_client(fake_response(payload={"ok": True}))
    assert client.get_json("/prices", params={"date": "2026-10-19"}) == {"ok": True}

    _, kwargs = session.request.call_args
    url = session.request.call_args.args[1]
    assert kwargs["headers"]["Authorization"] == f"Bearer {SECRET_KEY}"
    assert SECRET_KEY not in url and SECRET_KEY not in str(kwargs["params"])
    assert kwargs["timeout"] == (3.05, 10.0)  # her istekte zaman aşımı VAR


def test_timeout_is_retried_then_raises_external_timeout():
    client, session, sleeps = make_client(requests.Timeout(), requests.Timeout(), requests.Timeout(),
                                          max_retries=2)
    with pytest.raises(ExternalTimeout):
        client.get_json("/prices")
    assert session.request.call_count == 3       # 1 deneme + 2 tekrar
    assert sleeps == [0.5, 1.0]                  # üstel bekleme: 0.5 s, 1 s


def test_server_error_then_success():
    client, session, sleeps = make_client(fake_response(503), fake_response(payload={"items": []}))
    assert client.get_json("/prices") == {"items": []}
    assert session.request.call_count == 2 and sleeps == [0.5]


def test_connection_error_becomes_external_service_error():
    client, _, _ = make_client(requests.ConnectionError(), max_retries=0)
    with pytest.raises(ExternalServiceError):
        client.get_json("/prices")


def test_client_errors_are_not_retried():
    client, session, _ = make_client(fake_response(401))
    with pytest.raises(ExternalServiceError) as error:
        client.get_json("/prices")
    assert error.value.status_code == 401 and session.request.call_count == 1


def test_429_raises_rate_limit_with_retry_after():
    client, session, _ = make_client(fake_response(429, headers={"Retry-After": "30"}))
    with pytest.raises(RateLimitExceeded) as error:
        client.get_json("/prices")
    assert error.value.retry_after == 30 and session.request.call_count == 1


def test_invalid_json_raises():
    client, _, _ = make_client(fake_response(bad_json=True))
    with pytest.raises(ExternalServiceError):
        client.get_json("/prices")


def test_client_side_rate_limiter_blocks_before_network():
    limiter = RateLimiter(limit=2, period=60, clock=lambda: 100.0)
    client, session, _ = make_client(fake_response(payload={}), fake_response(payload={}), rate_limiter=limiter)
    client.get_json("/a")
    client.get_json("/b")
    with pytest.raises(RateLimitExceeded):
        client.get_json("/c")
    assert session.request.call_count == 2  # üçüncü istek internete hiç çıkmadı


def test_api_key_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    client, _, _ = make_client(fake_response(503), fake_response(payload={}))
    client.get_json("/prices")
    assert SECRET_KEY not in caplog.text
    assert SECRET_KEY not in repr(client)


# --- 2. Hız sınırlayıcı ----------------------------------------------------------------------

def test_rate_limiter_sliding_window():
    now = [0.0]
    limiter = RateLimiter(limit=3, period=10, clock=lambda: now[0])
    assert all(limiter.hit("u1") for _ in range(3))
    assert not limiter.hit("u1")
    assert limiter.hit("u2")                 # anahtarlar birbirinden bağımsız
    assert limiter.retry_after("u1") == 10
    now[0] = 10.5                            # pencere kaydı
    assert limiter.hit("u1")


# --- 3. Fiyat sağlayıcıları ------------------------------------------------------------------

def test_mock_price_provider_is_deterministic_and_valid():
    provider = MockPriceProvider()
    first = provider.fetch_daily_prices(date(2026, 10, 19))
    second = provider.fetch_daily_prices(date(2026, 10, 19))
    assert first == second                   # aynı gün = aynı fiyat (tekrarlanabilir testler)
    assert {q.product_name for q in first} >= {"Domates", "Biber", "Elma"}
    assert all(q.min_price <= q.avg_price <= q.max_price for q in first)
    assert first != provider.fetch_daily_prices(date(2026, 10, 20))


def test_http_price_provider_parses_and_skips_bad_rows(app):
    client = MagicMock()
    client.get_json.return_value = {"items": [
        {"name": "Domates", "unit": "kg", "min": 18, "max": 30, "avg": 24.5},
        {"name": "Biber", "avg": "35.10"},                 # min/max yoksa avg kullanılır
        {"unit": "kg", "avg": 10},                         # ad yok -> atlanır
        {"name": "Elma", "avg": "çok pahalı"},             # sayı değil -> atlanır
    ]}
    quotes = HttpPriceProvider(client).fetch_daily_prices(date(2026, 10, 19))
    client.get_json.assert_called_once_with("/prices", params={"date": "2026-10-19"})
    assert [q.product_name for q in quotes] == ["Domates", "Biber"]
    assert quotes[0].avg_price == Decimal("24.50") and quotes[1].min_price == Decimal("35.10")


def test_http_price_provider_rejects_unexpected_shape(app):
    client = MagicMock()
    client.get_json.return_value = {"data": "beklenmeyen"}
    with pytest.raises(ExternalServiceError):
        HttpPriceProvider(client).fetch_daily_prices(date(2026, 10, 19))


def test_real_provider_requires_url_in_env(app):
    app.config.update(USE_MOCK_APIS=False, PRICE_API_URL="")
    with pytest.raises(ConfigurationError):
        get_price_provider()


def test_mock_mode_selects_mock_providers(app):
    assert isinstance(get_price_provider(), MockPriceProvider)
    assert isinstance(get_payment_gateway(), MockPaymentGateway)


# --- 4. Ödeme sağlayıcıları ---------------------------------------------------------------------

def test_mock_gateway_test_cards():
    gateway = MockPaymentGateway()
    assert gateway.charge(Decimal("10"), "TRY", card(), "k1").success
    declined = gateway.charge(Decimal("10"), "TRY", card("4000000000000002"), "k2")
    assert not declined.success and declined.error_code == "card_declined"
    funds = gateway.charge(Decimal("10"), "TRY", card("4000000000009995"), "k3")
    assert funds.error_code == "insufficient_funds"


def test_mock_gateway_idempotency_prevents_double_charge():
    gateway = MockPaymentGateway()
    first = gateway.charge(Decimal("10"), "TRY", card(), "ayni-anahtar")
    second = gateway.charge(Decimal("10"), "TRY", card(), "ayni-anahtar")
    assert first == second and gateway.charge_calls == 1


def test_mock_gateway_timeout_then_retry_returns_original_charge():
    gateway = MockPaymentGateway()
    with pytest.raises(ExternalTimeout):
        gateway.charge(Decimal("10"), "TRY", card("4000000000000119"), "zaman-asimi")
    retry = gateway.charge(Decimal("10"), "TRY", card("4000000000000119"), "zaman-asimi")
    assert retry.success and gateway.charge_calls == 1  # para bir kez çekildi


def test_card_details_repr_is_masked():
    text = repr(card())
    assert "4111111111111111" not in text and "1111" in text and "123" not in text


def test_http_gateway_signs_body_and_sends_idempotency_key():
    client = MagicMock()
    client.request.return_value = {"id": "ch_1", "status": "succeeded"}
    gateway = HttpPaymentGateway(client, SECRET_KEY)

    result = gateway.charge(Decimal("85.5"), "TRY", card(), "idem-123", description="Siparis #1")
    assert result.success and result.transaction_ref == "ch_1"

    method, path = client.request.call_args.args
    kwargs = client.request.call_args.kwargs
    assert (method, path) == ("POST", "/charges")
    assert kwargs["headers"]["Idempotency-Key"] == "idem-123"
    expected = hmac.new(SECRET_KEY.encode(), kwargs["data"].encode(), hashlib.sha256).hexdigest()
    assert kwargs["headers"]["X-Signature"] == expected       # gövde imzalı
    assert json.loads(kwargs["data"])["amount"] == "85.50"    # tutar metin olarak, kuruş hassasiyetinde


def test_http_gateway_maps_failure_codes():
    client = MagicMock()
    client.request.return_value = {"status": "failed", "error": {"code": "insufficient_funds"}}
    result = HttpPaymentGateway(client, SECRET_KEY).charge(Decimal("10"), "TRY", card(), "k")
    assert not result.success and "limit" in result.message


def test_http_gateway_unknown_response_raises():
    client = MagicMock()
    client.request.return_value = {"status": "garip"}
    with pytest.raises(ExternalServiceError):
        HttpPaymentGateway(client, SECRET_KEY).charge(Decimal("10"), "TRY", card(), "k")


def test_real_payment_gateway_requires_keys(app):
    app.config.update(USE_MOCK_APIS=False, PAYMENT_API_URL="https://sandbox.ornek.com", PAYMENT_API_KEY="",
                      PAYMENT_SECRET_KEY="")
    with pytest.raises(ConfigurationError):
        get_payment_gateway()
