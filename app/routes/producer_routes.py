"""Üretici rotaları: panel, profil, ürünler (Hafta 6), ilanlar ve gelen siparişler (Hafta 7).

Bu Blueprint'teki her sayfa @role_required(RoleName.PRODUCER) ile korunur.
Sahiplik kontrolü: başka üreticinin ürün id'si yazılırsa 404 döner; böylece
o id'de bir ürün olup olmadığı bile belli olmaz.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.listing_forms import ListingForm, ToggleForm
from app.forms.producer_forms import DeleteForm, ProducerProfileForm, ProductForm
from app.models import ListingStatus, OrderStatus, RoleName
from app.services import (category_service, listing_service, order_service, prediction_service,
                          price_service, producer_service)
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

producer_bp = Blueprint("producer", __name__, url_prefix="/uretici")


def _profile():
    profile = current_user.producer_profile
    if profile is None:
        abort(404)
    return profile


def _owned_product_or_404(product_id):
    product = producer_service.get_owned_product(_profile(), product_id)
    if product is None:
        abort(404)
    return product


def _product_form_kwargs(form):
    return dict(
        category_id=form.category_id.data,
        name=form.name.data,
        unit=form.unit.data,
        stock_quantity=form.stock_quantity.data,
        description=form.description.data,
        is_organic=form.is_organic.data,
        is_active=form.is_active.data,
        image_file=form.image.data,
    )


# --- Panel ve profil ------------------------------------------------------

@producer_bp.route("/panel")
@role_required(RoleName.PRODUCER)
def dashboard():
    profile = _profile()
    return render_template("producer/dashboard.html", profile=profile,
                           insights=prediction_service.producer_insights(profile),  # Hafta 10
                           **producer_service.dashboard_data(profile))


@producer_bp.route("/profil", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_profile():
    profile = _profile()
    form = ProducerProfileForm()

    if request.method == "GET":
        # Formu mevcut bilgilerle doldur (iki farklı tablodan)
        form.full_name.data = current_user.full_name
        form.phone.data = current_user.phone
        form.city.data = current_user.city
        form.farm_name.data = profile.farm_name
        form.region.data = profile.region
        form.tax_number.data = profile.tax_number
        form.description.data = profile.description

    if form.validate_on_submit():
        try:
            producer_service.update_profile(
                current_user,
                full_name=form.full_name.data, phone=form.phone.data, city=form.city.data,
                farm_name=form.farm_name.data, region=form.region.data,
                description=form.description.data, tax_number=form.tax_number.data,
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash("Profiliniz güncellendi.", "success")
            return redirect(url_for("producer.dashboard"))

    return render_template("producer/profile.html", form=form, profile=profile)


# --- Ürünler (CRUD) -------------------------------------------------------

@producer_bp.route("/urunler")
@role_required(RoleName.PRODUCER)
def products():
    page = request.args.get("sayfa", 1, type=int)
    search = request.args.get("q", "")
    category_id = request.args.get("kategori", 0, type=int) or None

    pagination = producer_service.list_products(_profile(), search, category_id, page)
    return render_template(
        "producer/products.html",
        pagination=pagination,
        search=search,
        category_id=category_id,
        category_groups=category_service.product_category_choices(),
        delete_form=DeleteForm(),
    )


@producer_bp.route("/urunler/yeni", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def new_product():
    form = ProductForm()
    form.category_id.choices = category_service.product_category_choices()

    if form.validate_on_submit():
        try:
            product = producer_service.create_product(_profile(), **_product_form_kwargs(form))
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{product.name}' ürününüz eklendi.", "success")
            return redirect(url_for("producer.products"))

    return render_template("producer/product_form.html", form=form, product=None)


@producer_bp.route("/urunler/<int:product_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_product(product_id):
    product = _owned_product_or_404(product_id)
    form = ProductForm(obj=product)  # GET isteğinde alanları ürün bilgileriyle doldurur
    form.category_id.choices = category_service.product_category_choices()

    if form.validate_on_submit():
        try:
            producer_service.update_product(
                product, remove_image=form.remove_image.data, **_product_form_kwargs(form)
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{product.name}' güncellendi.", "success")
            return redirect(url_for("producer.products"))

    return render_template("producer/product_form.html", form=form, product=product)


@producer_bp.route("/urunler/<int:product_id>/sil", methods=["POST"])
@role_required(RoleName.PRODUCER)
def delete_product(product_id):
    product = _owned_product_or_404(product_id)
    form = DeleteForm()
    if not form.validate_on_submit():
        abort(400)

    name = product.name
    result = producer_service.delete_product(product)
    if result == "archived":
        flash(f"'{name}' geçmiş siparişlerde kullanıldığı için silinmedi, arşive alındı "
              "(satışa kapatıldı).", "warning")
    else:
        flash(f"'{name}' silindi.", "success")
    return redirect(url_for("producer.products"))


# --- İlanlar (Hafta 7) --------------------------------------------------------

def _owned_listing_or_404(listing_id):
    listing = listing_service.get_owned_listing(_profile(), listing_id)
    if listing is None:
        abort(404)
    return listing


def _listing_form_kwargs(form):
    return dict(
        product_id=form.product_id.data,
        title=form.title.data,
        price=form.price.data,
        stock_quantity=form.stock_quantity.data,
        min_order_quantity=form.min_order_quantity.data,
        start_date=form.start_date.data,
        end_date=form.end_date.data,
        is_active=form.is_active.data,
    )


@producer_bp.route("/ilanlar")
@role_required(RoleName.PRODUCER)
def listings():
    page = request.args.get("sayfa", 1, type=int)
    status = request.args.get("durum") or None
    return render_template(
        "producer/listings.html",
        pagination=listing_service.list_producer_listings(_profile(), status, page),
        status=status,
        statuses=ListingStatus.LABELS,
        badges=ListingStatus.BADGES,
        toggle_form=ToggleForm(),
    )


@producer_bp.route("/ilanlar/yeni", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def new_listing():
    profile = _profile()
    form = ListingForm()
    form.product_id.choices = listing_service.product_choices(profile)
    if not form.product_id.choices:
        flash("İlan açmak için önce satışa açık bir ürün ekleyin.", "info")
        return redirect(url_for("producer.new_product"))

    if request.method == "GET" and request.args.get("urun", type=int):
        form.product_id.data = request.args.get("urun", type=int)  # Ürün listesinden gelince seçili olsun

    if form.validate_on_submit():
        try:
            listing = listing_service.create_listing(profile, **_listing_form_kwargs(form))
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{listing.title}' ilanı yayında.", "success")
            return redirect(url_for("producer.listings"))

    return render_template("producer/listing_form.html", form=form, listing=None,
                           remaining=_remaining_by_product(profile),
                           suggestions=prediction_service.listing_suggestions(profile))


@producer_bp.route("/ilanlar/<int:listing_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.PRODUCER)
def edit_listing(listing_id):
    profile = _profile()
    listing = _owned_listing_or_404(listing_id)
    form = ListingForm(obj=listing)
    form.product_id.choices = listing_service.product_choices(profile)
    if listing.product_id not in [value for value, _ in form.product_id.choices]:
        # Ürün sonradan arşivlendiyse bile ilanın kendi ürünü listede görünsün
        form.product_id.choices.append((listing.product_id, listing.product.name))
    if request.method == "GET":
        form.is_active.data = listing.status != ListingStatus.CLOSED

    if form.validate_on_submit():
        try:
            listing_service.update_listing(profile, listing, **_listing_form_kwargs(form))
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{listing.title}' güncellendi.", "success")
            return redirect(url_for("producer.listings"))

    return render_template("producer/listing_form.html", form=form, listing=listing,
                           remaining=_remaining_by_product(profile, exclude_listing_id=listing.id),
                           suggestions=prediction_service.listing_suggestions(profile))


@producer_bp.route("/ilanlar/<int:listing_id>/durum", methods=["POST"])
@role_required(RoleName.PRODUCER)
def toggle_listing(listing_id):
    listing = _owned_listing_or_404(listing_id)
    if not ToggleForm().validate_on_submit():
        abort(400)
    try:
        listing_service.toggle_listing(_profile(), listing)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"'{listing.title}' artık: {listing.status_label}.", "success")
    return redirect(url_for("producer.listings", durum=request.args.get("durum")))


def _remaining_by_product(profile, exclude_listing_id=None):
    """Formdaki ipucu: her ürün için ilana ayrılabilecek miktar ve (Hafta 9) güncel hal ortalaması."""
    hints = {}
    for p in profile.products:
        if not p.is_active:
            continue
        reference = price_service.reference_price_for(p)
        hal = None
        if reference is not None and reference.unit == p.unit:
            hal = (reference.avg_price, reference.price_date)
        hints[p.id] = (listing_service.remaining_stock_for(p, exclude_listing_id), p.unit, hal)
    return hints


# --- Gelen siparişler (Hafta 7) ----------------------------------------------------

@producer_bp.route("/siparisler")
@role_required(RoleName.PRODUCER)
def orders():
    page = request.args.get("sayfa", 1, type=int)
    status = request.args.get("durum") or None
    return render_template(
        "producer/orders.html",
        pagination=order_service.list_producer_orders(_profile(), status, page),
        status=status,
        statuses=OrderStatus.LABELS,
    )
