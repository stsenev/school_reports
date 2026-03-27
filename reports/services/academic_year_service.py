from ..models import ReportPeriod


DEFAULT_ACADEMIC_YEAR = '2025/2026'


def get_available_academic_years():
    return list(
        ReportPeriod.objects.order_by('-academic_year')
        .values_list('academic_year', flat=True)
        .distinct()
    )


def get_default_academic_year():
    years = get_available_academic_years()
    if years:
        return years[0]
    return DEFAULT_ACADEMIC_YEAR


def get_selected_academic_year(request, fallback=None):
    academic_year = (
        request.GET.get('academic_year')
        or request.POST.get('academic_year')
        or request.session.get('selected_academic_year')
    )

    if academic_year:
        return academic_year

    if fallback:
        return fallback

    return get_default_academic_year()


def set_selected_academic_year(request, academic_year):
    request.session['selected_academic_year'] = academic_year


def get_academic_years_with_selected(request, selected_year=None):
    selected_year = selected_year or get_selected_academic_year(request)
    years = get_available_academic_years()

    if selected_year and selected_year not in years:
        years.insert(0, selected_year)

    return years, selected_year