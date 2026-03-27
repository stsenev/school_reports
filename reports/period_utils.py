# reports/period_utils.py
from .models import ReportPeriod, TeacherReport


def is_high_school_class(school_class):
    """
    10 и 11 классы работают по полугодиям.
    Остальные классы — по четвертям.
    """
    return school_class.parallel in [10, 11]


def is_period_allowed_for_class(school_class, period):
    """
    Проверяет, разрешен ли данный тип периода для конкретного класса.
    """
    if is_high_school_class(school_class):
        return period.period_type in ['start_year', 'half1', 'half2', 'year']

    return period.period_type in ['start_year', 'quarter1', 'quarter2', 'quarter3', 'quarter4', 'year']


def has_approved_report(teacher, school_class, period_type, academic_year):
    """
    Проверяет наличие утвержденного отчета по типу периода.
    """
    required_period = ReportPeriod.objects.filter(
        period_type=period_type,
        academic_year=academic_year,
        is_active=True
    ).first()

    if not required_period:
        return False

    return TeacherReport.objects.filter(
        teacher=teacher,
        school_class=school_class,
        period=required_period,
        status='approved'
    ).exists()


def check_period_availability(teacher, school_class, target_period):
    """
    Проверяет, доступен ли целевой период для заполнения.
    Возвращает (доступен, сообщение_об_ошибке)
    """

    if not is_period_allowed_for_class(school_class, target_period):
        if is_high_school_class(school_class):
            return False, (
                f'Для класса {school_class.name} доступны только отчеты '
                f'за начало учебного года, 1 полугодие, 2 полугодие и год. '
                f'Отчеты по четвертям недоступны.'
            )
        return False, (
            f'Для класса {school_class.name} доступны только отчеты '
            f'за начало учебного года, четверти и год. '
            f'Отчеты по полугодиям недоступны.'
        )

    # Логика для 10-11 классов
    if is_high_school_class(school_class):
        if target_period.period_type == 'start_year':
            return True, ''

        if target_period.period_type == 'half1':
            has_start_year = has_approved_report(
                teacher, school_class, 'start_year', target_period.academic_year
            )
            if not has_start_year:
                return False, (
                    'Для заполнения отчета за 1 полугодие необходимо наличие '
                    'утвержденного отчета за начало учебного года.'
                )
            return True, ''

        if target_period.period_type == 'half2':
            has_half1 = has_approved_report(
                teacher, school_class, 'half1', target_period.academic_year
            )
            if not has_half1:
                return False, (
                    'Для заполнения отчета за 2 полугодие необходимо наличие '
                    'утвержденного отчета за 1 полугодие.'
                )
            return True, ''

        if target_period.period_type == 'year':
            has_half2 = has_approved_report(
                teacher, school_class, 'half2', target_period.academic_year
            )
            if not has_half2:
                return False, (
                    'Для заполнения годового отчета необходимо наличие '
                    'утвержденного отчета за 2 полугодие.'
                )
            return True, ''

        return False, 'Недопустимый тип отчетного периода для данного класса.'

    # Логика для остальных классов
    if target_period.period_type == 'start_year':
        return True, ''

    if target_period.period_type == 'quarter1':
        has_start_year = has_approved_report(
            teacher, school_class, 'start_year', target_period.academic_year
        )
        if not has_start_year:
            return False, (
                'Для заполнения отчета за 1 четверть необходимо наличие '
                'утвержденного отчета за начало учебного года.'
            )
        return True, ''

    if target_period.period_type == 'quarter2':
        has_q1 = has_approved_report(
            teacher, school_class, 'quarter1', target_period.academic_year
        )
        if not has_q1:
            return False, (
                'Для заполнения отчета за 2 четверть необходимо наличие '
                'утвержденного отчета за 1 четверть.'
            )
        return True, ''

    if target_period.period_type == 'quarter3':
        has_q2 = has_approved_report(
            teacher, school_class, 'quarter2', target_period.academic_year
        )
        if not has_q2:
            return False, (
                'Для заполнения отчета за 3 четверть необходимо наличие '
                'утвержденного отчета за 2 четверть.'
            )
        return True, ''

    if target_period.period_type == 'quarter4':
        has_q3 = has_approved_report(
            teacher, school_class, 'quarter3', target_period.academic_year
        )
        if not has_q3:
            return False, (
                'Для заполнения отчета за 4 четверть необходимо наличие '
                'утвержденного отчета за 3 четверть.'
            )
        return True, ''

    if target_period.period_type == 'year':
        has_q4 = has_approved_report(
            teacher, school_class, 'quarter4', target_period.academic_year
        )
        if not has_q4:
            return False, (
                'Для заполнения годового отчета необходимо наличие '
                'утвержденного отчета за 4 четверть.'
            )
        return True, ''

    return False, 'Недопустимый тип отчетного периода.'


def get_previous_approved_report(teacher, school_class, current_period):
    """
    Получает предыдущий утвержденный отчет для указанного периода.
    """

    if is_high_school_class(school_class):
        previous_map = {
            'half1': 'start_year',
            'half2': 'half1',
            'year': 'half2',
        }
    else:
        previous_map = {
            'quarter1': 'start_year',
            'quarter2': 'quarter1',
            'quarter3': 'quarter2',
            'quarter4': 'quarter3',
            'year': 'quarter4',
        }

    previous_type = previous_map.get(current_period.period_type)
    if not previous_type:
        return None

    previous_period = ReportPeriod.objects.filter(
        period_type=previous_type,
        academic_year=current_period.academic_year,
        is_active=True
    ).first()

    if not previous_period:
        return None

    return TeacherReport.objects.filter(
        teacher=teacher,
        school_class=school_class,
        period=previous_period,
        status='approved'
    ).select_related(
        'family_education', 'health_groups', 'phys_ed_groups', 'special_needs'
    ).prefetch_related(
        'age_groups',
        'movements',
        'family_education__students',
        'phys_ed_groups__exempt_students',
        'special_needs__students',
        'academic_performance__excellent_students',
        'academic_performance__one_four_students',
        'academic_performance__one_three_students',
        'academic_performance__poor_students',
        'academic_performance__not_attested_students'
    ).first()