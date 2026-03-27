from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class User(AbstractUser):
    ROLE_CHOICES = (
        ('teacher', 'Учитель'),
        ('head_teacher', 'Завуч'),
        ('both', 'Учитель и Завуч'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher', verbose_name='Роль')

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def is_head_teacher(self):
        return self.role in ['head_teacher', 'both']

    def is_teacher(self):
        return self.role in ['teacher', 'both']


class SchoolClass(models.Model):
    name = models.CharField(max_length=20, verbose_name='Название класса')
    parallel = models.IntegerField(verbose_name='Параллель', validators=[MinValueValidator(1), MaxValueValidator(11)])
    is_active = models.BooleanField(default=True, verbose_name='Активный')

    class Meta:
        verbose_name = 'Класс'
        verbose_name_plural = 'Классы'
        ordering = ['parallel', 'name']

    def __str__(self):
        return self.name


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile',
                                verbose_name='Пользователь')
    full_name = models.CharField(max_length=100, verbose_name='ФИО')
    homeroom_classes = models.ManyToManyField(
        SchoolClass,
        related_name='homeroom_teachers',
        blank=True,
        verbose_name='Классное руководство'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активный')

    class Meta:
        verbose_name = 'Учитель'
        verbose_name_plural = 'Учителя'

    def __str__(self):
        return self.full_name

    def get_assignments_for_year(self, academic_year):
        return self.class_assignments.filter(
            academic_year=academic_year,
            is_active=True,
            school_class__is_active=True,
        ).select_related('school_class').order_by('school_class__parallel', 'school_class__name')

    def get_classes_for_year(self, academic_year):
        return SchoolClass.objects.filter(
            teacher_assignments__teacher=self,
            teacher_assignments__academic_year=academic_year,
            teacher_assignments__is_active=True,
            is_active=True,
        ).distinct().order_by('parallel', 'name')


class TeacherClassAssignment(models.Model):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name='class_assignments',
        verbose_name='Учитель'
    )
    school_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.CASCADE,
        related_name='teacher_assignments',
        verbose_name='Класс'
    )
    academic_year = models.CharField(max_length=9, verbose_name='Учебный год')
    assigned_date = models.DateField(auto_now_add=True, verbose_name='Дата назначения')
    is_active = models.BooleanField(default=True, verbose_name='Активно')

    class Meta:
        verbose_name = 'Назначение класса'
        verbose_name_plural = 'Назначения классов'
        unique_together = ['teacher', 'school_class', 'academic_year']
        ordering = ['academic_year', 'school_class__parallel', 'school_class__name']

    def __str__(self):
        return f"{self.teacher} - {self.school_class} ({self.academic_year})"


class ReportPeriod(models.Model):
    PERIOD_TYPES = (
        ('start_year', 'Начало учебного года'),
        ('quarter1', '1 четверть'),
        ('quarter2', '2 четверть'),
        ('quarter3', '3 четверть'),
        ('quarter4', '4 четверть'),
        ('half1', '1 полугодие'),
        ('half2', '2 полугодие'),
        ('year', 'Год'),
    )

    name = models.CharField(max_length=50, verbose_name='Название периода')
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, verbose_name='Тип периода')
    academic_year = models.CharField(max_length=9, verbose_name='Учебный год')
    start_date = models.DateField(verbose_name='Дата начала')
    end_date = models.DateField(verbose_name='Дата окончания')
    is_active = models.BooleanField(default=True, verbose_name='Активный')

    class Meta:
        verbose_name = 'Отчетный период'
        verbose_name_plural = 'Отчетные периоды'
        ordering = ['-start_date']
        unique_together = ['period_type', 'academic_year']

    def __str__(self):
        return f"{self.name} {self.academic_year}"


