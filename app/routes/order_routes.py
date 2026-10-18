"""Sipariş rotaları (Hafta 7): müşterinin siparişleri, sipariş detayı ve durum değiştirme.

Detay sayfasını siparişin müşterisi, siparişte ürünü olan üretici ve yönetici görebilir.
Diğer herkes 404 alır.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.cart_forms import OrderStatusForm
from app.models import OrderStatus, RoleName
from app.services import order_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required

order_bp = Blueprint("orders", __name__, url_prefix="/siparisler")


@order_bp.route("/")
@role_required(RoleName.CUSTOMER)
def my_orders():
    page = request.args.get("sayfa", 1, type=int)
    return render_template("orders/list.html",
                           pagination=order_service.list_customer_orders(current_user, page))


@order_bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = order_service.get_visible_order(order_id, current_user)
    if order is None:
        abort(404)
    return render_template(
        "orders/detail.html",
        order=order,
        actor=order_service.actor_for(order, current_user),
        actions=order_service.available_actions(order, current_user),
        status_form=OrderStatusForm(),
        flow=OrderStatus.FLOW,
    )


@order_bp.route("/<int:order_id>/durum", methods=["POST"])
@login_required
def change_status(order_id):
    order = order_service.get_visible_order(order_id, current_user)
    if order is None:
        abort(404)

    form = OrderStatusForm()
    if not form.validate_on_submit():
        flash("Geçersiz istek.", "danger")
        return redirect(url_for("orders.detail", order_id=order_id))

    try:
        order_service.change_status(order, current_user, form.status.data)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"Sipariş durumu: {order.status_label}.", "success")
    return redirect(url_for("orders.detail", order_id=order_id))
