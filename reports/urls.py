# reports/urls.py
from django.urls import path

from .views import (
    add_age_group_row,
    approve_report,
    assign_classes,
    bulk_change_status,
    change_report_status,
    class_reports,
    dashboard,
    delete_report,
    dynamics_report,
    edit_report,
    edit_teacher,
    export_dynamics_excel,
    export_social_excel,
    export_summary_excel,
    get_previous_report_data,
    head_dashboard,
    register_teacher,
    reject_report,
    reset_teacher_password,
    select_class_for_report,
    social_summary_report,
    submit_report,
    summary_report,
    switch_role,
    teacher_list,
    view_report,
)
from .wizard_views import (
    wizard_cancel,
    wizard_start,
    wizard_step1,
    wizard_step2,
    wizard_step3,
    wizard_step4,
    wizard_step5,
)

urlpatterns = [
    # Главная панель
    path('', dashboard, name='dashboard'),
    path('head/', head_dashboard, name='head_dashboard'),
    path('switch-role/', switch_role, name='switch_role'),

    # Отчеты
    path('report/select-class/<int:period_id>/', select_class_for_report, name='select_class_for_report'),
    path('report/<int:report_id>/', view_report, name='view_report'),
    path('report/<int:report_id>/edit/', edit_report, name='edit_report'),
    path('report/<int:report_id>/submit/', submit_report, name='submit_report'),
    path('report/<int:report_id>/approve/', approve_report, name='approve_report'),
    path('report/<int:report_id>/reject/', reject_report, name='reject_report'),
    path('report/<int:report_id>/delete/', delete_report, name='delete_report'),
    path('report/<int:report_id>/change-status/', change_report_status, name='change_report_status'),
    path('class/<int:class_id>/reports/', class_reports, name='class_reports'),

    # Сводные отчеты
    path('summary/', summary_report, name='summary_report'),
    path('summary/export/', export_summary_excel, name='export_summary_excel'),
    path('social-summary/', social_summary_report, name='social_summary_report'),
    path('social-summary/export/', export_social_excel, name='export_social_excel'),
    path('dynamics/', dynamics_report, name='dynamics_report'),
    path('dynamics/export/', export_dynamics_excel, name='export_dynamics_excel'),
    path('reports/bulk-change-status/', bulk_change_status, name='bulk_change_status'),

    # Пошаговый мастер
    path('wizard/start/<int:period_id>/<int:class_id>/', wizard_start, name='wizard_start'),
    path('wizard/step1/<int:report_id>/', wizard_step1, name='wizard_step1'),
    path('wizard/step2/<int:report_id>/', wizard_step2, name='wizard_step2'),
    path('wizard/step3/<int:report_id>/', wizard_step3, name='wizard_step3'),
    path('wizard/step4/<int:report_id>/', wizard_step4, name='wizard_step4'),
    path('wizard/step5/<int:report_id>/', wizard_step5, name='wizard_step5'),
    path('wizard/cancel/<int:report_id>/', wizard_cancel, name='wizard_cancel'),

    # AJAX
    path('ajax/add-age-group/', add_age_group_row, name='add_age_group'),
    path(
        'ajax/get-previous-report/<int:period_id>/<int:class_id>/',
        get_previous_report_data,
        name='get_previous_report_data',
    ),

    # Учителя
    path('teachers/', teacher_list, name='teacher_list'),
    path('teachers/register/', register_teacher, name='register_teacher'),
    path('teachers/<int:teacher_id>/edit/', edit_teacher, name='edit_teacher'),
    path('teachers/<int:teacher_id>/reset-password/', reset_teacher_password, name='reset_teacher_password'),
    path('teachers/<int:teacher_id>/assign-classes/', assign_classes, name='assign_classes'),
]