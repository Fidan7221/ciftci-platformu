"""Müşteri / yönetici hesap bilgileri formu (Hafta 8).

Üreticiler bu bilgileri üretici profili sayfasında (producer/profile.html) düzenler.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp


class AccountForm(FlaskForm):
    full_name = StringField("Ad Soyad", validators=[DataRequired(message="Ad soyad zorunludur."),
                                                    Length(min=3, max=100)])
    phone = StringField("Telefon", validators=[
        Optional(), Regexp(r"^0?5\d{9}$", message="Telefonu 05XXXXXXXXX biçiminde girin."),
    ])
    city = StringField("Şehir", validators=[Optional(), Length(max=50)])
    address = TextAreaField("Varsayılan teslimat adresi", validators=[
        Optional(), Length(min=10, max=255, message="Adres 10-255 karakter arasında olmalıdır."),
    ])
    submit = SubmitField("Bilgilerimi Kaydet")
