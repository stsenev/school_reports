from ..models import ClassReport, SchoolClass


DEPENDENCY_RULES = {
    # 10–11 классы
    'half1': ['start_year'],
    'half2': ['half1'],
    'year': ['half2'],

    # 1–9 классы
    'quarter2': ['quarter1'],
    'quarter3': ['quarter2'],
    'quarter4': ['quarter3'],
}


def get_parallel_from_class(school_class: SchoolClass):
    """
    Пытаемся взять параллель класса.
    """
    return getattr(school_class, 'parallel', None)


def uses_half_year_system(school_class: SchoolClass) -> bool:
    """
    10–11 классы работают по полугодиям.
    """
    parallel = get_parallel_from_class(school_class)
    return parallel in [10, 11]


def is_period_applicable_to_class(period, school_class: SchoolClass) -> bool:
    """
    Определяет, должен ли этот период вообще отображаться для класса.
    """
    period_type = period.period_type
    half_year_class = uses_half_year_system(school_class)

    if period_type == 'start_year':
        return half_year_class

    if period_type in ['half1', 'half2']:
        return half_year_class

    if period_type in ['quarter1', 'quarter2', 'quarter3', 'quarter4']:
        return not half_year_class

    if period_type == 'year':
        return True

    return False


def get_required_previous_period_types(period_type: str, school_class: SchoolClass):
    """
    Возвращает список обязательных предыдущих типов периодов.
    """
    if period_type == 'year':
        if uses_half_year_system(school_class):
            return ['half2']
        return ['quarter4']

    return DEPENDENCY_RULES.get(period_type, [])


def has_approved_report_for_period_type(*, school_class, academic_year, period_type):
    return ClassReport.objects.filter(
        school_class=school_class,
        period__academic_year=academic_year,
        period__period_type=period_type,
        status='approved'
    ).exists()


def can_create_report_for_period(*, school_class, period):
    """
    Проверяет, можно ли открыть/создать отчет по данному периоду для класса.
    """
    if not is_period_applicable_to_class(period, school_class):
        return False, 'Период не применяется для данного класса.'

    required_types = get_required_previous_period_types(period.period_type, school_class)
    for required_type in required_types:
        if not has_approved_report_for_period_type(
            school_class=school_class,
            academic_year=period.academic_year,
            period_type=required_type
        ):
            return False, f'Сначала нужен утвержденный отчет за период: {required_type}.'

    return True, ''


def get_available_periods_for_class(periods, school_class):
    """
    Возвращает список словарей по периодам с признаками доступности.
    Удобно для dashboard.
    """
    result = []

    for period in periods:
        applicable = is_period_applicable_to_class(period, school_class)

        if applicable:
            can_open, reason = can_create_report_for_period(
                school_class=school_class,
                period=period
            )
        else:
            can_open, reason = False, 'Период не используется для этого класса.'

        result.append({
            'period': period,
            'is_applicable': applicable,
            'is_available': can_open,
            'reason': reason,
        })

    return result