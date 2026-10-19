"""Pazar yeri filtreleri (Hafta 12): URL parametrelerini doğrulanmış bir filtre nesnesine çevirir.

Neden ayrı bir sınıf?
- Rota, servis, depo (repository) ve şablon aynı filtre nesnesini paylaşır; parametre adları tek yerde.
- Kullanıcı adres çubuğuna her şeyi yazabilir (?min_fiyat=abc&sirala=DROP). Geçersiz değer hata
  (500) üretmez; sessizce yok sayılır ya da düzeltilir ve kullanıcıya not olarak gösterilir.
- Veritabanına bağımlı değildir; birim testleri çok hızlı çalışır.

URL parametreleri:
    q            arama metni               kategori     kategori id (üst kategori alt kategorileri kapsar)
    il, ilce     üreticinin bölgesi        min_fiyat    birim fiyat alt sınırı (TL, "12,5" de olur)
    max_fiyat    birim fiyat üst sınırı    organik=1    yalnızca organik ürünler
    dogrulanmis=1  yalnızca doğrulanmış (sertifikalı) üreticiler
    sirala       yeni | fiyat_artan | fiyat_azalan | degerlendirme | puan | ilgi
"""
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation

from app.utils.text import fold, search_tokens

SORT_OPTIONS = {
    "ilgi": "En ilgili",
    "yeni": "En yeni",
    "fiyat_artan": "Fiyat: düşükten yükseğe",
    "fiyat_azalan": "Fiyat: yüksekten düşüğe",
    "degerlendirme": "En çok değerlendirilen",
    "puan": "En yüksek puanlı üretici",
}

MAX_PRICE = Decimal("1000000")
_TRUE_VALUES = {"1", "on", "true", "evet"}
_MAX_TEXT = 60


def _clean_text(value, limit=_MAX_TEXT):
    return " ".join((value or "").split())[:limit]


def parse_price(value):
    """'12,5' / '12.50' / ' 7 ' -> Decimal; boş, negatif, sıfır veya geçersiz -> None."""
    text = (value or "").strip().replace(" ", "")
    if not text:
        return None
    if "," in text:                       # Türkçe yazım: 1.250,50  -> 1250.50
        text = text.replace(".", "").replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0:
        return None
    return min(number, MAX_PRICE).quantize(Decimal("0.01"))


def _parse_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def split_region(region):
    """'Bingöl / Genç' -> ('Bingöl', 'Genç');  'Bingöl' -> ('Bingöl', None)."""
    parts = [part.strip() for part in (region or "").split("/")]
    city = parts[0] if parts and parts[0] else None
    district = parts[1] if len(parts) > 1 and parts[1] else None
    return city, district


