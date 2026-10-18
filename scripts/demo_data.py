"""Vize sunumu için demo verileri (Hafta 8).

Çalıştırma:  flask seed-demo
Tekrar çalıştırılabilir: var olan hesap ve ürünleri ikinci kez eklemez.

Veriler doğrudan veri tabanına değil, SERVİSLER üzerinden eklenir. Böylece
demo verisi de uygulamanın gerçek iş kurallarından geçer (parola hash'leme,
stok kontrolü, ilan miktarı <= ürün stoğu gibi).
"""
from datetime import date
from decimal import Decimal

from app.models import Category, RoleName
from app.repositories.user_repository import UserRepository
from app.services import auth_service, listing_service, producer_service
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
ADMIN = {"email": "admin@demo.com", "full_name": "Platform Yöneticisi"}


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


def seed_demo():
    """Demo verilerini ekler ve {rol: e-posta} sözlüğü döndürür."""
    seed_all()  # Roller ve kategoriler

    for producer in PRODUCERS:
        _seed_producer(producer)

    customer = _get_or_register(CUSTOMER["email"], lambda: auth_service.register_user(
        CUSTOMER["full_name"], CUSTOMER["email"], DEMO_PASSWORD, RoleName.CUSTOMER,
        phone=CUSTOMER["phone"], city="Bingöl"))
    customer.address = CUSTOMER["address"]
    UserRepository.commit()

    _get_or_register(ADMIN["email"], lambda: auth_service.create_admin_user(
        ADMIN["full_name"], ADMIN["email"], DEMO_PASSWORD))

    return {
        "Üretici": PRODUCERS[0]["email"],
        "Arıcı": PRODUCERS[1]["email"],
        "Müşteri": CUSTOMER["email"],
        "Yönetici": ADMIN["email"],
    }