class TeacherReport(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Черновик'),
        ('submitted', 'Отправлен'),
        ('approved', 'Утвержден'),
        ('rejected', 'Отклонен'),
    )

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, verbose_name='Учитель')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, verbose_name='Класс')
    period = models.ForeignKey(ReportPeriod, on_delete=models.CASCADE, verbose_name='Период')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Отправлен')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_reports', verbose_name='Утвердил')
    total_students_end = models.PositiveIntegerField(default=0, verbose_name='Количество учеников на конец периода')
    has_movement = models.BooleanField(default=False, verbose_name='Есть движение учеников')

    class Meta:
        verbose_name = 'Отчет учителя'
        verbose_name_plural = 'Отчеты учителей'
        unique_together = ['teacher', 'school_class', 'period']
        indexes = [
            models.Index(fields=['teacher', 'period']),
            models.Index(fields=['school_class', 'period']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.teacher} - {self.school_class} - {self.period}"

    @property
    def in_person_students_count(self):
        """Количество очных учеников"""
        if hasattr(self, 'family_education') and self.family_education:
            return self.total_students_end - self.family_education.count
        return self.total_students_end

    @property
    def has_family_education_students(self):
        """
        Проверяет, есть ли ученики на семейном обучении
        """
        return hasattr(self, 'family_education') and self.family_education and self.family_education.count > 0

    def get_family_education_students_list(self):
        """
        Возвращает список учеников на семейном обучении
        """
        if self.has_family_education_students:
            return self.family_education.students.all()
        return []

    @property
    def quality_percentage(self):
        """
        Рассчитывает процент качества знаний
        (отличники + ударники) / очные ученики * 100
        """
        if not hasattr(self, 'academic_performance') or not self.academic_performance:
            return 0

        in_person = self.in_person_students_count
        if in_person == 0:
            return 0

        perf = self.academic_performance
        excellent_good = perf.excellent_count + perf.good_count
        return round((excellent_good / in_person) * 100, 1)

    @property
    def success_percentage(self):
        """
        Рассчитывает процент успеваемости
        (очные - двоечники) / очные * 100
        """
        if not hasattr(self, 'academic_performance') or not self.academic_performance:
            return 0

        in_person = self.in_person_students_count
        if in_person == 0:
            return 0

        perf = self.academic_performance
        return round(((in_person - perf.poor_count) / in_person) * 100, 1)

class StudentMovement(models.Model):
    MOVEMENT_TYPE = (
        ('in', 'Прибыл'),
        ('out', 'Выбыл'),
    )

    report = models.ForeignKey(TeacherReport, on_delete=models.CASCADE, related_name='movements', verbose_name='Отчет')
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPE, verbose_name='Тип движения')
    student_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    # Для выбывших
    moved_to_another_class = models.BooleanField(default=False, verbose_name='Выбыл в другой класс')
    moved_to_another_school = models.BooleanField(default=False, verbose_name='Выбыл в другую школу')
    target_class = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name='Класс', related_name='+')
    target_school = models.CharField(max_length=200, blank=True, verbose_name='Школа')

    # Для прибывших
    came_from_another_class = models.BooleanField(default=False, verbose_name='Прибыл из другого класса')
    came_from_another_school = models.BooleanField(default=False, verbose_name='Прибыл из другой школы')
    source_class = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name='Класс', related_name='+')
    source_school = models.CharField(max_length=200, blank=True, verbose_name='Школа')

    # Общие поля - делаем необязательными
    order_number = models.CharField(max_length=50, blank=True, verbose_name='Номер приказа')
    order_date = models.DateField(null=True, blank=True, verbose_name='Дата приказа')

    class Meta:
        verbose_name = 'Движение ученика'
        verbose_name_plural = 'Движения учеников'

    def __str__(self):
        return f"{self.student_name} - {self.get_movement_type_display()}"


class FamilyEducation(models.Model):
    """
    Модель для хранения информации о семейном обучении в отчете.
    Связана с TeacherReport через OneToOneField.
    """
    report = models.OneToOneField(
        'TeacherReport',
        on_delete=models.CASCADE,
        related_name='family_education',
        verbose_name='Отчет'
    )
    has_family_education = models.BooleanField(
        default=False,
        verbose_name='Есть ученики на семейном обучении'
    )
    count = models.PositiveIntegerField(
        default=0,
        verbose_name='Количество'
    )

    class Meta:
        verbose_name = 'Семейное обучение'
        verbose_name_plural = 'Семейное обучение'

    def __str__(self):
        return f"Семейное обучение: {self.count} учеников"

    def save(self, *args, **kwargs):
        """
        Переопределяем save для автоматической синхронизации
        has_family_education и count
        """
        if self.count > 0:
            self.has_family_education = True
        else:
            self.has_family_education = False
        super().save(*args, **kwargs)


