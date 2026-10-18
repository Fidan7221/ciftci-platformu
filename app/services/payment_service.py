"""Ödeme iş mantığı (Hafta 9).

ÖDEME AKIŞI (pay_order)
 1. Kontrol: sipariş bu müşterinin mi, durumu "ödeme bekleniyor" mu, daha önce ödenmiş mi?
 2. Ödeme kaydı "initiated" olarak veri tabanına YAZILIR (sağlayıcıya gitmeden önce).
    Böylece sunucu tam bu anda çökse bile "bir ödeme denemesi başladı" bilgisi kaybolmaz.
 3. Sağlayıcıya tahsilat isteği gönderilir (idempotency anahtarıyla).
 4. Sonuca göre:
    - başarılı   -> sipariş koşullu UPDATE ile "paid" olur, ödeme "success"
    - reddedildi -> ödeme "failed", sipariş "pending" kalır, müşteri tekrar deneyebilir
    - zaman aşımı-> ödeme "initiated" kalır; tekrar denemede AYNI anahtar kullanılır,
                    sağlayıcı ilk sonucu döndürür, kart iki kez çekilmez.

Harici çağrı veri tabanı kilidi tutarken yapılmaz: önce commit, sonra API çağrısı.
"""
import uuid

from flask import current_app

from app.integrations.errors import ConfigurationError, ExternalTimeout, IntegrationError, RateLimitExceeded
from app.integrations.payment_gateway import RefundResult, get_payment_gateway
from app.models import OrderStatus, Payment, PaymentStatus
from app.models.base import utcnow
from app.repositories.order_repository import OrderRepository
from app.services.errors import ServiceError

MANUAL = "manual"


def _gateway():
    try:
        return get_payment_gateway()
    except ConfigurationError as error:
        current_app.logger.error("Ödeme yapılandırma hatası: %s", error.message)
        raise ServiceError("Ödeme sistemi şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.")


def get_customer_order(order_id, user):
    """Siparişi yalnızca bu müşteriye aitse döndürür (yoksa None -> 404)."""
    order = OrderRepository.get_by_id(order_id)
    if order is None or order.customer_id != user.id:
        return None
    return order


def can_pay(order):
    return order.status == OrderStatus.PENDING and not (
        order.payment is not None and order.payment.status == PaymentStatus.SUCCESS)


