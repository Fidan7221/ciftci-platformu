"""Satış raporunun hesaplanması (Hafta 12).

Girdi: veritabanından tek sorguyla gelen sipariş KALEMİ satırları (ReportRow).
Çıktı: ekranda, CSV'de ve PDF'te aynen kullanılan SalesReport nesnesi.

Neden hesap burada (Python) da yapılıyor?
- Gün/ay gruplaması Türkiye saatine göre yapılmalı. SQL'de bu, veritabanına özgü tarih fonksiyonları
  gerektirir (SQLite: date(created_at, '+3 hours'), PostgreSQL: AT TIME ZONE). Python'da taşınabilir.
- Ekran, CSV ve PDF aynı sayıları göstermeli. Tek hesaplama = tek doğruluk kaynağı.
- Veritabanına bağlı olmadığı için birim testleri milisaniyeler içinde çalışır.
Sınır: Dönem en fazla 1 yıl ve satır sayısı REPORT_MAX_ROWS ile sınırlı (bkz. report_service).
Çok büyük veride toplamlar SQL'de GROUP BY ile yapılmalıdır (docs/ARAMA_VE_RAPORLAMA.md).

Ciro tanımı: Yalnızca ödenmiş (paid), kargoda (shipped) ve teslim edilmiş (delivered) siparişlerin
kalem tutarları (miktar × sipariş anındaki birim fiyat). Ödeme bekleyen ve iptal edilen siparişler ciroya
girmez; ayrı satırlarda gösterilir.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, NamedTuple

ZERO = Decimal("0")
CENT = Decimal("0.01")

# app/models/order.py -> OrderStatus ile aynı değerler (testte karşılaştırılır)
REVENUE_STATUSES = ("paid", "shipped", "delivered")
PENDING_STATUS = "pending"
CANCELLED_STATUS = "cancelled"
STATUS_ORDER = ("pending", "paid", "shipped", "delivered", "cancelled")

TOP_N = 10


class ReportRow(NamedTuple):
    """Bir sipariş kalemi. created_at UTC'dir (saat dilimi bilgisi olsa da olmasa da)."""
    order_id: int
    created_at: datetime
    status: str
    customer_id: int
    customer_name: str
    producer_id: int
    farm_name: str
    product_id: int
    product_name: str
    unit: str
    category_name: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def amount(self):
        return (Decimal(str(self.quantity)) * Decimal(str(self.unit_price))).quantize(CENT)


@dataclass
class OrderLine:
    order_id: int
    created_local: datetime
    status: str
    status_label: str
    customer_name: str
    farm_name: str
    item_count: int
    amount: Decimal


@dataclass
class SalesReport:
    title: str
    scope_label: str
    period: Any                          # ReportPeriod
    generated_at: datetime               # yerel saat
    is_admin: bool
    summary: dict = field(default_factory=dict)
    statuses: list = field(default_factory=list)     # [(durum, etiket, sipariş sayısı, tutar)]
    series: list = field(default_factory=list)       # [(etiket, sipariş sayısı, ciro)]
    products: list = field(default_factory=list)     # [dict]
    categories: list = field(default_factory=list)   # [(kategori, ciro, pay %)]
    producers: list = field(default_factory=list)    # [(çiftlik, sipariş sayısı, ciro, pay %)]
    orders: list = field(default_factory=list)       # [OrderLine]  (en yeni önce)
    notes: list = field(default_factory=list)

    @property
    def is_empty(self):
        return not self.orders


def _to_local(value, offset_hours):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=offset_hours))).replace(tzinfo=None)


def _share(part, total):
    if not total:
        return ZERO
    return (Decimal(part) / Decimal(total) * 100).quantize(Decimal("0.1"))


