"""Yönetici formları (Hafta 6: kategori yönetimi)."""
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp


class CategoryForm(FlaskForm):
    name = StringField("Kategori adı", validators=[DataRequired(message="Kategori adı zorunludur."),
                                                   Length(min=2, max=60)])
    slug = StringField("URL adı (slug)", validators=[
        Optional(), Length(max=60),
        Regexp(r"^[a-z0-9-]+$", message="Yalnızca küçük harf, rakam ve tire kullanın."),
    ])
    # 0 = üst kategori yok. Seçenekler rotada doldurulur.
    parent_id = SelectField("Üst kategori", coerce=int, default=0)
    submit = SubmitField("Kaydet")
