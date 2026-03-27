from django.urls import path

from .views import (
    dashboard,
    head_dashboard,
    switch_role,
    select_class_for_report,
    teacher_list,
    register_teacher,
    assign_classes,
    set_academic_year,
)

urlpatterns = [

    # Главная страница
    path('', dashboard, name='dashboard'),

    # Панель завуча
    path('head/', head_dashboard, name='head_dashboard'),

    # Переключение роли (учитель / завуч)
    path('switch-role/', switch_role, name='switch_role'),

    # ==============================
    # Работа с отчетами
    # ==============================

    # выбор класса для периода
    path(
        'report/select-class/<int:period_id>/',
        select_class_for_report,
        name='select_class_for_report'
    ),

    # ==============================
    # Управление учителями
    # ==============================

    # список учителей
    path(
        'teachers/',
        teacher_list,
        name='teacher_list'
    ),

    # регистрация нового учителя
    path(
        'teachers/register/',
        register_teacher,
        name='register_teacher'
    ),

    # назначение классов учителю
    path(
        'teachers/<int:teacher_id>/assign-classes/',
        assign_classes,
        name='assign_classes'
    ),

    # ==============================
    # Переключение учебного года
    # ==============================

    path(
        'set-academic-year/<str:academic_year>/',
        set_academic_year,
        name='set_academic_year'
    ),

]