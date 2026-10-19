"""Sipariş iş mantığı (Hafta 7, Hafta 9'da ödeme ile birleşti): sepeti siparişe dönüştürme ve durum yönetimi.

1) SİPARİŞ OLUŞTURMA TEK BİR TRANSACTION'DIR
   Stok düşürme, sipariş ve kalemleri yazma, sepeti boşaltma ya HEP BİRLİKTE
   gerçekleşir ya da HİÇBİRİ gerçekleşmez. Herhangi bir adımda hata olursa
   rollback() ile veri tabanı işlem öncesi hâline döner.

2) SEPET ÜRETİCİYE GÖRE BÖLÜNÜR
   İki farklı üreticiden ürün alan müşteri için iki ayrı sipariş açılır.
   Her üretici kendi siparişini bağımsız olarak onaylar, kargolar veya iptal eder.

3) FİYAT DONDURULUR
   order_items.unit_price = sipariş anındaki ilan fiyatı. İlan fiyatı sonradan
   değişse bile sipariş tutarı değişmez.

4) DURUM MAKİNESİ (kim, hangi durumdan hangisine geçebilir)
   pending  -> paid       : ÖDEME SERVİSİ (kartla ödeme başarılı olunca, payment_service)
                            veya yönetici (havale / kapıda ödeme elle onayı)
   pending  -> cancelled  : müşteri / üretici / yönetici; ödenmeyen sipariş süre dolunca sistem
   paid     -> shipped    : üretici / yönetici
   paid     -> cancelled  : üretici / yönetici — önce ödeme sağlayıcısından İADE alınır
   shipped  -> delivered  : müşteri / yönetici
   delivered, cancelled   : son durumlar, değiştirilemez
"""
from datetime import timedelta
from decimal import Decimal

from flask import current_app

from app.models import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.base import utcnow
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.services import cart_service, payment_service
from app.services.errors import ServiceError

CUSTOMER, PRODUCER, ADMIN = "customer", "producer", "admin"

TRANSITIONS = {
    OrderStatus.PENDING: {
        OrderStatus.PAID: {ADMIN},  # Hafta 9: üretici artık elle "ödendi" yapamaz; ödeme sağlayıcısı yapar
        OrderStatus.CANCELLED: {CUSTOMER, PRODUCER, ADMIN},
    },
    OrderStatus.PAID: {
        OrderStatus.SHIPPED: {PRODUCER, ADMIN},
        OrderStatus.CANCELLED: {PRODUCER, ADMIN},
    },
    OrderStatus.SHIPPED: {
        OrderStatus.DELIVERED: {CUSTOMER, ADMIN},
    },
}

# Düğme metni, Bootstrap sınıfı ve onay sorusu
ACTIONS = {
    OrderStatus.PAID: ("Ödemeyi elle onayla (havale / kapıda)", "btn-outline-info",
                       "Ödemenin sağlayıcı dışında alındığını onaylıyor musunuz?"),
    OrderStatus.SHIPPED: ("Kargoya verildi", "btn-primary", "Sipariş kargoya verildi mi?"),
    OrderStatus.DELIVERED: ("Teslim aldım", "btn-success", "Siparişi teslim aldığınızı onaylıyor musunuz?"),
    OrderStatus.CANCELLED: ("Siparişi iptal et", "btn-outline-danger",
                            "Sipariş iptal edilecek, stoklar geri eklenecek; ödendiyse ücret iade edilecek. Emin misiniz?"),
}


# --- Erişim -------------------------------------------------------------------

def actor_for(order, user):
    """Kullanıcının bu siparişteki rolü: customer / producer / admin / None (erişim yok)."""
    if user.is_admin:
        return ADMIN
    if order.customer_id == user.id:
        return CUSTOMER
    if user.is_producer and user.producer_profile is not None and \
            OrderRepository.producer_has_items(order.id, user.producer_profile.id):
        return PRODUCER
    return None


def get_visible_order(order_id, user):
    """Sipariş yoksa veya kullanıcı göremiyorsa None (rota 404 gösterir)."""
    order = OrderRepository.get_with_details(order_id)  # Hafta 11: kalemler tek seferde
    if order is None or actor_for(order, user) is None:
        return None
    return order


def available_actions(order, user):
    actor = actor_for(order, user)
    actions = []
    for target, allowed in TRANSITIONS.get(order.status, {}).items():
        if actor in allowed:
            label, css, question = ACTIONS[target]
            actions.append({"status": target, "label": label, "css": css, "confirm": question})
    return actions


def list_customer_orders(user, page=1):
    return OrderRepository.paginate_for_customer(user.id, page)


def list_producer_orders(profile, status=None, page=1):
    if status not in OrderStatus.ALL:
        status = None
    return OrderRepository.paginate_for_producer(profile.id, status, page)


# --- Sipariş oluşturma (TRANSACTION) ------------------------------------------------

