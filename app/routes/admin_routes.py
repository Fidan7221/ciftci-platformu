"""Yönetici rotaları: kategori yönetimi (Hafta 6) ve tüm siparişler (Hafta 8)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.forms.admin_forms import CategoryForm
from app.forms.producer_forms import DeleteForm
from app.models import OrderStatus, RoleName
from app.repositories.order_repository import StatsRepository
from app.repositories.product_repository import CategoryRepository
from app.services import category_service
from app.services.errors import ServiceError
from app.utils.decorators import role_required
from app.utils.forms import show_service_error

admin_bp = Blueprint("admin", __name__, url_prefix="/yonetici")


def _category_or_404(category_id):
    category = CategoryRepository.get_by_id(category_id)
    if category is None:
        abort(404)
    return category


@admin_bp.route("/kategoriler")
@role_required(RoleName.ADMIN)
def categories():
    return render_template("admin/categories.html", tree=category_service.category_tree(),
                           counts=CategoryRepository.product_counts(),  # Hafta 11: N+1 yerine tek sorgu
                           delete_form=DeleteForm())


@admin_bp.route("/kategoriler/yeni", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def new_category():
    form = CategoryForm()
    form.parent_id.choices = category_service.parent_choices()

    if form.validate_on_submit():
        try:
            category = category_service.create_category(
                form.name.data, form.slug.data, form.parent_id.data or None
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{category.name}' kategorisi eklendi.", "success")
            return redirect(url_for("admin.categories"))

    return render_template("admin/category_form.html", form=form, category=None)


@admin_bp.route("/kategoriler/<int:category_id>/duzenle", methods=["GET", "POST"])
@role_required(RoleName.ADMIN)
def edit_category(category_id):
    category = _category_or_404(category_id)
    form = CategoryForm(obj=category)
    form.parent_id.choices = category_service.parent_choices(exclude_id=category.id)
    if form.parent_id.data is None:
        form.parent_id.data = 0  # Ana kategoride parent_id boştur; listede "yok" seçili olsun

    if form.validate_on_submit():
        try:
            category_service.update_category(
                category, form.name.data, form.slug.data, form.parent_id.data or None
            )
        except ServiceError as error:
            show_service_error(form, error)
        else:
            flash(f"'{category.name}' güncellendi.", "success")
            return redirect(url_for("admin.categories"))

    return render_template("admin/category_form.html", form=form, category=category)


@admin_bp.route("/kategoriler/<int:category_id>/sil", methods=["POST"])
@role_required(RoleName.ADMIN)
def delete_category(category_id):
    category = _category_or_404(category_id)
    if not DeleteForm().validate_on_submit():
        abort(400)
    try:
        name = category.name
        category_service.delete_category(category)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        flash(f"'{name}' kategorisi silindi.", "success")
    return redirect(url_for("admin.categories"))


# --- Tüm siparişler (Hafta 8) -------------------------------------------------------

@admin_bp.route("/siparisler")
@role_required(RoleName.ADMIN)
def orders():
    page = request.args.get("sayfa", 1, type=int)
    status = request.args.get("durum") or None
    if status not in OrderStatus.ALL:
        status = None
    return render_template("admin/orders.html",
                           pagination=StatsRepository.paginate_all_orders(status, page),
                           status=status, statuses=OrderStatus.LABELS)
