# reports/services/report_filters.py
from reports.models import TeacherReport


def get_approved_reports():
    """Базовый queryset утвержденных отчетов."""
    return TeacherReport.objects.filter(status='approved')


def apply_report_filters(
    queryset,
    *,
    period_id=None,
    class_id=None,
    status=None,
    teacher_id=None,
    parallel=None,
):
    """Применяет стандартные фильтры к queryset отчетов."""
    if period_id:
        queryset = queryset.filter(period_id=period_id)

    if class_id:
        queryset = queryset.filter(school_class_id=class_id)

    if status:
        queryset = queryset.filter(status=status)

    if teacher_id:
        queryset = queryset.filter(teacher_id=teacher_id)

    if parallel:
        queryset = queryset.filter(school_class__parallel=parallel)

    return queryset