class FamilyEducationStudent(models.Model):
    """
    Модель для хранения списка учеников на семейном обучении.
    Связана с FamilyEducation через ForeignKey.
    """
    family_education = models.ForeignKey(
        FamilyEducation,
        on_delete=models.CASCADE,
        related_name='students',
        verbose_name='Семейное обучение'
    )
    full_name = models.CharField(
        max_length=100,
        verbose_name='ФИО ученика'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата добавления'
    )

    class Meta:
        verbose_name = 'Ученик на семейном обучении'
        verbose_name_plural = 'Ученики на семейном обучении'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

class StudentAgeGroup(models.Model):
    report = models.ForeignKey(TeacherReport, on_delete=models.CASCADE, related_name='age_groups', verbose_name='Отчет')
    birth_year = models.IntegerField(verbose_name='Год рождения')
    boys_count = models.PositiveIntegerField(default=0, verbose_name='Мальчики')
    girls_count = models.PositiveIntegerField(default=0, verbose_name='Девочки')

    class Meta:
        verbose_name = 'Возрастная группа'
        verbose_name_plural = 'Возрастные группы'
        unique_together = ['report', 'birth_year']


class HealthGroup(models.Model):
    report = models.OneToOneField(TeacherReport, on_delete=models.CASCADE, related_name='health_groups',
                                  verbose_name='Отчет')
    group1 = models.PositiveIntegerField(default=0, verbose_name='1 группа')
    group2 = models.PositiveIntegerField(default=0, verbose_name='2 группа')
    group3 = models.PositiveIntegerField(default=0, verbose_name='3 группа')
    group4 = models.PositiveIntegerField(default=0, verbose_name='4 группа')
    group5 = models.PositiveIntegerField(default=0, verbose_name='5 группа')

    class Meta:
        verbose_name = 'Группа здоровья'
        verbose_name_plural = 'Группы здоровья'


class PhysicalEducationGroup(models.Model):
    report = models.OneToOneField(TeacherReport, on_delete=models.CASCADE, related_name='phys_ed_groups',
                                  verbose_name='Отчет')
    main_group = models.PositiveIntegerField(default=0, verbose_name='Основная группа')
    preparatory_group = models.PositiveIntegerField(default=0, verbose_name='Подготовительная группа')
    special_group = models.PositiveIntegerField(default=0, verbose_name='Специальная группа')
    exempt_count = models.PositiveIntegerField(default=0, verbose_name='Освобождены')

    class Meta:
        verbose_name = 'Физкультурная группа'
        verbose_name_plural = 'Физкультурные группы'


class ExemptStudent(models.Model):
    phys_ed_group = models.ForeignKey(PhysicalEducationGroup, on_delete=models.CASCADE, related_name='exempt_students',
                                      verbose_name='Физгруппа')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    class Meta:
        verbose_name = 'Освобожденный ученик'
        verbose_name_plural = 'Освобожденные ученики'


class SpecialNeeds(models.Model):
    report = models.OneToOneField(TeacherReport, on_delete=models.CASCADE, related_name='special_needs',
                                  verbose_name='Отчет')
    disabled_count = models.PositiveIntegerField(default=0, verbose_name='Дети-инвалиды')
    special_needs_count = models.PositiveIntegerField(default=0, verbose_name='Дети с ОВЗ')
    disabled_special_needs_count = models.PositiveIntegerField(default=0, verbose_name='Дети-инвалиды с ОВЗ')
    home_schooling_count = models.PositiveIntegerField(default=0, verbose_name='Обучающиеся на дому')
    home_schooling_disabled_count = models.PositiveIntegerField(default=0, verbose_name='из них дети-инвалиды')
    foster_care_count = models.PositiveIntegerField(default=0, verbose_name='Опекаемые дети')

    class Meta:
        verbose_name = 'Дети с ОВЗ/инвалиды'
        verbose_name_plural = 'Дети с ОВЗ/инвалиды'


class SpecialNeedsStudent(models.Model):
    STUDENT_TYPE = (
        ('disabled', 'Дети-инвалиды'),
        ('special_needs', 'Дети с ОВЗ'),
        ('disabled_special', 'Дети-инвалиды с ОВЗ'),
        ('home_schooling', 'Обучающиеся на дому'),
        ('home_disabled', 'Обучающиеся на дому (инвалиды)'),
        ('foster_care', 'Опекаемые дети'),
    )
    special_needs = models.ForeignKey(SpecialNeeds, on_delete=models.CASCADE, related_name='students',
                                      verbose_name='Категория')
    student_type = models.CharField(max_length=20, choices=STUDENT_TYPE, verbose_name='Тип')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    class Meta:
        verbose_name = 'Ученик особой категории'
        verbose_name_plural = 'Ученики особых категорий'

    def __str__(self):
        return self.full_name

    @property
    def student_type_display(self):
        return dict(self.STUDENT_TYPE).get(self.student_type, self.student_type)


class AcademicPerformance(models.Model):
    report = models.OneToOneField(TeacherReport, on_delete=models.CASCADE, related_name='academic_performance',
                                  verbose_name='Отчет')
    excellent_count = models.PositiveIntegerField(default=0, verbose_name='Количество отличников')
    good_count = models.PositiveIntegerField(default=0, verbose_name='Количество ударников')
    one_four_count = models.PositiveIntegerField(default=0, verbose_name='С одной "4"')
    one_three_count = models.PositiveIntegerField(default=0, verbose_name='С одной "3"')
    poor_count = models.PositiveIntegerField(default=0, verbose_name='Количество двоечников')
    not_attested_count = models.PositiveIntegerField(default=0, verbose_name='Не аттестованы')
    retained_count = models.PositiveIntegerField(default=0, verbose_name='Оставлены на повторный год')
    conditionally_promoted_count = models.PositiveIntegerField(default=0, verbose_name='Переведены условно')
    days_missed = models.PositiveIntegerField(default=0, verbose_name='Пропущено учебных дней')
    days_missed_illness = models.PositiveIntegerField(default=0, verbose_name='из них по болезни')
    lessons_missed = models.PositiveIntegerField(default=0, verbose_name='Пропущено уроков всего')
    lessons_missed_illness = models.PositiveIntegerField(default=0, verbose_name='из них по болезни')
    injury_school = models.PositiveIntegerField(default=0, verbose_name='Травматизм в школе')
    injury_outside = models.PositiveIntegerField(default=0, verbose_name='Травматизм вне школы')

    class Meta:
        verbose_name = 'Успеваемость'
        verbose_name_plural = 'Успеваемость'


class ExcellentStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='excellent_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    class Meta:
        verbose_name = 'Отличник'
        verbose_name_plural = 'Отличники'


class OneFourStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='one_four_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')
    subject = models.CharField(max_length=100, verbose_name='Предмет')
    subject_code = models.CharField(max_length=50, blank=True, verbose_name='Код предмета')
    teacher = models.CharField(max_length=100, verbose_name='Учитель')

    class Meta:
        verbose_name = 'Ученик с одной "4"'
        verbose_name_plural = 'Ученики с одной "4"'


class OneThreeStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='one_three_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')
    subject = models.CharField(max_length=100, verbose_name='Предмет')
    subject_code = models.CharField(max_length=50, blank=True, verbose_name='Код предмета')
    teacher = models.CharField(max_length=100, verbose_name='Учитель')

    class Meta:
        verbose_name = 'Ученик с одной "3"'
        verbose_name_plural = 'Ученики с одной "3"'


class NotAttestedStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='not_attested_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')
    subjects = models.TextField(verbose_name='Предметы с указанием учителей')

    class Meta:
        verbose_name = 'Не аттестованный ученик'
        verbose_name_plural = 'Не аттестованные ученики'


class RetainedStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='retained_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    class Meta:
        verbose_name = 'Оставленный на повторный год'
        verbose_name_plural = 'Оставленные на повторный год'


class ConditionallyPromotedStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE,
                                    related_name='conditionally_promoted_students', verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')

    class Meta:
        verbose_name = 'Переведенный условно'
        verbose_name_plural = 'Переведенные условно'

# models.py - проверьте, что поле is_recurring определено правильно

class PoorStudent(models.Model):
    performance = models.ForeignKey(AcademicPerformance, on_delete=models.CASCADE, related_name='poor_students',
                                    verbose_name='Успеваемость')
    full_name = models.CharField(max_length=100, verbose_name='ФИО ученика')
    subject = models.CharField(max_length=100, verbose_name='Предмет')
    subject_code = models.CharField(max_length=50, blank=True, verbose_name='Код предмета')
    teacher = models.CharField(max_length=100, verbose_name='Учитель')
    is_recurring = models.BooleanField(default=False, verbose_name='Сквозная двойка')

    class Meta:
        verbose_name = 'Двоечник'
        verbose_name_plural = 'Двоечники'

    def __str__(self):
        return f"{self.full_name} - {self.subject}"