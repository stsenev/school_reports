# reports/view_helpers.py

from django.contrib import messages
from django.shortcuts import redirect

from .models import ReportPeriod, SchoolClass, Teacher, TeacherReport
from .services.report_filters import apply_report_filters


def get_current_mode(user, session):
    """Определяет текущий режим работы пользователя."""
    if user.role != 'both':
        return user.role
    return session.get('user_mode', 'teacher')


def get_teacher_or_none(user):
    """Возвращает профиль учителя или None."""
    try:
        return Teacher.objects.select_related('user').get(user=user)
    except Teacher.DoesNotExist:
        return None


def get_teacher_or_redirect(request):
    """
    Возвращает (teacher, None), если профиль найден,
    иначе (None, redirect_response).
    """
    teacher = get_teacher_or_none(request.user)
    if teacher is None:
        messages.error(request, 'Профиль учителя не найден')
        return None, redirect('logout' if request.user.is_authenticated else 'dashboard')
    return teacher, None


def user_can_access_report(user, report):
    """Проверка доступа пользователя к отчету."""
    if user.is_head_teacher():
        return True

    if user.is_teacher():
        teacher = get_teacher_or_none(user)
        return teacher is not None and report.teacher_id == teacher.id

    return False


def get_report_filter_context(include_teachers=False):
    """Справочники для фильтров отчетов."""
    context = {
        'periods': ReportPeriod.objects.filter(is_active=True).order_by('-start_date'),
        'classes': SchoolClass.objects.filter(is_active=True).order_by('parallel', 'name'),
        'parallels': SchoolClass.objects.values_list('parallel', flat=True).distinct().order_by('parallel'),
    }

    if include_teachers:
        context['teachers'] = Teacher.objects.filter(
            is_active=True
        ).select_related('user').order_by('full_name')

    return context


def get_filtered_head_reports(request):
    """Отфильтрованный queryset отчетов для панели завуча."""
    period_id = request.GET.get('period')
    class_id = request.GET.get('class')
    status = request.GET.get('status')
    teacher_id = request.GET.get('teacher')

    reports = TeacherReport.objects.select_related(
        'teacher', 'school_class', 'period'
    ).order_by('-period__start_date', 'school_class__name')

    reports = apply_report_filters(
        reports,
        period_id=period_id,
        class_id=class_id,
        status=status,
        teacher_id=teacher_id,
    )

    return reports, period_id, class_id, status, teacher_id


def build_filename(base_name, *, period=None, school_class=None, parallel=None):
    """Формирует безопасное имя файла."""
    filename_parts = [base_name]

    if period:
        filename_parts.append(period.name.replace(' ', '_').replace('/', '_'))
    if school_class:
        filename_parts.append(f'class_{school_class.name}')
    if parallel:
        filename_parts.append(f'parallel_{parallel}')

    return "_".join(filename_parts).replace(' ', '_').replace('/', '_') + ".xlsx"