# reports/services/dynamics_service.py
from django.shortcuts import get_object_or_404

from ..models import ReportPeriod
from .report_filters import apply_report_filters, get_approved_reports
from .report_metrics import (
    calc_percent_change,
    calculate_quality_and_success_from_report,
    sum_gender_from_age_groups,
)


def get_dynamics_report_data(*, period_from_id, period_to_id, class_id=None, parallel=None):
    """
    Собирает данные для отчета по динамике между двумя периодами.
    """
    period_from = get_object_or_404(ReportPeriod, id=period_from_id)
    period_to = get_object_or_404(ReportPeriod, id=period_to_id)

    base_reports = get_approved_reports().select_related(
        'teacher',
        'school_class',
        'period',
        'academic_performance',
        'family_education',
        'health_groups',
        'phys_ed_groups',
        'special_needs',
    ).prefetch_related(
        'age_groups',
        'movements',
        'special_needs__students',
    )

    base_reports = apply_report_filters(
        base_reports,
        class_id=class_id,
        parallel=parallel,
    )

    reports_from = base_reports.filter(period_id=period_from_id)
    reports_to = base_reports.filter(period_id=period_to_id)

    reports_from_dict = {report.school_class_id: report for report in reports_from}
    reports_to_dict = {report.school_class_id: report for report in reports_to}
    common_class_ids = sorted(set(reports_from_dict.keys()) & set(reports_to_dict.keys()))

    dynamics_data = []
    totals = {
        'students_from': 0, 'students_to': 0, 'students_diff': 0, 'students_percent': 0,
        'boys_from': 0, 'boys_to': 0, 'boys_diff': 0, 'boys_percent': 0,
        'girls_from': 0, 'girls_to': 0, 'girls_diff': 0, 'girls_percent': 0,
        'excellent_from': 0, 'excellent_to': 0, 'excellent_diff': 0, 'excellent_percent': 0,
        'good_from': 0, 'good_to': 0, 'good_diff': 0, 'good_percent': 0,
        'poor_from': 0, 'poor_to': 0, 'poor_diff': 0, 'poor_percent': 0,
        'quality_from': 0, 'quality_to': 0, 'quality_diff': 0,
        'success_from': 0, 'success_to': 0, 'success_diff': 0,
        'disabled_from': 0, 'disabled_to': 0, 'disabled_diff': 0,
        'special_needs_from': 0, 'special_needs_to': 0, 'special_needs_diff': 0,
        'home_schooling_from': 0, 'home_schooling_to': 0, 'home_schooling_diff': 0,
        'foster_care_from': 0, 'foster_care_to': 0, 'foster_care_diff': 0,
        'family_education_from': 0, 'family_education_to': 0, 'family_education_diff': 0,
    }

    for school_class_id in common_class_ids:
        report_from = reports_from_dict[school_class_id]
        report_to = reports_to_dict[school_class_id]

        boys_from, girls_from = sum_gender_from_age_groups(report_from)
        boys_to, girls_to = sum_gender_from_age_groups(report_to)

        perf_from = getattr(report_from, 'academic_performance', None)
        perf_to = getattr(report_to, 'academic_performance', None)

        excellent_from = perf_from.excellent_count if perf_from else 0
        excellent_to = perf_to.excellent_count if perf_to else 0
        good_from = perf_from.good_count if perf_from else 0
        good_to = perf_to.good_count if perf_to else 0
        poor_from = perf_from.poor_count if perf_from else 0
        poor_to = perf_to.poor_count if perf_to else 0

        quality_from, success_from = calculate_quality_and_success_from_report(report_from)
        quality_to, success_to = calculate_quality_and_success_from_report(report_to)

        special_from = getattr(report_from, 'special_needs', None)
        special_to = getattr(report_to, 'special_needs', None)

        disabled_from = special_from.disabled_count if special_from else 0
        disabled_to = special_to.disabled_count if special_to else 0
        special_needs_from = special_from.special_needs_count if special_from else 0
        special_needs_to = special_to.special_needs_count if special_to else 0
        home_schooling_from = special_from.home_schooling_count if special_from else 0
        home_schooling_to = special_to.home_schooling_count if special_to else 0
        foster_care_from = special_from.foster_care_count if special_from else 0
        foster_care_to = special_to.foster_care_count if special_to else 0

        family_from = getattr(report_from, 'family_education', None)
        family_to = getattr(report_to, 'family_education', None)
        family_from_count = family_from.count if family_from and family_from.has_family_education else 0
        family_to_count = family_to.count if family_to and family_to.has_family_education else 0

        row = {
            'class': report_from.school_class.name,
            'teacher': report_from.teacher.full_name,

            'students_from': report_from.total_students_end,
            'students_to': report_to.total_students_end,
            'students_diff': report_to.total_students_end - report_from.total_students_end,
            'students_percent': calc_percent_change(report_from.total_students_end, report_to.total_students_end),

            'boys_from': boys_from,
            'boys_to': boys_to,
            'boys_diff': boys_to - boys_from,
            'boys_percent': calc_percent_change(boys_from, boys_to),

            'girls_from': girls_from,
            'girls_to': girls_to,
            'girls_diff': girls_to - girls_from,
            'girls_percent': calc_percent_change(girls_from, girls_to),

            'excellent_from': excellent_from,
            'excellent_to': excellent_to,
            'excellent_diff': excellent_to - excellent_from,
            'excellent_percent': calc_percent_change(excellent_from, excellent_to),

            'good_from': good_from,
            'good_to': good_to,
            'good_diff': good_to - good_from,
            'good_percent': calc_percent_change(good_from, good_to),

            'poor_from': poor_from,
            'poor_to': poor_to,
            'poor_diff': poor_to - poor_from,
            'poor_percent': calc_percent_change(poor_from, poor_to),

            'quality_from': quality_from,
            'quality_to': quality_to,
            'quality_diff': round(quality_to - quality_from, 1),

            'success_from': success_from,
            'success_to': success_to,
            'success_diff': round(success_to - success_from, 1),

            'disabled_from': disabled_from,
            'disabled_to': disabled_to,
            'disabled_diff': disabled_to - disabled_from,

            'special_needs_from': special_needs_from,
            'special_needs_to': special_needs_to,
            'special_needs_diff': special_needs_to - special_needs_from,

            'home_schooling_from': home_schooling_from,
            'home_schooling_to': home_schooling_to,
            'home_schooling_diff': home_schooling_to - home_schooling_from,

            'foster_care_from': foster_care_from,
            'foster_care_to': foster_care_to,
            'foster_care_diff': foster_care_to - foster_care_from,

            'family_education_from': family_from_count,
            'family_education_to': family_to_count,
            'family_education_diff': family_to_count - family_from_count,
        }
        dynamics_data.append(row)

        for key in [
            'students_from', 'students_to',
            'boys_from', 'boys_to',
            'girls_from', 'girls_to',
            'excellent_from', 'excellent_to',
            'good_from', 'good_to',
            'poor_from', 'poor_to',
            'disabled_from', 'disabled_to',
            'special_needs_from', 'special_needs_to',
            'home_schooling_from', 'home_schooling_to',
            'foster_care_from', 'foster_care_to',
            'family_education_from', 'family_education_to',
        ]:
            totals[key] += row[key]

    totals['students_diff'] = totals['students_to'] - totals['students_from']
    totals['students_percent'] = calc_percent_change(totals['students_from'], totals['students_to'])

    totals['boys_diff'] = totals['boys_to'] - totals['boys_from']
    totals['boys_percent'] = calc_percent_change(totals['boys_from'], totals['boys_to'])

    totals['girls_diff'] = totals['girls_to'] - totals['girls_from']
    totals['girls_percent'] = calc_percent_change(totals['girls_from'], totals['girls_to'])

    totals['excellent_diff'] = totals['excellent_to'] - totals['excellent_from']
    totals['excellent_percent'] = calc_percent_change(totals['excellent_from'], totals['excellent_to'])

    totals['good_diff'] = totals['good_to'] - totals['good_from']
    totals['good_percent'] = calc_percent_change(totals['good_from'], totals['good_to'])

    totals['poor_diff'] = totals['poor_to'] - totals['poor_from']
    totals['poor_percent'] = calc_percent_change(totals['poor_from'], totals['poor_to'])

    total_in_person_from = totals['students_from'] - totals['family_education_from']
    total_in_person_to = totals['students_to'] - totals['family_education_to']

    if total_in_person_from > 0:
        totals['quality_from'] = round(
            (totals['excellent_from'] + totals['good_from']) / total_in_person_from * 100,
            1,
        )
        totals['success_from'] = round(
            (total_in_person_from - totals['poor_from']) / total_in_person_from * 100,
            1,
        )

    if total_in_person_to > 0:
        totals['quality_to'] = round(
            (totals['excellent_to'] + totals['good_to']) / total_in_person_to * 100,
            1,
        )
        totals['success_to'] = round(
            (total_in_person_to - totals['poor_to']) / total_in_person_to * 100,
            1,
        )

    totals['quality_diff'] = round(totals['quality_to'] - totals['quality_from'], 1)
    totals['success_diff'] = round(totals['success_to'] - totals['success_from'], 1)

    totals['disabled_diff'] = totals['disabled_to'] - totals['disabled_from']
    totals['special_needs_diff'] = totals['special_needs_to'] - totals['special_needs_from']
    totals['home_schooling_diff'] = totals['home_schooling_to'] - totals['home_schooling_from']
    totals['foster_care_diff'] = totals['foster_care_to'] - totals['foster_care_from']
    totals['family_education_diff'] = totals['family_education_to'] - totals['family_education_from']

    return {
        'period_from': period_from,
        'period_to': period_to,
        'dynamics_data': dynamics_data,
        'totals': totals,
        'has_data': True,
    }