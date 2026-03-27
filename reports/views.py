from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import (
    StudentAgeGroupForm,
    StudentMovementForm,
    TeacherRegistrationForm,
)
from .models import (
    ReportPeriod,
    SchoolClass,
    Teacher,
    TeacherReport,
    User,
)
from .period_utils import check_period_availability, is_period_allowed_for_class
from .services.dynamics_service import get_dynamics_report_data
from .services.excel_export_utils import (
    build_excel_response,
    create_workbook,
    set_column_widths,
    write_data_rows,
    write_filter_row,
    write_headers,
    write_total_row,
)
from .services.report_metrics import calculate_quality_and_success, sum_gender_from_age_groups
from .services.social_summary_service import get_social_summary_report_data
from .services.summary_service import get_summary_report_data
from .services.academic_utils import check_recurring_poor_student
from .view_helpers import (
    build_filename,
    get_current_mode,
    get_filtered_head_reports,
    get_report_filter_context,
    get_teacher_or_none,
    get_teacher_or_redirect,
    user_can_access_report,
)


@login_required
def dashboard(request):
    """Главная панель управления учителя."""
    user = request.user
    current_mode = get_current_mode(user, request.session)

    if current_mode not in ['teacher', 'both']:
        return redirect('head_dashboard')

    teacher, redirect_response = get_teacher_or_redirect(request)
    if redirect_response:
        return redirect_response

    homeroom_classes = teacher.homeroom_classes.filter(is_active=True).order_by('parallel', 'name')

    # Все активные учебные годы без дублей
    academic_years = sorted(set(
        ReportPeriod.objects.filter(is_active=True).values_list('academic_year', flat=True)
    ))

    # Выбранный год
    selected_year = request.GET.get('year')

    if not selected_year or selected_year not in academic_years:
        selected_year = academic_years[-1] if academic_years else None

    # Все активные периоды выбранного года
    all_periods = list(
        ReportPeriod.objects.filter(
            is_active=True,
            academic_year=selected_year
        ).order_by('start_date')
    ) if selected_year else []

    reports = TeacherReport.objects.filter(
        teacher=teacher,
        school_class__in=homeroom_classes,
        period__academic_year=selected_year,
    ).select_related(
        'period',
        'school_class',
    ).order_by(
        'school_class__parallel',
        'school_class__name',
        'period__start_date'
    )

    quarter_order = ['start_year', 'quarter1', 'quarter2', 'quarter3', 'quarter4', 'year']
    half_order = ['start_year', 'half1', 'half2', 'year']

    quarter_periods = sorted(
        [p for p in all_periods if p.period_type in quarter_order],
        key=lambda p: quarter_order.index(p.period_type)
    )
    half_periods = sorted(
        [p for p in all_periods if p.period_type in half_order],
        key=lambda p: half_order.index(p.period_type)
    )

    report_map = {
        (report.school_class_id, report.period_id): report
        for report in reports
    }

    dashboard_classes = []

    for class_obj in homeroom_classes:
        class_periods = half_periods if class_obj.parallel in [10, 11] else quarter_periods

        period_cards = []
        approved_count = 0
        total_count = len(class_periods)

        for period in class_periods:
            report = report_map.get((class_obj.id, period.id))

            if report:
                if report.status == 'approved':
                    approved_count += 1

                period_cards.append({
                    'period': period,
                    'report': report,
                    'status': report.status,
                    'available': True,
                    'message': '',
                })
            else:
                is_allowed = is_period_allowed_for_class(class_obj, period)
                is_available, error_message = check_period_availability(teacher, class_obj, period)

                period_cards.append({
                    'period': period,
                    'report': None,
                    'status': None,
                    'available': is_allowed and is_available,
                    'message': error_message if not is_available else '',
                })

        dashboard_classes.append({
            'class_obj': class_obj,
            'period_cards': period_cards,
            'approved_count': approved_count,
            'total_count': total_count,
        })

    context = {
        'teacher': teacher,
        'homeroom_classes': homeroom_classes,
        'reports': reports,
        'dashboard_classes': dashboard_classes,
        'academic_years': academic_years,
        'selected_year': selected_year,
        'is_head_teacher': user.is_head_teacher(),
        'current_mode': current_mode,
    }
    return render(request, 'reports/teacher_dashboard.html', context)


