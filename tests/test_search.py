"""Hafta 12: Gelişmiş arama, filtreleme ve sıralama testleri.

Bölüm 1 — birim testleri (veritabanı yok): Türkçe metin katlama, filtre ayrıştırma, bölge dizini.
Bölüm 2 — pazar sayfası (gerçek HTTP istekleri): her filtre tek tek, birlikte, sıralamalar,
          geçersiz girdiler, sayfalama, N+1 kontrolü ve üreticinin kendi ilanlarında araması.

Çalıştırma: pytest -v tests/test_search.py
"""
import html
import re
from decimal import Decimal

import pytest

from app.utils.market_filter import MarketFilter, RegionIndex, parse_price, split_region
from app.utils.text import MAX_SEARCH_TOKENS, fold, search_tokens
from tests.conftest import login, make_listing, make_producer, make_product


def text(response):
    return response.get_data(as_text=True)


# =====================================================================================
# 1. Birim testleri
# =====================================================================================

@pytest.mark.parametrize("raw, expected", [
    ("ÇİLEK", "cilek"),
    ("Çilek", "cilek"),
    ("cilek", "cilek"),
    ("IĞDIR", "igdir"),          # büyük I önce ı olur (Türkçe kural), sonra sadeleşir
    ("İstanbul", "istanbul"),    # İ -> i  (lower() "i̇stanbul" üretirdi)
    ("Şahin Arıcılık", "sahin aricilik"),
    ("Üzüm Pekmezi", "uzum pekmezi"),
])
def test_fold_is_turkish_aware(raw, expected):
    assert fold(raw) == expected


def test_fold_keeps_like_wildcards_for_escaping():
    # Katlama %, _ ve \ karakterlerine dokunmaz; bunlar contains_pattern() ile ayrıca kaçırılır (Hafta 11)
    assert fold("100%_Organik\\") == "100%_organik\\"
    assert fold(None) is None


def test_search_tokens_split_dedupe_and_limit():
    assert search_tokens("  Organik   ÇİLEK  organik ") == ["organik", "cilek"]
    assert search_tokens("") == [] and search_tokens(None) == []
    many = " ".join(f"k{i}" for i in range(20))
    assert len(search_tokens(many)) == MAX_SEARCH_TOKENS
    assert search_tokens("x" * 500) == ["x" * 100]          # aşırı uzun girdi kesilir


@pytest.mark.parametrize("raw, expected", [
    ("12", Decimal("12.00")), ("12,5", Decimal("12.50")), ("12.5", Decimal("12.50")),
    ("1.250,75", Decimal("1250.75")), (" 7 ", Decimal("7.00")),
    ("", None), ("abc", None), ("-5", None), ("0", None), ("NaN", None), ("Infinity", None),
    ("99999999", Decimal("1000000.00")),
])
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


def test_market_filter_parses_and_cleans_arguments():
    f = MarketFilter.from_args({"q": "  taze   domates ", "kategori": "3", "il": "Bingöl", "ilce": "Genç",
                                "min_fiyat": "10", "max_fiyat": "50,5", "organik": "1", "dogrulanmis": "on",
                                "sirala": "fiyat_artan"})
    assert f.q == "taze domates" and f.tokens == ["taze", "domates"]
    assert (f.category_id, f.il, f.ilce) == (3, "Bingöl", "Genç")
    assert (f.min_price, f.max_price) == (Decimal("10.00"), Decimal("50.50"))
    assert f.organic and f.verified and f.sort == "fiyat_artan"
    assert f.is_filtered and f.active_count == 7


def test_market_filter_ignores_garbage_instead_of_failing():
    f = MarketFilter.from_args({"kategori": "abc", "min_fiyat": "x", "max_fiyat": "-3",
                                "organik": "belki", "sirala": "DROP TABLE"})
    assert f == MarketFilter()
    assert not f.is_filtered and f.sort == "yeni"


def test_market_filter_swaps_reversed_price_range_and_tells_user():
    f = MarketFilter.from_args({"min_fiyat": "200", "max_fiyat": "50"})
    assert (f.min_price, f.max_price) == (Decimal("50.00"), Decimal("200.00"))
    assert any("yer değiştirildi" in note for note in f.notes)


