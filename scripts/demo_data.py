"""Vize sunumu için demo verileri (Hafta 8).

Çalıştırma:  flask seed-demo
Tekrar çalıştırılabilir: var olan hesap ve ürünleri ikinci kez eklemez.

Veriler doğrudan veri tabanına değil, SERVİSLER üzerinden eklenir. Böylece
demo verisi de uygulamanın gerçek iş kurallarından geçer (parola hash'leme,
stok kontrolü, ilan miktarı <= ürün stoğu gibi).
"""
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models import Category, Order, OrderStatus, RoleName
from app.repositories.user_repository import UserRepository
from app.services import auth_service, cart_service, listing_service, order_service, producer_service
from scripts.seed_data import seed_all

DEMO_PASSWORD = "Demo12345"

PRODUCERS = [
    {
        "email": "ciftci@demo.com", "full_name": "Mehmet Yılmaz", "phone": "05321112233",
        "farm_name": "Genç Organik Çiftliği", "region": "Bingöl / Genç",
        "description": "Üç kuşaktır Genç ovasında ilaçsız sebze ve meyve yetiştiriyoruz.",
        "products": [
            # (ürün adı, kategori slug, birim, depo stoğu, organik mi, ilan miktarı, fiyat, en az sipariş)
            ("Salkım Domates", "domates", "kg", "200", True, "80", "28.50", "1"),
            ("Çarliston Biber", "biber", "kg", "100", True, "40", "35.00", "0.5"),
            ("Amasya Elması", "elma", "kg", "300", False, "120", "22.00", "2"),
        ],
    },
    {
        "email": "arici@demo.com", "full_name": "Ayşe Demir", "phone": "05334445566",
        "farm_name": "Solhan Bal Evi", "region": "Bingöl / Solhan",
        "description": "Bingöl yaylalarından süzme çiçek ve petek bal.",
        "products": [
            ("Süzme Çiçek Balı (850 g)", "cicek-bali", "adet", "60", False, "30", "450.00", "1"),
            ("Petek Bal (1 kg)", "petek-bal", "adet", "20", False, "10", "650.00", "1"),
        ],
    },
]

CUSTOMER = {
    "email": "musteri@demo.com", "full_name": "Zeynep Kaya", "phone": "05357778899",
    "address": "Yenişehir Mah. Çiçek Sok. No:5 D:3 Merkez / Bingöl",
}
SECOND_CUSTOMER = {"email": "musteri2@demo.com", "full_name": "Ahmet Öztürk", "phone": "05369990011",
                   "address": "Saray Mah. Hükümet Cad. No:10 Merkez / Bingöl"}
ADMIN = {"email": "admin@demo.com", "full_name": "Platform Yöneticisi"}

# Hafta 12: Raporların boş görünmemesi için son 45 güne yayılmış demo siparişleri.
# (ürün adı, en az, en çok) — miktarlar ilan stoklarını tüketmeyecek kadar küçük tutuldu
DEMO_BASKET = [("Salkım Domates", 1, 3), ("Çarliston Biber", 1, 2), ("Amasya Elması", 2, 4),
               ("Süzme Çiçek Balı (850 g)", 1, 1), ("Petek Bal (1 kg)", 1, 1)]
DEMO_ORDER_COUNT = 24


def _get_or_register(email, create):
    user = UserRepository.get_by_email(email)
    return user if user is not None else create()


def _seed_producer(data):
    user = _get_or_register(data["email"], lambda: auth_service.register_user(
        data["full_name"], data["email"], DEMO_PASSWORD, RoleName.PRODUCER,
        phone=data["phone"], city="Bingöl", farm_name=data["farm_name"], region=data["region"]))
    profile = user.producer_profile
    profile.description = data["description"]
    profile.is_verified = True  # Demoda "Doğrulanmış üretici" rozeti görünsün

    existing = {p.name for p in profile.products}
    for name, slug, unit, stock, organic, listing_qty, price, min_order in data["products"]:
        if name in existing:
            continue
        category = Category.query.filter_by(slug=slug).first()
        product = producer_service.create_product(
            profile, category.id, name, unit, Decimal(stock),
            description=f"{data['farm_name']} üretimi {name.lower()}.", is_organic=organic)
        listing_service.create_listing(
            profile, product.id, None, Decimal(price), Decimal(listing_qty), Decimal(min_order), date.today())
    UserRepository.commit()