@login_required
def head_dashboard(request):
    """Панель завуча."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    all_reports = TeacherReport.objects.all()
    total_reports = all_reports.count()
    pending_count = all_reports.filter(status='submitted').count()
    approved_count = all_reports.filter(status='approved').count()
    draft_count = all_reports.filter(status='draft').count()
    rejected_count = all_reports.filter(status='rejected').count()

    reports, period_id, class_id, status, teacher_id = get_filtered_head_reports(request)

    context = {
        'reports': reports,
        'total_reports': total_reports,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'draft_count': draft_count,
        'rejected_count': rejected_count,
        'selected_period': period_id,
        'selected_class': class_id,
        'selected_status': status,
        'selected_teacher': teacher_id,
        **get_report_filter_context(include_teachers=True),
    }
    return render(request, 'reports/head_dashboard.html', context)


@login_required
def switch_role(request):
    """Переключение между ролями."""
    if request.user.role != 'both':
        messages.error(request, 'Эта функция недоступна')
        return redirect('dashboard')

    current_mode = request.session.get('user_mode', 'teacher')
    request.session['user_mode'] = 'head_teacher' if current_mode == 'teacher' else 'teacher'

    messages.success(
        request,
        f'Режим переключен на {"завуча" if current_mode == "teacher" else "учителя"}'
    )
    return redirect('dashboard')


@login_required
def select_class_for_report(request, period_id):
    """Выбор класса для создания отчета."""
    if not request.user.is_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period = get_object_or_404(ReportPeriod, id=period_id, is_active=True)

    teacher, redirect_response = get_teacher_or_redirect(request)
    if redirect_response:
        return redirect_response

    all_homeroom_classes = teacher.homeroom_classes.filter(is_active=True)

    if not all_homeroom_classes.exists():
        messages.error(request, 'У вас нет назначенных классов')
        return redirect('dashboard')

    # Показываем только те классы, которым этот период вообще разрешен
    homeroom_classes = [
        class_obj for class_obj in all_homeroom_classes
        if is_period_allowed_for_class(class_obj, period)
    ]

    if not homeroom_classes:
        messages.error(
            request,
            f'Для периода "{period.name}" у вас нет подходящих классов.'
        )
        return redirect('dashboard')

    period_availability = {}
    for class_obj in homeroom_classes:
        is_available, error_message = check_period_availability(teacher, class_obj, period)
        period_availability[class_obj.id] = {
            'available': is_available,
            'message': error_message if not is_available else '',
        }

    start_year_approved = {}
    if period.period_type == 'quarter1':
        start_year_period = ReportPeriod.objects.filter(
            period_type='start_year',
            academic_year=period.academic_year,
            is_active=True,
        ).first()

        if start_year_period:
            for class_obj in homeroom_classes:
                start_year_approved[class_obj.id] = TeacherReport.objects.filter(
                    teacher=teacher,
                    school_class=class_obj,
                    period=start_year_period,
                    status='approved',
                ).exists()

    existing_reports = TeacherReport.objects.filter(
        teacher=teacher,
        period=period,
        school_class__in=homeroom_classes,
    ).select_related('school_class')

    existing_class_ids = list(existing_reports.values_list('school_class_id', flat=True))

    context = {
        'period': period,
        'homeroom_classes': homeroom_classes,
        'existing_reports': existing_reports,
        'existing_class_ids': existing_class_ids,
        'start_year_approved': start_year_approved,
        'period_availability': period_availability,
    }
    return render(request, 'reports/select_class.html', context)


@login_required
def create_report(request, period_id, class_id):
    """Перенаправление на пошаговый мастер."""
    messages.info(request, 'Используйте пошаговый мастер для заполнения отчета')
    return redirect('wizard_start', period_id=period_id, class_id=class_id)


@login_required
def edit_report(request, report_id):
    """Перенаправление на пошаговый мастер."""
    messages.info(request, 'Используйте пошаговый мастер для редактирования отчета')
    return redirect('wizard_step1', report_id=report_id)


@login_required
def view_report(request, report_id):
    """Просмотр отчета."""
    report = get_object_or_404(
        TeacherReport.objects.select_related(
            'teacher',
            'school_class',
            'period',
            'family_education',
            'health_groups',
            'phys_ed_groups',
            'special_needs',
            'academic_performance',
        ).prefetch_related(
            'movements',
            'age_groups',
            'family_education__students',
            'phys_ed_groups__exempt_students',
            'special_needs__students',
            'academic_performance__excellent_students',
            'academic_performance__one_four_students',
            'academic_performance__one_three_students',
            'academic_performance__poor_students',
            'academic_performance__not_attested_students',
            'academic_performance__retained_students',
            'academic_performance__conditionally_promoted_students',
        ),
        id=report_id,
    )

    if not user_can_access_report(request.user, report):
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    academic = getattr(report, 'academic_performance', None)

    if academic and report.total_students_end > 0:
        quality = round(
            (academic.excellent_count + academic.good_count) / report.total_students_end * 100,
            1,
        )
        success = round(
            (report.total_students_end - academic.poor_count) / report.total_students_end * 100,
            1,
        )
    else:
        quality = 0
        success = 0

    context = {
        'report': report,
        'movements': report.movements.all(),
        'family_education': getattr(report, 'family_education', None),
        'age_groups': report.age_groups.all().order_by('-birth_year'),
        'health_groups': getattr(report, 'health_groups', None),
        'phys_ed_groups': getattr(report, 'phys_ed_groups', None),
        'special_needs': getattr(report, 'special_needs', None),
        'academic': academic,
        'quality': quality,
        'success': success,
        'subject_dict': dict(settings.SCHOOL_SUBJECTS),
    }

    if academic:
        context.update({
            'excellent_students': academic.excellent_students.all(),
            'one_four_students': academic.one_four_students.all(),
            'one_three_students': academic.one_three_students.all(),
            'poor_students': academic.poor_students.all(),
            'not_attested_students': academic.not_attested_students.all(),
            'retained_students': academic.retained_students.all(),
            'conditionally_promoted_students': academic.conditionally_promoted_students.all(),
        })

    return render(request, 'reports/view_report.html', context)


@login_required
def submit_report(request, report_id):
    """Отправка отчета на проверку."""
    if request.method != 'POST':
        return redirect('view_report', report_id=report_id)

    report = get_object_or_404(TeacherReport, id=report_id)

    if not user_can_access_report(request.user, report):
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    if request.user.is_teacher():
        if report.status != 'draft':
            messages.error(request, 'Отчет уже отправлен')
            return redirect('view_report', report_id=report_id)

        report.status = 'submitted'
        report.submitted_at = timezone.now()
        report.save(update_fields=['status', 'submitted_at'])

        messages.success(request, 'Отчет отправлен на проверку')

    return redirect('view_report', report_id=report_id)


@login_required
def approve_report(request, report_id):
    """Утверждение отчета."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('view_report', report_id=report_id)

    report = get_object_or_404(TeacherReport, id=report_id)

    if report.status != 'submitted':
        messages.error(request, 'Можно утверждать только отправленные отчеты')
        return redirect('view_report', report_id=report_id)

    report.status = 'approved'
    report.approved_by = request.user
    report.save(update_fields=['status', 'approved_by'])

    messages.success(request, 'Отчет утвержден')
    return redirect('view_report', report_id=report_id)


