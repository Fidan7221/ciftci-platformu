"""Raporun CSV olarak dışa aktarılması (Hafta 12).

Türkçe Excel ile sorunsuz açılsın diye üç ayar:
1) Kodlama UTF-8 + BOM ("utf-8-sig"): BOM olmazsa Excel dosyayı ANSI sanar, "Çiftçi" -> "Ã‡iftÃ§i" olur.
2) Ayırıcı noktalı virgül (;): Türkçe bölge ayarında virgül ondalık ayırıcıdır; sütun ayırıcı olamaz.
3) Sayılar "1234,50" biçiminde (binlik ayırıcı yok): Excel sayıyı metin değil sayı olarak tanır.

Güvenlik — CSV/formül enjeksiyonu (CWE-1236):
Ürün adını üretici yazar. Ad "=HYPERLINK(...)" ya da "=cmd|..." ile başlarsa Excel bunu formül olarak
çalıştırabilir. Bu yüzden =, +, -, @, sekme ve satır başı ile başlayan metinlerin başına ' eklenir.
"""
import csv
import io
from decimal import Decimal

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Kullanıcıdan gelen metni formül olarak yorumlanamayacak hâle getirir."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def number(value, places=2):
    """Decimal('1234.5') -> '1234,50'   (places=None: gereksiz sıfırlar atılır: 12.50 -> '12,5')"""
    value = Decimal(str(value or 0))
    if places is None:
        text = f"{value.quantize(Decimal('0.01')):f}"
        text = text.rstrip("0").rstrip(".") if "." in text else text
    else:
        text = f"{value.quantize(Decimal(1).scaleb(-places)):f}"
    return text.replace(".", ",")


def to_csv(headers, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return buffer.getvalue().encode("utf-8-sig")


# --- Dışa aktarılabilen tablolar --------------------------------------------------------

def orders_table(report):
    headers = ["Sipariş No", "Tarih", "Durum", "Müşteri"]
    if report.is_admin:
        headers.append("Üretici")
    headers += ["Kalem Sayısı", "Tutar (TL)"]
    rows = []
    for line in report.orders:
        row = [line.order_id, f"{line.created_local:%d.%m.%Y %H:%M}", line.status_label, line.customer_name]
        if report.is_admin:
            row.append(line.farm_name)
        row += [line.item_count, number(line.amount)]
        rows.append(row)
    return headers, rows


def products_table(report):
    headers = ["Ürün", "Üretici", "Birim", "Satılan Miktar", "Sipariş Sayısı", "Ciro (TL)", "Ciro Payı (%)"]
    rows = [[p["name"], p["farm_name"], p["unit"], number(p["quantity"], None), p["order_count"],
             number(p["revenue"]), number(p["share"], 1)] for p in report.products]
    return headers, rows


def series_table(report):
    label = "Gün" if report.period.granularity == "day" else "Ay"
    headers = [label, "Sipariş Sayısı", "Ciro (TL)"]
    return headers, [[name, count, number(amount)] for name, count, amount in report.series]


EXPORT_TABLES = {
    "siparisler": ("Siparişler", orders_table),
    "urunler": ("En çok satan ürünler", products_table),
    "donemler": ("Günlük / aylık ciro", series_table),
}


def export_csv(report, table="siparisler"):
    _, builder = EXPORT_TABLES.get(table, EXPORT_TABLES["siparisler"])
    return to_csv(*builder(report))
