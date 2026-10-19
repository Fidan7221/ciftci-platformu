"""Türkçe metin arama yardımcıları (Hafta 12).

Sorun: SQLite'ın LOWER() / ILIKE işlemi yalnızca İngilizce harfleri küçültür. "ÇİLEK" ile "çilek"
eşleşmez; kullanıcı Türkçe klavyesi olmadığı için "cilek" yazarsa hiç sonuç bulamaz.

Çözüm: Hem aranan metni hem de veritabanındaki sütunu aynı "katlama" (fold) işleminden geçiririz:
    1) Türkçe kurallarla küçült:  "İ" -> "i", "I" -> "ı"   (Python'un lower() bunu yanlış yapar)
    2) Türkçe karakterleri sadeleştir: ç->c, ğ->g, ı->i, ö->o, ş->s, ü->u (şapkalı harfler de)
Böylece "ÇİLEK", "Çilek", "çilek", "cilek", "CILEK" hepsi "cilek" olur.

Veritabanı tarafında aynı fonksiyon SQLite'a `tr_fold` adıyla kaydedilir (app/extensions.py);
sorguda `func.tr_fold(Product.name).like("%cilek%")` yazılabilir.
"""
import re

_ASCII_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "â": "a", "î": "i", "û": "u", "é": "e",
})

MAX_SEARCH_LENGTH = 100   # daha uzun aramalar kesilir (gereksiz yük ve kötüye kullanım)
MAX_SEARCH_TOKENS = 5     # en fazla 5 kelime dikkate alınır


def fold(text):
    """Türkçe duyarlı küçük harf + karakter sadeleştirme.  fold("ÇİLEK Işık") -> "cilek isik" """
    if text is None:
        return None
    text = str(text).replace("İ", "i").replace("I", "ı").lower()
    return text.translate(_ASCII_MAP)


def search_tokens(query):
    """Arama kutusundaki metni katlanmış kelimelere böler.

    "  Organik  ÇİLEK  " -> ["organik", "cilek"]
    Tekrarlanan kelimeler bir kez sayılır; sıra korunur.
    """
    if not query:
        return []
    words = re.split(r"\s+", fold(query[:MAX_SEARCH_LENGTH]).strip())
    tokens = []
    for word in words:
        if word and word not in tokens:
            tokens.append(word)
    return tokens[:MAX_SEARCH_TOKENS]