@login_required
def reject_report(request, report_id):
    """Отклонение отчета."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    if request.method != 'POST':
        return redirect('view_report', report_id=report_id)

    report = get_object_or_404(TeacherReport, id=report_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        messages.error(request, 'Укажите причину отклонения')
        return redirect('view_report', report_id=report_id)

    if report.status != 'submitted':
        messages.error(request, 'Можно отклонять только отправленные отчеты')
        return redirect('view_report', report_id=report_id)

    report.status = 'rejected'
    report.save(update_fields=['status'])

    messages.success(request, 'Отчет отклонен')
    return redirect('view_report', report_id=report_id)


@login_required
def change_report_status(request, report_id):
    """Изменение статуса отчета (для завуча)."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    report = get_object_or_404(TeacherReport, id=report_id)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        comment = request.POST.get('comment', '').strip()

        if new_status not in dict(TeacherReport.STATUS_CHOICES):
            messages.error(request, 'Некорректный статус')
            return redirect('view_report', report_id=report.id)

        old_status = report.status
        report.status = new_status
        report.approved_by = request.user
        report.save(update_fields=['status', 'approved_by'])

        messages.success(
            request,
            f'Статус отчета изменен с "{dict(TeacherReport.STATUS_CHOICES)[old_status]}" '
            f'на "{dict(TeacherReport.STATUS_CHOICES)[new_status]}"'
        )

        if comment:
            messages.info(request, f'Комментарий: {comment}')

        return redirect('view_report', report_id=report.id)

    return render(request, 'reports/change_status.html', {
        'report': report,
        'status_choices': TeacherReport.STATUS_CHOICES,
        'back_url': request.META.get('HTTP_REFERER', 'head_dashboard'),
    })


