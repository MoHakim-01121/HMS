"""Musim umrah (Season) dan periode bulanan yang dicakupnya.

Buku ditutup per bulan; musim adalah rentang laporan di atasnya. Setiap
tanggal yang diposting harus jatuh di sebuah FinancialPeriod, jadi membuat
atau melebarkan musim sekaligus membuat bulan-bulan yang belum ada.
"""
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models.period import FinancialPeriod, Season


def month_period_name(d):
    return f'{d.year}-{d.month:02d}'


def ensure_monthly_periods(date_from, date_to):
    """Create the calendar-month periods covering [date_from, date_to] that do
    not exist yet; a month an existing period already touches is left as it
    is. Returns the periods created."""
    created = []
    month = date_from.replace(day=1)
    while month <= date_to:
        end = month + relativedelta(months=1, days=-1)
        if not FinancialPeriod.objects.filter(date_from__lte=end, date_to__gte=month).exists():
            created.append(FinancialPeriod.objects.create(
                name=month_period_name(month), date_from=month, date_to=end,
            ))
        month += relativedelta(months=1)
    return created


def save_season(season=None, *, name, date_from, date_to):
    """Create (season=None) or change a season, then add the monthly periods
    it needs. Raises ValidationError with a message for the user."""
    name = (name or '').strip()
    if not name:
        raise ValidationError('Nama musim wajib diisi.')
    if not isinstance(date_from, date) or not isinstance(date_to, date):
        raise ValidationError('Tanggal mulai dan selesai wajib diisi.')
    if date_from >= date_to:
        raise ValidationError('Tanggal selesai harus setelah tanggal mulai.')
    if Season.objects.filter(name__iexact=name).exclude(pk=season.pk if season else None).exists():
        raise ValidationError(f'Musim "{name}" sudah ada.')
    with transaction.atomic():
        season = season or Season()
        season.name, season.date_from, season.date_to = name, date_from, date_to
        season.save()
        ensure_monthly_periods(date_from, date_to)
    return season


def season_choices():
    """Seasons for a report's period picker, newest first."""
    return [{
        'id': s.pk,
        'name': s.name,
        'date_from': s.date_from.isoformat(),
        'date_to': s.date_to.isoformat(),
    } for s in Season.objects.all()]


# Musim umrah resmi Saudi dibuka 14 Dzulhijjah, tepat setelah haji (kalender
# Kementerian Haji dan Umrah: 1448 H mulai 14 Dzulhijjah 1447 = 31 Mei 2026).
_SEASON_OPENS = (12, 14)   # (bulan Hijriah, tanggal)


def _season_start(hijri_year):
    """Tanggal Masehi musim `hijri_year` H dibuka: 14 Dzulhijjah tahun sebelumnya."""
    from hijridate import Hijri
    return date(*Hijri(hijri_year - 1, *_SEASON_OPENS).to_gregorian().datetuple())


def suggest_next_season(today=None):
    """{'name', 'date_from', 'date_to'} untuk musim berikutnya, menurut kalender
    Umm al-Qura (keputusan user 2026-10-20). Musim bersambung: berakhir sehari
    sebelum musim berikutnya dibuka, supaya setiap tanggal (termasuk masa haji)
    jatuh di satu musim. Tanpa musim tersimpan: musim yang sedang berjalan.
    Hanya saran -- user bisa mengubahnya sebelum menyimpan."""
    from hijridate import Gregorian
    last = Season.objects.order_by('-date_to').first()
    if last is not None:
        start = last.date_to + relativedelta(days=1)
        h = Gregorian.fromdate(start).to_hijri()
        # A season opening from Syawal onwards is next year's season.
        year = h.year + 1 if h.month >= 10 else h.year
    else:
        today = today or timezone.localdate()
        year = Gregorian.fromdate(today).to_hijri().year + 1
        if today < _season_start(year):
            year -= 1
        start = _season_start(year)
    return {'name': f'Musim {year}H', 'date_from': start,
            'date_to': _season_start(year + 1) - relativedelta(days=1)}
