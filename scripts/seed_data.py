"""Başlangıç verileri: roller ve temel kategoriler.

Çalıştırma: flask seed-db
Tekrar çalıştırılırsa var olan kayıtları ikinci kez eklemez.
"""
from app.extensions import db
from app.models import Category, Role, RoleName

ROLES = {
    RoleName.ADMIN: "Sistem yöneticisi",
    RoleName.PRODUCER: "Ürün satan çiftçi / üretici",
    RoleName.CUSTOMER: "Ürün satın alan müşteri",
}

# Üst kategori: [alt kategoriler]
CATEGORIES = {
    ("Sebze", "sebze"): [("Domates", "domates"), ("Biber", "biber"), ("Patates", "patates")],
    ("Meyve", "meyve"): [("Elma", "elma"), ("Üzüm", "uzum"), ("Kayısı", "kayisi")],
    ("Bal ve Arı Ürünleri", "bal"): [("Çiçek Balı", "cicek-bali"), ("Petek Bal", "petek-bal")],
    ("Süt Ürünleri", "sut-urunleri"): [("Peynir", "peynir"), ("Tereyağı", "tereyagi")],
    ("Bakliyat", "bakliyat"): [("Nohut", "nohut"), ("Fasulye", "fasulye")],
}


def seed_roles():
    for name, description in ROLES.items():
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name, description=description))


def seed_categories():
    for (parent_name, parent_slug), children in CATEGORIES.items():
        parent = Category.query.filter_by(slug=parent_slug).first()
        if not parent:
            parent = Category(name=parent_name, slug=parent_slug)
            db.session.add(parent)
        for child_name, child_slug in children:
            if not Category.query.filter_by(slug=child_slug).first():
                db.session.add(Category(name=child_name, slug=child_slug, parent=parent))


def seed_all():
    seed_roles()
    seed_categories()
    db.session.commit()
