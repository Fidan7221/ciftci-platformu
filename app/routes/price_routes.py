"""Hal fiyatları rotaları (Hafta 9).

/fiyatlar               : herkese açık güncel fiyat tablosu
/fiyatlar/guncelle      : yönetici, sağlayıcıdan bugünün fiyatlarını çeker (hız sınırlı)
/fiyatlar/<slug>        : ürün fiyat geçmişi + yapay zekâ tahmini (Hafta 10)
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm

from app.models import RoleName
from app.repositories.product_repository import CategoryRepository
from app.services import prediction_service, price_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.rate_limit import rate_limited

price_bp = Blueprint("prices", __name__, url_prefix="/fiyatlar")


class SyncForm(FlaskForm):
    """Yalnızca CSRF anahtarı taşır."""


@price_bp.route("/")
def index():
    search = request.args.get("q", "")
    board = price_service.latest_board(search)
    # Hafta 10: her satır için kategori ve 7 günlük tahmin (veri yetersizse None)
    forecasts = {}
    for row in board["rows"]:
        category = row["price"].category
        if category is not None and category.id not in forecasts:
            forecasts[category.id] = prediction_service.forecast_for_category(category.id)
    return render_template("prices/index.html", board=board, search=search, forecasts=forecasts,
                           info=price_service.status(), sync_form=SyncForm())


@price_bp.route("/<slug>")
def detail(slug):
    """Bir ürünün hal fiyatı geçmişi, yapay zekâ tahmini ve modelin açıklaması (Hafta 10)."""
    category = CategoryRepository.get_by_slug(slug)
    if category is None:
        abort(404)
    insight = prediction_service.insight_for_category(category)
    return render_template("prices/detail.html", category=category, insight=insight)


@price_bp.route("/guncelle", methods=["POST"])
@role_required(RoleName.ADMIN)
@rate_limited("price_sync", "PRICE_SYNC_PER_MINUTE", period=60)
def sync():
    if not SyncForm().validate_on_submit():
        flash("Geçersiz istek.", "danger")
        return redirect(url_for("prices.index"))
    try:
        summary = price_service.sync_prices()
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"Fiyatlar güncellendi: {summary['fetched']} kayıt alındı, {summary['inserted']} yeni, "
              f"{summary['updated']} güncellendi, {summary['invalid']} hatalı satır atlandı.", "success")
    return redirect(url_for("prices.index"))
