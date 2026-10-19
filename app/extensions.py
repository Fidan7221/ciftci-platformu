"""Flask eklenti nesneleri.

Nesneler burada oluşturulur, create_app() içinde uygulamaya bağlanır.
Böylece modeller "from app.extensions import db" diyerek döngüsel
import hatasına düşmeden db nesnesine erişebilir.
"""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

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