def build_report(rows, period, *, scope_label, is_admin, status_labels, utc_offset_hours=3,
                 now=None, title="Satış Raporu", notes=None):
    """Kalem satırlarından rapor üretir. rows dönem ve kapsam (üretici) filtresinden geçmiş olmalıdır."""
    now = now or datetime.now(timezone.utc)
    report = SalesReport(title=title, scope_label=scope_label, period=period,
                         generated_at=_to_local(now, utc_offset_hours), is_admin=is_admin,
                         notes=list(notes or []))

    # 1) Kalemleri siparişlere topla
    orders = {}
    for row in rows:
        order = orders.get(row.order_id)
        if order is None:
            order = orders[row.order_id] = {
                "row": row, "amount": ZERO, "items": 0, "farms": [],
                "local": _to_local(row.created_at, utc_offset_hours),
            }
        order["amount"] += row.amount
        order["items"] += 1
        if row.farm_name not in order["farms"]:
            order["farms"].append(row.farm_name)

    # 2) Durumlara göre sayılar
    by_status = {status: [0, ZERO] for status in STATUS_ORDER}
    for order in orders.values():
        bucket = by_status.setdefault(order["row"].status, [0, ZERO])
        bucket[0] += 1
        bucket[1] += order["amount"]
    report.statuses = [(status, status_labels.get(status, status), count, amount)
                       for status, (count, amount) in by_status.items()]

    # 3) Özet (yalnızca ciroya giren siparişler)
    sold = [o for o in orders.values() if o["row"].status in REVENUE_STATUSES]
    revenue = sum((o["amount"] for o in sold), ZERO)
    cancelled = by_status.get(CANCELLED_STATUS, [0, ZERO])
    pending = by_status.get(PENDING_STATUS, [0, ZERO])
    report.summary = {
        "revenue": revenue,
        "order_count": len(sold),
        "average_order": (revenue / len(sold)).quantize(CENT) if sold else ZERO,
        "customer_count": len({o["row"].customer_id for o in sold}),
        "all_order_count": len(orders),
        "pending_count": pending[0],
        "pending_amount": pending[1],
        "cancelled_count": cancelled[0],
        "cancelled_amount": cancelled[1],
        "cancel_rate": _share(cancelled[0], len(orders)),
    }

    # 4) Zaman serisi: boş günler/aylar da 0 olarak yer alır (grafikte boşluk görünür)
    series = {key: [label, 0, ZERO] for key, label in period.buckets()}
    for order in sold:
        key = period.bucket_key(order["local"].date())
        if key in series:
            series[key][1] += 1
            series[key][2] += order["amount"]
    report.series = [tuple(values) for values in series.values()]

    # 5) Ürün, kategori ve üretici kırılımları (yalnızca ciroya giren kalemler)
    products = defaultdict(lambda: {"quantity": ZERO, "revenue": ZERO, "orders": set()})
    categories = defaultdict(lambda: ZERO)
    producers = defaultdict(lambda: {"revenue": ZERO, "orders": set()})
    for row in rows:
        if row.status not in REVENUE_STATUSES:
            continue
        product = products[(row.product_id, row.product_name, row.unit, row.farm_name)]
        product["quantity"] += Decimal(str(row.quantity))
        product["revenue"] += row.amount
        product["orders"].add(row.order_id)
        categories[row.category_name] += row.amount
        producer = producers[(row.producer_id, row.farm_name)]
        producer["revenue"] += row.amount
        producer["orders"].add(row.order_id)

    ranked = sorted(products.items(), key=lambda item: (-item[1]["revenue"], item[0][1]))
    report.products = [
        {"name": name, "unit": unit, "farm_name": farm, "quantity": data["quantity"],
         "revenue": data["revenue"], "order_count": len(data["orders"]), "share": _share(data["revenue"], revenue)}
        for (_, name, unit, farm), data in ranked[:TOP_N]
    ]
    report.categories = [(name, amount, _share(amount, revenue))
                         for name, amount in sorted(categories.items(), key=lambda item: (-item[1], item[0]))]
    if is_admin:
        ranked_producers = sorted(producers.items(), key=lambda item: (-item[1]["revenue"], item[0][1]))
        report.producers = [(farm, len(data["orders"]), data["revenue"], _share(data["revenue"], revenue))
                            for (_, farm), data in ranked_producers[:TOP_N]]

    # 6) Sipariş listesi (tümü; en yeni önce)
    report.orders = [
        OrderLine(order_id=order_id, created_local=o["local"], status=o["row"].status,
                  status_label=status_labels.get(o["row"].status, o["row"].status),
                  customer_name=o["row"].customer_name, farm_name=", ".join(o["farms"]),
                  item_count=o["items"], amount=o["amount"])
        for order_id, o in sorted(orders.items(), key=lambda item: (item[1]["local"], item[0]), reverse=True)
    ]
    return report
