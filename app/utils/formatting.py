"""Sayı biçimlendirme yardımcıları (şablon filtreleri ve hata mesajları ortak kullanır)."""
from decimal import Decimal


def format_qty(value):
    """Decimal('12.50') -> '12,5'   Decimal('100.00') -> '100'"""
    if value is None:
        return "0"
    text = f"{Decimal(str(value)).quantize(Decimal('0.01')):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_money(value):
    """Decimal('1234.5') -> '1.234,50 ₺'"""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"                      # 1,234.50
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} ₺"
