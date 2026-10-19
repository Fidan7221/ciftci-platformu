"""Veri tabanını tek adımda hazırlama (Hafta 13).

Hem `flask kurulum` komutu hem de masaüstü uygulaması bu fonksiyonu kullanır:

    prepare_database(reset=False, demo=False)

1. reset=True ise TÜM tablolar silinir (geri alınamaz; komut onay ister).
2. Eksik tablolar oluşturulur (var olanlara dokunulmaz — tekrar çalıştırmak güvenlidir).
3. stamp=True ise (flask kurulum), proje klasöründe migrations/ varsa ve veri tabanı yeni oluşturulduysa
   Alembic "head" olarak işaretlenir. Böylece sonraki `flask db upgrade` aynı tabloları ikinci kez oluşturmaya çalışmaz.
4. Roller ve kategoriler eklenir; demo=True ise demo hesapları, ürünler, fiyatlar, tahminler, siparişler.
"""
import os

from flask import current_app
from sqlalchemy import inspect

from app.extensions import db


def _model_tables():
    return set(db.metadata.tables)


def _stamp_migrations_if_new(was_empty):
    """Yeni oluşturulan veri tabanını Alembic'e "güncel" olarak tanıt (yalnızca migrations/ varsa).

    Not: Alembic'in env.py dosyası logging.config.fileConfig() çağırır ve mevcut logger'ları kapatır.
    Bu yüzden yalnızca `flask kurulum` komutunda (kısa ömürlü süreç) yapılır; masaüstü uygulamasında yapılmaz.
    """
    if not was_empty or current_app.testing:
        return False
    directory = os.path.join(os.path.dirname(current_app.root_path), "migrations")
    if not os.path.isdir(directory):
        return False                  # .exe paketinde migrations/ yoktur; gerek de yoktur
    from flask_migrate import stamp
    stamp(directory=directory)
    return True


def prepare_database(reset=False, demo=False, stamp=False):
    """Veri tabanını hazırlar ve ne yapıldığını özetleyen bir sözlük döndürür.
    stamp=True: yeni veri tabanını Alembic'e "head" olarak işaretle (yalnızca `flask kurulum`)."""
    from app.models import Category, Listing, Order, User
    from scripts.seed_data import seed_all

    if reset:
        db.session.remove()
        db.drop_all()

    existing = set(inspect(db.engine).get_table_names())
    was_empty = not (existing & _model_tables())
    db.create_all()
    created = sorted(_model_tables() - existing)
    stamped = _stamp_migrations_if_new(was_empty) if stamp else False

    seed_all()
    accounts = {}
    if demo:
        from scripts.demo_data import seed_demo
        accounts = seed_demo()

    summary = {
        "reset": reset,
        "created_tables": created,
        "stamped": stamped,
        "users": User.query.count(),
        "categories": Category.query.count(),
        "listings": Listing.query.count(),
        "orders": Order.query.count(),
        "demo_accounts": accounts,
    }
    current_app.logger.info("Veri tabanı hazırlandı: %s", {k: v for k, v in summary.items() if k != "demo_accounts"})
    return summary
