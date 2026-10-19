"""Hafta 12: Satış/sipariş raporları ve CSV/PDF dışa aktarma testleri.

Bölüm 1 — birim testleri (veritabanı yok): dönem seçimi, rapor hesaplaması, CSV ve PDF üretimi.
Bölüm 2 — rotalar: kim neyi görür (yetki ve IDOR), sayılar, saat dilimi sınırı, indirme başlıkları,
          hız sınırı, kayıt sınırı ve N+1 kontrolü.

Çalıştırma: pytest -v tests/test_reports.py
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.reports import builder, export_pdf
from app.reports.builder import ReportRow, build_report
from app.reports.export_csv import export_csv, number, orders_table, safe_cell, to_csv
from app.reports.export_pdf import build_pdf
from app.reports.period import MAX_DAYS, ReportPeriod, parse_date, parse_period
from tests.conftest import login, make_customer, make_listing, make_producer, make_product

LABELS = {"pending": "Ödeme bekleniyor", "paid": "Ödendi", "shipped": "Kargoda",
          "delivered": "Teslim edildi", "cancelled": "İptal edildi"}
TODAY = date(2026, 10, 19)


def text(response):
    return response.get_data(as_text=True)


# =====================================================================================
# 1a. Dönem seçimi
# =====================================================================================

@pytest.mark.parametrize("preset, start, end", [
    ("7g", date(2026, 10, 13), TODAY),
    ("30g", date(2026, 9, 20), TODAY),
    ("bu_ay", date(2026, 10, 1), TODAY),
    ("gecen_ay", date(2026, 9, 1), date(2026, 9, 30)),
    ("bu_yil", date(2026, 1, 1), TODAY),
])
def test_presets(preset, start, end):
    period, notes = parse_period({"donem": preset}, TODAY)
    assert (period.start, period.end, period.preset, notes) == (start, end, preset, [])


def test_last_month_across_new_year():
    period, _ = parse_period({"donem": "gecen_ay"}, date(2027, 1, 10))
    assert (period.start, period.end) == (date(2026, 12, 1), date(2026, 12, 31))


def test_custom_range_and_default():
    period, notes = parse_period({"baslangic": "2026-10-01", "bitis": "19.10.2026"}, TODAY)
    assert (period.start, period.end, period.preset, notes) == (date(2026, 10, 1), TODAY, None, [])
    assert parse_period({}, TODAY)[0].preset == "30g"
    assert parse_date("31.02.2026") is None


@pytest.mark.parametrize("args, start, end, note", [
    ({"baslangic": "2026-10-10", "bitis": "2026-10-01"}, date(2026, 10, 1), date(2026, 10, 10), "yer değiştirildi"),
    ({"baslangic": "2026-10-10", "bitis": "2027-01-01"}, date(2026, 10, 10), TODAY, "Gelecek"),
    ({"baslangic": "2027-03-01", "bitis": "2027-02-01"}, TODAY, TODAY, "Gelecek"),
    ({"baslangic": "2020-01-01", "bitis": "2026-10-19"}, TODAY - timedelta(days=MAX_DAYS - 1), TODAY, "en fazla"),
    ({"baslangic": "dün", "bitis": "2026-10-19"}, date(2026, 9, 20), TODAY, "anlaşılamadı"),
])
def test_invalid_ranges_are_corrected_with_a_note(args, start, end, note):
    period, notes = parse_period(args, TODAY)
    assert (period.start, period.end) == (start, end)
    assert period.start <= period.end <= TODAY
    assert any(note in n for n in notes)


def test_utc_bounds_use_turkey_time():
    period = ReportPeriod(date(2026, 10, 19), date(2026, 10, 19))
    assert period.utc_bounds(3) == (datetime(2026, 10, 18, 21, 0), datetime(2026, 10, 19, 21, 0))


def test_buckets_daily_or_monthly():
    daily = ReportPeriod(date(2026, 10, 1), date(2026, 10, 19))
    assert daily.granularity == "day" and len(daily.buckets()) == 19
    assert daily.buckets()[0] == ("2026-10-01", "01.10")
    monthly = ReportPeriod(date(2026, 1, 15), TODAY)
    assert monthly.granularity == "month"
    assert [label for _, label in monthly.buckets()][-2:] == ["Eyl 2026", "Eki 2026"]
    assert len(monthly.buckets()) == 10


# =====================================================================================
# 1b. Rapor hesaplaması
# =====================================================================================

def row(order_id, status, day, hour=12, qty="1", price="10", customer=1, producer=1, product=1,
        product_name="Domates", category="Domates", farm="Ali Çiftliği", unit="kg"):
    """Yerel saatle (UTC+3) verilen anı UTC'ye çevirerek satır üretir."""
    created = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour - 3)
    return ReportRow(order_id, created, status, customer, f"Müşteri {customer}", producer, farm, product,
                     product_name, unit, category, Decimal(qty), Decimal(price))