def test_default_sort_is_relevance_only_when_searching():
    assert MarketFilter.from_args({"q": "bal"}).sort == "ilgi"
    assert MarketFilter.from_args({}).sort == "yeni"
    assert MarketFilter.from_args({"sirala": "ilgi"}).sort == "yeni"      # aranacak kelime yokken anlamsız
    assert MarketFilter.from_args({"q": "bal", "sirala": "fiyat_azalan"}).sort == "fiyat_azalan"


def test_district_without_city_is_understood():
    f = MarketFilter.from_args({"ilce": "Bingöl / Genç"})
    assert (f.il, f.ilce) == ("Bingöl", "Genç")
    assert MarketFilter.from_args({"ilce": "Genç"}).il == ""                # il olmadan ilçe anlamsız


def test_to_args_round_trip_keeps_only_set_filters():
    original = MarketFilter.from_args({"q": "bal", "kategori": "4", "il": "Muş", "min_fiyat": "12,5",
                                       "organik": "1", "sirala": "puan"})
    args = original.to_args()
    assert args == {"q": "bal", "kategori": 4, "il": "Muş", "min_fiyat": "12.5", "organik": 1, "sirala": "puan"}
    assert MarketFilter.from_args({k: str(v) for k, v in args.items()}) == original
    assert MarketFilter().to_args() == {}


def test_chips_remove_one_filter_each():
    f = MarketFilter.from_args({"q": "bal", "il": "Bingöl", "ilce": "Genç", "organik": "1", "max_fiyat": "100"})
    chips = dict(f.chips())
    assert set(chips) == {"“bal”", "Bingöl / Genç", "0 – 100 ₺", "Organik"}
    assert "il" not in chips["Bingöl / Genç"] and "ilce" not in chips["Bingöl / Genç"]
    assert "q" not in chips["“bal”"] and chips["“bal”"].get("sirala") is None  # "ilgi" de düşer


def test_region_index_groups_free_text_spellings():
    assert split_region("Bingöl / Genç") == ("Bingöl", "Genç")
    assert split_region("Bingöl") == ("Bingöl", None)
    index = RegionIndex.build(["Bingöl / Genç", "BİNGÖL/genç", "Bingöl / Merkez", "Muş / Varto", "Bingöl", "", None])
    assert index.options() == [("Bingöl", ["Genç", "Merkez"]), ("Muş", ["Varto"])]
    assert index.raw_regions("bingol", "GENÇ") == ["Bingöl / Genç", "BİNGÖL/genç"]
    assert len(index.raw_regions("Bingöl")) == 4
    assert index.raw_regions("Ankara") == []


# =====================================================================================
# 2. Pazar sayfası
# =====================================================================================

def catalog():
    """3 üretici, 5 ilan. Fiyatlar: 25, 30, 120, 250, 400."""
    from app.extensions import db

    ali = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    ali.region, ali.is_verified, ali.review_count, ali.reputation_score = "Bingöl / Genç", True, 12, 4.8
    veli = make_producer("veli@test.com", farm_name="Veli Bahçesi")
    veli.region, veli.review_count, veli.reputation_score = "bingöl/merkez", 3, 4.0   # farklı yazım
    ayse = make_producer("ayse@test.com", farm_name="Ayşe Arıcılık")
    ayse.region = "Muş / Varto"

    tomato = make_product(ali, name="Salkım Domates", slug="domates")
    tomato.is_organic = True
    make_listing(ali, tomato, price="30", title="Organik Salkım Domates")
    make_listing(ali, make_product(ali, name="Çiçek Balı", slug="cicek-bali"), price="250", title="Yayla Balı")
    make_listing(veli, make_product(veli, name="Kayısı", slug="kayisi"), price="120", title="Kuru Kayısı")
    pepper = make_product(veli, name="Sivri Biber", slug="biber")
    pepper.description = "Közlemelik; domates ile çok iyi gider."
    make_listing(veli, pepper, price="25", title="Sivri Biber")
    comb = make_product(ayse, name="Petek Bal", slug="petek-bal")
    comb.is_organic = True
    make_listing(ayse, comb, price="400", title="Petek Bal")
    db.session.commit()
    return ali, veli, ayse


ALL_TITLES = ("Organik Salkım Domates", "Yayla Balı", "Kuru Kayısı", "Sivri Biber", "Petek Bal")


# Yalnızca ilan KARTLARINDAKİ başlıklar okunur. Sayfanın tamamında metin aramak yanıltıcıdır:
# "Petek Bal" aynı zamanda bir kategori adıdır ve filtre panelindeki kategori listesinde her zaman görünür.
CARD_TITLE = re.compile(r'<h2 class="h6 fw-semibold mb-1">(.*?)</h2>')