@login_required
def delete_report(request, report_id):
    """Удаление отчета."""
    report = get_object_or_404(TeacherReport, id=report_id)

    if not user_can_access_report(request.user, report):
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    teacher_only = request.user.is_teacher() and not request.user.is_head_teacher()
    if teacher_only and report.status != 'draft':
        messages.error(request, 'Можно удалять только черновики отчетов')
        return redirect('view_report', report_id=report.id)

    if request.method == 'POST':
        report_name = (
            f'Отчет {report.teacher.full_name} - {report.school_class.name} - '
            f'{report.period.name} {report.period.academic_year}'
        )
        report.delete()
        messages.success(request, f'Отчет "{report_name}" успешно удален')

        if request.user.is_head_teacher() and not request.user.is_teacher():
            return redirect('head_dashboard')
        return redirect('dashboard')

    return render(request, 'reports/confirm_delete.html', {
        'report': report,
        'back_url': request.META.get('HTTP_REFERER', 'dashboard'),
    })


@login_required
def bulk_change_status(request):
    """Массовое изменение статусов отчетов."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    if request.method == 'POST':
        report_ids = request.POST.getlist('report_ids')
        new_status = request.POST.get('status')

        if not report_ids:
            messages.error(request, 'Не выбрано ни одного отчета')
            return redirect('head_dashboard')

        if new_status not in dict(TeacherReport.STATUS_CHOICES):
            messages.error(request, 'Некорректный статус')
            return redirect('head_dashboard')

        updated = TeacherReport.objects.filter(id__in=report_ids).update(
            status=new_status,
            approved_by=request.user,
        )

        messages.success(request, f'Статус изменен для {updated} отчетов')
        return redirect('head_dashboard')

    reports, period_id, class_id, status, teacher_id = get_filtered_head_reports(request)

    context = {
        'reports': reports,
        'status_choices': TeacherReport.STATUS_CHOICES,
        'selected_period': period_id,
        'selected_class': class_id,
        'selected_status': status,
        'selected_teacher': teacher_id,
        **get_report_filter_context(include_teachers=True),
    }
    return render(request, 'reports/bulk_change_status.html', context)


@login_required
def class_reports(request, class_id):
    """Все отчеты по классу."""
    school_class = get_object_or_404(SchoolClass, id=class_id)
    reports = TeacherReport.objects.filter(
        school_class=school_class
    ).select_related(
        'teacher', 'period'
    ).order_by('-period__start_date')

    return render(request, 'reports/class_reports.html', {
        'school_class': school_class,
        'reports': reports,
    })


@login_required
def add_age_group_row(request):
    """AJAX обработчик для добавления строки возрастной группы."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    form_index = request.POST.get('form_index', 0)
    form = StudentAgeGroupForm(prefix=f'age-{form_index}')

    html = render_to_string('reports/partials/age_group_row.html', {
        'form': form,
        'index': form_index,
    }, request=request)

    return JsonResponse({
        'html': html,
        'index': int(form_index) + 1,
    })


@login_required
def get_movement_row(request):
    """AJAX обработчик для получения HTML строки движения учеников."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    movement_type = request.GET.get('type', 'out')
    index = request.GET.get('index', 0)
    prefix = request.GET.get('prefix', 'movement')

    form = StudentMovementForm(prefix=f'{prefix}-{index}')

    context = {
        'movement_form': form,
        'type': movement_type,
        'index': index,
        'prefix': prefix,
        'classes': SchoolClass.objects.filter(is_active=True),
    }

    html = render_to_string('reports/wizard/partials/movement_row.html', context, request=request)

    return JsonResponse({
        'html': html,
        'success': True,
    })


@login_required
def get_previous_report_data(request, period_id, class_id):
    """Получение данных предыдущего отчета."""
    if not request.user.is_teacher():
        return JsonResponse({'error': 'Access denied'}, status=403)

    teacher = get_teacher_or_none(request.user)
    if teacher is None:
        return JsonResponse({'error': 'Teacher not found'}, status=404)

    current_period = get_object_or_404(ReportPeriod, id=period_id)

    previous_report = TeacherReport.objects.filter(
        teacher=teacher,
        school_class_id=class_id,
        period__start_date__lt=current_period.start_date,
        status='approved',
    ).order_by('-period__start_date').first()

    if not previous_report:
        return JsonResponse({'data': None})

    return JsonResponse({
        'data': {
            'total_students_end': previous_report.total_students_end,
            'has_movement': previous_report.has_movement,
        }
    })


@login_required
def summary_report(request):
    """Сводный отчет для завуча."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period_id = request.GET.get('period')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')
    show_family = request.GET.get('show_family') == 'on'

    summary_data = get_summary_report_data(
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
        show_family=show_family,
    )

    context = {
        'selected_period': period_id,
        'selected_class': class_id,
        'selected_parallel': parallel,
        'show_family': show_family,
        **summary_data,
        **get_report_filter_context(),
    }
    return render(request, 'reports/summary_report.html', context)


