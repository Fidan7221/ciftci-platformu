"""Genel sayfalar, role göre paneller ve hesap bilgileri."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.account_forms import AccountForm
from app.models import Listing, ListingStatus, Order, OrderStatus, Product, RoleName, User
from app.repositories.order_repository import StatsRepository
from app.services import auth_service, prediction_service
from app.services.auth_service import AuthError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("main/index.html")


@main_bp.route("/panel")
@login_required
def dashboard():
    """Kullanıcıyı rolüne uygun panele yönlendirir."""
    if current_user.is_producer:
        return redirect(url_for("producer.dashboard"))
    if current_user.is_admin:
        return redirect(url_for("main.admin_dashboard"))
    return redirect(url_for("main.customer_dashboard"))


@main_bp.route("/musteri/panel")
@role_required(RoleName.CUSTOMER)
def customer_dashboard():
    return render_template("customer/dashboard.html",
                           recent_orders=StatsRepository.recent_orders_for_customer(current_user.id),
                           market_cards=prediction_service.market_overview(limit=3))  # Hafta 10


@main_bp.route("/yonetici/panel")
@role_required(RoleName.ADMIN)
def admin_dashboard():
    stats = {
        "users": StatsRepository.count(User),
        "products": StatsRepository.count(Product, Product.is_active.is_(True)),
        "listings": StatsRepository.count(Listing, Listing.status == ListingStatus.ACTIVE),
        "orders": StatsRepository.count(Order),
        "open_orders": StatsRepository.count(
            Order, Order.status.in_((OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.SHIPPED))),
        "revenue": StatsRepository.revenue((OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED)),
    }
    return render_template("admin/dashboard.html", stats=stats)


@main_bp.route("/hesabim", methods=["GET", "POST"])
@login_required
def account():
    """Müşteri ve yönetici hesap bilgileri. Üreticiler kendi profil sayfasına yönlendirilir."""
    if current_user.is_producer:
        return redirect(url_for("producer.edit_profile"))

    form = AccountForm(obj=current_user) if request.method == "GET" else AccountForm()
    if form.validate_on_submit():
        try:
            auth_service.update_account(current_user, form.full_name.data, form.phone.data,
                                        form.city.data, form.address.data)
        except AuthError as error:
            show_service_error(form, error)
        else:
            flash("Hesap bilgileriniz güncellendi.", "success")
            return redirect(url_for("main.account"))
    return render_template("main/account.html", form=form)
