"""Satış ve sipariş raporları iş mantığı (Hafta 12).

Kapsam (kim neyi görür?) — rotada değil burada belirlenir:
- Yönetici: tüm platform. İsterse ?uretici=<id> ile tek bir üreticiye daraltabilir.
- Üretici : yalnızca KENDİ kalemleri. URL'de ?uretici=<başka id> gönderse bile yok sayılır;
            kapsam her zaman current_user.producer_profile'dan gelir (IDOR koruması).
- Müşteri : rapor sayfasına hiç giremez (rota @role_required ile 403 verir).

Akış: parse_period -> ReportRepository.order_item_rows (tek sorgu) -> build_report -> ekran / CSV / PDF
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from app.models import OrderStatus
from app.reports.builder import build_report
from app.reports.export_csv import EXPORT_TABLES, export_csv
from app.reports.export_pdf import build_pdf
from app.reports.period import parse_period
from app.repositories.report_repository import ReportRepository
from app.services.category_service import slugify
from app.services.errors import ServiceError


@dataclass
class ReportScope:
    producer: Any                # ProducerProfile ya da None (tüm platform)
    is_admin: bool

    @property
    def label(self):
        return self.producer.farm_name if self.producer else "Tüm platform"

    @property
    def slug(self):
        return slugify(self.producer.farm_name) if self.producer else "platform"

    def to_args(self):
        """Yönetici bir üreticiye daralttıysa indirme bağlantılarında da korunur."""
        return {"uretici": self.producer.id} if self.is_admin and self.producer else {}


def resolve_scope(user, args):
    if user.is_admin:
        producer_id = args.get("uretici", type=int)
        producer = ReportRepository.get_producer(producer_id) if producer_id else None
        return ReportScope(producer=producer, is_admin=True)
    if user.is_producer and user.producer_profile is not None:
        return ReportScope(producer=user.producer_profile, is_admin=False)  # args["uretici"] yok sayılır
    raise ServiceError("Raporları yalnızca üreticiler ve yöneticiler görebilir.")


def local_today(now=None):
    offset = current_app.config.get("DISPLAY_UTC_OFFSET_HOURS", 3)
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=offset)).date()


def sales_report(user, args, now=None):
    """(rapor, kapsam) döndürür. Kayıt sınırı aşılırsa ServiceError."""
    scope = resolve_scope(user, args)
    offset = current_app.config.get("DISPLAY_UTC_OFFSET_HOURS", 3)
    period, notes = parse_period(args, local_today(now))
    start_utc, end_utc = period.utc_bounds(offset)

    max_rows = current_app.config.get("REPORT_MAX_ROWS", 50_000)
    rows = ReportRepository.order_item_rows(
        start_utc, end_utc, scope.producer.id if scope.producer else None, limit=max_rows + 1)
    if len(rows) > max_rows:
        # Kesip eksik toplam göstermek yanıltıcı olurdu; kullanıcıdan dönemi daraltması istenir.
        raise ServiceError(f"Seçilen dönemde {max_rows:,} kalemden fazla kayıt var. "
                           f"Lütfen daha kısa bir dönem seçin.".replace(",", "."))

    report = build_report(rows, period, scope_label=scope.label, is_admin=scope.is_admin,
                          status_labels=OrderStatus.LABELS, utc_offset_hours=offset, now=now,
                          title="Satış ve Sipariş Raporu", notes=notes)
    return report, scope


# --- Dışa aktarma ----------------------------------------------------------------------

EXPORT_FORMATS = ("csv", "pdf")


def export(report, scope, fmt, table=None):
    """(içerik bytes, MIME türü, dosya adı)"""
    base = f"satis-raporu_{scope.slug}_{report.period.slug}"
    if fmt == "csv":
        table = table if table in EXPORT_TABLES else "siparisler"
        return export_csv(report, table), "text/csv; charset=utf-8", f"{base}_{table}.csv"
    if fmt == "pdf":
        return build_pdf(report, current_app.config.get("APP_NAME", "")), "application/pdf", f"{base}.pdf"
    raise ValueError(f"Bilinmeyen biçim: {fmt}")


def chart_data(report):
    """Ekrandaki grafik için JSON'a çevrilebilir veri."""
    return {
        "labels": [label for label, _, _ in report.series],
        "revenue": [float(amount) for _, _, amount in report.series],
        "orders": [count for _, count, _ in report.series],
    }
