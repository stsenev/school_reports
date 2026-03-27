# reports/admin.py

from typing import Any, List, Optional, Tuple
from datetime import datetime, timedelta

from django.contrib import admin
from django.contrib.admin import ModelAdmin, TabularInline, StackedInline
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.shortcuts import redirect

from .models import Subject, ClassGroup, Report

User = get_user_model()


# ============================================================
# Кастомные действия для админки
# ============================================================

def approve_reports(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> None:
    """
    Утвердить выбранные отчеты.
    """
    updated = queryset.update(status='approved')
    modeladmin.message_user(
        request,
        f'Утверждено {updated} отчетов.',
        level='success'
    )


approve_reports.short_description = 'Утвердить выбранные отчеты'


def reject_reports(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> None:
    """
    Отклонить выбранные отчеты.
    """
    updated = queryset.update(status='rejected')
    modeladmin.message_user(
        request,
        f'Отклонено {updated} отчетов.',
        level='warning'
    )


reject_reports.short_description = 'Отклонить выбранные отчеты'


def submit_reports(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> None:
    """
    Отправить выбранные отчеты на проверку.
    """
    updated = queryset.update(status='submitted')
    modeladmin.message_user(
        request,
        f'Отправлено на проверку {updated} отчетов.',
        level='info'
    )


submit_reports.short_description = 'Отправить на проверку'


def make_draft(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> None:
    """
    Перевести выбранные отчеты в черновики.
    """
    updated = queryset.update(status='draft')
    modeladmin.message_user(
        request,
        f'{updated} отчетов переведены в черновики.',
        level='info'
    )


make_draft.short_description = 'Перевести в черновики'


def export_as_csv(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> HttpResponse:
    """
    Экспорт выбранных отчетов в CSV.
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="reports_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Дата', 'Учитель (ID)', 'Учитель (Имя)', 'Предмет',
        'Класс', 'Тема', 'Домашнее задание', 'Примечания', 'Статус',
        'Создан', 'Обновлен'
    ])

    for report in queryset:
        writer.writerow([
            report.id,
            report.date.strftime('%d.%m.%Y'),
            report.teacher.id,
            report.teacher.get_full_name() or report.teacher.username,
            report.subject.name,
            report.class_group.name,
            report.topic,
            report.homework.replace('\n', ' '),
            report.notes.replace('\n', ' '),
            report.get_status_display(),
            report.created_at.strftime('%d.%m.%Y %H:%M'),
            report.updated_at.strftime('%d.%m.%Y %H:%M'),
        ])

    modeladmin.message_user(
        request,
        f'Экспортировано {queryset.count()} отчетов.',
        level='success'
    )
    return response


export_as_csv.short_description = 'Экспорт выбранных в CSV'


def delete_reports(modeladmin: ModelAdmin, request: HttpRequest, queryset: QuerySet) -> None:
    """
    Удалить выбранные отчеты (с подтверждением).
    """
    count = queryset.count()
    queryset.delete()
    modeladmin.message_user(
        request,
        f'Удалено {count} отчетов.',
        level='error'
    )


delete_reports.short_description = 'Удалить выбранные'


# ============================================================
# Кастомные фильтры
# ============================================================

class ThisWeekFilter(admin.SimpleListFilter):
    """
    Фильтр для отчетов за текущую неделю.
    """
    title = _('период')
    parameter_name = 'period'

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> List[Tuple[str, str]]:
        return [
            ('today', _('Сегодня')),
            ('this_week', _('Эта неделя')),
            ('this_month', _('Этот месяц')),
            ('last_week', _('Прошлая неделя')),
            ('last_month', _('Прошлый месяц')),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        today = datetime.now().date()

        if self.value() == 'today':
            return queryset.filter(date=today)
        elif self.value() == 'this_week':
            start_of_week = today - timedelta(days=today.weekday())
            return queryset.filter(date__gte=start_of_week)
        elif self.value() == 'this_month':
            return queryset.filter(date__year=today.year, date__month=today.month)
        elif self.value() == 'last_week':
            start_of_last_week = today - timedelta(days=today.weekday() + 7)
            end_of_last_week = start_of_last_week + timedelta(days=6)
            return queryset.filter(date__range=[start_of_last_week, end_of_last_week])
        elif self.value() == 'last_month':
            last_month = today.replace(day=1) - timedelta(days=1)
            return queryset.filter(date__year=last_month.year, date__month=last_month.month)

        return queryset


class TeacherGroupFilter(admin.SimpleListFilter):
    """
    Фильтр для группировки учителей по алфавиту.
    """
    title = _('учитель')
    parameter_name = 'teacher_letter'

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> List[Tuple[str, str]]:
        letters = User.objects.filter(
            reports__isnull=False
        ).values_list('username', flat=True).distinct()

        first_letters = sorted(set(username[0].upper() for username in letters if username))
        return [(letter, letter) for letter in first_letters]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value():
            return queryset.filter(teacher__username__startswith=self.value().lower())
        return queryset


# ============================================================
# Inline модели
# ============================================================

class ReportInline(TabularInline):
    """
    Inline для отображения отчетов учителя.
    """
    model = Report
    fields = ['date', 'subject', 'class_group', 'topic', 'status', 'view_link']
    readonly_fields = ['date', 'subject', 'class_group', 'topic', 'status', 'view_link']
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True
    classes = ['collapse']

    def view_link(self, obj: Report) -> str:
        """
        Ссылка на просмотр отчета в админке.
        """
        url = reverse('admin:reports_report_change', args=[obj.id])
        return format_html('<a href="{}">Просмотр</a>', url)

    view_link.short_description = 'Действие'


class SubjectReportInline(TabularInline):
    """
    Inline для отображения отчетов по предмету.
    """
    model = Report
    fields = ['date', 'teacher', 'class_group', 'topic', 'status']
    readonly_fields = ['date', 'teacher', 'class_group', 'topic', 'status']
    extra = 0
    max_num = 5
    classes = ['collapse']

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related('teacher', 'class_group')[:5]


class ClassGroupReportInline(TabularInline):
    """
    Inline для отображения отчетов по классу.
    """
    model = Report
    fields = ['date', 'teacher', 'subject', 'topic', 'status']
    readonly_fields = ['date', 'teacher', 'subject', 'topic', 'status']
    extra = 0
    max_num = 5
    classes = ['collapse']


# ============================================================
# Админ-классы
# ============================================================

@admin.register(Subject)
class SubjectAdmin(ModelAdmin):
    """
    Администрирование предметов.
    """
    list_display = ['id', 'name', 'reports_count', 'last_report_date', 'view_reports_link']
    list_display_links = ['name']
    search_fields = ['name']
    ordering = ['name']
    list_per_page = 20

    fieldsets = (
        ('Основная информация', {
            'fields': ('name',),
            'description': 'Управление предметами, которые преподаются в школе.'
        }),
    )

    def reports_count(self, obj: Subject) -> int:
        """
        Количество отчетов по предмету.
        """
        return obj.report_set.count()

    reports_count.short_description = 'Количество отчетов'
    reports_count.admin_order_field = 'reports_count'

    def last_report_date(self, obj: Subject) -> str:
        """
        Дата последнего отчета по предмету.
        """
        last_report = obj.report_set.order_by('-date').first()
        if last_report:
            return last_report.date.strftime('%d.%m.%Y')
        return '-'

    last_report_date.short_description = 'Последний отчет'

    def view_reports_link(self, obj: Subject) -> str:
        """
        Ссылка на фильтр отчетов по предмету.
        """
        url = f"/admin/reports/report/?subject__id__exact={obj.id}"
        return format_html('<a href="{}">Просмотреть отчеты</a>', url)

    view_reports_link.short_description = 'Отчеты'

    inlines = [SubjectReportInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).annotate(
            reports_count=Count('report')
        )


@admin.register(ClassGroup)
class ClassGroupAdmin(ModelAdmin):
    """
    Администрирование классов.
    """
    list_display = ['id', 'name', 'class_teacher_info', 'reports_count',
                    'last_report_date', 'students_count_display']
    list_display_links = ['name']
    list_filter = ['class_teacher']
    search_fields = ['name']
    ordering = ['name']
    list_per_page = 20
    list_select_related = ['class_teacher']

    fieldsets = (
        ('Информация о классе', {
            'fields': ('name', 'class_teacher'),
            'description': 'Управление классами и классными руководителями.'
        }),
    )

    raw_id_fields = ['class_teacher']
    autocomplete_fields = ['class_teacher']

    def class_teacher_info(self, obj: ClassGroup) -> str:
        """
        Отображение информации о классном руководителе.
        """
        if obj.class_teacher:
            full_name = obj.class_teacher.get_full_name()
            if full_name:
                return format_html(
                    '<strong>{}</strong><br><span style="color: #666;">@{}</span>',
                    full_name,
                    obj.class_teacher.username
                )
            return obj.class_teacher.username
        return format_html('<span style="color: #999;">Не назначен</span>')

    class_teacher_info.short_description = 'Классный руководитель'
    class_teacher_info.admin_order_field = 'class_teacher__username'

    def reports_count(self, obj: ClassGroup) -> int:
        """
        Количество отчетов по классу.
        """
        return obj.report_set.count()

    reports_count.short_description = 'Количество отчетов'
    reports_count.admin_order_field = 'reports_count'

    def last_report_date(self, obj: ClassGroup) -> str:
        """
        Дата последнего отчета по классу.
        """
        last_report = obj.report_set.order_by('-date').first()
        if last_report:
            return last_report.date.strftime('%d.%m.%Y')
        return '-'

    last_report_date.short_description = 'Последний отчет'

    def students_count_display(self, obj: ClassGroup) -> str:
        """
        Заглушка для количества учеников.
        """
        # Можно подключить модель Student, если есть
        return '-'

    students_count_display.short_description = 'Учеников'

    inlines = [ClassGroupReportInline]

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).annotate(
            reports_count=Count('report')
        )


@admin.register(Report)
class ReportAdmin(ModelAdmin):
    """
    Администрирование отчетов.
    """
    list_display = ['id', 'date_display', 'teacher_info', 'subject',
                    'class_group', 'topic_preview', 'status_badge',
                    'created_at_display', 'actions_links']
    list_display_links = ['id']
    list_filter = [
        'status',
        ThisWeekFilter,
        'subject',
        'class_group',
        ('teacher', admin.RelatedOnlyFieldListFilter),
        'date',
    ]
    search_fields = ['topic', 'homework', 'notes', 'teacher__username',
                     'teacher__first_name', 'teacher__last_name',
                     'subject__name', 'class_group__name']
    list_per_page = 25
    list_select_related = ['teacher', 'subject', 'class_group']
    date_hierarchy = 'date'
    ordering = ['-date', '-created_at']
    save_on_top = True
    actions = [
        approve_reports,
        reject_reports,
        submit_reports,
        make_draft,
        export_as_csv,
        delete_reports
    ]

    fieldsets = (
        ('Основная информация', {
            'fields': ('teacher', 'subject', 'class_group', 'date', 'status'),
            'classes': ('wide',),
        }),
        ('Содержание отчета', {
            'fields': ('topic', 'homework', 'notes'),
            'classes': ('wide',),
            'description': 'Основное содержание отчета: тема урока, домашнее задание и примечания.'
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'Даты создания и последнего обновления отчета.',
        }),
    )

    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['teacher']
    autocomplete_fields = ['teacher', 'subject', 'class_group']

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related(
            'teacher', 'subject', 'class_group'
        )

    def date_display(self, obj: Report) -> str:
        """
        Отображение даты с днем недели.
        """
        weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        weekday = weekdays[obj.date.weekday()]
        return format_html(
            '<strong>{}</strong><br><span style="color: #666;">{}</span>',
            obj.date.strftime('%d.%m.%Y'),
            weekday
        )

    date_display.short_description = 'Дата'
    date_display.admin_order_field = 'date'

    def teacher_info(self, obj: Report) -> str:
        """
        Отображение информации об учителе.
        """
        full_name = obj.teacher.get_full_name()
        if full_name:
            return format_html(
                '<strong>{}</strong><br><span style="color: #666;">@{}</span>',
                full_name,
                obj.teacher.username
            )
        return format_html('<strong>{}</strong>', obj.teacher.username)

    teacher_info.short_description = 'Учитель'
    teacher_info.admin_order_field = 'teacher__username'

    def topic_preview(self, obj: Report) -> str:
        """
        Превью темы урока.
        """
        if len(obj.topic) > 50:
            return f"{obj.topic[:50]}..."
        return obj.topic

    topic_preview.short_description = 'Тема'

    def status_badge(self, obj: Report) -> str:
        """
        Отображение статуса в виде цветного бейджа.
        """
        status_colors = {
            'draft': '#6c757d',  # серый
            'submitted': '#ffc107',  # желтый
            'approved': '#28a745',  # зеленый
            'rejected': '#dc3545',  # красный
        }
        color = status_colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 12px;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_badge.short_description = 'Статус'
    status_badge.admin_order_field = 'status'

    def created_at_display(self, obj: Report) -> str:
        """
        Отображение даты создания.
        """
        return obj.created_at.strftime('%d.%m.%Y %H:%M')

    created_at_display.short_description = 'Создан'
    created_at_display.admin_order_field = 'created_at'

    def actions_links(self, obj: Report) -> str:
        """
        Быстрые действия для отчета.
        """
        change_url = reverse('admin:reports_report_change', args=[obj.id])
        delete_url = reverse('admin:reports_report_delete', args=[obj.id])

        # Ссылка на просмотр на сайте (если есть детальная страница)
        site_url = reverse('reports:report_detail', args=[obj.id])

        return format_html(
            '<a href="{}" class="button" style="margin-right: 5px;">✏️ Изменить</a> '
            '<a href="{}" class="button" style="color: #dc3545;">🗑️ Удалить</a> '
            '<a href="{}" class="button" target="_blank">👁️ Просмотр</a>',
            change_url, delete_url, site_url
        )

    actions_links.short_description = 'Действия'

    def save_model(self, request: HttpRequest, obj: Report, form: Any, change: bool) -> None:
        """
        Переопределение сохранения для дополнительной логики.
        """
        if not change and not obj.teacher_id:
            # Если отчет создается в админке и учитель не выбран,
            # ставим текущего пользователя (если он учитель)
            if request.user.groups.filter(name='teachers').exists():
                obj.teacher = request.user
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request: HttpRequest, obj: Optional[Report] = None) -> List[str]:
        """
        Динамические readonly поля.
        """
        if obj and obj.status == 'approved':
            # Утвержденные отчеты нельзя редактировать
            return self.readonly_fields + ['teacher', 'subject', 'class_group',
                                           'date', 'topic', 'homework', 'notes']
        return self.readonly_fields

    def get_fieldsets(self, request: HttpRequest, obj: Optional[Report] = None):
        """
        Динамические поля для разных статусов.
        """
        fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.status == 'approved':
            # Добавляем предупреждение для утвержденных отчетов
            return (
                ('Утвержденный отчет (только для просмотра)', {
                    'fields': [],
                    'description': '<div style="padding: 10px; background-color: #d4edda; '
                                   'border: 1px solid #c3e6cb; border-radius: 4px; color: #155724;">'
                                   '⚠️ Этот отчет уже утвержден и не может быть изменен.</div>',
                }),
            ) + fieldsets
        return fieldsets


# ============================================================
# Настройка админки для пользователей (опционально)
# ============================================================

class TeacherInline(StackedInline):
    """
    Inline для отображения дополнительной информации об учителе.
    """
    model = ClassGroup
    fields = ['name']
    extra = 0
    max_num = 5
    verbose_name = 'Классное руководство'
    verbose_name_plural = 'Классы, которыми руководит'


def add_teacher_fields_to_user_admin():
    """
    Расширение стандартного UserAdmin для добавления учительских полей.
    """
    from django.contrib.auth.admin import UserAdmin

    # Сохраняем оригинальные поля
    original_fieldsets = UserAdmin.fieldsets

    # Добавляем новые поля
    UserAdmin.fieldsets = original_fieldsets + (
        ('Учительская информация', {
            'fields': ('groups',),
            'description': 'Добавьте пользователя в группу "teachers", чтобы он мог создавать отчеты.'
        }),
    )

    # Добавляем inline
    UserAdmin.inlines = getattr(UserAdmin, 'inlines', []) + [TeacherInline]

    # Добавляем фильтр по группам
    if 'groups' not in UserAdmin.list_filter:
        UserAdmin.list_filter = list(UserAdmin.list_filter) + ['groups']


# Раскомментировать для расширения UserAdmin
# add_teacher_fields_to_user_admin()


# ============================================================
# Настройка заголовков админки
# ============================================================

admin.site.site_header = 'Система отчетов учителей'
admin.site.site_title = 'Панель управления'
admin.site.index_title = 'Добро пожаловать в панель управления отчетами'