"""Ödeme formu (Hafta 9).

Kart bilgileri yalnızca bu istek süresince bellekte durur: doğrulanır, CardDetails
nesnesine çevrilir, sağlayıcıya gönderilir. Hata olsa bile forma GERİ YAZILMAZ.
"""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from app.integrations.payment_gateway import CardDetails


def digits_only(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())


def luhn_valid(number):
    """Luhn (mod 10) algoritması: kart numarasındaki yazım hatalarını sunucuya gitmeden yakalar.

    Sağdan sola her ikinci rakam iki katına çıkarılır (9'dan büyükse 9 çıkarılır),
    tüm rakamlar toplanır; toplam 10'a tam bölünüyorsa numara geçerlidir.
    """
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class PaymentForm(FlaskForm):
    holder = StringField("Kart üzerindeki ad", validators=[
        DataRequired(message="Kart sahibinin adını girin."), Length(min=3, max=60)])
    card_number = StringField("Kart numarası", validators=[DataRequired(message="Kart numarasını girin.")])
    expiry = StringField("Son kullanma (AA/YY)", validators=[
        DataRequired(message="Son kullanma tarihini girin."),
        Regexp(r"^(0[1-9]|1[0-2])\s*/\s*\d{2}$", message="AA/YY biçiminde girin (ör. 08/28)."),
    ])
    cvc = StringField("CVC", validators=[
        DataRequired(message="Güvenlik kodunu girin."),
        Regexp(r"^\d{3,4}$", message="CVC 3 veya 4 haneli olmalıdır."),
    ])
    submit = SubmitField("Ödemeyi tamamla")

    def validate_card_number(self, field):
        number = digits_only(field.data)
        if not 13 <= len(number) <= 19:
            raise ValidationError("Kart numarası 13-19 haneli olmalıdır.")
        if not luhn_valid(number):
            raise ValidationError("Kart numarası geçersiz. Lütfen kontrol edin.")

    def validate_expiry(self, field):
        try:
            month, year = (int(part) for part in field.data.replace(" ", "").split("/"))
        except ValueError:
            return  # Biçim hatasını Regexp zaten bildirir
        year += 2000
        today = date.today()
        if (year, month) < (today.year, today.month):
            raise ValidationError("Kartın son kullanma tarihi geçmiş.")

    def to_card(self):
        month, year = (int(part) for part in self.expiry.data.replace(" ", "").split("/"))
        return CardDetails(holder=self.holder.data.strip(), number=digits_only(self.card_number.data),
                           exp_month=month, exp_year=2000 + year, cvc=self.cvc.data.strip())

    def clear_sensitive(self):
        """Hatalı gönderimden sonra kart numarası ve CVC sayfaya geri yazılmasın."""
        for field in (self.card_number, self.cvc):
            field.data = ""
            field.raw_data = []
