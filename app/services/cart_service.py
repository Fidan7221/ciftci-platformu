"""Sepet iş mantığı (Hafta 7).

Sepete ekleme bir REZERVASYON değildir: stok yalnızca sipariş onaylanınca düşer.
Bu yüzden sepet sayfası ve ödeme adımı stokları her seferinde yeniden kontrol eder.
"""
from decimal import Decimal

from app.models import Cart, CartItem, Unit
from app.repositories.cart_repository import CartRepository
from app.repositories.listing_repository import ListingRepository
from app.services.errors import ServiceError
from app.utils.formatting import format_qty


def get_or_create_cart(user):
    cart = CartRepository.get_by_user_id(user.id)
    if cart is None:
        cart = Cart(user=user)
        CartRepository.add(cart)
        CartRepository.commit()
    return cart


def item_count(user):
    return CartRepository.item_count(user.id)


def _validate_quantity(listing, quantity):
    """Miktar bu ilan için geçerli mi? Geçersizse ServiceError."""
    if not listing.is_available:
        raise ServiceError(f"'{listing.title}' şu anda satışta değil.")
    if quantity is None or quantity <= 0:
        raise ServiceError("Miktar sıfırdan büyük olmalıdır.", field="quantity")
    unit = listing.product.unit
    if unit in Unit.COUNTABLE and quantity != quantity.to_integral_value():
        raise ServiceError(f"Bu ürün '{unit}' birimiyle satılıyor; tam sayı girin.", field="quantity")
    if quantity < listing.min_order_quantity:
        raise ServiceError(f"Bu ilan için en az {format_qty(listing.min_order_quantity)} {unit} sipariş verilebilir.",
                           field="quantity")
    if quantity > listing.stock_quantity:
        raise ServiceError(f"Stokta yalnızca {format_qty(listing.stock_quantity)} {unit} var.", field="quantity")


def add_to_cart(user, listing_id, quantity):
    listing = ListingRepository.get_by_id(listing_id)
    if listing is None:
        raise ServiceError("İlan bulunamadı.")

    cart = get_or_create_cart(user)
    item = CartRepository.get_item(cart.id, listing.id)
    new_quantity = Decimal(quantity) + (item.quantity if item else 0)
    _validate_quantity(listing, new_quantity)  # Toplam miktar stoğu aşmasın

    if item:
        item.quantity = new_quantity
    else:
        item = CartItem(cart=cart, listing=listing, quantity=new_quantity)
        CartRepository.add(item)
    CartRepository.commit()
    return item


def update_item(user, item_id, quantity):
    item = CartRepository.get_item_for_user(item_id, user.id)
    if item is None:
        raise ServiceError("Sepet kalemi bulunamadı.")
    if quantity is not None and quantity == 0:
        return remove_item(user, item_id)
    _validate_quantity(item.listing, quantity)
    item.quantity = quantity
    CartRepository.commit()
    return item


def remove_item(user, item_id):
    item = CartRepository.get_item_for_user(item_id, user.id)
    if item is None:
        raise ServiceError("Sepet kalemi bulunamadı.")
    CartRepository.delete(item)
    CartRepository.commit()
    return None


def cart_summary(user):
    """Sepet sayfası için kalemler, toplam ve sorunlar (tükenen/stoğu düşen ilanlar).

    Dönen sözlük:
      groups   -> {üretici: [kalemler]}  (sipariş üreticiye göre bölüneceği için)
      problems -> {kalem_id: "açıklama"}
      total    -> Decimal
    """
    cart = get_or_create_cart(user)
    groups, problems = {}, {}
    total = Decimal("0")

    for item in sorted(cart.items, key=lambda i: i.id):
        listing = item.listing
        try:
            _validate_quantity(listing, item.quantity)
        except ServiceError as error:
            problems[item.id] = error.message
        groups.setdefault(listing.producer, []).append(item)
        total += item.subtotal

    return {"cart": cart, "groups": groups, "problems": problems, "total": total,
            "is_empty": not cart.items}
