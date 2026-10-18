"""Ödeme rotası (Hafta 9): /odeme/siparis/<id>

Koruma katmanları:
- @role_required: yalnızca müşteri
- Sahiplik: sipariş başkasınınsa 404
- @rate_limited: kullanıcı başına 10 dakikada en fazla N ödeme denemesi (kart deneme saldırılarına karşı)
- CSRF: Flask-WTF formu
"""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.forms.payment_forms import PaymentForm
from app.models import RoleName
from app.services import payment_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.rate_limit import rate_limited

payment_bp = Blueprint("payments", __name__, url_prefix="/odeme")


@payment_bp.route("/siparis/<int:order_id>", methods=["GET", "POST"])
@role_required(RoleName.CUSTOMER)
@rate_limited("payment", "PAYMENT_ATTEMPTS_PER_10_MIN", period=600)
def pay(order_id):
    user = current_user._get_current_object()
    order = payment_service.get_customer_order(order_id, user)
    if order is None:
        abort(404)
    if not payment_service.can_pay(order):
        flash(f"Bu sipariş için ödeme beklenmiyor (durum: {order.status_label}).", "info")
        return redirect(url_for("orders.detail", order_id=order.id))

    form = PaymentForm()
    if form.validate_on_submit():
        try:
            payment = payment_service.pay_order(order, user, form.to_card())
        except ServiceError as error:
            flash(error.message, "danger")
        else:
            flash(f"Ödemeniz alındı (kart **** {payment.card_last4}). Üretici siparişinizi hazırlamaya başlayabilir.",
                  "success")
            return redirect(url_for("orders.detail", order_id=order.id))

    form.clear_sensitive()
    return render_template("payments/pay.html", order=order, form=form,
                           payment=order.payment, test_cards=payment_service.sandbox_cards())
