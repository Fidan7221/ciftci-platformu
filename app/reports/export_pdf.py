"""Raporun PDF olarak dışa aktarılması (Hafta 12) — ReportLab.

Türkçe karakter sorunu: PDF'in standart yazı tipleri (Helvetica, Times) "ğ, ş, ı, İ" ve "₺" içermez;
bu harfler kutucuk ya da boşluk olarak çıkar. Bu yüzden proje içinde gelen DejaVu Sans (TTF) yazı tipi
PDF'e gömülür (app/reports/fonts/). Yazı tipi dosyası bulunamazsa Helvetica'ya dönülür ve
Türkçe harfler en yakın Latin harfine çevrilir (rapor yine okunur, çökmez).

Bellekte üretilir (BytesIO); diske geçici dosya yazılmaz.
"""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.formatting import format_money, format_qty

FONT_DIR = Path(__file__).resolve().parent / "fonts"
BRAND = colors.HexColor("#2f7d32")
BRAND_SOFT = colors.HexColor("#eef6ec")
MUTED = colors.HexColor("#6c757d")
GRID = colors.HexColor("#d9e3d6")
MAX_ORDER_ROWS = 300            # PDF'te en fazla bu kadar sipariş satırı (tamamı CSV'de)

_FONTS = {}
_ASCII = str.maketrans("ğĞşŞıİçÇöÖüÜ₺–“”…", "gGsSiIcCoOuUT-\"\".")


def _register_fonts():
    """Yazı tiplerini bir kez kaydeder. (normal, kalın, unicode_destekli_mi) döner."""
    if not _FONTS:
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(FONT_DIR / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
            _FONTS.update(normal="DejaVuSans", bold="DejaVuSans-Bold", unicode=True)
        except Exception:  # dosya yok/bozuk: rapor yine üretilsin
            _FONTS.update(normal="Helvetica", bold="Helvetica-Bold", unicode=False)
    return _FONTS["normal"], _FONTS["bold"], _FONTS["unicode"]


class _Writer:
    """Paragraf/tablo üretimini ve yazı tipi seçimini tek yerde toplar."""

    def __init__(self):
        self.font, self.bold, self.unicode = _register_fonts()
        self.body = ParagraphStyle("body", fontName=self.font, fontSize=8.5, leading=11)
        self.cell = ParagraphStyle("cell", parent=self.body, fontSize=8, leading=10)
        self.cell_right = ParagraphStyle("cell_r", parent=self.cell, alignment=TA_RIGHT)
        self.h1 = ParagraphStyle("h1", fontName=self.bold, fontSize=17, leading=21, textColor=BRAND)
        self.h2 = ParagraphStyle("h2", fontName=self.bold, fontSize=11.5, leading=15, spaceBefore=10,
                                 spaceAfter=5, textColor=colors.HexColor("#1f5a23"))
        self.muted = ParagraphStyle("muted", parent=self.body, textColor=MUTED)

    def text(self, value):
        value = "" if value is None else str(value)
        return value if self.unicode else value.translate(_ASCII)

    def p(self, value, style=None):
        # Kullanıcı verisi (ürün adı vb.) ReportLab'in mini-HTML'inde yorumlanmasın: escape
        return Paragraph(escape(self.text(value)), style or self.body)

    def money(self, value):
        text = format_money(value)
        return text if self.unicode else text.replace("₺", "TL")

    def table(self, headers, rows, widths, numeric_cols=(), empty="Bu dönemde kayıt yok."):
        if not rows:
            return self.p(empty, self.muted)
        data = [[self.p(h, ParagraphStyle("th", parent=self.cell, fontName=self.bold, textColor=colors.white,
                                         alignment=TA_RIGHT if i in numeric_cols else 0))
                 for i, h in enumerate(headers)]]
        for row in rows:
            data.append([self.p(value, self.cell_right if i in numeric_cols else self.cell)
                         for i, value in enumerate(row)])
        table = Table(data, colWidths=widths, repeatRows=1)  # sayfa bölünürse başlık tekrar eder
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_SOFT]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table


def _kpis(w, report):
    s = report.summary
    cells = [
        ("Ciro", w.money(s["revenue"])),
        ("Satış (sipariş)", str(s["order_count"])),
        ("Ortalama sipariş", w.money(s["average_order"])),
        ("Müşteri", str(s["customer_count"])),
        ("Ödeme bekleyen", f"{s['pending_count']} · {w.money(s['pending_amount'])}"),
        ("İptal", f"{s['cancelled_count']} (%{format_qty(s['cancel_rate'])})"),
    ]
    label = ParagraphStyle("kpi_l", parent=w.muted, fontSize=7.5)
    value = ParagraphStyle("kpi_v", fontName=w.bold, fontSize=12, leading=15)
    data = [[[w.p(name, label), w.p(val, value)] for name, val in cells[i:i + 3]] for i in (0, 3)]
    table = Table(data, colWidths=[60 * mm] * 3)
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfdfa")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _chart(w, report):
    """Dönem cirosu sütun grafiği. Ciro yoksa çizilmez."""
    values = [float(amount) for _, _, amount in report.series]
    if not any(values):
        return None
    labels = [label for label, _, _ in report.series]
    step = max(1, len(labels) // 15)        # en fazla ~15 etiket; üst üste binmesin
    drawing = Drawing(180 * mm, 62 * mm)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 14 * mm, 10 * mm, 162 * mm, 46 * mm
    chart.data = [values]
    chart.bars[0].fillColor = BRAND
    chart.bars[0].strokeColor = None
    chart.barSpacing = 1
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = w.font
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.strokeColor = GRID
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}".replace(",", ".")
    chart.categoryAxis.categoryNames = [w.text(l) if i % step == 0 else "" for i, l in enumerate(labels)]
    chart.categoryAxis.labels.fontName = w.font
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 45 if len(labels) > 12 else 0
    chart.categoryAxis.labels.boxAnchor = "ne" if len(labels) > 12 else "n"
    chart.categoryAxis.strokeColor = GRID
    drawing.add(chart)
    drawing.add(String(0, 58 * mm, w.text("Ciro (₺)") if w.unicode else "Ciro (TL)",
                       fontName=w.font, fontSize=7, fillColor=MUTED))
    return drawing


