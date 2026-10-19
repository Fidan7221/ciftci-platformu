"""Pazar vitrini (Hafta 7): herkese açık ilan listesi ve ilan detayı. Filtreleme Hafta 12."""
from flask import Blueprint, abort, render_template, request

from app.forms.cart_forms import AddToCartForm
from app.services import category_service, listing_service, prediction_service, price_service, search_service

market_bp = Blueprint("market", __name__, url_prefix="/pazar")


@market_bp.route("/")
def index():
    """Hafta 12: çoklu filtre + sıralama + Türkçe duyarsız arama. Tüm seçimler URL'de durur;
    böylece sonuç sayfası paylaşılabilir, yer imine eklenebilir ve geri tuşu doğru çalışır."""
    return render_template(
        "listings/index.html",
        category_tree=category_service.category_tree(),
        **search_service.market_page(request.args),
    )


@market_bp.route("/ilan/<int:listing_id>")
def detail(listing_id):
    listing = listing_service.get_public_listing(listing_id)
    if listing is None:
        abort(404)
    form = AddToCartForm(quantity=listing.min_order_quantity)
    return render_template("listings/detail.html", listing=listing, form=form,
                           comparison=price_service.compare_listing(listing),  # Hafta 9: hal fiyatı karşılaştırması
                           insight=prediction_service.insight_for_category(listing.product.category))  # Hafta 10
