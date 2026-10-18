"""Üretici profili ve ürün formları (Hafta 6)."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import (
    BooleanField, DecimalField, SelectField, StringField, SubmitField, TextAreaField,
)
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional, Regexp

from app.models import Unit

ALLOWED_IMAGES = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ProducerProfileForm(FlaskForm):
    full_name = StringField("Ad Soyad", validators=[DataRequired(message="Ad soyad zorunludur."),
                                                    Length(min=3, max=100)])
    phone = StringField("Telefon", validators=[
        Optional(), Regexp(r"^0?5\d{9}$", message="Telefonu 05XXXXXXXXX biçiminde girin."),
    ])
    city = StringField("Şehir", validators=[Optional(), Length(max=50)])
    farm_name = StringField("Çiftlik / İşletme adı",
                            validators=[DataRequired(message="Çiftlik adı zorunludur."), Length(max=120)])
    region = StringField("Bölge (İl / İlçe)",
                         validators=[DataRequired(message="Bölge zorunludur."), Length(max=80)])
    tax_number = StringField("Vergi / TC kimlik no", validators=[
        Optional(), Regexp(r"^\d{10,11}$", message="10 veya 11 haneli bir numara girin."),
    ])
    description = TextAreaField("Çiftliğinizi tanıtın", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Profili Kaydet")


class ProductForm(FlaskForm):
    name = StringField("Ürün adı", validators=[DataRequired(message="Ürün adı zorunludur."),
                                               Length(min=2, max=120)])
    # Seçenekler rotada category_service.product_category_choices() ile doldurulur
    category_id = SelectField("Kategori", coerce=int,
                              validators=[DataRequired(message="Kategori seçin.")])
    unit = SelectField("Satış birimi", choices=Unit.CHOICES, default=Unit.KG)
    # InputRequired: DataRequired 0 değerini "boş" sayardı; stok 0 olabilmeli
    stock_quantity = DecimalField(
        "Stok miktarı", places=2,
        validators=[InputRequired(message="Stok miktarı girin."),
                    NumberRange(min=0, message="Stok negatif olamaz.")],
    )
    description = TextAreaField("Açıklama", validators=[Optional(), Length(max=2000)])
    is_organic = BooleanField("Organik ürün")
    is_active = BooleanField("Satışa açık", default=True)
    image = FileField("Ürün görseli", validators=[
        FileAllowed(ALLOWED_IMAGES, "Yalnızca JPG, PNG veya WEBP yükleyebilirsiniz."),
        FileSize(max_size=MAX_IMAGE_BYTES, message="Görsel en fazla 5 MB olabilir."),
    ])
    remove_image = BooleanField("Mevcut görseli kaldır")
    submit = SubmitField("Kaydet")


class DeleteForm(FlaskForm):
    """Silme düğmeleri için yalnızca CSRF anahtarı taşıyan boş form."""

    submit = SubmitField("Sil")
