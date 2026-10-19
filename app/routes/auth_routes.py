"""Kimlik doğrulama rotaları: /auth/register, /auth/login, /auth/logout"""
from math import ceil
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.forms.auth_forms import LoginForm, LogoutForm, RegistrationForm
from app.services import auth_service
from app.services.auth_service import AuthError
from app.utils.decorators import anonymous_required
from app.utils.rate_limit import get_limiter, rate_limited

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _login_failures():
    config = current_app.config
    return get_limiter("login_failures", config["LOGIN_FAILURES_PER_ACCOUNT"], config["LOGIN_LOCKOUT_SECONDS"])


def _is_safe_next_url(target):
    """?next= parametresi yalnızca kendi sitemizdeki bir sayfayı gösterebilir.

    Aksi halde saldırgan /auth/login?next=https://sahte-site.com bağlantısıyla
    kullanıcıyı girişten sonra kendi sitesine yönlendirebilir (Open Redirect).
    """
    if not target or "\\" in target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/")


@auth_bp.route("/register", methods=["GET", "POST"])
@anonymous_required
@rate_limited("register_ip", "REGISTRATIONS_PER_IP_PER_HOUR", period=3600)  # sahte hesap / spam sınırı
def register():
    form = RegistrationForm()

    if form.validate_on_submit():
        try:
            auth_service.register_user(
                full_name=form.full_name.data,
                email=form.email.data,
                password=form.password.data,
                role_name=form.role.data,
                phone=form.phone.data,
                city=form.city.data,
                farm_name=form.farm_name.data,
                region=form.region.data,
            )
        except AuthError as error:
            if error.field and hasattr(form, error.field):
                getattr(form, error.field).errors.append(error.message)
            else:
                flash(error.message, "danger")
        else:
            flash("Kaydınız oluşturuldu. Şimdi giriş yapabilirsiniz.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@anonymous_required
@rate_limited("login_ip", "LOGIN_ATTEMPTS_PER_IP_PER_MIN", period=60)  # IP başına deneme sınırı
def login():
    form = LoginForm()

    if form.validate_on_submit():
        # Hafta 11: Hesap başına kaba kuvvet koruması. Aynı e-posta için 15 dakikada 5 hatalı
        # denemeden sonra (parola doğru olsa bile) giriş geçici olarak engellenir.
        account_key = auth_service.normalize_email(form.email.data)
        failures = _login_failures()
        wait = failures.retry_after(account_key)
        if wait:
            flash(f"Bu hesap için çok fazla hatalı deneme yapıldı. Lütfen {ceil(wait / 60)} dakika sonra "
                  "tekrar deneyin.", "danger")
            return render_template("auth/login.html", form=form), 429

        try:
            user = auth_service.authenticate(form.email.data, form.password.data)
        except AuthError as error:
            flash(error.message, "danger")
            return render_template("auth/login.html", form=form)

        if user is None:
            failures.hit(account_key)
            flash("E-posta veya parola hatalı.", "danger")
        else:
            failures.reset(account_key)  # Başarılı girişte sayaç sıfırlanır
            login_user(user, remember=form.remember_me.data)
            flash(f"Hoş geldiniz, {user.full_name}!", "success")

            next_url = request.args.get("next")
            if _is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # Çıkış POST + CSRF ile yapılır; böylece başka bir site <img src="/auth/logout">
    # gibi bir hileyle kullanıcının oturumunu kapatamaz.
    form = LogoutForm()
    if form.validate_on_submit():
        logout_user()
        flash("Oturumunuz kapatıldı.", "info")
    return redirect(url_for("main.index"))


@auth_bp.app_context_processor
def inject_logout_form():
    """Gezinme çubuğundaki çıkış düğmesi için tüm şablonlara logout_form gönderir."""
    return {"logout_form": LogoutForm() if current_user.is_authenticated else None}
