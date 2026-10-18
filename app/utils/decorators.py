"""Erişim kontrolü dekoratörleri (Hafta 5).

Kullanım:
    @main_bp.route("/uretici/panel")
    @role_required(RoleName.PRODUCER)
    def producer_dashboard(): ...

Giriş yapılmamışsa  -> giriş sayfasına yönlendirilir (401 mantığı, Flask-Login)
Giriş var, rol yanlış -> 403 Yasak sayfası gösterilir
"""
from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user, login_required


def role_required(*role_names):
    """Görünüme yalnızca belirtilen rollerden birine sahip kullanıcılar girebilir."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not any(current_user.has_role(name) for name in role_names):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def anonymous_required(view):
    """Giriş yapmış kullanıcı giriş/kayıt sayfasını açarsa panele yönlendirilir."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.is_authenticated:
            flash("Zaten giriş yaptınız.", "info")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped
