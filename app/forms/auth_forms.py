"""Kayıt ve giriş formları (Flask-WTF).

Formlar yalnızca girdinin BİÇİMİNİ doğrular (boş mu, e-posta mı, uzunluk...).
"Bu e-posta zaten kayıtlı mı?" gibi veri tabanı gerektiren kontroller
iş mantığı katmanında (auth_service) yapılır.
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, RadioField, StringField, SubmitField
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError,
)

from app.models import RoleName


def strong_password(form, field):
    """Parola en az bir harf ve bir rakam içermeli."""
    value = field.data or ""
    if not any(ch.isalpha() for ch in value) or not any(ch.isdigit() for ch in value):
        raise ValidationError("Parola en az bir harf ve bir rakam içermelidir.")


class RegistrationForm(FlaskForm):
    role = RadioField(
        "Hesap türü",
        choices=[(RoleName.CUSTOMER, "Müşteri"), (RoleName.PRODUCER, "Üretici / Çiftçi")],
        default=RoleName.CUSTOMER,
        validators=[DataRequired(message="Hesap türü seçin.")],
    )
    full_name = StringField(
        "Ad Soyad",
        validators=[DataRequired(message="Ad soyad zorunludur."), Length(min=3, max=100)],
    )
    email = EmailField(
        "E-posta",
        validators=[
            DataRequired(message="E-posta zorunludur."),
            Email(message="Geçerli bir e-posta adresi girin."),
            Length(max=120),
        ],
    )
    phone = StringField(
        "Telefon",
        validators=[
            Optional(),
            Regexp(r"^0?5\d{9}$", message="Telefonu 05XXXXXXXXX biçiminde girin."),
        ],
    )
    city = StringField("Şehir", validators=[Optional(), Length(max=50)])

    # Yalnızca üretici seçilirse zorunlu (aşağıdaki validate_ metotlarına bakın).
    # Burada Optional() KULLANILMAZ; çünkü Optional boş alanda tüm kontrolleri durdurur.
    farm_name = StringField("Çiftlik / İşletme adı", validators=[Length(max=120)])
    region = StringField("Bölge (İl / İlçe)", validators=[Length(max=80)])

    password = PasswordField(
        "Parola",
        validators=[
            DataRequired(message="Parola zorunludur."),
            Length(min=8, max=128, message="Parola en az 8 karakter olmalıdır."),
            strong_password,
        ],
    )
    confirm_password = PasswordField(
        "Parola (tekrar)",
        validators=[
            DataRequired(message="Parolayı tekrar girin."),
            EqualTo("password", message="Parolalar eşleşmiyor."),
        ],
    )
    accept_terms = BooleanField(
        "Kullanım koşullarını ve KVKK aydınlatma metnini okudum, kabul ediyorum.",
        validators=[DataRequired(message="Devam etmek için koşulları kabul etmelisiniz.")],
    )
    submit = SubmitField("Kayıt Ol")

    # WTForms, "validate_<alan_adı>" isimli metotları o alanın ek kuralı olarak çalıştırır
    def validate_farm_name(self, field):
        if self.role.data == RoleName.PRODUCER and not (field.data or "").strip():
            raise ValidationError("Üretici hesabı için çiftlik adı zorunludur.")

    def validate_region(self, field):
        if self.role.data == RoleName.PRODUCER and not (field.data or "").strip():
            raise ValidationError("Üretici hesabı için bölge zorunludur.")


class LoginForm(FlaskForm):
    email = EmailField(
        "E-posta",
        validators=[DataRequired(message="E-posta zorunludur."), Email(message="Geçerli bir e-posta girin.")],
    )
    password = PasswordField("Parola", validators=[DataRequired(message="Parola zorunludur.")])
    remember_me = BooleanField("Beni hatırla")
    submit = SubmitField("Giriş Yap")


class LogoutForm(FlaskForm):
    """Yalnızca CSRF anahtarı taşır; çıkış işlemi POST ile yapılır."""

    submit = SubmitField("Çıkış")
