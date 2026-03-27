# reports/decorators.py

from functools import wraps
from typing import Optional, Callable, Any, List, Union
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login


# ============================================================
# Базовые декораторы авторизации
# ============================================================

def login_required_message(
        view_func: Optional[Callable] = None,
        message: str = 'Необходимо войти в систему',
        login_url: Optional[str] = None,
        redirect_field_name: str = REDIRECT_FIELD_NAME
) -> Callable:
    """
    Декоратор, требующий авторизации с кастомным сообщением.

    Args:
        message: Сообщение, которое будет показано пользователю
        login_url: URL страницы входа (по умолчанию используется LOGIN_URL из settings)
        redirect_field_name: Имя GET-параметра для URL возврата
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                messages.warning(request, message)

                # Сохраняем текущий URL для редиректа после входа
                if login_url:
                    path = login_url
                else:
                    from django.conf import settings
                    path = settings.LOGIN_URL

                return redirect_to_login(request.get_full_path(), path, redirect_field_name)

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def teacher_required(
        view_func: Optional[Callable] = None,
        redirect_url: str = 'reports:report_list',
        message: str = 'Доступ только для учителей'
) -> Callable:
    """
    Декоратор, требующий принадлежности пользователя к группе 'teachers'.
    Суперпользователь также имеет доступ.

    Args:
        redirect_url: URL для перенаправления при отсутствии прав
        message: Сообщение об ошибке
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            # Проверка: суперпользователь или учитель
            is_teacher = request.user.is_superuser or request.user.groups.filter(name='teachers').exists()

            if not is_teacher:
                messages.error(request, message)
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def admin_required(
        view_func: Optional[Callable] = None,
        redirect_url: str = 'reports:report_list',
        message: str = 'Доступ только для администраторов'
) -> Callable:
    """
    Декоратор, требующий прав суперпользователя.

    Args:
        redirect_url: URL для перенаправления при отсутствии прав
        message: Сообщение об ошибке
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
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


# ============================================================
# Декораторы для работы с объектами
# ============================================================

def report_owner_required(view_func: Optional[Callable] = None) -> Callable:
    """
    Декоратор для проверки, что текущий пользователь является владельцем отчета.
    Используется для views, где в kwargs есть 'pk' - id отчета.
    Суперпользователь имеет доступ ко всем отчетам.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            from .models import Report  # Импорт внутри функции для избежания циклического импорта

            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            # Суперпользователь имеет доступ ко всем отчетам
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Получаем id отчета из kwargs (поддерживаем разные варианты)
            report_id = kwargs.get('pk') or kwargs.get('report_id') or kwargs.get('id')

            if not report_id:
                messages.error(request, 'ID отчета не указан')
                return redirect('reports:report_list')

            try:
                report = Report.objects.select_related('teacher').get(pk=report_id)
                if report.teacher != request.user:
                    messages.error(request, 'У вас нет доступа к этому отчету')
                    return redirect('reports:report_list')
            except Report.DoesNotExist:
                messages.error(request, 'Отчет не найден')
                return redirect('reports:report_list')

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def class_teacher_required(
        view_func: Optional[Callable] = None,
        redirect_url: str = 'reports:report_list'
) -> Callable:
    """
    Декоратор для проверки, что пользователь является классным руководителем класса.
    Для views, где в kwargs есть 'class_id', 'class_pk' или 'pk'.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            from .models import ClassGroup

            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Получаем id класса из kwargs (поддерживаем разные варианты)
            class_id = kwargs.get('class_id') or kwargs.get('class_pk') or kwargs.get('pk')

            if not class_id:
                # Если id не передан, возможно view не требует проверки конкретного класса
                return view_func(request, *args, **kwargs)

            try:
                class_group = ClassGroup.objects.select_related('class_teacher').get(pk=class_id)
                if class_group.class_teacher != request.user:
                    messages.error(
                        request,
                        f'Вы не являетесь классным руководителем класса {class_group.name}'
                    )
                    return redirect(redirect_url)
            except ClassGroup.DoesNotExist:
                messages.error(request, 'Класс не найден')
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def object_owner_required(model, owner_field='user', pk_name='pk'):
    """
    Универсальный декоратор для проверки владельца объекта.

    Args:
        model: Модель Django
        owner_field: Имя поля, содержащего владельца (по умолчанию 'user')
        pk_name: Имя параметра в kwargs с id объекта (по умолчанию 'pk')
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            obj_id = kwargs.get(pk_name)
            if not obj_id:
                messages.error(request, f'ID объекта не указан')
                return redirect('reports:report_list')

            try:
                obj = model.objects.select_related(owner_field).get(pk=obj_id)
                owner = getattr(obj, owner_field)
                if owner != request.user:
                    messages.error(request, 'У вас нет доступа к этому объекту')
                    return redirect('reports:report_list')
            except model.DoesNotExist:
                messages.error(request, 'Объект не найден')
                return redirect('reports:report_list')

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# Декораторы для проверки статусов и прав
# ============================================================

