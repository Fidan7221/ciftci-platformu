"""Hafta 9 testleri: ödeme servisi, ödeme sayfası, iade ve ödenmeyen siparişlerin iptali.

Ödeme sağlayıcısı test modunda MockPaymentGateway'dir; kart numarası sonucu belirler.

Çalıştırma: pytest -v tests/test_payments.py
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import update

from app.extensions import db
from app.integrations.errors import ExternalServiceError
from app.integrations.payment_gateway import CardDetails, get_payment_gateway
from app.models import Order, OrderStatus, Payment, PaymentStatus
from app.models.base import utcnow
from app.services import cart_service, order_service, payment_service
from app.services.errors import ServiceError
from tests.conftest import login, make_customer, make_listing, make_producer, make_product

ADDRESS = "Yenişehir Mah. Çiçek Sok. No:5 Merkez / Bingöl"
OK_CARD = "4111111111111111"
DECLINED = "4000000000000002"
TIMEOUT = "4000000000000119"


def card(number=OK_CARD):
    return CardDetails(holder="Test Kişi", number=number, exp_month=12, exp_year=2099, cvc="123")


def new_order(quantity="10"):
    profile = make_producer("ciftci@test.com")
    product = make_product(profile, stock="100")
    listing = make_listing(profile, product, quantity="50", price="20")
    customer = make_customer("musteri@test.com")
    cart_service.add_to_cart(customer, listing.id, Decimal(quantity))
    order = order_service.place_order(customer, ADDRESS)[0]
    return order, customer, product


def pay_form(number=OK_CARD, expiry="12/99", cvc="123"):
    return {"holder": "Zeynep Kaya", "card_number": number, "expiry": expiry, "cvc": cvc}


# --- Servis ------------------------------------------------------------------------------

def test_successful_payment_marks_order_paid(client):
    order, customer, _ = new_order()
    payment = payment_service.pay_order(order, customer, card())

    db.session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert payment.status == PaymentStatus.SUCCESS and payment.amount == Decimal("200.00")
    assert payment.transaction_ref.startswith("mock_tx_") and payment.paid_at is not None
    assert payment.card_last4 == "1111" and payment.attempt_count == 1


def test_card_number_is_never_stored(client):
    order, customer, _ = new_order()
    payment_service.pay_order(order, customer, card())
    row = db.session.execute(db.select(Payment.__table__)).mappings().one()
    stored = " ".join(str(value) for value in row.values())
    assert OK_CARD not in stored and "123" not in str(row["card_last4"])


def test_declined_then_retry_with_new_key(client):
    order, customer, _ = new_order()
    with pytest.raises(ServiceError, match="reddedildi"):
        payment_service.pay_order(order, customer, card(DECLINED))

    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING
    first_key = order.payment.idempotency_key
    assert order.payment.status == PaymentStatus.FAILED

    payment_service.pay_order(order, customer, card())
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert order.payment.attempt_count == 2 and order.payment.idempotency_key != first_key


def test_timeout_retry_uses_same_key_and_charges_once(client):
    order, customer, _ = new_order()
    with pytest.raises(ServiceError, match="iki kez çekim yapılmaz"):
        payment_service.pay_order(order, customer, card(TIMEOUT))

    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING and order.payment.status == PaymentStatus.INITIATED
    key = order.payment.idempotency_key

    payment_service.pay_order(order, customer, card(TIMEOUT))   # müşteri tekrar dener
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert order.payment.idempotency_key == key
    assert get_payment_gateway().charge_calls == 1              # kart yalnızca BİR kez çekildi


def test_cannot_cancel_while_payment_is_uncertain(client):
    order, customer, _ = new_order()
    with pytest.raises(ServiceError):
        payment_service.pay_order(order, customer, card(TIMEOUT))
    with pytest.raises(ServiceError, match="kesinleşmedi"):
        order_service.change_status(order, customer, OrderStatus.CANCELLED)


def test_cannot_pay_twice_or_someone_elses_order(client):
    order, customer, _ = new_order()
    other = make_customer("baska@test.com")
    with pytest.raises(ServiceError, match="yalnızca siparişi veren"):
        payment_service.pay_order(order, other, card())

    payment_service.pay_order(order, customer, card())
    with pytest.raises(ServiceError, match="uygun değil"):
        payment_service.pay_order(order, customer, card())
    assert get_payment_gateway().charge_calls == 1


def test_provider_outage_keeps_order_pending(client):
    order, customer, _ = new_order()
    with patch.object(get_payment_gateway(), "charge", side_effect=ExternalServiceError("kapalı")):
        with pytest.raises(ServiceError, match="ulaşılamadı"):
            payment_service.pay_order(order, customer, card())
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING


def test_cancelling_paid_order_refunds_and_restores_stock(client):
    order, customer, product = new_order()
    payment_service.pay_order(order, customer, card())

    producer_user = order.items[0].producer.user
    order_service.change_status(order, producer_user, OrderStatus.CANCELLED)

    db.session.refresh(order)
    db.session.refresh(product)
    assert order.status == OrderStatus.CANCELLED
    assert order.payment.status == PaymentStatus.REFUNDED and order.payment.refund_ref
    assert product.stock_quantity == Decimal("100")


def test_failed_refund_blocks_cancellation(client):
    order, customer, product = new_order()
    payment_service.pay_order(order, customer, card())
    producer_user = order.items[0].producer.user

    with patch.object(get_payment_gateway(), "refund", side_effect=ExternalServiceError("kapalı")):
        with pytest.raises(ServiceError, match="iptal edilmedi"):
            order_service.change_status(order, producer_user, OrderStatus.CANCELLED)

    db.session.refresh(order)
    db.session.refresh(product)
    assert order.status == OrderStatus.PAID           # para müşteriye dönmeden sipariş iptal görünmez
    assert product.stock_quantity == Decimal("90")


def test_order_cancelled_during_payment_is_refunded(client):
    order, customer, _ = new_order()
    real_charge = get_payment_gateway().charge

    def charge_while_cancelled(*args, **kwargs):
        result = real_charge(*args, **kwargs)
        # Tam ödeme sırasında başka bir sekmede sipariş iptal edildi
        db.session.execute(update(Order).where(Order.id == order.id).values(status=OrderStatus.CANCELLED))
        return result

    with patch.object(get_payment_gateway(), "charge", side_effect=charge_while_cancelled):
        with pytest.raises(ServiceError, match="iade edildi"):
            payment_service.pay_order(order, customer, card())
    db.session.refresh(order)
    assert order.payment.status == PaymentStatus.REFUNDED


def test_admin_manual_payment_creates_record(client):
    from app.services.auth_service import create_admin_user
    order, _, _ = new_order()
    admin = create_admin_user("Yönetici", "admin@test.com", "Yonetici123")
    order_service.change_status(order, admin, OrderStatus.PAID)
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID and order.payment.provider == "manual"


# --- Ödenmeyen siparişlerin otomatik iptali ------------------------------------------------------

def test_cancel_unpaid_orders_releases_stock(client, app):
    order, _, product = new_order()
    order.created_at = utcnow() - timedelta(hours=30)
    db.session.commit()

    result = app.test_cli_runner().invoke(args=["cancel-unpaid", "--hours", "24"])
    assert "1 ödenmemiş sipariş iptal edildi" in result.output

    db.session.refresh(order)
    db.session.refresh(product)
    assert order.status == OrderStatus.CANCELLED and product.stock_quantity == Decimal("100")


def test_recent_unpaid_orders_are_kept(client):
    order, _, _ = new_order()
    assert order_service.cancel_unpaid_orders(24) == 0
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING


# --- Ödeme sayfası (rota) ---------------------------------------------------------------------

def test_checkout_redirects_to_payment_and_pays_via_form(client):
    order, _, _ = new_order()
    login(client, "musteri@test.com")

    page = client.get(f"/odeme/siparis/{order.id}").get_data(as_text=True)
    assert "Kartla öde" in page and "Test ortamı" in page

    response = client.post(f"/odeme/siparis/{order.id}", data=pay_form("4111 1111 1111 1111"),
                           follow_redirects=True)
    assert "Ödemeniz alındı" in response.get_data(as_text=True)
    db.session.refresh(order)
    assert order.status == OrderStatus.PAID


def test_invalid_card_number_rejected_by_luhn(client):
    order, _, _ = new_order()
    login(client, "musteri@test.com")
    page = client.post(f"/odeme/siparis/{order.id}", data=pay_form("4111111111111112")).get_data(as_text=True)
    assert "Kart numarası geçersiz" in page
    assert "4111111111111112" not in page  # hatalı numara bile sayfaya geri yazılmaz


def test_expired_card_rejected(client):
    order, _, _ = new_order()
    login(client, "musteri@test.com")
    page = client.post(f"/odeme/siparis/{order.id}", data=pay_form(expiry="01/20")).get_data(as_text=True)
    assert "son kullanma tarihi geçmiş" in page


def test_declined_card_message_and_form_cleared(client):
    order, _, _ = new_order()
    login(client, "musteri@test.com")
    page = client.post(f"/odeme/siparis/{order.id}", data=pay_form(DECLINED), follow_redirects=True).get_data(as_text=True)
    assert "reddedildi" in page and DECLINED not in page


def test_payment_page_access_control(client):
    order, _, _ = new_order()
    make_customer("baska@test.com")

    login(client, "baska@test.com")
    assert client.get(f"/odeme/siparis/{order.id}").status_code == 404   # başkasının siparişi
    login(client, "ciftci@test.com")
    assert client.get(f"/odeme/siparis/{order.id}").status_code == 403   # üretici ödeme yapamaz


def test_paid_order_payment_page_redirects(client):
    order, customer, _ = new_order()
    payment_service.pay_order(order, customer, card())
    login(client, "musteri@test.com")
    response = client.get(f"/odeme/siparis/{order.id}")
    assert response.status_code == 302 and f"/siparisler/{order.id}" in response.headers["Location"]


def test_payment_attempts_are_rate_limited(client, app):
    app.config["PAYMENT_ATTEMPTS_PER_10_MIN"] = 3
    order, _, _ = new_order()
    login(client, "musteri@test.com")
    for _ in range(3):
        client.post(f"/odeme/siparis/{order.id}", data=pay_form(DECLINED))
    response = client.post(f"/odeme/siparis/{order.id}", data=pay_form(OK_CARD))
    assert response.status_code == 429
    assert response.headers["Retry-After"]
    db.session.refresh(order)
    assert order.status == OrderStatus.PENDING  # 4. istek sağlayıcıya hiç gitmedi


def test_order_detail_shows_payment_info(client):
    order, customer, _ = new_order()
    payment_service.pay_order(order, customer, card())
    login(client, "musteri@test.com")
    page = client.get(f"/siparisler/{order.id}").get_data(as_text=True)
    assert "**** 1111" in page and "Başarılı" in page
