"""Sepet ve sipariş onayı rotaları (Hafta 7). Yalnızca müşteriler kullanabilir."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.forms.cart_forms import AddToCartForm, CheckoutForm, RemoveCartItemForm, UpdateCartItemForm
from app.models import RoleName
from app.services import cart_service, order_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

cart_bp = Blueprint("cart", __name__, url_prefix="/sepet")


@cart_bp.app_context_processor
def inject_cart_count():
    """Menüdeki sepet rozetinde gösterilecek kalem sayısı."""
    if current_user.is_authenticated and current_user.is_customer:
        return {"cart_count": cart_service.item_count(_me())}
    return {"cart_count": 0}


def _me():
    """current_user bir vekil (LocalProxy) nesnedir. İlişkiye atanacak gerçek User
    nesnesini (ör. Order(customer=...)) servislere bu şekilde veriyoruz."""
    return current_user._get_current_object()


def _first_form_error(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return "Geçersiz istek."


@cart_bp.route("/")
@role_required(RoleName.CUSTOMER)
def view():
    return render_template("cart/cart.html", summary=cart_service.cart_summary(_me()),
                           update_form=UpdateCartItemForm(), remove_form=RemoveCartItemForm())


@cart_bp.route("/ekle/<int:listing_id>", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def add(listing_id):
    form = AddToCartForm()
    back = url_for("market.detail", listing_id=listing_id)

    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return redirect(back)
    try:
        item = cart_service.add_to_cart(_me(), listing_id, form.quantity.data)
    except ServiceError as error:
        flash(error.message, "danger")
        return redirect(back)

    flash(f"'{item.listing.title}' sepetinize eklendi.", "success")
    return redirect(url_for("cart.view"))


@cart_bp.route("/kalem/<int:item_id>", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def update(item_id):
    form = UpdateCartItemForm()
    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return redirect(url_for("cart.view"))
    try:
        item = cart_service.update_item(_me(), item_id, form.quantity.data)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash("Ürün sepetten çıkarıldı." if item is None else "Miktar güncellendi.", "success")
    return redirect(url_for("cart.view"))


@cart_bp.route("/kalem/<int:item_id>/sil", methods=["POST"])
@role_required(RoleName.CUSTOMER)
def remove(item_id):
    if RemoveCartItemForm().validate_on_submit():
        try:
            cart_service.remove_item(_me(), item_id)
        except ServiceError as error:
            flash(error.message, "danger")
        else:
            flash("Ürün sepetten çıkarıldı.", "success")
    return redirect(url_for("cart.view"))


@cart_bp.route("/onay", methods=["GET", "POST"])
@role_required(RoleName.CUSTOMER)
def checkout():
    summary = cart_service.cart_summary(_me())
    if summary["is_empty"]:
        flash("Sepetiniz boş.", "info")
        return redirect(url_for("market.index"))
    if summary["problems"]:
        flash("Sepetinizdeki bazı ürünlerde sorun var. Lütfen düzeltip tekrar deneyin.", "warning")
        return redirect(url_for("cart.view"))

    form = CheckoutForm()
    if request.method == "GET" and current_user.address:
        form.shipping_address.data = current_user.address

    if form.validate_on_submit():
        try:
            orders = order_service.place_order(
                _me(), form.shipping_address.data, form.note.data, form.save_address.data)
        except ServiceError as error:
            show_service_error(form, error)
            if not error.field:  # Stok hatası: sepete dön, güncel durumu görsün
                return redirect(url_for("cart.view"))
        else:
            if len(orders) == 1:
                flash("Siparişiniz alındı. Ödemeyi tamamladığınızda üreticiye iletilecek.", "success")
                return redirect(url_for("payments.pay", order_id=orders[0].id))
            flash(f"Siparişiniz {len(orders)} üreticiye göre {len(orders)} ayrı siparişe bölündü. "
                  "Her birini listeden ödeyebilirsiniz.", "success")
            return redirect(url_for("orders.my_orders"))

    return render_template("cart/checkout.html", form=form, summary=summary)
