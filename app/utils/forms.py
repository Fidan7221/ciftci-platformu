"""Form yardımcıları."""
from flask import flash


def show_service_error(form, error):
    """Servisten gelen hatayı ilgili alanın altına yazar; alan yoksa flash mesajı gösterir."""
    field = getattr(form, error.field, None) if error.field else None
    if field is not None:
        field.errors = list(field.errors) + [error.message]
    else:
        flash(error.message, "danger")