def build_pdf(report, app_name="Tarladan Sofraya"):
    w = _Writer()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=16 * mm,
        title=w.text(f"{report.title} — {report.scope_label}"), author=w.text(app_name),
        subject=w.text(report.period.label),
    )

    story = [
        w.p(report.title, w.h1),
        Spacer(0, 2 * mm),
        w.p(f"{report.scope_label}  ·  {report.period.label}", ParagraphStyle("sub", parent=w.body, fontSize=10)),
        w.p(f"Oluşturulma: {report.generated_at:%d.%m.%Y %H:%M}  ·  Ciroya yalnızca ödenmiş, kargodaki ve "
            f"teslim edilmiş siparişler dahildir.", w.muted),
        Spacer(0, 4 * mm),
        _kpis(w, report),
    ]
    for note in report.notes:
        story.append(w.p(f"Not: {note}", w.muted))

    chart = _chart(w, report)
    if chart is not None:
        story += [w.p("Dönem cirosu" + (" (günlük)" if report.period.granularity == "day" else " (aylık)"), w.h2), chart]

    story += [
        w.p("Sipariş durumları", w.h2),
        w.table(["Durum", "Sipariş", "Tutar"],
                [[label, count, w.money(amount)] for _, label, count, amount in report.statuses],
                [100 * mm, 35 * mm, 45 * mm], numeric_cols=(1, 2)),
        w.p("En çok satan ürünler", w.h2),
        w.table(["Ürün", "Üretici", "Miktar", "Sipariş", "Ciro", "Pay"],
                [[p["name"], p["farm_name"], f"{format_qty(p['quantity'])} {p['unit']}", p["order_count"],
                  w.money(p["revenue"]), f"%{format_qty(p['share'])}"] for p in report.products],
                [50 * mm, 38 * mm, 24 * mm, 17 * mm, 32 * mm, 19 * mm], numeric_cols=(2, 3, 4, 5)),
        KeepTogether([
            w.p("Kategorilere göre ciro", w.h2),
            w.table(["Kategori", "Ciro", "Pay"],
                    [[name, w.money(amount), f"%{format_qty(share)}"] for name, amount, share in report.categories],
                    [100 * mm, 50 * mm, 30 * mm], numeric_cols=(1, 2)),
        ]),
    ]
    if report.is_admin:
        story.append(KeepTogether([   # başlık sayfa sonunda yalnız kalmasın
            w.p("En çok satan üreticiler", w.h2),
            w.table(["Üretici", "Sipariş", "Ciro", "Pay"],
                    [[farm, count, w.money(amount), f"%{format_qty(share)}"]
                     for farm, count, amount, share in report.producers],
                    [90 * mm, 30 * mm, 35 * mm, 25 * mm], numeric_cols=(1, 2, 3)),
        ]))

    lines = report.orders[:MAX_ORDER_ROWS]
    headers = ["No", "Tarih", "Durum", "Müşteri"] + (["Üretici"] if report.is_admin else []) + ["Kalem", "Tutar"]
    widths = ([14 * mm, 31 * mm, 32 * mm, 29 * mm] + ([36 * mm] if report.is_admin else []) +
              [16 * mm, 22 * mm])
    if not report.is_admin:
        widths[3] = 65 * mm
    rows = []
    for line in lines:
        row = [f"#{line.order_id}", f"{line.created_local:%d.%m.%Y %H:%M}", line.status_label, line.customer_name]
        if report.is_admin:
            row.append(line.farm_name)
        row += [line.item_count, w.money(line.amount)]
        rows.append(row)
    story += [w.p("Siparişler", w.h2),
              w.table(headers, rows, widths, numeric_cols=(len(headers) - 2, len(headers) - 1))]
    if len(report.orders) > MAX_ORDER_ROWS:
        story.append(w.p(f"PDF'te ilk {MAX_ORDER_ROWS} sipariş gösterildi; tamamı ({len(report.orders)}) "
                         f"CSV dosyasındadır.", w.muted))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(w.font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 9 * mm, w.text(f"{app_name} · {report.title} · {report.scope_label}"))
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, w.text(f"Sayfa {document.page}"))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
