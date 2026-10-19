"""Satış ve sipariş raporları (Hafta 12): ekran, CSV ve PDF.

/raporlar/                  rapor sayfası (üretici: kendi satışları, yönetici: tüm platform)
/raporlar/indir/csv         ?tablo=siparisler|urunler|donemler
/raporlar/indir/pdf
Dönem parametreleri: ?donem=7g|30g|bu_ay|gecen_ay|bu_yil  ya da  ?baslangic=YYYY-AA-GG&bitis=YYYY-AA-GG
"""
import io

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app.models import RoleName
from app.reports.export_csv import EXPORT_TABLES
from app.reports.period import PRESETS
from app.repositories.report_repository import ReportRepository
from app.services import report_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.rate_limit import rate_limited

report_bp = Blueprint("reports", __name__, url_prefix="/raporlar")


@report_bp.route("/")
@role_required(RoleName.PRODUCER, RoleName.ADMIN)
def index():
    try:
        report, scope = report_service.sales_report(current_user, request.args)
    except ServiceError as error:
        flash(error.message, "warning")
        report, scope = None, report_service.resolve_scope(current_user, request.args)

    args = {**(report.period.to_args() if report else {}), **scope.to_args()}
    return render_template(
        "reports/index.html",
        report=report,
        scope=scope,
        args=args,
        presets=PRESETS,
        export_tables={key: label for key, (label, _) in EXPORT_TABLES.items()},
        producers=ReportRepository.producers() if scope.is_admin else [],
        chart=report_service.chart_data(report) if report else None,
        max_date=report_service.local_today().isoformat(),
    )


@report_bp.route("/indir/<fmt>")
@role_required(RoleName.PRODUCER, RoleName.ADMIN)
@rate_limited("report_export", "REPORT_EXPORTS_PER_MIN", 60, methods=("GET",))  # PDF üretimi pahalı
def download(fmt):
    if fmt not in report_service.EXPORT_FORMATS:
        abort(404)
    try:
        report, scope = report_service.sales_report(current_user, request.args)
    except ServiceError as error:
        flash(error.message, "warning")
        return redirect(url_for("reports.index", **request.args.to_dict()))

    content, mimetype, filename = report_service.export(report, scope, fmt, request.args.get("tablo"))
    response = send_file(io.BytesIO(content), mimetype=mimetype, as_attachment=True, download_name=filename)
    # Satış verisi kişisel/ticari bilgidir: tarayıcı ve ara sunucular önbelleğe almasın
    response.headers["Cache-Control"] = "no-store"
    return response
