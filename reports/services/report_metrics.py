# reports/services/report_metrics.py

def sum_gender_from_age_groups(report):
    """Суммирует количество мальчиков и девочек по возрастным группам отчета."""
    boys = sum(group.boys_count for group in report.age_groups.all())
    girls = sum(group.girls_count for group in report.age_groups.all())
    return boys, girls


def calculate_quality_and_success(*, total_students, family_students, excellent, good, poor):
    """
    Рассчитывает:
    - качество знаний
    - успеваемость
    - число очно обучающихся

    Возвращает: (quality, success, in_person_students)
    """
    in_person_students = max(total_students - family_students, 0)

    if in_person_students <= 0:
        return 0, 0, 0

    quality = round(((excellent + good) / in_person_students) * 100, 1)
    success = round(((in_person_students - poor) / in_person_students) * 100, 1)
    return quality, success, in_person_students


def calculate_quality_and_success_from_report(report):
    """
    Рассчитывает качество и успеваемость по объекту отчета.
    Использует очный контингент (без семейного обучения).
    Возвращает: (quality, success)
    """
    academic = getattr(report, 'academic_performance', None)
    family = getattr(report, 'family_education', None)

    total_students = report.total_students_end
    family_students = family.count if family and family.has_family_education else 0

    excellent = academic.excellent_count if academic else 0
    good = academic.good_count if academic else 0
    poor = academic.poor_count if academic else 0

    quality, success, _ = calculate_quality_and_success(
        total_students=total_students,
        family_students=family_students,
        excellent=excellent,
        good=good,
        poor=poor,
    )
    return quality, success


def calc_percent_change(old_value, new_value):
    """Рассчитывает процентное изменение между двумя значениями."""
    if old_value == 0:
        return 100 if new_value > 0 else 0
    return round(((new_value - old_value) / old_value) * 100, 1)