def place_order(user, shipping_address, note=None, save_address=False):
    """Sepeti siparişe dönüştürür ve oluşan siparişlerin listesini döndürür."""
    summary = cart_service.cart_summary(user)
    if summary["is_empty"]:
        raise ServiceError("Sepetiniz boş.")
    if summary["problems"]:
        raise ServiceError("Sepetinizdeki bazı ürünlerin stok veya satış durumu değişti. "
                           "Lütfen sepetinizi kontrol edin.")

    address = (shipping_address or "").strip()
    if len(address) < 10:
        raise ServiceError("Lütfen açık bir teslimat adresi girin.", field="shipping_address")

    orders, touched_listing_ids = [], []
    try:
        for producer, items in summary["groups"].items():
            order = Order(customer=user, shipping_address=address,
                          note=(note or "").strip() or None,
                          status=OrderStatus.PENDING, total_amount=Decimal("0"))
            total = Decimal("0")

            for item in items:
                listing = item.listing
                quantity = Decimal(item.quantity)

                # Koşullu UPDATE: stok yetmiyorsa satır güncellenmez -> False
                if not OrderRepository.decrease_listing_stock(listing.id, quantity):
                    raise ServiceError(f"'{listing.title}' için yeterli stok kalmadı. "
                                       "Başka bir müşteri sizden önce satın almış olabilir.")
                if not OrderRepository.decrease_product_stock(listing.product_id, quantity):
                    raise ServiceError(f"'{listing.title}' için depoda yeterli ürün kalmadı.")

                unit_price = Decimal(listing.price)  # FİYAT DONDURMA
                order.items.append(OrderItem(listing=listing, producer=producer,
                                             quantity=quantity, unit_price=unit_price))
                total += quantity * unit_price
                touched_listing_ids.append(listing.id)

            order.total_amount = total.quantize(Decimal("0.01"))
            OrderRepository.add(order)
            orders.append(order)

        OrderRepository.mark_sold_out(touched_listing_ids)

        for item in list(summary["cart"].items):  # Sepeti boşalt
            CartRepository.delete(item)
        if save_address:
            user.address = address

        OrderRepository.commit()  # Her şey başarılı: kalıcı yap
    except Exception:
        OrderRepository.rollback()  # Herhangi bir hata: stoklar ve sepet eski hâline döner
        raise

    current_app.logger.info("Kullanıcı %s için %d sipariş oluşturuldu.", user.id, len(orders))
    return orders


# --- Durum değiştirme -------------------------------------------------------------

def change_status(order, user, new_status):
    actor = actor_for(order, user)
    if actor is None:
        raise ServiceError("Bu sipariş üzerinde işlem yetkiniz yok.")

    current = order.status
    allowed = TRANSITIONS.get(current, {}).get(new_status)
    if not allowed or actor not in allowed:
        raise ServiceError(
            f"'{OrderStatus.LABELS.get(current, current)}' durumundaki sipariş "
            f"'{OrderStatus.LABELS.get(new_status, new_status)}' durumuna geçirilemez."
        )

    _apply_transition(order, current, new_status)
    return order


def _apply_transition(order, current, new_status):
    """Durum geçişini ve yan etkilerini (iade, stok iadesi, elle ödeme kaydı) tek transaction'da uygular."""
    payment = order.payment
    if new_status == OrderStatus.CANCELLED and payment is not None \
            and payment.status == PaymentStatus.INITIATED:
        # Zaman aşımına uğramış bir ödemenin sonucu belli değil; iptal edersek çekilmiş para kaybolabilir
        raise ServiceError("Bu siparişin ödeme sonucu henüz kesinleşmedi. Lütfen önce ödemeyi tekrar deneyin.")

    try:
        if new_status == OrderStatus.CANCELLED:
            # 1) Ödenmişse önce iade (başarısızsa ServiceError -> sipariş iptal edilmez)
            payment_service.refund_order_payment(order)
        if not OrderRepository.transition_status(order.id, current, new_status):
            raise ServiceError("Sipariş bu sırada başka biri tarafından güncellendi. Sayfayı yenileyin.")
        if new_status == OrderStatus.CANCELLED:
            for item in order.items:  # 2) Stokları geri ekle
                OrderRepository.restore_stock(item.listing_id, item.listing.product_id, item.quantity)
        if new_status == OrderStatus.PAID:
            payment_service.record_manual_payment(order)  # Yönetici elle onayladı
        OrderRepository.commit()
    except Exception:
        OrderRepository.rollback()
        raise

    OrderRepository.expire(order)  # Nesne veri tabanındaki yeni durumu okusun


def cancel_unpaid_orders(older_than_hours):
    """Belirtilen süreden uzun süredir ödenmemiş siparişleri iptal eder ve stokları serbest bırakır.

    Sonucu belirsiz (initiated) ödemesi olan siparişlere dokunulmaz. Kaç sipariş iptal edildiğini döndürür.
    Komut: flask cancel-unpaid
    """
    cutoff = utcnow() - timedelta(hours=older_than_hours)
    cancelled = 0
    for order in OrderRepository.pending_created_before(cutoff):
        if order.payment is not None and order.payment.status == PaymentStatus.INITIATED:
            continue
        try:
            _apply_transition(order, OrderStatus.PENDING, OrderStatus.CANCELLED)
            cancelled += 1
        except ServiceError as error:
            current_app.logger.warning("Sipariş #%s otomatik iptal edilemedi: %s", order.id, error.message)
    return cancelled
