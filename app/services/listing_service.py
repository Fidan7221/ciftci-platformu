"""İlan yönetimi iş mantığı (Hafta 7).

Kurallar:
- Üretici yalnızca kendi, satışa açık (is_active) ürünleri için ilan açabilir.
- Bir ürünün AKTİF ilanlarına ayrılan toplam miktar ürün stoğunu aşamaz.
- Bitiş tarihi başlangıçtan önce olamaz; minimum sipariş ilan miktarını aşamaz.
- İlan silinmez; "Pasif" yapılır (geçmiş siparişler ilana bağlıdır).
"""
from decimal import Decimal

from flask import current_app

from app.models import Listing, ListingStatus
from app.repositories.listing_repository import ListingRepository
from app.repositories.product_repository import CategoryRepository, ProductRepository
from app.services.errors import ServiceError
from app.utils.formatting import format_qty


# --- Sorgular ---------------------------------------------------------------

def product_choices(profile):
    """İlan formundaki ürün listesi: yalnızca bu üreticinin satışa açık ürünleri."""
    return [(p.id, f"{p.name} (stok: {format_qty(p.stock_quantity)} {p.unit})")
            for p in sorted(profile.products, key=lambda p: p.name) if p.is_active]


def get_owned_listing(profile, listing_id):
    return ListingRepository.get_for_producer(listing_id, profile.id)


def list_producer_listings(profile, status=None, page=1):
    if status not in ListingStatus.ALL:
        status = None
    return ListingRepository.paginate_for_producer(
        profile.id, status, page, current_app.config.get("ITEMS_PER_PAGE", 12))


def list_market(search=None, category_id=None, page=1):
    """Pazar vitrini. Üst kategori seçilirse alt kategorilerindeki ilanlar da gelir."""
    category_ids = None
    if category_id:
        category = CategoryRepository.get_by_id(category_id)
        if category is not None:
            category_ids = [category.id] + [c.id for c in category.children]
    search = (search or "").strip() or None
    return ListingRepository.paginate_available(
        search, category_ids, page, current_app.config.get("ITEMS_PER_PAGE", 12))


def get_public_listing(listing_id):
    """Detay sayfası: pasif ilan da gösterilir (eski bağlantılar kırılmasın) ama satın alınamaz."""
    return ListingRepository.get_by_id(listing_id)


def remaining_stock_for(product, exclude_listing_id=None):
    """Bu ürün için yeni ilana ayrılabilecek miktar."""
    reserved = Decimal(str(ListingRepository.active_reserved_quantity(product.id, exclude_listing_id)))
    return max(Decimal(product.stock_quantity) - reserved, Decimal("0"))


# --- Doğrulama ----------------------------------------------------------------

def _validate(profile, product_id, price, stock_quantity, min_order_quantity,
              start_date, end_date, is_active, listing=None):
    product = ProductRepository.get_for_producer(product_id, profile.id)
    if product is None:
        raise ServiceError("Geçerli bir ürün seçin.", field="product_id")
    if is_active and not product.is_active:
        raise ServiceError("Bu ürün satışa kapalı. Önce ürünü aktif yapın.", field="product_id")
    if price is None or price <= 0:
        raise ServiceError("Fiyat sıfırdan büyük olmalıdır.", field="price")
    if stock_quantity is None or stock_quantity < 0:
        raise ServiceError("Miktar negatif olamaz.", field="stock_quantity")
    if min_order_quantity is None or min_order_quantity <= 0:
        raise ServiceError("Minimum sipariş sıfırdan büyük olmalıdır.", field="min_order_quantity")
    if stock_quantity > 0 and min_order_quantity > stock_quantity:
        raise ServiceError("Minimum sipariş, ilandaki miktardan büyük olamaz.",
                           field="min_order_quantity")
    if end_date and start_date and end_date < start_date:
        raise ServiceError("Bitiş tarihi başlangıç tarihinden önce olamaz.", field="end_date")

    if is_active:
        available = remaining_stock_for(product, exclude_listing_id=listing.id if listing else None)
        if stock_quantity > available:
            raise ServiceError(
                f"Depoda bu ilana ayrılabilecek en fazla {format_qty(available)} {product.unit} var "
                "(diğer aktif ilanlarınız da stoktan pay alıyor).",
                field="stock_quantity",
            )
    return product


def _status_for(is_active, stock_quantity):
    if not is_active:
        return ListingStatus.CLOSED
    return ListingStatus.ACTIVE if stock_quantity > 0 else ListingStatus.SOLD_OUT


# --- Ekleme / güncelleme / durum ------------------------------------------------

def create_listing(profile, product_id, title, price, stock_quantity, min_order_quantity,
                   start_date, end_date=None, is_active=True):
    product = _validate(profile, product_id, price, stock_quantity, min_order_quantity,
                        start_date, end_date, is_active)
    listing = Listing(
        product=product,
        title=(title or "").strip() or product.name,
        price=price,
        stock_quantity=stock_quantity,
        min_order_quantity=min_order_quantity,
        start_date=start_date,
        end_date=end_date,
        status=_status_for(is_active, stock_quantity),
    )
    ListingRepository.add(listing)
    ListingRepository.commit()
    return listing


def update_listing(profile, listing, product_id, title, price, stock_quantity, min_order_quantity,
                   start_date, end_date=None, is_active=True):
    if listing.order_items and product_id != listing.product_id:
        raise ServiceError("Siparişi olan bir ilanın ürünü değiştirilemez.", field="product_id")
    product = _validate(profile, product_id, price, stock_quantity, min_order_quantity,
                        start_date, end_date, is_active, listing)

    listing.product = product
    listing.title = (title or "").strip() or product.name
    listing.price = price  # Eski siparişler etkilenmez: fiyatları order_items'ta dondurulmuştur
    listing.stock_quantity = stock_quantity
    listing.min_order_quantity = min_order_quantity
    listing.start_date = start_date
    listing.end_date = end_date
    listing.status = _status_for(is_active, stock_quantity)
    ListingRepository.commit()
    return listing


def toggle_listing(profile, listing):
    """Aktif <-> Pasif. Tekrar aktif yaparken stok kuralı yeniden kontrol edilir."""
    if listing.status == ListingStatus.CLOSED:
        _validate(profile, listing.product_id, listing.price, listing.stock_quantity,
                  listing.min_order_quantity, listing.start_date, listing.end_date, True, listing)
        listing.status = _status_for(True, listing.stock_quantity)
    else:
        listing.status = ListingStatus.CLOSED
    ListingRepository.commit()
    return listing
