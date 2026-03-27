from .services.academic_year_service import (
    get_available_academic_years,
    get_selected_academic_year,
)


def academic_year_context(request):
    current_year = get_selected_academic_year(request)
    academic_years = get_available_academic_years()

    if current_year and current_year not in academic_years:
        academic_years.insert(0, current_year)

    return {
        'current_academic_year': current_year,
        'academic_years': academic_years,
    }