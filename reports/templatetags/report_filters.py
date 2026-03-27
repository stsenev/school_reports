# reports/templatetags/report_filters.py
from django import template
from django.conf import settings

register = template.Library()

@register.filter
def filter_by_period(reports, period):
    if hasattr(reports, 'filter'):
        return reports.filter(period=period).first()
    elif isinstance(reports, dict):
        return reports.get(period.id)
    else:
        for report in reports:
            if report.period_id == period.id:
                return report
    return None

@register.filter
def get_item(dictionary, key):
    """Получение значения из словаря по ключу"""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def subject_name(subject_code):
    subjects_dict = dict(settings.SCHOOL_SUBJECTS)
    return subjects_dict.get(subject_code, subject_code)

@register.filter
def verbose_status(status):
    status_dict = {'draft': 'Черновик', 'submitted': 'Отправлен', 'approved': 'Утвержден', 'rejected': 'Отклонен'}
    return status_dict.get(status, status)

@register.filter
def status_color(status):
    color_dict = {'draft': 'warning', 'submitted': 'info', 'approved': 'success', 'rejected': 'danger'}
    return color_dict.get(status, 'secondary')

@register.filter
def add_class(value, css_class):
    return value.as_widget(attrs={'class': css_class})

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def subtract(value, arg):
    """Вычитание в шаблонах с возвратом целого числа"""
    try:
        result = float(value) - float(arg)
        # Если результат целое число, возвращаем как int
        if result.is_integer():
            return int(result)
        return result
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Безопасное деление с проверкой на ноль"""
    try:
        value = float(value)
        arg = float(arg)
        if arg == 0:
            return 0
        return (value / arg) * 100
    except (ValueError, TypeError):
        return 0

@register.filter
def floatformat_int(value, decimals=0):
    """Форматирование числа с указанным количеством знаков после запятой"""
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return "0"

@register.filter
def sum_boys(age_groups):
    """Суммирует количество мальчиков из возрастных групп"""
    total = 0
    for group in age_groups:
        total += group.boys_count
    return total

@register.filter
def sum_girls(age_groups):
    """Суммирует количество девочек из возрастных групп"""
    total = 0
    for group in age_groups:
        total += group.girls_count
    return total