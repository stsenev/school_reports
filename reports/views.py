# reports/views.py

from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count, QuerySet
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import HttpRequest, HttpResponse
from django.urls import reverse

from .models import Report, Subject, ClassGroup
from .forms import ReportForm, ReportFilterForm
from .filters import ReportFilter
from .utils import get_teacher_stats
from .decorators import (
    login_required_message,
    teacher_required,
    admin_required,
    report_owner_required,
    status_allowed,
)


# ============================================================
# Вспомогательные функции
# ============================================================

def _get_filtered_reports(request: HttpRequest) -> QuerySet:
    """
    Получает отфильтрованный queryset отчетов с учетом всех параметров.
    """
    reports = Report.objects.select_related(
        'teacher', 'subject', 'class_group'
    ).all()

    # Применение фильтров через django-filter
    report_filter = ReportFilter(request.GET, queryset=reports)
    reports = report_filter.qs

    # Поиск по тексту
    search_query = request.GET.get('search', '').strip()
    if search_query:
        reports = reports.filter(
            Q(topic__icontains=search_query) |
            Q(teacher__username__icontains=search_query) |
            Q(teacher__first_name__icontains=search_query) |
            Q(teacher__last_name__icontains=search_query) |
            Q(subject__name__icontains=search_query) |
            Q(class_group__name__icontains=search_query) |
            Q(homework__icontains=search_query)
        )

    return reports


def _paginate_reports(request: HttpRequest, reports: QuerySet, per_page: int = 20):
    """
    Пагинирует список отчетов и возвращает объект пагинации.
    """
    paginator = Paginator(reports, per_page)
    page_number = request.GET.get('page')
    return paginator.get_page(page_number)


# ============================================================
# Публичные views
# ============================================================

@login_required_message(message='Пожалуйста, войдите в систему для просмотра отчетов')
def report_list(request: HttpRequest) -> HttpResponse:
    """
    Список отчетов с фильтрацией, поиском и пагинацией.
    """
    reports = _get_filtered_reports(request)
    page_obj = _paginate_reports(request, reports)

    # Форма фильтров для отображения
    filter_form = ReportFilterForm(request.GET)
    search_query = request.GET.get('search', '').strip()

    # Статистика для учителей (только если пользователь учитель или админ)
    stats = None
    if request.user.is_authenticated and (
            request.user.is_superuser or
            request.user.groups.filter(name='teachers').exists()
    ):
        stats = get_teacher_stats(request.user)

    context = {
        'reports': page_obj,
        'filter_form': filter_form,
        'search_query': search_query,
        'stats': stats,
        'title': 'Список отчетов',
    }

    return render(request, 'reports/report_list.html', context)


@teacher_required(message='Создавать отчеты могут только учителя')
def report_create(request: HttpRequest) -> HttpResponse:
    """
    Создание нового отчета.
    """
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.teacher = request.user
            report.save()
            messages.success(
                request,
                f'Отчет за {report.date.strftime("%d.%m.%Y")} успешно создан'
            )
            return redirect('reports:report_list')
    else:
        # Предзаполнение даты текущим днем
        initial = {'date': timezone.now().date()}
        form = ReportForm(initial=initial)

    context = {
        'form': form,
        'title': 'Создание отчета',
        'button_text': 'Создать',
    }

    return render(request, 'reports/report_form.html', context)


@report_owner_required
def report_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Детальный просмотр отчета.
    """
    report = get_object_or_404(
        Report.objects.select_related('teacher', 'subject', 'class_group'),
        pk=pk
    )

    # Получение следующего и предыдущего отчета для навигации
    previous_report = None
    next_report = None

    if request.user.is_superuser or report.teacher == request.user:
        user_reports = Report.objects.filter(teacher=report.teacher).values_list('id', flat=True)
        report_ids = list(user_reports.order_by('-date', '-created_at'))

        try:
            current_index = report_ids.index(report.id)
            if current_index > 0:
                previous_report = Report.objects.get(id=report_ids[current_index - 1])
            if current_index < len(report_ids) - 1:
                next_report = Report.objects.get(id=report_ids[current_index + 1])
        except (ValueError, Report.DoesNotExist):
            pass

    context = {
        'report': report,
        'previous_report': previous_report,
        'next_report': next_report,
        'title': f'Отчет #{report.id}',
    }

    return render(request, 'reports/report_detail.html', context)


@teacher_required
@report_owner_required
@status_allowed(['draft', 'submitted'])
def report_update(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Редактирование отчета.
    Доступно только для отчетов в статусе 'draft' или 'submitted'.
    """
    report = get_object_or_404(Report, pk=pk)

    if request.method == 'POST':
        form = ReportForm(request.POST, instance=report)
        if form.is_valid():
            updated_report = form.save()
            messages.success(
                request,
                f'Отчет за {updated_report.date.strftime("%d.%m.%Y")} успешно обновлен'
            )
            return redirect('reports:report_detail', pk=report.pk)
    else:
        form = ReportForm(instance=report)

    context = {
        'form': form,
        'report': report,
        'title': f'Редактирование отчета #{report.id}',
        'button_text': 'Сохранить',
    }

    return render(request, 'reports/report_form.html', context)


