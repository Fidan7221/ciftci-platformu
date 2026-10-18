"""Sepet, ödeme ve sipariş durumu formları (Hafta 7)."""
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, HiddenField, SubmitField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, InputRequired, Length, NumberRange, Optional

from app.models import OrderStatus


class AddToCartForm(FlaskForm):
    quantity = DecimalField("Miktar", places=2, default=Decimal("1"), validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0.01, message="Miktar sıfırdan büyük olmalıdır."),
    ])
    submit = SubmitField("Sepete ekle")


class UpdateCartItemForm(FlaskForm):
    # 0 girilirse kalem sepetten çıkarılır
    quantity = DecimalField("Miktar", places=2, validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0, message="Miktar negatif olamaz."),
    ])
    submit = SubmitField("Güncelle")


class RemoveCartItemForm(FlaskForm):
    submit = SubmitField("Çıkar")


class CheckoutForm(FlaskForm):
    shipping_address = TextAreaField("Teslimat adresi", validators=[
        DataRequired(message="Teslimat adresi zorunludur."),
        Length(min=10, max=255, message="Adres 10-255 karakter arasında olmalıdır."),
    ])
    note = TextAreaField("Üreticiye not", validators=[Optional(), Length(max=255)])
    save_address = BooleanField("Bu adresi sonraki siparişlerim için kaydet", default=True)
    submit = SubmitField("Siparişi onayla")


class OrderStatusForm(FlaskForm):
    status = HiddenField(validators=[
        DataRequired(), AnyOf(OrderStatus.ALL, message="Geçersiz durum."),
    ])
    submit = SubmitField("Uygula")
