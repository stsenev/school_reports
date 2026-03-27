# reports/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.http import HttpResponseForbidden


def login_required_message(view_func=None, message='Необходимо войти в систему'):
    """
    Декоратор, требующий авторизации с кастомным сообщением.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, message)
                return redirect('login')
            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def teacher_required(view_func=None, redirect_url='report_list', message='Доступ только для учителей'):
    """
    Декоратор, требующий принадлежности пользователя к группе 'teachers'.
    Если пользователь не учитель, перенаправляет на указанный URL.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            # Проверка: суперпользователь или учитель
            if not (request.user.is_superuser or
                    request.user.groups.filter(name='teachers').exists()):
                messages.error(request, message)
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def admin_required(view_func=None, redirect_url='report_list', message='Доступ только для администраторов'):
    """
    Декоратор, требующий прав суперпользователя.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            if not request.user.is_superuser:
                messages.error(request, message)
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def report_owner_required(view_func):
    """
    Декоратор для проверки, что текущий пользователь является владельцем отчета.
    Используется для views, где в kwargs есть 'pk' - id отчета.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .models import Report  # Импорт внутри функции, чтобы избежать циклического импорта

        if not request.user.is_authenticated:
            messages.warning(request, 'Необходимо войти в систему')
            return redirect('login')

        # Суперпользователь имеет доступ ко всем отчетам
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Получаем id отчета из kwargs
        report_id = kwargs.get('pk')
        if not report_id:
            # Если pk нет, возможно в kwargs есть report_id
            report_id = kwargs.get('report_id')

        if report_id:
            try:
                report = Report.objects.get(pk=report_id)
                if report.teacher != request.user:
                    messages.error(request, 'У вас нет доступа к этому отчету')
                    return redirect('report_list')
            except Report.DoesNotExist:
                messages.error(request, 'Отчет не найден')
                return redirect('report_list')

        return view_func(request, *args, **kwargs)

    return wrapper


def class_teacher_required(view_func):
    """
    Декоратор для проверки, что пользователь является классным руководителем класса.
    Для views, где в kwargs есть 'class_id' или 'class_pk'.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .models import ClassGroup

        if not request.user.is_authenticated:
            messages.warning(request, 'Необходимо войти в систему')
            return redirect('login')

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        class_id = kwargs.get('class_id') or kwargs.get('class_pk') or kwargs.get('pk')

        if class_id:
            try:
                class_group = ClassGroup.objects.get(pk=class_id)
                if class_group.class_teacher != request.user:
                    messages.error(request, f'Вы не являетесь классным руководителем класса {class_group.name}')
                    return redirect('report_list')
            except ClassGroup.DoesNotExist:
                messages.error(request, 'Класс не найден')
                return redirect('report_list')

        return view_func(request, *args, **kwargs)

    return wrapper


def multiple_permissions_required(permissions, require_all=True):
    """
    Декоратор для проверки нескольких прав.

    Args:
        permissions: список прав для проверки (например, ['reports.add_report', 'reports.change_report'])
        require_all: если True, нужны все права; если False, достаточно любого из них
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_permissions = set(request.user.get_all_permissions())
            required_permissions = set(permissions)

            if require_all:
                has_permission = required_permissions.issubset(user_permissions)
                message = 'У вас недостаточно прав для выполнения этого действия'
            else:
                has_permission = bool(required_permissions.intersection(user_permissions))
                message = 'У вас нет необходимых прав для выполнения этого действия'

            if not has_permission:
                messages.error(request, message)
                return redirect('report_list')

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def status_allowed(allowed_statuses):
    """
    Декоратор для проверки, что отчет имеет допустимый статус.
    Для views, где в kwargs есть 'pk' - id отчета.

    Args:
        allowed_statuses: список допустимых статусов (например, ['draft', 'submitted'])
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from .models import Report

            report_id = kwargs.get('pk')
            if report_id:
                try:
                    report = Report.objects.get(pk=report_id)
                    if report.status not in allowed_statuses:
                        messages.error(
                            request,
                            f'Невозможно выполнить действие: отчет имеет статус "{report.get_status_display()}"'
                        )
                        return redirect('report_detail', pk=report_id)
                except Report.DoesNotExist:
                    messages.error(request, 'Отчет не найден')
                    return redirect('report_list')

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def ajax_required(view_func):
    """
    Декоратор для views, которые должны обрабатывать только AJAX запросы.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return HttpResponseForbidden('Только AJAX запросы разрешены')
        return view_func(request, *args, **kwargs)

    return wrapper