@teacher_required
@report_owner_required
def report_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Удаление отчета.
    """
    report = get_object_or_404(Report, pk=pk)

    if request.method == 'POST':
        report_date = report.date.strftime('%d.%m.%Y')
        report.delete()
        messages.success(request, f'Отчет за {report_date} успешно удален')
        return redirect('reports:report_list')

    context = {
        'report': report,
        'title': f'Удаление отчета #{report.id}',
    }

    return render(request, 'reports/report_confirm_delete.html', context)


@admin_required(message='Дашборд доступен только администраторам')
def dashboard(request: HttpRequest) -> HttpResponse:
    """
    Административная панель со статистикой.
    """
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Основная статистика
    total_reports = Report.objects.count()
    pending_reports = Report.objects.filter(status='submitted').count()
    weekly_reports = Report.objects.filter(date__gte=week_ago).count()
    monthly_reports = Report.objects.filter(date__gte=month_ago).count()

    # Статистика по статусам
    status_stats = list(Report.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status'))

    # Добавляем названия статусов для читаемости
    status_display = dict(Report.STATUS_CHOICES)
    for stat in status_stats:
        stat['display'] = status_display.get(stat['status'], stat['status'])

    # Популярные предметы (топ-10)
    popular_subjects = Subject.objects.annotate(
        report_count=Count('report')
    ).filter(report_count__gt=0).order_by('-report_count')[:10]

    # Активность по классам (топ-10)
    class_activity = ClassGroup.objects.annotate(
        report_count=Count('report')
    ).filter(report_count__gt=0).order_by('-report_count')[:10]

    # Активность учителей (топ-10)
    teacher_activity = Report.objects.values(
        'teacher__id',
        'teacher__username',
        'teacher__first_name',
        'teacher__last_name'
    ).annotate(
        report_count=Count('id')
    ).order_by('-report_count')[:10]

    # Динамика по месяцам (последние 12 месяцев)
    monthly_trend = Report.objects.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('-month')[:12]

    # Отчеты, требующие проверки
    pending_reports_list = Report.objects.filter(
        status='submitted'
    ).select_related('teacher', 'subject', 'class_group')[:10]

    context = {
        'total_reports': total_reports,
        'pending_reports': pending_reports,
        'weekly_reports': weekly_reports,
        'monthly_reports': monthly_reports,
        'status_stats': status_stats,
        'popular_subjects': popular_subjects,
        'class_activity': class_activity,
        'teacher_activity': teacher_activity,
        'monthly_trend': monthly_trend,
        'pending_reports_list': pending_reports_list,
        'title': 'Панель управления',
    }

    return render(request, 'reports/dashboard.html', context)


# ============================================================
# API-подобные views (для AJAX)
# ============================================================

@teacher_required
def report_change_status(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Быстрое изменение статуса отчета (AJAX).
    """
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return redirect('reports:report_detail', pk=pk)

    import json
    from django.http import JsonResponse

    report = get_object_or_404(Report, pk=pk)

    # Проверка прав: только автор или админ могут менять статус
    if not (request.user.is_superuser or report.teacher == request.user):
        return JsonResponse({'error': 'Нет прав для изменения статуса'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_status = data.get('status')

            if new_status in dict(Report.STATUS_CHOICES):
                report.status = new_status
                report.save()

                return JsonResponse({
                    'success': True,
                    'status': report.status,
                    'status_display': report.get_status_display(),
                    'message': f'Статус изменен на "{report.get_status_display()}"'
                })
            else:
                return JsonResponse({'error': 'Неверный статус'}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Неверный формат данных'}, status=400)

    return JsonResponse({'error': 'Метод не разрешен'}, status=405)


@teacher_required
def my_reports(request: HttpRequest) -> HttpResponse:
    """
    Просмотр только своих отчетов (для учителей).
    """
    reports = Report.objects.filter(
        teacher=request.user
    ).select_related('subject', 'class_group').all()

    # Применение фильтров
    report_filter = ReportFilter(request.GET, queryset=reports)
    reports = report_filter.qs

    # Поиск
    search_query = request.GET.get('search', '').strip()
    if search_query:
        reports = reports.filter(
            Q(topic__icontains=search_query) |
            Q(subject__name__icontains=search_query) |
            Q(class_group__name__icontains=search_query)
        )

    page_obj = _paginate_reports(request, reports)
    filter_form = ReportFilterForm(request.GET)
    stats = get_teacher_stats(request.user)

    context = {
        'reports': page_obj,
        'filter_form': filter_form,
        'search_query': search_query,
        'stats': stats,
        'title': 'Мои отчеты',
        'is_my_reports': True,
    }

    return render(request, 'reports/report_list.html', context)


@admin_required
def reports_export(request: HttpRequest) -> HttpResponse:
    """
    Экспорт отчетов в CSV.
    """
    import csv
    from django.http import HttpResponse

    reports = _get_filtered_reports(request)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="reports_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Дата', 'Учитель', 'Предмет', 'Класс',
        'Тема', 'Домашнее задание', 'Примечания', 'Статус', 'Создан'
    ])

    for report in reports:
        writer.writerow([
            report.id,
            report.date.strftime('%d.%m.%Y'),
            report.teacher.get_full_name() or report.teacher.username,
            report.subject.name,
            report.class_group.name,
            report.topic,
            report.homework,
            report.notes,
            report.get_status_display(),
            report.created_at.strftime('%d.%m.%Y %H:%M'),
        ])

    messages.success(request, f'Экспортировано {reports.count()} отчетов')
    return response


# ============================================================
# Обработчики ошибок
# ============================================================

def handler_404(request: HttpRequest, exception) -> HttpResponse:
    """Кастомная страница 404"""
    return render(request, 'errors/404.html', status=404)


def handler_500(request: HttpRequest) -> HttpResponse:
    """Кастомная страница 500"""
    return render(request, 'errors/500.html', status=500)


def handler_403(request: HttpRequest, exception) -> HttpResponse:
    """Кастомная страница 403"""
    return render(request, 'errors/403.html', status=403)