"""Kimlik doğrulama iş mantığı (Hafta 5).

Rotalar (routes) bu fonksiyonları çağırır; veri tabanına repository üzerinden erişilir.
Kurallar:
- Kayıt formundan yalnızca "müşteri" ve "üretici" hesabı açılabilir.
- Yönetici hesabı yalnızca terminalden açılır: flask create-admin
- Parola düz metin olarak hiçbir yerde saklanmaz (User.set_password hash'ler).
"""
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import Cart, ProducerProfile, RoleName, User
from app.repositories.user_repository import RoleRepository, UserRepository

SELF_REGISTER_ROLES = (RoleName.CUSTOMER, RoleName.PRODUCER)
_DUMMY_HASH = generate_password_hash("zamanlama-esitleme-icin-sahte-parola")


class AuthError(Exception):
    """Kullanıcıya gösterilecek hata. field doluysa hata o form alanının altında gösterilir."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def normalize_email(email):
    return (email or "").strip().lower()


def _create_user(full_name, email, password, role_name, phone=None, city=None):
    email = normalize_email(email)

    if UserRepository.email_exists(email):
        raise AuthError("Bu e-posta adresiyle kayıtlı bir hesap zaten var.", field="email")

    role = RoleRepository.get_by_name(role_name)
    if role is None:
        raise AuthError("Roller tanımlı değil. Önce terminalde 'flask seed-db' çalıştırın.")

    user = User(
        full_name=full_name.strip(),
        email=email,
        role=role,
        phone=(phone or "").strip() or None,
        city=(city or "").strip() or None,
    )
    user.set_password(password)
    return user


def register_user(full_name, email, password, role_name,
                  phone=None, city=None, farm_name=None, region=None):
    """Yeni müşteri veya üretici kaydı oluşturur ve kullanıcıyı döndürür."""
    if role_name not in SELF_REGISTER_ROLES:
        raise AuthError("Geçersiz hesap türü.", field="role")

    user = _create_user(full_name, email, password, role_name, phone, city)

    if role_name == RoleName.PRODUCER:
        user.producer_profile = ProducerProfile(
            farm_name=farm_name.strip(), region=region.strip()
        )
    else:
        user.cart = Cart()  # Her müşterinin tek sepeti olur (Hafta 7)

    UserRepository.add(user)
    UserRepository.commit()
    return user


def create_admin_user(full_name, email, password):
    """Yalnızca CLI komutundan çağrılır."""
    user = _create_user(full_name, email, password, RoleName.ADMIN)
    UserRepository.add(user)
    UserRepository.commit()
    return user


def authenticate(email, password):
    """E-posta ve parola doğruysa kullanıcıyı, değilse None döndürür.

    Kullanıcı bulunamadığında da parolası yanlış olduğunda da aynı sonuç döner;
    böylece saldırgan hangi e-postaların kayıtlı olduğunu öğrenemez.
    """
    user = UserRepository.get_by_email(normalize_email(email))
    if user is None:
        # Hafta 11: Kullanıcı yoksa da aynı maliyette bir hash kontrolü yap. Aksi halde "kayıtlı değil"
        # yanıtı ~50 ms daha hızlı döner ve saldırgan yanıt süresinden kayıtlı e-postaları çıkarabilir.
        check_password_hash(_DUMMY_HASH, password or "")
        return None
    if not user.check_password(password):
        return None
    if not user.is_active:
        raise AuthError("Hesabınız pasif durumda. Lütfen yöneticiyle iletişime geçin.")
    return user


def update_account(user, full_name, phone=None, city=None, address=None):
    """Müşteri ve yöneticinin kendi iletişim bilgilerini güncellemesi (Hafta 8)."""
    if not (full_name or "").strip():
        raise AuthError("Ad soyad zorunludur.", field="full_name")
    user.full_name = full_name.strip()
    user.phone = (phone or "").strip() or None
    user.city = (city or "").strip() or None
    user.address = (address or "").strip() or None
    UserRepository.commit()
    return user
