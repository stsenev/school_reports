from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import TeacherRegistrationForm
from .models import ReportPeriod, SchoolClass, Teacher
from .services.academic_year_service import (
    get_academic_years_with_selected,
    get_selected_academic_year,
    set_selected_academic_year,
)
from .services.period_service import (
    ensure_report_periods_for_year,
    get_periods_for_year,
)
from .services.teacher_assignment_service import (
    get_teacher_assignment_ids_for_year,
    get_teacher_classes_for_year,
    get_teacher_rows_for_year,
    replace_teacher_assignments_for_year,
    sync_legacy_homeroom_classes,
)
from .services.report_access_service import (
    can_create_report_for_period,
    get_available_periods_for_class,
)


def _get_current_teacher(request):
    if not request.user.is_authenticated:
        return None
    return Teacher.objects.filter(user=request.user, is_active=True).first()


def _get_teacher_dashboard_classes(request, academic_year):
    teacher = _get_current_teacher(request)
    if not teacher:
        return SchoolClass.objects.none(), None
    return get_teacher_classes_for_year(teacher, academic_year), teacher


@login_required
def dashboard(request):
    academic_year = get_selected_academic_year(request)
    set_selected_academic_year(request, academic_year)

    periods = get_periods_for_year(academic_year)
    classes, teacher = _get_teacher_dashboard_classes(request, academic_year)

    if request.user.role in ['head_teacher', 'both'] or request.user.is_staff:
        return redirect('head_dashboard')

    class_period_map = []
    for school_class in classes:
        class_period_map.append({
            'school_class': school_class,
            'period_rows': get_available_periods_for_class(periods, school_class),
        })

    return render(request, 'reports/dashboard.html', {
        'periods': periods,
        'classes': classes,
        'teacher': teacher,
        'academic_year': academic_year,
        'class_period_map': class_period_map,
    })


@login_required
def head_dashboard(request):
    academic_year = get_selected_academic_year(request)
    set_selected_academic_year(request, academic_year)

    ensure_report_periods_for_year(academic_year)
    periods = get_periods_for_year(academic_year)

    teachers_count = Teacher.objects.filter(is_active=True).count()
    classes_count = SchoolClass.objects.filter(is_active=True).count()

    return render(request, 'reports/head_dashboard.html', {
        'periods': periods,
        'academic_year': academic_year,
        'teachers_count': teachers_count,
        'classes_count': classes_count,
    })


@login_required
def switch_role(request):
    """
    Простой переход между интерфейсами.
    """
    if request.user.role == 'both':
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)

        referer = request.META.get('HTTP_REFERER', '')
        if '/head/' in referer:
            return redirect('dashboard')
        return redirect('head_dashboard')

    if request.user.role == 'head_teacher' or request.user.is_staff:
        return redirect('head_dashboard')

    return redirect('dashboard')


@login_required
def set_academic_year(request, academic_year):
    set_selected_academic_year(request, academic_year)

    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)

    if request.user.role in ['head_teacher', 'both'] or request.user.is_staff:
        return redirect('head_dashboard')
    return redirect('dashboard')


@login_required
def select_class_for_report(request, period_id):
    period = get_object_or_404(ReportPeriod, id=period_id)
    academic_year = period.academic_year
    set_selected_academic_year(request, academic_year)

    if request.user.role in ['head_teacher', 'both'] or request.user.is_staff:
        candidate_classes = SchoolClass.objects.filter(is_active=True).order_by('parallel', 'name')
    else:
        teacher = _get_current_teacher(request)
        if not teacher:
            messages.error(request, 'Профиль учителя не найден.')
            return redirect('dashboard')
        candidate_classes = get_teacher_classes_for_year(teacher, academic_year)

    class_rows = []
    for school_class in candidate_classes:
        is_allowed, reason = can_create_report_for_period(
            school_class=school_class,
            period=period
        )
        class_rows.append({
            'school_class': school_class,
            'is_available': is_allowed,
            'reason': reason,
        })

    return render(request, 'reports/select_class.html', {
        'period': period,
        'class_rows': class_rows,
        'academic_year': academic_year,
    })


@staff_member_required
def teacher_list(request):
    academic_year = get_selected_academic_year(request)
    set_selected_academic_year(request, academic_year)

    academic_years, selected_year = get_academic_years_with_selected(request, academic_year)
    teacher_data = get_teacher_rows_for_year(selected_year)

    return render(request, 'reports/teacher_list.html', {
        'academic_year': selected_year,
        'academic_years': academic_years,
        **teacher_data,
    })


@staff_member_required
def register_teacher(request):
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            teacher = form.save()
            academic_year = form.cleaned_data['academic_year']
            selected_classes = form.cleaned_data['homeroom_classes']

            replace_teacher_assignments_for_year(
                teacher=teacher,
                academic_year=academic_year,
                class_ids=[school_class.id for school_class in selected_classes]
            )
            sync_legacy_homeroom_classes(teacher, academic_year)
            ensure_report_periods_for_year(academic_year)
            set_selected_academic_year(request, academic_year)

            messages.success(
                request,
                f'Учитель {teacher.full_name} зарегистрирован. Назначения на {academic_year} сохранены.'
            )
            return redirect('teacher_list')
    else:
        initial_year = get_selected_academic_year(request)
        form = TeacherRegistrationForm(initial={'academic_year': initial_year})

    return render(request, 'reports/register_teacher.html', {
        'form': form,
    })


@staff_member_required
def assign_classes(request, teacher_id):
    teacher = get_object_or_404(Teacher, id=teacher_id)

    academic_year = get_selected_academic_year(request)
    set_selected_academic_year(request, academic_year)

    if request.method == 'POST':
        class_ids = request.POST.getlist('classes')

        replace_teacher_assignments_for_year(
            teacher=teacher,
            academic_year=academic_year,
            class_ids=class_ids
        )
        sync_legacy_homeroom_classes(teacher, academic_year)

        messages.success(
            request,
            f'Классы на {academic_year} назначены учителю {teacher.full_name}'
        )
        return redirect('teacher_list')

    academic_years, selected_year = get_academic_years_with_selected(request, academic_year)
    classes = SchoolClass.objects.filter(is_active=True).order_by('parallel', 'name')
    current_classes = get_teacher_assignment_ids_for_year(teacher, selected_year)

    return render(request, 'reports/assign_classes.html', {
        'teacher': teacher,
        'classes': classes,
        'current_classes': current_classes,
        'academic_year': selected_year,
        'academic_years': academic_years,
    })


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')