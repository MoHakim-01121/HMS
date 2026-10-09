"""Musim umrah (Season) dan periode bulanan yang dicakupnya.

Buku ditutup per bulan; musim adalah rentang laporan di atasnya. Setiap
tanggal yang diposting harus jatuh di sebuah FinancialPeriod, jadi membuat
atau melebarkan musim sekaligus membuat bulan-bulan yang belum ada.
"""
from datetime import date

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import transaction

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
