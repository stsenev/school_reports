# reports/services/summary_service.py
from django.db.models import Sum

from .report_filters import apply_report_filters, get_approved_reports
from .report_metrics import sum_gender_from_age_groups


def get_summary_report_data(*, period_id=None, class_id=None, parallel=None, show_family=False):
    """
    Собирает данные для сводного отчета.
    Возвращает словарь для context.
    """
    reports = get_approved_reports().select_related(
        'teacher',
        'school_class',
        'period',
        'academic_performance',
        'family_education',
    ).prefetch_related(
        'age_groups',
        'family_education__students',
        'academic_performance__poor_students',
    ).order_by('school_class__parallel', 'school_class__name', 'period__start_date')

    reports = apply_report_filters(
        reports,
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
    )

    total_reports = reports.count()
    total_all_students = reports.aggregate(total=Sum('total_students_end'))['total'] or 0

    total_family_students = 0
    total_boys = 0
    total_girls = 0
    total_recurring_poor = 0
    family_students_list = []

    for report in reports:
        family = getattr(report, 'family_education', None)
        if family and family.has_family_education:
            total_family_students += family.count

            if show_family:
                for student in family.students.all():
                    family_students_list.append({
                        'name': student.full_name,
                        'class': report.school_class.name,
                        'teacher': report.teacher.full_name,
                        'period': f'{report.period.name} {report.period.academic_year}',
                    })

        boys, girls = sum_gender_from_age_groups(report)
        total_boys += boys
        total_girls += girls

        academic = getattr(report, 'academic_performance', None)
        if academic:
            total_recurring_poor += academic.poor_students.filter(is_recurring=True).count()

    total_in_person_students = total_all_students - total_family_students

    stats = reports.aggregate(
        total_excellent=Sum('academic_performance__excellent_count'),
        total_good=Sum('academic_performance__good_count'),
        total_poor=Sum('academic_performance__poor_count'),
    )

    if total_in_person_students > 0:
        quality = round(
            ((stats['total_excellent'] or 0) + (stats['total_good'] or 0))
            / total_in_person_students * 100,
            1,
        )
        success = round(
            (total_in_person_students - (stats['total_poor'] or 0))
            / total_in_person_students * 100,
            1,
        )
    else:
        quality = 0
        success = 0

    return {
        'reports': reports,
        'total_reports': total_reports,
        'total_all_students': total_all_students,
        'total_family_students': total_family_students,
        'total_in_person_students': total_in_person_students,
        'total_boys': total_boys,
        'total_girls': total_girls,
        'total_recurring_poor': total_recurring_poor,
        'family_students_list': family_students_list if show_family else [],
        'stats': stats,
        'quality': quality,
        'success': success,
    }