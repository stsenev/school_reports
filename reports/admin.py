# reports/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import *


class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (('Роль', {'fields': ('role',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Роль', {'fields': ('role',)}),)


class TeacherClassAssignmentInline(admin.TabularInline):
    model = TeacherClassAssignment
    extra = 1
    fields = ['school_class', 'academic_year', 'is_active']


class FamilyEducationStudentInline(admin.TabularInline):
    """Inline для учеников на семейном обучении"""
    model = FamilyEducationStudent
    extra = 0
    fields = ['full_name']
    readonly_fields = ['full_name']


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'get_homeroom_classes', 'is_active', 'user_role')
    list_filter = ('is_active', 'homeroom_classes', 'user__role')
    search_fields = ('full_name', 'user__username', 'user__email')
    filter_horizontal = ['homeroom_classes']
    inlines = [TeacherClassAssignmentInline]

    def get_homeroom_classes(self, obj):
        classes = obj.homeroom_classes.all()
        if classes:
            return format_html('<span class="badge badge-primary">{}</span>', ", ".join([c.name for c in classes]))
        return '-'

    get_homeroom_classes.short_description = 'Классное руководство'

    def user_role(self, obj):
        role_display = dict(User.ROLE_CHOICES).get(obj.user.role, obj.user.role)
        colors = {'teacher': 'success', 'head_teacher': 'warning', 'both': 'info'}
        return format_html('<span class="badge badge-{}">{}</span>', colors.get(obj.user.role, 'secondary'),
                           role_display)

    user_role.short_description = 'Роль пользователя'


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'parallel', 'is_active')
    list_filter = ('parallel', 'is_active')
    search_fields = ('name',)


@admin.register(ReportPeriod)
class ReportPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'period_type', 'academic_year', 'start_date', 'end_date', 'is_active')
    list_filter = ('period_type', 'academic_year', 'is_active')
    search_fields = ('name', 'academic_year')


@admin.register(TeacherReport)
class TeacherReportAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'school_class', 'period', 'status', 'created_at', 'submitted_at')
    list_filter = ('status', 'period', 'school_class__parallel')
    search_fields = ('teacher__full_name', 'school_class__name')
    date_hierarchy = 'created_at'
    raw_id_fields = ('teacher', 'school_class', 'period', 'approved_by')


@admin.register(TeacherClassAssignment)
class TeacherClassAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'school_class', 'academic_year', 'assigned_date', 'is_active')
    list_filter = ('is_active', 'academic_year', 'school_class__parallel')
    search_fields = ('teacher__full_name', 'school_class__name')
    date_hierarchy = 'assigned_date'


@admin.register(FamilyEducation)
class FamilyEducationAdmin(admin.ModelAdmin):
    list_display = ['report', 'has_family_education', 'count']
    list_filter = ['has_family_education']
    search_fields = ['report__teacher__full_name', 'report__school_class__name']
    inlines = [FamilyEducationStudentInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'report__teacher', 'report__school_class', 'report__period'
        )

    def has_add_permission(self, request):
        """Запрещаем добавление FamilyEducation через админку вручную"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Разрешаем удаление"""
        return True


@admin.register(FamilyEducationStudent)
class FamilyEducationStudentAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'family_education']
    list_filter = ['family_education__has_family_education']
    search_fields = ['full_name']
    raw_id_fields = ['family_education']


@admin.register(StudentMovement)
class StudentMovementAdmin(admin.ModelAdmin):
    list_display = ('student_name', 'movement_type', 'report', 'order_number', 'order_date')
    list_filter = ('movement_type',)
    search_fields = ('student_name',)
    raw_id_fields = ('report', 'target_class', 'source_class')


@admin.register(StudentAgeGroup)
class StudentAgeGroupAdmin(admin.ModelAdmin):
    list_display = ('report', 'birth_year', 'boys_count', 'girls_count')
    list_filter = ('birth_year',)
    search_fields = ('report__teacher__full_name',)


@admin.register(HealthGroup)
class HealthGroupAdmin(admin.ModelAdmin):
    list_display = ('report', 'group1', 'group2', 'group3', 'group4', 'group5')
    raw_id_fields = ('report',)


@admin.register(PhysicalEducationGroup)
class PhysicalEducationGroupAdmin(admin.ModelAdmin):
    list_display = ('report', 'main_group', 'preparatory_group', 'special_group', 'exempt_count')
    raw_id_fields = ('report',)


@admin.register(ExemptStudent)
class ExemptStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phys_ed_group')
    search_fields = ('full_name',)
    raw_id_fields = ('phys_ed_group',)


@admin.register(SpecialNeeds)
class SpecialNeedsAdmin(admin.ModelAdmin):
    list_display = ('report', 'disabled_count', 'special_needs_count', 'disabled_special_needs_count',
                    'home_schooling_count', 'foster_care_count')
    raw_id_fields = ('report',)


@admin.register(SpecialNeedsStudent)
class SpecialNeedsStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'student_type_display', 'special_needs')
    list_filter = ('student_type',)
    search_fields = ('full_name',)
    raw_id_fields = ('special_needs',)

    def student_type_display(self, obj):
        return obj.get_student_type_display()

    student_type_display.short_description = 'Тип'


@admin.register(AcademicPerformance)
class AcademicPerformanceAdmin(admin.ModelAdmin):
    list_display = ('report', 'excellent_count', 'good_count', 'poor_count', 'quality_percentage')
    raw_id_fields = ('report',)

    def quality_percentage(self, obj):
        if obj.report and obj.report.in_person_students_count > 0:
            quality = (obj.excellent_count + obj.good_count) / obj.report.in_person_students_count * 100
            return f"{quality:.1f}%"
        return "0%"

    quality_percentage.short_description = 'Качество'


@admin.register(ExcellentStudent)
class ExcellentStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'performance')
    search_fields = ('full_name',)
    raw_id_fields = ('performance',)


@admin.register(OneFourStudent)
class OneFourStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'subject', 'teacher', 'performance')
    list_filter = ('subject_code',)
    search_fields = ('full_name', 'subject', 'teacher')
    raw_id_fields = ('performance',)


@admin.register(OneThreeStudent)
class OneThreeStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'subject', 'teacher', 'performance')
    list_filter = ('subject_code',)
    search_fields = ('full_name', 'subject', 'teacher')
    raw_id_fields = ('performance',)


@admin.register(PoorStudent)
class PoorStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'subject', 'teacher', 'is_recurring', 'get_report_info')
    list_filter = ('is_recurring', 'subject_code')
    search_fields = ('full_name', 'subject', 'teacher')
    raw_id_fields = ('performance',)

    def get_report_info(self, obj):
        if obj.performance and obj.performance.report:
            return f"{obj.performance.report.school_class.name} - {obj.performance.report.period.name}"
        return "-"

    get_report_info.short_description = 'Класс / Период'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'performance__report__school_class',
            'performance__report__period'
        )


@admin.register(NotAttestedStudent)
class NotAttestedStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'performance')
    search_fields = ('full_name',)
    raw_id_fields = ('performance',)


@admin.register(RetainedStudent)
class RetainedStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'performance')
    search_fields = ('full_name',)
    raw_id_fields = ('performance',)


@admin.register(ConditionallyPromotedStudent)
class ConditionallyPromotedStudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'performance')
    search_fields = ('full_name',)
    raw_id_fields = ('performance',)


# Регистрация пользовательской модели User
admin.site.register(User, CustomUserAdmin)