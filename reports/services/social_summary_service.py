# reports/services/social_summary_service.py

from .report_filters import apply_report_filters, get_approved_reports


def get_social_summary_report_data(*, period_id=None, class_id=None, parallel=None, show_details=False):
    """
    Собирает данные для сводного социального отчета.
    Возвращает словарь, готовый для template context.
    """
    reports = get_approved_reports().select_related(
        'teacher',
        'school_class',
        'period',
        'special_needs',
        'family_education',
    ).prefetch_related(
        'special_needs__students',
        'family_education__students',
    ).order_by('school_class__parallel', 'school_class__name')

    reports = apply_report_filters(
        reports,
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
    )

    total_reports = reports.count()
    table_data = []

    total_all_students = 0
    total_disabled = 0
    total_special_needs = 0
    total_disabled_special = 0
    total_home_schooling = 0
    total_foster_care = 0
    total_family_education = 0

    for report in reports:
        row = {
            'class': report.school_class.name,
            'teacher': report.teacher.full_name,
            'period': f"{report.period.name} {report.period.academic_year}",
            'total_students': report.total_students_end,
            'disabled': 0,
            'special_needs': 0,
            'disabled_special': 0,
            'home_schooling': 0,
            'foster_care': 0,
            'family_education': 0,
            'students_list': [],
        }

        total_all_students += report.total_students_end

        special = getattr(report, 'special_needs', None)
        if special:
            row['disabled'] = special.disabled_count
            row['special_needs'] = special.special_needs_count
            row['disabled_special'] = special.disabled_special_needs_count
            row['home_schooling'] = special.home_schooling_count
            row['foster_care'] = special.foster_care_count

            total_disabled += special.disabled_count
            total_special_needs += special.special_needs_count
            total_disabled_special += special.disabled_special_needs_count
            total_home_schooling += special.home_schooling_count
            total_foster_care += special.foster_care_count

            if show_details:
                for student in special.students.all():
                    row['students_list'].append({
                        'name': student.full_name,
                        'type': student.get_student_type_display(),
                        'category': 'special',
                    })

        family = getattr(report, 'family_education', None)
        if family and family.has_family_education:
            row['family_education'] = family.count
            total_family_education += family.count

            if show_details:
                for student in family.students.all():
                    row['students_list'].append({
                        'name': student.full_name,
                        'type': 'Семейное обучение',
                        'category': 'family',
                    })

        table_data.append(row)

    return {
        'reports': reports,
        'table_data': table_data,
        'total_reports': total_reports,
        'total_all_students': total_all_students,
        'total_disabled': total_disabled,
        'total_special_needs': total_special_needs,
        'total_disabled_special': total_disabled_special,
        'total_home_schooling': total_home_schooling,
        'total_foster_care': total_foster_care,
        'total_family_education': total_family_education,
        'show_details': show_details,
    }