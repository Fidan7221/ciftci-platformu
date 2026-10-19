"""Rapor dönemi (tarih aralığı) seçimi ve doğrulaması (Hafta 12).

Kullanıcı ya hazır bir dönem seçer (?donem=30g) ya da iki tarih girer (?baslangic=2026-10-01&bitis=2026-10-19).
Geçersiz girdi hata (500) üretmez: varsayılan döneme dönülür ve kullanıcıya not gösterilir.

Saat dilimi: Veritabanındaki saatler UTC'dir; kullanıcı ise "19 Ekim" derken Türkiye saatini kasteder.
19 Ekim 00:00 (TR) = 18 Ekim 21:00 (UTC). utc_bounds() bu çeviriyi yapar; aksi hâlde gece 00:00-03:00
arasındaki siparişler yanlış güne yazılırdı.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

PRESETS = {
    "7g": "Son 7 gün",
    "30g": "Son 30 gün",
    "bu_ay": "Bu ay",
    "gecen_ay": "Geçen ay",
    "bu_yil": "Bu yıl",
}
DEFAULT_PRESET = "30g"
MAX_DAYS = 366                 # bir rapor en fazla ~1 yıl kapsar (sorgu yükü sınırlı kalsın)
DAILY_LIMIT_DAYS = 62          # 62 günden uzun dönemler aylık gruplanır

MONTHS_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def preset_range(key, today):
    if key == "7g":
        return today - timedelta(days=6), today
    if key == "bu_ay":
        return today.replace(day=1), today
    if key == "gecen_ay":
        last_day = today.replace(day=1) - timedelta(days=1)
        return last_day.replace(day=1), last_day
    if key == "bu_yil":
        return today.replace(month=1, day=1), today
    return today - timedelta(days=29), today          # "30g" ve bilinmeyenler


def parse_date(text):
    """'2026-10-19' (tarayıcı tarih kutusu) veya '19.10.2026' -> date; geçersizse None."""
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class ReportPeriod:
    start: date
    end: date
    preset: str | None = None

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def granularity(self):
        return "day" if self.days <= DAILY_LIMIT_DAYS else "month"

    @property
    def label(self):
        if self.preset:
            return f"{PRESETS[self.preset]} ({self.start:%d.%m.%Y} – {self.end:%d.%m.%Y})"
        return f"{self.start:%d.%m.%Y} – {self.end:%d.%m.%Y}"

    @property
    def slug(self):
        """Dosya adı için: 2026-09-20_2026-10-19"""
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    def utc_bounds(self, offset_hours):
        """[başlangıç, bitiş) aralığının UTC karşılığı (saat dilimi bilgisi olmadan, SQLite gibi).

        Bitiş dahil olsun diye ertesi günün 00:00'ı "hariç" sınır olarak kullanılır:
        created_at >= start_utc AND created_at < end_utc
        """
        shift = timedelta(hours=offset_hours)
        start_utc = datetime.combine(self.start, time.min) - shift
        end_utc = datetime.combine(self.end + timedelta(days=1), time.min) - shift
        return start_utc, end_utc

    def to_args(self):
        if self.preset:
            return {"donem": self.preset}
        return {"baslangic": self.start.isoformat(), "bitis": self.end.isoformat()}

    def buckets(self):
        """Grafikteki/tablodaki dilimler: [(anahtar, etiket), ...] boş günler de dahil."""
        if self.granularity == "day":
            return [((self.start + timedelta(days=i)).isoformat(),
                     f"{self.start + timedelta(days=i):%d.%m}") for i in range(self.days)]
        result, year, month = [], self.start.year, self.start.month
        while (year, month) <= (self.end.year, self.end.month):
            result.append((f"{year:04d}-{month:02d}", f"{MONTHS_TR[month - 1][:3]} {year}"))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return result

    def bucket_key(self, local_day):
        return local_day.isoformat() if self.granularity == "day" else f"{local_day:%Y-%m}"


def parse_period(args, today):
    """request.args -> (ReportPeriod, [notlar])"""
    notes = []
    preset = args.get("donem")
    if preset in PRESETS:
        return ReportPeriod(*preset_range(preset, today), preset=preset), notes

    raw_start, raw_end = args.get("baslangic"), args.get("bitis")
    if not raw_start and not raw_end:
        return ReportPeriod(*preset_range(DEFAULT_PRESET, today), preset=DEFAULT_PRESET), notes

    start, end = parse_date(raw_start), parse_date(raw_end)
    if (raw_start and start is None) or (raw_end and end is None):
        notes.append("Tarih anlaşılamadı; son 30 gün gösteriliyor.")
        return ReportPeriod(*preset_range(DEFAULT_PRESET, today), preset=DEFAULT_PRESET), notes

    end = end or today
    start = start or end - timedelta(days=29)
    if start > end:
        start, end = end, start
        notes.append("Başlangıç tarihi bitişten sonraydı; tarihler yer değiştirildi.")
    if end > today:
        end = today
        start = min(start, today)
        notes.append("Gelecek tarihler raporlanamaz; bitiş bugün olarak alındı.")
    if (end - start).days + 1 > MAX_DAYS:
        start = end - timedelta(days=MAX_DAYS - 1)
        notes.append(f"Bir rapor en fazla {MAX_DAYS} gün kapsayabilir; başlangıç {start:%d.%m.%Y} olarak alındı.")
    return ReportPeriod(start, end), notes
