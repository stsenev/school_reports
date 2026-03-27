from datetime import date

from ..models import ReportPeriod


PERIOD_TEMPLATES = [
    ('start_year', 'Начало учебного года', (9, 1), (9, 15)),
    ('quarter1', '1 четверть', (9, 1), (10, 31)),
    ('quarter2', '2 четверть', (11, 1), (12, 31)),
    ('quarter3', '3 четверть', (1, 9), (3, 20)),
    ('quarter4', '4 четверть', (3, 21), (5, 31)),
    ('half1', '1 полугодие', (9, 1), (12, 31)),
    ('half2', '2 полугодие', (1, 9), (5, 31)),
    ('year', 'Год', (9, 1), (5, 31)),
]


def parse_academic_year(academic_year: str):
    start_year, end_year = academic_year.split('/')
    return int(start_year), int(end_year)


def build_period_dates(start_year: int, end_year: int, start_md: tuple, end_md: tuple):
    start_month, start_day = start_md
    end_month, end_day = end_md

    start_date = date(start_year if start_month >= 9 else end_year, start_month, start_day)
    end_date = date(start_year if end_month >= 9 else end_year, end_month, end_day)

    return start_date, end_date


def ensure_report_periods_for_year(academic_year: str):
    existing_types = set(
        ReportPeriod.objects.filter(
            academic_year=academic_year
        ).values_list('period_type', flat=True)
    )

    start_year, end_year = parse_academic_year(academic_year)
    created = []

    for period_type, name, start_md, end_md in PERIOD_TEMPLATES:
        if period_type in existing_types:
            continue

        start_date, end_date = build_period_dates(start_year, end_year, start_md, end_md)

        period = ReportPeriod.objects.create(
            name=name,
            period_type=period_type,
            academic_year=academic_year,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
        )
        created.append(period)

    return created


def get_periods_for_year(academic_year):
    return ReportPeriod.objects.filter(
        academic_year=academic_year
    ).order_by('start_date')


def get_period_by_id(period_id):
    return ReportPeriod.objects.select_related().get(id=period_id)