def _seed_demo_orders(customers, admin):
    """Siparişler GERÇEK akıştan geçer: sepete ekle -> sipariş ver (stok düşer) -> durum geçişleri
    (yönetici elle ödeme onayı, kargo, teslim; bazıları iptal -> stok geri eklenir).
    Yalnızca oluşturulma tarihi geriye alınır; böylece raporlarda 45 günlük bir geçmiş görünür.
    Hiç sipariş yoksa çalışır; komut tekrar çalıştırılırsa yeni sipariş eklemez.
    """
    if Order.query.count():
        return 0
    from app.models import Listing, Product
    listings = {}
    for name, _, _ in DEMO_BASKET:
        listing = Listing.query.join(Listing.product).filter(Product.name == name).first()
        if listing is not None:
            listings[name] = listing

    rng = random.Random(12)                         # her çalıştırmada aynı demo verisi
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created = 0
    for i in range(DEMO_ORDER_COUNT):
        name, low, high = DEMO_BASKET[0] if i % 4 == 0 else rng.choice(DEMO_BASKET)
        listing = listings.get(name)
        if listing is None or (name.startswith("Petek") and rng.random() < 0.6):
            continue
        customer = customers[i % len(customers)]
        cart_service.add_to_cart(customer, listing.id, Decimal(rng.randint(low, high)))
        order = order_service.place_order(customer, customer.address or SECOND_CUSTOMER["address"])[0]

        days_ago = rng.randint(0, 45)
        if days_ago > 7:
            path = [OrderStatus.CANCELLED] if rng.random() < 0.12 else \
                [OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED]
        elif days_ago > 2:
            path = [OrderStatus.PAID, OrderStatus.SHIPPED][:rng.randint(1, 2)]
        else:
            path = [] if rng.random() < 0.5 else [OrderStatus.PAID]
        for status in path:
            order_service.change_status(order, admin, status)

        order.created_at = now - timedelta(days=days_ago, hours=rng.randint(0, 10), minutes=rng.randint(0, 59))
        db.session.commit()
        created += 1
    return created


def seed_demo():
    """Demo verilerini ekler ve {rol: e-posta} sözlüğü döndürür."""
    seed_all()  # Roller ve kategoriler

    for producer in PRODUCERS:
        _seed_producer(producer)

    customer = _get_or_register(CUSTOMER["email"], lambda: auth_service.register_user(
        CUSTOMER["full_name"], CUSTOMER["email"], DEMO_PASSWORD, RoleName.CUSTOMER,
        phone=CUSTOMER["phone"], city="Bingöl"))
    customer.address = CUSTOMER["address"]
    second = _get_or_register(SECOND_CUSTOMER["email"], lambda: auth_service.register_user(
        SECOND_CUSTOMER["full_name"], SECOND_CUSTOMER["email"], DEMO_PASSWORD, RoleName.CUSTOMER,
        phone=SECOND_CUSTOMER["phone"], city="Bingöl"))
    second.address = SECOND_CUSTOMER["address"]
    UserRepository.commit()

    admin = _get_or_register(ADMIN["email"], lambda: auth_service.create_admin_user(
        ADMIN["full_name"], ADMIN["email"], DEMO_PASSWORD))

    _seed_demo_orders([customer, second], admin)  # Hafta 12: rapor demosu

    # Hafta 9-10: son 60 günün hal fiyatları (sahte sağlayıcıdan) ve yapay zekâ tahminleri
    from app.services import prediction_service, price_service
    if price_service.status()["count"] == 0:
        price_service.backfill(60)
    prediction_service.generate_predictions()

    return {
        "Üretici": PRODUCERS[0]["email"],
        "Arıcı": PRODUCERS[1]["email"],
        "Müşteri": CUSTOMER["email"],
        "Yönetici": ADMIN["email"],
    }