def sample_rows():
    d = date(2026, 10, 10)
    return [
        row(1, "delivered", d, qty="2", price="20"),                        # 40
        row(1, "delivered", d, qty="1", price="15", product=2, product_name="Biber", category="Biber"),  # +15
        row(2, "paid", d, hour=23, qty="3", price="20", customer=2),        # 60 (yerel 23:00 -> aynı gün)
        row(3, "shipped", d + timedelta(days=1), hour=1, qty="1", price="25",
            producer=2, farm="Veli Bahçesi", product=3, product_name="Kayısı", category="Kayısı"),  # 25
        row(4, "cancelled", d, qty="5", price="20"),                         # 100, ciroya girmez
        row(5, "pending", d, qty="1", price="20", customer=3),               # 20, ciroya girmez
    ]


def make_report(rows=None, is_admin=True, period=None):
    period = period or ReportPeriod(date(2026, 10, 1), date(2026, 10, 19))
    return build_report(sample_rows() if rows is None else rows, period, scope_label="Tüm platform",
                        is_admin=is_admin, status_labels=LABELS, now=datetime(2026, 10, 19, 9, 0))


def test_summary_counts_only_paid_shipped_and_delivered():
    s = make_report().summary
    assert s["revenue"] == Decimal("140.00")                   # 55 + 60 + 25
    assert s["order_count"] == 3 and s["customer_count"] == 2
    assert s["average_order"] == Decimal("46.67")
    assert (s["pending_count"], s["pending_amount"]) == (1, Decimal("20.00"))
    assert (s["cancelled_count"], s["cancelled_amount"]) == (1, Decimal("100.00"))
    assert s["all_order_count"] == 5 and s["cancel_rate"] == Decimal("20.0")


def test_status_breakdown_lists_every_status():
    statuses = {status: (count, amount) for status, _, count, amount in make_report().statuses}
    assert statuses == {"pending": (1, Decimal("20.00")), "paid": (1, Decimal("60.00")),
                        "shipped": (1, Decimal("25.00")), "delivered": (1, Decimal("55.00")),
                        "cancelled": (1, Decimal("100.00"))}


def test_series_uses_local_day_and_fills_empty_days():
    report = make_report()
    series = {label: (count, amount) for label, count, amount in report.series}
    assert len(series) == 19                                   # 1-19 Ekim, boş günler dahil
    assert series["10.10"] == (2, Decimal("115.00"))           # sipariş 1 + sipariş 2 (yerel 23:00)
    assert series["11.10"] == (1, Decimal("25.00"))            # yerel 01:00 = UTC önceki gün 22:00
    assert series["05.10"] == (0, Decimal("0"))
    assert sum(amount for _, _, amount in report.series) == report.summary["revenue"]


def test_product_category_and_producer_rankings():
    report = make_report()
    assert [p["name"] for p in report.products] == ["Domates", "Kayısı", "Biber"]
    top = report.products[0]
    assert (top["quantity"], top["revenue"], top["order_count"]) == (Decimal("5"), Decimal("100.00"), 2)
    assert sum(p["share"] for p in report.products) == Decimal("100.0")
    assert report.categories[0] == ("Domates", Decimal("100.00"), Decimal("71.4"))
    assert report.producers == [("Ali Çiftliği", 2, Decimal("115.00"), Decimal("82.1")),
                                ("Veli Bahçesi", 1, Decimal("25.00"), Decimal("17.9"))]
    assert make_report(is_admin=False).producers == []         # üretici raporunda üretici kırılımı yok


