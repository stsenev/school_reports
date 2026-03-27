# reports/utils.py
# Этот файл теперь будет реэкспортировать функции из period_utils.py
from .period_utils import check_period_availability, get_previous_approved_report

__all__ = ['check_period_availability', 'get_previous_approved_report']