def pay_order(order, user, card):
    if order.customer_id != user.id:
        raise ServiceError("Bu siparişi yalnızca siparişi veren müşteri ödeyebilir.")
    if not can_pay(order):
        raise ServiceError(f"Bu sipariş ödenmeye uygun değil (durum: {order.status_label}).")

    gateway = _gateway()
    currency = current_app.config.get("PAYMENT_CURRENCY", "TRY")

    # --- 2. Denemeyi kaydet ---------------------------------------------------------------
    payment = order.payment
    if payment is None:
        payment = Payment(order=order, provider=gateway.name, amount=order.total_amount,
                          status=PaymentStatus.INITIATED, attempt_count=0)
        OrderRepository.add(payment)
    # Önceki deneme kesin sonuçlanmadıysa (initiated) aynı anahtar kullanılır -> çift çekim olmaz.
    # Önceki deneme kesin başarısızsa (failed) yeni bir anahtar üretilir -> yeni bir deneme.
    if payment.status != PaymentStatus.INITIATED or not payment.idempotency_key:
        payment.idempotency_key = uuid.uuid4().hex
    payment.status = PaymentStatus.INITIATED
    payment.provider = gateway.name
    payment.amount = order.total_amount
    payment.attempt_count = (payment.attempt_count or 0) + 1
    payment.card_last4 = card.last4          # Kart numarasının tamamı ASLA saklanmaz
    payment.error_message = None
    OrderRepository.commit()

    # --- 3. Sağlayıcıya gönder ----------------------------------------------------------------
    try:
        result = gateway.charge(order.total_amount, currency, card, payment.idempotency_key,
                                description=f"Tarladan Sofraya siparis #{order.id}")
    except ExternalTimeout:
        payment.error_message = "Ödeme sağlayıcısı zamanında yanıt vermedi."
        OrderRepository.commit()
        raise ServiceError("Ödeme sağlayıcısından yanıt alınamadı. Lütfen aynı kartla tekrar deneyin; "
                           "kartınızdan iki kez çekim yapılmaz.")
    except RateLimitExceeded:
        payment.status = PaymentStatus.FAILED  # 429: istek işlenmeden reddedildi, çekim yok
        payment.error_message = "Sağlayıcı hız sınırı."
        OrderRepository.commit()
        raise ServiceError("Ödeme sistemi şu anda yoğun. Lütfen bir dakika sonra tekrar deneyin.")
    except IntegrationError as error:
        payment.error_message = error.message[:255]
        OrderRepository.commit()
        raise ServiceError("Ödeme sağlayıcısına ulaşılamadı. Lütfen biraz sonra tekrar deneyin.")

    # --- 4. Sonucu işle ---------------------------------------------------------------------------
    if not result.success:
        payment.status = PaymentStatus.FAILED
        payment.error_message = result.message
        OrderRepository.commit()
        raise ServiceError(result.message)

    if not OrderRepository.transition_status(order.id, OrderStatus.PENDING, OrderStatus.PAID):
        # Para çekildi ama sipariş bu arada iptal edilmiş: parayı hemen iade et
        try:
            refund = gateway.refund(result.transaction_ref, order.total_amount, f"{payment.idempotency_key}-rf")
        except IntegrationError:
            refund = RefundResult(False, message="İade isteği gönderilemedi.")
        payment.transaction_ref = result.transaction_ref
        payment.status = PaymentStatus.REFUNDED if refund.success else PaymentStatus.SUCCESS
        payment.refund_ref = refund.refund_ref
        payment.refunded_at = utcnow() if refund.success else None
        OrderRepository.commit()
        current_app.logger.warning("Sipariş #%s ödeme sırasında değişti; iade: %s", order.id, refund.success)
        if not refund.success:
            current_app.logger.critical("ELLE İNCELE: sipariş #%s iptal ama ödeme iade edilemedi.", order.id)
            raise ServiceError("Sipariş ödeme sırasında iptal edildi. İade otomatik yapılamadı; "
                               "destek ekibimiz sizinle iletişime geçecek.")
        raise ServiceError("Sipariş ödeme sırasında iptal edildi; çekilen tutar iade edildi.")

    payment.status = PaymentStatus.SUCCESS
    payment.transaction_ref = result.transaction_ref
    payment.paid_at = utcnow()
    OrderRepository.commit()
    OrderRepository.expire(order)
    current_app.logger.info("Sipariş #%s ödendi (%s, **** %s).", order.id, gateway.name, payment.card_last4)
    return payment


def record_manual_payment(order):
    """Yönetici havale / kapıda ödemeyi elle onayladığında çağrılır (commit çağıran tarafta)."""
    payment = order.payment or Payment(order=order, amount=order.total_amount)
    if payment.id is None:
        OrderRepository.add(payment)
    payment.provider = MANUAL
    payment.status = PaymentStatus.SUCCESS
    payment.amount = order.total_amount
    payment.paid_at = utcnow()
    return payment


def refund_order_payment(order):
    """Ödenmiş sipariş iptal edilirken çağrılır. İade başarısızsa ServiceError fırlatır ve
    sipariş iptal EDİLMEZ (para müşteride değilken sipariş iptal görünmesin). Commit çağıran tarafta."""
    payment = order.payment
    if payment is None or payment.status != PaymentStatus.SUCCESS:
        return None

    if payment.provider == MANUAL:
        payment.status = PaymentStatus.REFUNDED
        payment.refund_ref = MANUAL
        payment.refunded_at = utcnow()
        return payment

    gateway = _gateway()
    try:
        result = gateway.refund(payment.transaction_ref, payment.amount, f"{payment.idempotency_key}-rf")
    except IntegrationError as error:
        current_app.logger.error("İade başarısız (sipariş #%s): %s", order.id, error.message)
        raise ServiceError("İade işlemi ödeme sağlayıcısına iletilemedi; sipariş iptal edilmedi. "
                           "Lütfen biraz sonra tekrar deneyin.")
    if not result.success:
        raise ServiceError(f"İade reddedildi ({result.message}); sipariş iptal edilmedi.")

    payment.status = PaymentStatus.REFUNDED
    payment.refund_ref = result.refund_ref
    payment.refunded_at = utcnow()
    return payment


def sandbox_cards():
    """Ödeme sayfasında gösterilecek test kartları (yalnızca sahte sağlayıcı modunda)."""
    if not current_app.config["USE_MOCK_APIS"]:
        return []
    from app.integrations.payment_gateway import MockPaymentGateway
    return [(number, label) for number, (_, label) in MockPaymentGateway.TEST_CARDS.items()]