def status_allowed(allowed_statuses: List[str]):
    """
    Декоратор для проверки, что отчет имеет допустимый статус.
    Для views, где в kwargs есть 'pk' - id отчета.

    Args:
        allowed_statuses: список допустимых статусов (например, ['draft', 'submitted'])
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            from .models import Report

            report_id = kwargs.get('pk') or kwargs.get('report_id')
            if report_id:
                try:
                    report = Report.objects.get(pk=report_id)
                    if report.status not in allowed_statuses:
                        messages.error(
                            request,
                            f'Невозможно выполнить действие: отчет имеет статус "{report.get_status_display()}". '
                            f'Допустимые статусы: {", ".join(dict(Report.STATUS_CHOICES)[s] for s in allowed_statuses)}'
                        )
                        return redirect('reports:report_detail', pk=report_id)
                except Report.DoesNotExist:
                    messages.error(request, 'Отчет не найден')
                    return redirect('reports:report_list')

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def multiple_permissions_required(
        permissions: List[str],
        require_all: bool = True,
        redirect_url: str = 'reports:report_list',
        message: Optional[str] = None
) -> Callable:
    """
    Декоратор для проверки нескольких прав.

    Args:
        permissions: список прав для проверки (например, ['reports.add_report', 'reports.change_report'])
        require_all: если True, нужны все права; если False, достаточно любого из них
        redirect_url: URL для перенаправления при отсутствии прав
        message: Сообщение об ошибке (будет сгенерировано автоматически, если не указано)
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                messages.warning(request, 'Необходимо войти в систему')
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_permissions = set(request.user.get_all_permissions())
            required_permissions = set(permissions)

            if require_all:
                has_permission = required_permissions.issubset(user_permissions)
                default_message = f'Для выполнения этого действия необходимы все права: {", ".join(permissions)}'
            else:
                has_permission = bool(required_permissions.intersection(user_permissions))
                default_message = f'Для выполнения этого действия необходимо хотя бы одно из прав: {", ".join(permissions)}'

            if not has_permission:
                error_message = message or default_message
                messages.error(request, error_message)
                return redirect(redirect_url)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# Декораторы для AJAX и API
# ============================================================

def ajax_required(view_func: Optional[Callable] = None) -> Callable:
    """
    Декоратор для views, которые должны обрабатывать только AJAX запросы.
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
                if request.method == 'GET':
                    return redirect('reports:report_list')
                return HttpResponseForbidden('Только AJAX запросы разрешены')
            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def require_http_methods(allowed_methods: List[str]):
    """
    Декоратор для ограничения HTTP методов.

    Args:
        allowed_methods: список разрешенных методов (например, ['GET', 'POST'])
    """

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if request.method not in allowed_methods:
                return HttpResponse(status=405, headers={'Allow': ', '.join(allowed_methods)})
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# Декораторы для кэширования и логирования
# ============================================================

def cache_page_for_anonymous(timeout: int = 300):
    """
    Кэширует страницу только для анонимных пользователей.
    Авторизованные пользователи получают актуальную версию.
    """
    from django.views.decorators.cache import cache_page
    from django.utils.decorators import method_decorator

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            return cache_page(timeout)(view_func)(request, *args, **kwargs)

        return wrapper

    return decorator


def log_user_action(view_func: Optional[Callable] = None) -> Callable:
    """
    Декоратор для логирования действий пользователя.
    """
    import logging
    logger = logging.getLogger(__name__)

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            response = view_func(request, *args, **kwargs)

            if request.user.is_authenticated:
                logger.info(
                    f"User {request.user.username} accessed {request.path} "
                    f"with method {request.method}"
                )

            return response

        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


# ============================================================
# Комбинированные декораторы
# ============================================================

def teacher_and_owner_required(view_func: Callable) -> Callable:
    """
    Комбинированный декоратор: пользователь должен быть учителем и владельцем отчета.
    """

    @teacher_required
    @report_owner_required
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return view_func(request, *args, **kwargs)

    return wrapper


def admin_or_owner_required(view_func: Callable) -> Callable:
    """
    Комбинированный декоратор: пользователь должен быть администратором или владельцем отчета.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        return report_owner_required(view_func)(request, *args, **kwargs)

    return wrapper