def test_order_lines_newest_first_with_item_totals():
    lines = make_report().orders
    assert [line.order_id for line in lines][:2] == [3, 2]
    first = next(line for line in lines if line.order_id == 1)
    assert (first.item_count, first.amount, first.status_label) == (2, Decimal("55.00"), "Teslim edildi")


def test_empty_report():
    report = make_report(rows=[])
    assert report.is_empty and report.summary["revenue"] == 0 and report.summary["average_order"] == 0
    assert report.products == [] and all(count == 0 for _, count, _ in report.series)


def test_status_constants_match_the_model():
    from app.models import OrderStatus
    assert set(builder.REVENUE_STATUSES) == {OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED}
    assert builder.STATUS_ORDER == OrderStatus.ALL


# =====================================================================================
# 1c. CSV ve PDF
# =====================================================================================

@pytest.mark.parametrize("value, expected", [
    ("=HYPERLINK(\"http://kotu.example\")", "'=HYPERLINK(\"http://kotu.example\")"),
    ("+90 555", "'+90 555"), ("-2+3", "'-2+3"), ("@SUM(A1)", "'@SUM(A1)"), ("\tsekme", "'\tsekme"),
    ("Domates", "Domates"), (42, 42),
])
def test_csv_formula_injection_is_neutralized(value, expected):
    assert safe_cell(value) == expected


def test_csv_number_format_for_turkish_excel():
    assert number(Decimal("1234.5")) == "1234,50"
    assert number(Decimal("12.50"), None) == "12,5" and number(Decimal("100"), None) == "100"
    assert number(Decimal("71.43"), 1) == "71,4"


def test_csv_file_is_excel_friendly():
    data = to_csv(["Ürün", "Not"], [["Çilek", 'Tırnak " ve ; içerir'], ["=1+1", ""]])
    assert data.startswith(b"\xef\xbb\xbf")                    # UTF-8 BOM
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    assert rows == [["Ürün", "Not"], ["Çilek", 'Tırnak " ve ; içerir'], ["'=1+1", ""]]
    assert b"\r\n" in data


def test_csv_tables_for_admin_and_producer():
    headers, rows = orders_table(make_report(is_admin=True))
    assert "Üretici" in headers and len(rows) == 5
    headers, rows = orders_table(make_report(is_admin=False))
    assert "Üretici" not in headers
    assert rows[-1][0] == 1 and rows[-1][-1] == "55,00"           # en eski sipariş en sonda
    products = export_csv(make_report(), "urunler").decode("utf-8-sig").splitlines()
    assert products[0].startswith("Ürün;Üretici;Birim") and products[1].startswith("Domates;")
    assert export_csv(make_report(), "bilinmeyen") == export_csv(make_report(), "siparisler")


def test_pdf_is_generated_with_embedded_turkish_font():
    pdf = build_pdf(make_report(), app_name="Tarladan Sofraya")
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    assert b"DejaVuSans" in pdf                                # yazı tipi gömüldü (ğ, ş, ı, ₺ için)
    assert (export_pdf.FONT_DIR / "DejaVuSans.ttf").exists()


def test_pdf_handles_empty_and_long_reports():
    assert build_pdf(make_report(rows=[])).startswith(b"%PDF")
    many = [row(i, "delivered", date(2026, 10, 1) + timedelta(days=i % 19), customer=i % 9)
            for i in range(1, export_pdf.MAX_ORDER_ROWS + 50)]
    assert build_pdf(make_report(rows=many, is_admin=False)).startswith(b"%PDF")


def test_pdf_falls_back_to_builtin_font(monkeypatch):
    monkeypatch.setattr(export_pdf, "_FONTS", {"normal": "Helvetica", "bold": "Helvetica-Bold", "unicode": False})
    pdf = build_pdf(make_report())
    assert pdf.startswith(b"%PDF") and b"DejaVuSans" not in pdf


# =====================================================================================
# 2. Rotalar
# =====================================================================================

ADDRESS = "Yenişehir Mah. Çiçek Sok. No:5 Merkez / Bingöl"


