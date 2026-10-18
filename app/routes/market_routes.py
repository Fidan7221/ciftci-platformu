"""Pazar vitrini (Hafta 7): herkese açık ilan listesi ve ilan detayı."""
from flask import Blueprint, abort, render_template, request

from app.forms.cart_forms import AddToCartForm
from app.services import category_service, listing_service

market_bp = Blueprint("market", __name__, url_prefix="/pazar")


@market_bp.route("/")
def index():
    page = request.args.get("sayfa", 1, type=int)
    search = request.args.get("q", "")
    category_id = request.args.get("kategori", 0, type=int) or None

    return render_template(
        "listings/index.html",
        pagination=listing_service.list_market(search, category_id, page),
        search=search,
        category_id=category_id,
        category_tree=category_service.category_tree(),
    )


@market_bp.route("/ilan/<int:listing_id>")
def detail(listing_id):
    listing = listing_service.get_public_listing(listing_id)
    if listing is None:
        abort(404)
    form = AddToCartForm(quantity=listing.min_order_quantity)
    return render_template("listings/detail.html", listing=listing, form=form)
