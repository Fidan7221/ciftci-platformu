"""İlan formu (Hafta 7)."""
from datetime import date
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional


class ListingForm(FlaskForm):
    # Seçenekler rotada listing_service.product_choices() ile doldurulur
    product_id = SelectField("Ürün", coerce=int, validators=[DataRequired(message="Ürün seçin.")])
    title = StringField("İlan başlığı", validators=[Optional(), Length(max=150)],
                        description="Boş bırakırsanız ürün adı kullanılır.")
    price = DecimalField("Birim fiyatı (₺)", places=2, validators=[
        InputRequired(message="Fiyat girin."),
        NumberRange(min=0.01, message="Fiyat sıfırdan büyük olmalıdır."),
    ])
    stock_quantity = DecimalField("Satışa ayrılan miktar", places=2, validators=[
        InputRequired(message="Miktar girin."),
        NumberRange(min=0, message="Miktar negatif olamaz."),
    ])
    min_order_quantity = DecimalField("En az sipariş miktarı", places=2, default=Decimal("1"), validators=[
        InputRequired(message="En az sipariş miktarını girin."),
        NumberRange(min=0.01, message="Sıfırdan büyük olmalıdır."),
    ])
    start_date = DateField("Başlangıç tarihi", default=date.today,
                           validators=[DataRequired(message="Başlangıç tarihi girin.")])
    end_date = DateField("Bitiş tarihi", validators=[Optional()],
                         description="Boş bırakırsanız ilan siz kapatana kadar açık kalır.")
    is_active = BooleanField("Satışta (aktif)", default=True)
    submit = SubmitField("Kaydet")


class ToggleForm(FlaskForm):
    """Aktif/pasif düğmesi için yalnızca CSRF anahtarı taşıyan form."""

    submit = SubmitField("Değiştir")