def buy(customer, listing, qty, status, created_at):
    from app.extensions import db
    from app.services import cart_service, order_service
    cart_service.add_to_cart(customer, listing.id, Decimal(qty))
    order = order_service.place_order(customer, ADDRESS)[0]
    order.status, order.created_at = status, created_at
    db.session.commit()
    return order


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def sales_setup():
    """Ali: domates 20 TL, Veli: biber 10 TL. Son 30 günde Ali'nin cirosu 100, Veli'nin 50."""
    from app.models import OrderStatus as S
    ali = make_producer("ali@test.com", farm_name="Ali Çiftliği")
    veli = make_producer("veli@test.com", farm_name="Veli Bahçesi")
    tomato = make_listing(ali, make_product(ali, name="Salkım Domates", stock="200"), quantity="200",
                          price="20", title="Domates İlanı")
    pepper = make_listing(veli, make_product(veli, name="Sivri Biber", slug="biber", stock="200"),
                          quantity="200", price="10", title="Biber İlanı")
    ayse, mert = make_customer("ayse@test.com"), make_customer("mert@test.com")
    now = utc_now_naive() - timedelta(days=2)
    buy(ayse, tomato, "2", S.DELIVERED, now)                       # 40
    buy(mert, tomato, "3", S.PAID, now)                            # 60
    buy(ayse, pepper, "5", S.SHIPPED, now)                         # 50 (Veli)
    buy(ayse, tomato, "1", S.CANCELLED, now)                       # ciroya girmez
    buy(mert, tomato, "1", S.PENDING, now)                         # ciroya girmez
    buy(ayse, tomato, "4", S.DELIVERED, now - timedelta(days=60))  # 30 günün dışında
    return ali, veli


def admin_login(client):
    from app.services.auth_service import create_admin_user
    user = create_admin_user("Yönetici", "admin@test.com", "Yonetici123")
    login(client, "admin@test.com", "Yonetici123")
    return user


def test_report_access_by_role(client):
    sales_setup()
    assert client.get("/raporlar/").status_code == 302                          # giriş yok -> girişe
    make_customer("musteri@test.com")
    login(client, "musteri@test.com")
    assert client.get("/raporlar/").status_code == 403
    assert client.get("/raporlar/indir/csv").status_code == 403
    login(client, "ali@test.com")
    assert client.get("/raporlar/").status_code == 200
    admin_login(client)
    assert client.get("/raporlar/").status_code == 200


def test_service_numbers_for_producer_and_admin(app):
    from werkzeug.datastructures import MultiDict
    from app.services import report_service
    ali, veli = sales_setup()
    report, scope = report_service.sales_report(ali.user, MultiDict({"donem": "30g"}))
    s = report.summary
    assert (s["revenue"], s["order_count"], s["customer_count"]) == (Decimal("100.00"), 2, 2)
    assert (s["cancelled_count"], s["pending_count"], s["all_order_count"]) == (1, 1, 4)
    assert scope.label == "Ali Çiftliği" and not report.is_admin

    report, _ = report_service.sales_report(veli.user, MultiDict({"donem": "7g"}))
    assert report.summary["revenue"] == Decimal("50.00") and report.scope_label == "Veli Bahçesi"


def test_producer_sees_only_own_sales_even_with_tampered_url(client):
    ali, veli = sales_setup()
    login(client, "ali@test.com")
    for url in ("/raporlar/", f"/raporlar/?uretici={veli.id}"):     # IDOR denemesi
        page = text(client.get(url))
        assert "100,00 ₺" in page and "Ali Çiftliği" in page
        assert "Sivri Biber" not in page and "Veli Bahçesi" not in page


def test_admin_sees_platform_and_can_narrow_to_one_producer(client):
    ali, veli = sales_setup()
    admin_login(client)
    page = text(client.get("/raporlar/"))
    assert "150,00 ₺" in page and "Veli Bahçesi" in page and "Sivri Biber" in page
    assert "En çok satan üreticiler" in page
    page = text(client.get(f"/raporlar/?uretici={veli.id}"))
    assert "50,00 ₺" in page and "Salkım Domates" not in page
    assert text(client.get("/raporlar/?uretici=99999")).count("Tüm platform") >= 1   # olmayan üretici