def cards(page):
    """Sayfadaki ilan kartlarının başlıkları, ekrandaki sırayla."""
    return [html.unescape(title) for title in CARD_TITLE.findall(page)]


def visible(client, query):
    page = text(client.get("/pazar/" + query))
    return set(cards(page)), page


def order_of(page, titles):
    return [title for title in cards(page) if title in titles]


def test_filter_by_city_and_district(client):
    catalog()
    assert visible(client, "?il=Bingöl")[0] == {"Organik Salkım Domates", "Yayla Balı", "Kuru Kayısı", "Sivri Biber"}
    assert visible(client, "?il=BİNGÖL")[0] == visible(client, "?il=bingol")[0]       # yazım farkı önemsiz
    assert visible(client, "?il=Bingöl&ilce=Merkez")[0] == {"Kuru Kayısı", "Sivri Biber"}  # "bingöl/merkez"
    assert visible(client, "?il=Muş&ilce=Varto")[0] == {"Petek Bal"}
    titles, page = visible(client, "?il=Ankara")
    assert titles == set() and "Aramanıza uyan ilan bulunamadı" in page


def test_region_options_come_from_active_producers(client):
    catalog()
    _, page = visible(client, "")
    assert '<option value="Muş"' in page and '<option value="Varto"' in page
    assert '<optgroup label="Bingöl" data-city="Bingöl">' in page


def test_filter_by_price_range(client):
    catalog()
    assert visible(client, "?min_fiyat=100&max_fiyat=260")[0] == {"Yayla Balı", "Kuru Kayısı"}
    assert visible(client, "?min_fiyat=250")[0] == {"Yayla Balı", "Petek Bal"}          # sınır dahil
    assert visible(client, "?max_fiyat=29,99")[0] == {"Sivri Biber"}                     # Türkçe ondalık
    titles, page = visible(client, "?min_fiyat=260&max_fiyat=100")                       # ters girilmiş
    assert titles == {"Yayla Balı", "Kuru Kayısı"} and "yer değiştirildi" in page


def test_filter_organic_and_verified_producer(client):
    catalog()
    assert visible(client, "?organik=1")[0] == {"Organik Salkım Domates", "Petek Bal"}
    assert visible(client, "?dogrulanmis=1")[0] == {"Organik Salkım Domates", "Yayla Balı"}
    assert visible(client, "?organik=1&dogrulanmis=1")[0] == {"Organik Salkım Domates"}


def test_parent_category_includes_children_and_filters_combine(client):
    from app.models import Category
    catalog()
    bal = Category.query.filter_by(slug="bal").one()
    assert visible(client, f"?kategori={bal.id}")[0] == {"Yayla Balı", "Petek Bal"}
    assert visible(client, f"?kategori={bal.id}&il=Bingöl")[0] == {"Yayla Balı"}
    assert visible(client, f"?kategori={bal.id}&il=Bingöl&organik=1")[0] == set()
    assert visible(client, "?kategori=99999")[0] == set(ALL_TITLES)   # olmayan kategori yok sayılır


@pytest.mark.parametrize("query", ["?q=cicek", "?q=ÇİÇEK", "?q=Çiçek", "?q=CICEK"])
def test_search_ignores_turkish_case_and_characters(client, query):
    catalog()
    assert visible(client, query)[0] == {"Yayla Balı"}     # ürün adı "Çiçek Balı"


def test_search_covers_title_product_farm_region_and_description(client):
    catalog()
    assert visible(client, "?q=kayisi")[0] == {"Kuru Kayısı"}          # başlık + ürün
    assert visible(client, "?q=veli")[0] == {"Kuru Kayısı", "Sivri Biber"}   # çiftlik adı
    assert visible(client, "?q=varto")[0] == {"Petek Bal"}             # bölge
    assert visible(client, "?q=közlemelik")[0] == {"Sivri Biber"}      # ürün açıklaması
    assert visible(client, "?q=sal")[0] == {"Organik Salkım Domates"}  # kelimenin bir parçası (partial match)


def test_every_search_word_must_match(client):
    catalog()
    assert visible(client, "?q=bal")[0] == {"Yayla Balı", "Petek Bal"}
    assert visible(client, "?q=bal petek")[0] == {"Petek Bal"}
    assert visible(client, "?q=bal yayla")[0] == {"Yayla Balı"}
    assert visible(client, "?q=bal domates")[0] == set()