@login_required
def export_summary_excel(request):
    """Экспорт сводного отчета в Excel с учетом текущих фильтров."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    from datetime import datetime

    period_id = request.GET.get('period')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')

    summary_data = get_summary_report_data(
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
        show_family=False,
    )

    reports = summary_data['reports']
    period = ReportPeriod.objects.filter(id=period_id).first() if period_id else None
    school_class = SchoolClass.objects.filter(id=class_id).first() if class_id else None

    wb, ws = create_workbook("Сводный отчет")

    filter_info = []
    if period:
        filter_info.append(f"Период: {period.name} {period.academic_year}")
    if school_class:
        filter_info.append(f"Класс: {school_class.name}")
    if parallel:
        filter_info.append(f"Параллель: {parallel} класс")

    start_row = write_filter_row(ws, filter_info, 'A1:M1')

    headers = [
        'Класс', 'Учитель', 'Период',
        'Всего учеников', 'Семейных', 'Очных',
        'Мальчики', 'Девочки',
        'Отличники', 'Ударники', 'Двоечники',
        'Качество %', 'Успеваемость %',
    ]
    write_headers(ws, start_row, headers)

    data_rows = []
    for report in reports:
        academic = getattr(report, 'academic_performance', None)
        family = getattr(report, 'family_education', None)

        total_students = report.total_students_end
        family_count = family.count if family and family.has_family_education else 0
        boys, girls = sum_gender_from_age_groups(report)

        excellent = academic.excellent_count if academic else 0
        good = academic.good_count if academic else 0
        poor = academic.poor_count if academic else 0

        quality, success, in_person = calculate_quality_and_success(
            total_students=total_students,
            family_students=family_count,
            excellent=excellent,
            good=good,
            poor=poor,
        )

        data_rows.append([
            report.school_class.name,
            report.teacher.full_name,
            f"{report.period.name} {report.period.academic_year}",
            total_students,
            family_count,
            in_person,
            boys,
            girls,
            excellent,
            good,
            poor,
            quality,
            success,
        ])

    next_row = write_data_rows(ws, start_row + 1, data_rows)

    write_total_row(ws, next_row, {
        1: "ИТОГО:",
        4: summary_data['total_all_students'],
        5: summary_data['total_family_students'],
        6: summary_data['total_in_person_students'],
        7: summary_data['total_boys'],
        8: summary_data['total_girls'],
        9: summary_data['stats']['total_excellent'] or 0,
        10: summary_data['stats']['total_good'] or 0,
        11: summary_data['stats']['total_poor'] or 0,
        12: summary_data['quality'],
        13: summary_data['success'],
    })

    set_column_widths(ws, [15, 30, 20, 12, 10, 10, 10, 10, 10, 10, 10, 12, 12])

    date_row = next_row + 2
    ws.cell(
        row=date_row,
        column=1,
        value=f"Отчет сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
    )
    from openpyxl.styles import Font
    ws.cell(row=date_row, column=1).font = Font(italic=True, size=10)

    filename = build_filename(
        'summary_report',
        period=period,
        school_class=school_class,
        parallel=parallel,
    )

    response = build_excel_response(filename)
    wb.save(response)
    return response


@login_required
def social_summary_report(request):
    """Сводный отчет по социальным категориям учеников."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period_id = request.GET.get('period')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')
    show_details = request.GET.get('show_details') == 'on'

    social_data = get_social_summary_report_data(
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
        show_details=show_details,
    )

    context = {
        'selected_period': period_id,
        'selected_class': class_id,
        'selected_parallel': parallel,
        **social_data,
        **get_report_filter_context(),
    }
    return render(request, 'reports/social_summary_report.html', context)