def test_day_boundary_follows_turkey_time(client):
    """Yerel 00:30 siparişi o güne, yerel 23:59 siparişi bir önceki güne yazılır."""
    from app.models import OrderStatus as S
    ali = make_producer("ali@test.com")
    listing = make_listing(ali, make_product(ali, stock="100"), quantity="100", price="10")
    customer = make_customer("musteri@test.com")
    day = (utc_now_naive() + timedelta(hours=3)).date() - timedelta(days=3)
    midnight_utc = datetime.combine(day, datetime.min.time()) - timedelta(hours=3)   # yerel 00:00
    buy(customer, listing, "1", S.PAID, midnight_utc + timedelta(minutes=30))        # yerel 00:30 -> dahil
    buy(customer, listing, "7", S.PAID, midnight_utc - timedelta(minutes=1))         # yerel 23:59 dün -> hariç

    login(client, "ali@test.com")
    page = text(client.get(f"/raporlar/?baslangic={day.isoformat()}&bitis={day.isoformat()}"))
    assert "10,00 ₺" in page and "70,00 ₺" not in page and "80,00 ₺" not in page


def test_csv_download(client):
    sales_setup()
    login(client, "ali@test.com")
    response = client.get("/raporlar/indir/csv?donem=30g&tablo=siparisler")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment") and "satis-raporu_ali-ciftligi_" in disposition
    assert response.headers["Cache-Control"] == "no-store"
    assert response.data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(response.data.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Sipariş No", "Tarih", "Durum", "Müşteri", "Kalem Sayısı", "Tutar (TL)"]
    assert len(rows) == 1 + 4                                  # Ali'nin 30 gündeki 4 siparişi
    assert sorted(r[-1] for r in rows[1:]) == ["20,00", "20,00", "40,00", "60,00"]

    products = client.get("/raporlar/indir/csv?donem=30g&tablo=urunler").data.decode("utf-8-sig")
    assert "Salkım Domates;Ali Çiftliği;kg;5;2;100,00;100,0" in products


def test_pdf_download(client):
    sales_setup()
    admin_login(client)
    response = client.get("/raporlar/indir/pdf?donem=bu_ay")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert ".pdf" in response.headers["Content-Disposition"]
    assert client.get("/raporlar/indir/xlsx").status_code == 404


def test_invalid_dates_do_not_break_the_page(client):
    sales_setup()
    login(client, "ali@test.com")
    page = text(client.get("/raporlar/?baslangic=abc&bitis=2026-99-99"))
    assert "Tarih anlaşılamadı" in page and "100,00 ₺" in page


def test_export_rate_limit(client, app):
    app.config["REPORT_EXPORTS_PER_MIN"] = 2
    sales_setup()
    login(client, "ali@test.com")
    assert [client.get("/raporlar/indir/csv").status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/raporlar/").status_code == 200        # sayfayı görmek sınırlanmaz


def test_too_many_rows_asks_for_shorter_period(client, app):
    app.config["REPORT_MAX_ROWS"] = 2
    sales_setup()
    login(client, "ali@test.com")
    response = client.get("/raporlar/?donem=30g")
    assert response.status_code == 200 and "daha kısa bir dönem" in text(response)
    assert client.get("/raporlar/indir/csv?donem=30g").status_code == 302


def test_empty_period_message(client):
    make_producer("ali@test.com")
    login(client, "ali@test.com")
    assert "Bu dönemde sipariş yok" in text(client.get("/raporlar/?donem=7g"))


def test_report_page_has_no_n_plus_one(client):
    from app.models import OrderStatus as S
    from tests.test_security import query_count
    ali, veli = sales_setup()
    admin_login(client)
    few = query_count(client, "/raporlar/")
    customer = make_customer("yeni@test.com")
    listing = ali.products[0].listings[0]
    for _ in range(6):
        buy(customer, listing, "1", S.DELIVERED, utc_now_naive())
    assert query_count(client, "/raporlar/") == few


def test_navigation_links_to_reports(client):
    make_producer("ali@test.com")
    login(client, "ali@test.com")
    assert 'href="/raporlar/"' in text(client.get("/uretici/panel"))


def test_report_date_index_exists(app):
    from sqlalchemy import inspect
    from app.extensions import db
    indexes = {tuple(index["column_names"]) for index in inspect(db.engine).get_indexes("orders")}
    assert ("created_at",) in indexes