def test_relevance_sort_puts_title_matches_first(client):
    catalog()
    titles, page = visible(client, "?q=domates")
    assert titles == {"Organik Salkım Domates", "Sivri Biber"}         # biberin açıklamasında geçiyor
    assert order_of(page, titles)[0] == "Organik Salkım Domates"       # varsayılan: en ilgili
    _, page = visible(client, "?q=domates&sirala=yeni")
    assert order_of(page, titles)[0] == "Sivri Biber"                  # daha yeni ilan önce


def test_sort_options(client):
    catalog()
    _, page = visible(client, "?sirala=fiyat_artan")
    assert order_of(page, ALL_TITLES) == ["Sivri Biber", "Organik Salkım Domates", "Kuru Kayısı",
                                          "Yayla Balı", "Petek Bal"]
    _, page = visible(client, "?sirala=fiyat_azalan")
    assert order_of(page, ALL_TITLES) == ["Petek Bal", "Yayla Balı", "Kuru Kayısı",
                                          "Organik Salkım Domates", "Sivri Biber"]
    _, page = visible(client, "?sirala=yeni")
    assert order_of(page, ALL_TITLES) == list(reversed(ALL_TITLES))
    for sort in ("degerlendirme", "puan"):     # Ali (12 değ., 4.8) > Veli (3, 4.0) > Ayşe (0)
        _, page = visible(client, f"?sirala={sort}")
        ranked = order_of(page, ALL_TITLES)
        assert set(ranked[:2]) == {"Organik Salkım Domates", "Yayla Balı"} and ranked[-1] == "Petek Bal"


def test_relevance_option_only_offered_when_searching(client):
    catalog()
    assert "En ilgili" not in visible(client, "")[1]
    assert "En ilgili" in visible(client, "?q=bal")[1]


def test_garbage_parameters_never_break_the_page(client):
    catalog()
    response = client.get("/pazar/?min_fiyat=abc&max_fiyat=-5&kategori=x&sirala=DROP&sayfa=-1"
                          "&organik=belki&il=" + "A" * 500 + "&q=" + "%25" * 300)
    assert response.status_code == 200


def test_active_filters_are_shown_as_removable_chips(client):
    catalog()
    _, page = visible(client, "?organik=1&il=Bingöl")
    assert page.count('title="Bu filtreyi kaldır"') == 2
    assert 'href="/pazar/?il=Bing%C3%B6l"' in page          # "Organik" etiketi kaldırılınca
    assert 'href="/pazar/?organik=1"' in page               # konum etiketi kaldırılınca
    assert "Filtreleri temizle" in page


def test_pagination_keeps_filters(client, app):
    app.config["ITEMS_PER_PAGE"] = 2
    catalog()
    _, page = visible(client, "?il=Bingöl&sirala=fiyat_artan")
    assert "4</strong> ilan bulundu" in page
    assert "sayfa=2" in page and "il=Bing%C3%B6l" in page and "sirala=fiyat_artan" in page
    second = text(client.get("/pazar/?il=Bingöl&sirala=fiyat_artan&sayfa=2"))
    assert cards(second) == ["Kuru Kayısı", "Yayla Balı"]                # Petek Bal Muş'ta, filtre dışında


def test_filtered_search_has_no_n_plus_one(client):
    from tests.test_security import query_count
    ali, veli, _ = catalog()
    url = "/pazar/?il=Bingöl&q=a&sirala=puan&min_fiyat=1"
    few = query_count(client, url)
    for i in range(6):
        make_listing(ali, make_product(ali, name=f"Ürün {i}"), title=f"Taze ürün {i}")
    assert query_count(client, url) == few


def test_producer_searches_only_own_listings(client):
    catalog()
    login(client, "ali@test.com")
    page = text(client.get("/uretici/ilanlar?q=YAYLA"))
    assert "Yayla Balı" in page and "Organik Salkım Domates" not in page
    page = text(client.get("/uretici/ilanlar?q=kayisi"))          # Veli'nin ilanı
    assert "Kuru Kayısı" not in page and "eşleşen ilan yok" in page
    page = text(client.get("/uretici/ilanlar?sirala=fiyat_azalan"))
    assert page.index("Yayla Balı") < page.index("Organik Salkım Domates")
    assert client.get("/uretici/ilanlar?sirala=gecersiz").status_code == 200