@dataclass(frozen=True)
class MarketFilter:
    q: str = ""
    category_id: int | None = None
    il: str = ""
    ilce: str = ""
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    organic: bool = False
    verified: bool = False
    sort: str = "yeni"
    notes: tuple = field(default=(), compare=False)   # kullanıcıya gösterilecek düzeltmeler

    # --- Oluşturma ------------------------------------------------------------------

    @classmethod
    def from_args(cls, args):
        """request.args (veya herhangi bir sözlük) -> MarketFilter"""
        notes = []
        q = _clean_text(args.get("q"), 100)
        min_price = parse_price(args.get("min_fiyat"))
        max_price = parse_price(args.get("max_fiyat"))
        if min_price is not None and max_price is not None and min_price > max_price:
            min_price, max_price = max_price, min_price
            notes.append("En düşük fiyat en yüksek fiyattan büyüktü; değerler yer değiştirildi.")

        il = _clean_text(args.get("il"))
        ilce = _clean_text(args.get("ilce"))
        if ilce and not il:            # yalnızca ilçe gelmiş: "Bingöl / Genç" biçimindeyse il çıkarılır
            il, ilce = split_region(ilce) if "/" in ilce else ("", ilce)
            il, ilce = il or "", ilce or ""

        sort = args.get("sirala") or ("ilgi" if q else "yeni")
        if sort not in SORT_OPTIONS or (sort == "ilgi" and not search_tokens(q)):
            sort = "ilgi" if search_tokens(q) else "yeni"

        return cls(
            q=q,
            category_id=_parse_int(args.get("kategori")),
            il=il,
            ilce=ilce if il else "",
            min_price=min_price,
            max_price=max_price,
            organic=(args.get("organik") or "").lower() in _TRUE_VALUES,
            verified=(args.get("dogrulanmis") or "").lower() in _TRUE_VALUES,
            sort=sort,
            notes=tuple(notes),
        )

    # --- Kullanım --------------------------------------------------------------------

    @property
    def tokens(self):
        return search_tokens(self.q)

    @property
    def is_filtered(self):
        """Arama veya herhangi bir filtre seçili mi? (Boş sonuç mesajını seçmek için.)"""
        return bool(self.tokens or self.category_id or self.il or self.min_price or self.max_price
                    or self.organic or self.verified)

    @property
    def active_count(self):
        """Filtre panelindeki rozet: kaç filtre seçili (arama ve sıralama hariç)."""
        return sum(bool(x) for x in (self.category_id, self.il, self.ilce, self.min_price,
                                     self.max_price, self.organic, self.verified))

    def without(self, *names):
        """Belirtilen filtreler kaldırılmış kopya (etiketlerdeki ✕ bağlantısı için)."""
        defaults = {"q": "", "category_id": None, "il": "", "ilce": "", "min_price": None,
                    "max_price": None, "organic": False, "verified": False}
        changes = {name: defaults[name] for name in names}
        if "il" in names:
            changes["ilce"] = ""
        result = replace(self, notes=(), **changes)
        if "q" in names and result.sort == "ilgi":
            result = replace(result, sort="yeni")
        return result

    def to_args(self, **extra):
        """url_for() için yalnızca dolu parametreler (adres kısa ve okunur kalır)."""
        args = {}
        if self.q:
            args["q"] = self.q
        if self.category_id:
            args["kategori"] = self.category_id
        if self.il:
            args["il"] = self.il
        if self.ilce:
            args["ilce"] = self.ilce
        if self.min_price is not None:
            args["min_fiyat"] = _price_arg(self.min_price)
        if self.max_price is not None:
            args["max_fiyat"] = _price_arg(self.max_price)
        if self.organic:
            args["organik"] = 1
        if self.verified:
            args["dogrulanmis"] = 1
        default_sort = "ilgi" if self.tokens else "yeni"
        if self.sort != default_sort:
            args["sirala"] = self.sort
        args.update(extra)
        return args

    def chips(self, category_name=None):
        """Seçili filtreler: [(etiket, kaldırılınca oluşan url argümanları), ...]"""
        chips = []
        if self.q:
            chips.append((f"“{self.q}”", self.without("q").to_args()))
        if self.category_id:
            chips.append((category_name or "Kategori", self.without("category_id").to_args()))
        if self.il:
            label = f"{self.il} / {self.ilce}" if self.ilce else self.il
            chips.append((label, self.without("il").to_args()))
        if self.min_price is not None or self.max_price is not None:
            low = _price_label(self.min_price) if self.min_price is not None else "0"
            high = _price_label(self.max_price) if self.max_price is not None else "∞"
            chips.append((f"{low} – {high} ₺", self.without("min_price", "max_price").to_args()))
        if self.organic:
            chips.append(("Organik", self.without("organic").to_args()))
        if self.verified:
            chips.append(("Doğrulanmış üretici", self.without("verified").to_args()))
        return chips


def _price_arg(value):
    return f"{value:f}".rstrip("0").rstrip(".")


def _price_label(value):
    return _price_arg(value).replace(".", ",")


# --- Bölge (il / ilçe) dizini ----------------------------------------------------------

@dataclass
class RegionIndex:
    """Üreticilerin serbest metin bölgelerinden il → ilçe seçenekleri.

    Üretici bölgeyi elle yazar: "Bingöl / Genç", "bingöl/genç", "BİNGÖL". Hepsi aynı il sayılmalı.
    Bu yüzden karşılaştırma fold() ile yapılır; ekranda ilk görülen yazım gösterilir.
    Filtrelemede ise veritabanındaki ham değerler kullanılır: region IN ('Bingöl / Genç', 'bingöl/genç').
    """
    cities: dict = field(default_factory=dict)  # il_anahtarı -> {"name", "districts": {anahtar: ad}, "raw": {anahtar: set}}

    @classmethod
    def build(cls, regions):
        index = cls()
        for raw in sorted(set(r for r in regions if r)):
            city, district = split_region(raw)
            if not city:
                continue
            entry = index.cities.setdefault(fold(city), {"name": city, "districts": {}, "raw": {}})
            key = fold(district) if district else ""
            if district:
                entry["districts"].setdefault(key, district)
            entry["raw"].setdefault(key, set()).add(raw)
        index.cities = dict(sorted(index.cities.items(), key=lambda item: item[0]))
        return index

    def options(self):
        """Şablon için: [(il, [ilçe, ...]), ...] alfabetik."""
        return [(entry["name"], sorted(entry["districts"].values(), key=fold))
                for entry in self.cities.values()]

    def raw_regions(self, city, district=None):
        """Filtreye uyan ham bölge metinleri; il bilinmiyorsa [] (sonuç da boş olur)."""
        entry = self.cities.get(fold(city or ""))
        if entry is None:
            return []
        if district:
            return sorted(entry["raw"].get(fold(district), set()))
        return sorted(set().union(*entry["raw"].values()))