@login_required
def export_social_excel(request):
    """Экспорт социального сводного отчета в Excel."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period_id = request.GET.get('period')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')
    show_details = request.GET.get('show_details') == 'on'

    social_data = get_social_summary_report_data(
        period_id=period_id,
        class_id=class_id,
        parallel=parallel,
        show_details=show_details,
    )

    table_data = social_data['table_data']
    period = ReportPeriod.objects.filter(id=period_id).first() if period_id else None
    school_class = SchoolClass.objects.filter(id=class_id).first() if class_id else None

    wb, ws = create_workbook("Социальный отчет")

    filter_info = []
    if period:
        filter_info.append(f"Период: {period.name} {period.academic_year}")
    if school_class:
        filter_info.append(f"Класс: {school_class.name}")
    if parallel:
        filter_info.append(f"Параллель: {parallel} класс")

    start_row = write_filter_row(ws, filter_info, 'A1:J1')

    headers = [
        'Класс', 'Учитель', 'Период', 'Всего уч.',
        'Инвалиды', 'ОВЗ', 'Инв. с ОВЗ', 'На дому', 'Опека', 'Семейное',
    ]
    write_headers(ws, start_row, headers)

    data_rows = [
        [
            item['class'],
            item['teacher'],
            item['period'],
            item['total_students'],
            item['disabled'],
            item['special_needs'],
            item['disabled_special'],
            item['home_schooling'],
            item['foster_care'],
            item['family_education'],
        ]
        for item in table_data
    ]

    next_row = write_data_rows(ws, start_row + 1, data_rows)

    write_total_row(ws, next_row, {
        1: "ИТОГО:",
        4: social_data['total_all_students'],
        5: social_data['total_disabled'],
        6: social_data['total_special_needs'],
        7: social_data['total_disabled_special'],
        8: social_data['total_home_schooling'],
        9: social_data['total_foster_care'],
        10: social_data['total_family_education'],
    })

    set_column_widths(ws, [15, 30, 20, 12, 10, 10, 10, 10, 10, 10])

    filename = build_filename(
        'social_report',
        period=period,
        school_class=school_class,
        parallel=parallel,
    )

    response = build_excel_response(filename)
    wb.save(response)
    return response


@login_required
def dynamics_report(request):
    """Отчет по динамике показателей между периодами."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period_from_id = request.GET.get('period_from')
    period_to_id = request.GET.get('period_to')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')
    show_absolute = request.GET.get('show_absolute') == 'on'

    base_context = {
        'selected_period_from': period_from_id,
        'selected_period_to': period_to_id,
        'selected_class': class_id,
        'selected_parallel': parallel,
        'show_absolute': show_absolute,
        **get_report_filter_context(),
    }

    if not period_from_id or not period_to_id:
        messages.warning(request, 'Выберите начальный и конечный периоды для сравнения')
        return render(request, 'reports/dynamics_report.html', {
            **base_context,
            'has_data': False,
        })

    dynamics_data = get_dynamics_report_data(
        period_from_id=period_from_id,
        period_to_id=period_to_id,
        class_id=class_id,
        parallel=parallel,
    )

    return render(request, 'reports/dynamics_report.html', {
        **base_context,
        **dynamics_data,
    })


@login_required
def export_dynamics_excel(request):
    """Экспорт отчета по динамике в Excel."""
    if not request.user.is_head_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period_from_id = request.GET.get('period_from')
    period_to_id = request.GET.get('period_to')
    class_id = request.GET.get('class')
    parallel = request.GET.get('parallel')

    if not period_from_id or not period_to_id:
        messages.error(request, 'Не выбраны периоды для сравнения')
        return redirect('dynamics_report')

    dynamics_data = get_dynamics_report_data(
        period_from_id=period_from_id,
        period_to_id=period_to_id,
        class_id=class_id,
        parallel=parallel,
    )

    period_from = dynamics_data['period_from']
    period_to = dynamics_data['period_to']
    rows = dynamics_data['dynamics_data']
    totals = dynamics_data['totals']
    school_class = SchoolClass.objects.filter(id=class_id).first() if class_id else None

    wb, ws = create_workbook("Динамика показателей")

    filter_info = [
        f"Начальный период: {period_from.name} {period_from.academic_year}",
        f"Конечный период: {period_to.name} {period_to.academic_year}",
    ]
    if school_class:
        filter_info.append(f"Класс: {school_class.name}")
    if parallel:
        filter_info.append(f"Параллель: {parallel} класс")

    start_row = write_filter_row(ws, filter_info, 'A1:Q1')

    headers = [
        'Класс', 'Учитель',
        'Уч-ся нач.', 'Уч-ся кон.', 'Δ уч-ся',
        'Мальч. нач.', 'Мальч. кон.', 'Δ мальч.',
        'Дев. нач.', 'Дев. кон.', 'Δ дев.',
        'Качество нач. %', 'Качество кон. %', 'Δ кач.',
        'Успеваемость нач. %', 'Успеваемость кон. %', 'Δ усп.',
    ]
    write_headers(ws, start_row, headers)

    data_rows = [
        [
            item['class'],
            item['teacher'],
            item['students_from'],
            item['students_to'],
            item['students_diff'],
            item['boys_from'],
            item['boys_to'],
            item['boys_diff'],
            item['girls_from'],
            item['girls_to'],
            item['girls_diff'],
            item['quality_from'],
            item['quality_to'],
            item['quality_diff'],
            item['success_from'],
            item['success_to'],
            item['success_diff'],
        ]
        for item in rows
    ]

    next_row = write_data_rows(ws, start_row + 1, data_rows)

    write_total_row(ws, next_row, {
        1: "ИТОГО:",
        3: totals['students_from'],
        4: totals['students_to'],
        5: totals['students_diff'],
        6: totals['boys_from'],
        7: totals['boys_to'],
        8: totals['boys_diff'],
        9: totals['girls_from'],
        10: totals['girls_to'],
        11: totals['girls_diff'],
        12: totals['quality_from'],
        13: totals['quality_to'],
        14: totals['quality_diff'],
        15: totals['success_from'],
        16: totals['success_to'],
        17: totals['success_diff'],
    })

    set_column_widths(
        ws,
        [15, 30, 12, 12, 10, 12, 12, 10, 12, 12, 10, 12, 12, 10, 12, 12, 10],
    )

    filename = build_filename(
        f'dynamics_{period_from.name}_{period_to.name}',
        school_class=school_class,
        parallel=parallel,
    )

    response = build_excel_response(filename)
    wb.save(response)
    return response


