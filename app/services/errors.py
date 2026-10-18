"""Servis katmanının ortak hata sınıfı.

Servis bir iş kuralı ihlali gördüğünde ServiceError fırlatır; rota bunu yakalayıp
mesajı ilgili form alanının altında (field doluysa) ya da flash olarak gösterir.
"""


class ServiceError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field
