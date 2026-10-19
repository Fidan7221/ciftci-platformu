"""Flask eklenti nesneleri.

Nesneler burada oluşturulur, create_app() içinde uygulamaya bağlanır.
Böylece modeller "from app.extensions import db" diyerek döngüsel
import hatasına düşmeden db nesnesine erişebilir.
"""
import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.utils.text import fold

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# Giriş yapmamış kullanıcı korumalı sayfaya girerse yönlendirilecek yer (Hafta 5)
login_manager.login_view = "auth.login"
login_manager.login_message = "Bu sayfayı görmek için giriş yapmalısınız."
login_manager.login_message_category = "warning"
# Hafta 11: Oturum çerezi başka bir tarayıcı/IP'ye taşınırsa (çalınırsa) oturum geçersiz sayılır
login_manager.session_protection = "strong"


@event.listens_for(Engine, "connect")
def register_sqlite_functions(dbapi_connection, _record):
    """Hafta 12: Her yeni SQLite bağlantısına Türkçe arama için tr_fold() fonksiyonunu ekler.

    Sorguda func.tr_fold(Product.name).like("%cilek%") yazılabilir (bkz. app/utils/text.py).
    deterministic=True: aynı girdi hep aynı sonucu verir; SQLite sorguyu buna göre planlayabilir.
    PostgreSQL'e geçilirse bu fonksiyonun SQL tarafında ayrıca tanımlanması gerekir.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function("tr_fold", 1, fold, deterministic=True)