@staff_member_required
def teacher_list(request):
    """Список учителей."""
    teachers = Teacher.objects.select_related('user').prefetch_related(
        'homeroom_classes'
    ).order_by('full_name')

    total_teachers = teachers.count()
    with_class = teachers.filter(homeroom_classes__isnull=False).distinct().count()
    without_class = total_teachers - with_class

    return render(request, 'reports/teacher_list.html', {
        'teachers': teachers,
        'total_teachers': total_teachers,
        'with_class': with_class,
        'without_class': without_class,
    })


@staff_member_required
def register_teacher(request):
    """Регистрация нового учителя."""
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            teacher = form.save()
            messages.success(request, f'Учитель {teacher.full_name} успешно зарегистрирован')
            return redirect('teacher_list')
    else:
        form = TeacherRegistrationForm()

    return render(request, 'reports/register_teacher.html', {'form': form})


@staff_member_required
def edit_teacher(request, teacher_id):
    """Редактирование учителя."""
    teacher = get_object_or_404(Teacher, id=teacher_id)

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        if full_name:
            teacher.full_name = full_name
            teacher.save(update_fields=['full_name'])

        role = request.POST.get('role')
        if role and role in dict(User.ROLE_CHOICES):
            teacher.user.role = role
            teacher.user.save(update_fields=['role'])

        messages.success(request, 'Данные учителя обновлены')
        return redirect('teacher_list')

    return render(request, 'reports/edit_teacher.html', {
        'teacher': teacher,
        'role_choices': User.ROLE_CHOICES,
    })


@staff_member_required
def reset_teacher_password(request, teacher_id):
    """Сброс пароля учителя."""
    teacher = get_object_or_404(Teacher, id=teacher_id)

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        if new_password:
            teacher.user.set_password(new_password)
            teacher.user.save()
            messages.success(request, f'Пароль для {teacher.full_name} изменен')
            return redirect('teacher_list')

    return render(request, 'reports/reset_password.html', {'teacher': teacher})


@staff_member_required
def assign_classes(request, teacher_id):
    """Назначение классов учителю."""
    teacher = get_object_or_404(Teacher, id=teacher_id)

    if request.method == 'POST':
        class_ids = request.POST.getlist('classes')
        teacher.homeroom_classes.set(class_ids)
        messages.success(request, f'Классы назначены учителю {teacher.full_name}')
        return redirect('teacher_list')

    classes = SchoolClass.objects.filter(is_active=True).order_by('parallel', 'name')
    current_classes = list(teacher.homeroom_classes.values_list('id', flat=True))

    return render(request, 'reports/assign_classes.html', {
        'teacher': teacher,
        'classes': classes,
        'current_classes': current_classes,
    })