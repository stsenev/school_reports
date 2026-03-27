# reports/wizard_views.py - полный файл с правильными импортами

from .services.academic_utils import check_recurring_poor_student
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from .models import *
from .forms import *
from .period_utils import get_previous_approved_report, check_period_availability  # Импортируем обе функции
import traceback


@login_required
def wizard_start(request, period_id, class_id):
    """Начало мастера заполнения отчета"""
    if not request.user.is_teacher():
        messages.error(request, 'Доступ запрещен')
        return redirect('dashboard')

    period = get_object_or_404(ReportPeriod, id=period_id, is_active=True)
    school_class = get_object_or_404(SchoolClass, id=class_id, is_active=True)

    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        messages.error(request, 'Профиль учителя не найден')
        return redirect('dashboard')

    if school_class not in teacher.homeroom_classes.all():
        messages.error(request, 'Вы не являетесь классным руководителем этого класса')
        return redirect('dashboard')

    # Проверка последовательности отчетов
    is_available, error_message = check_period_availability(teacher, school_class, period)

    if not is_available:
        messages.error(request, error_message)
        return redirect('select_class_for_report', period_id=period.id)

    # Проверка наличия утвержденного отчета за начало года для 1 четверти
    if period.period_type == 'quarter1':
        start_year_period = ReportPeriod.objects.filter(
            period_type='start_year',
            academic_year=period.academic_year,
            is_active=True
        ).first()

        if not start_year_period:
            messages.error(request, 'Не найден период "Начало учебного года"')
            return redirect('dashboard')

        start_year_report = TeacherReport.objects.filter(
            teacher=teacher,
            school_class=school_class,
            period=start_year_period,
            status='approved'
        ).exists()

        if not start_year_report:
            messages.error(
                request,
                'Для заполнения отчета за 1 четверть необходимо сначала получить утвержденный отчет за начало учебного года.'
            )
            return redirect('select_class_for_report', period_id=period.id)

    # Проверяем, есть ли уже отчет
    existing_report = TeacherReport.objects.filter(
        teacher=teacher,
        school_class=school_class,
        period=period
    ).first()

    if existing_report:
        if existing_report.status == 'draft':
            messages.info(request, 'Продолжаем заполнение существующего черновика')
            return redirect('wizard_step1', report_id=existing_report.id)
        else:
            messages.warning(request, f'Отчет за этот период уже {existing_report.get_status_display()}')
            return redirect('view_report', report_id=existing_report.id)

    # Создаем новый отчет
    report = TeacherReport.objects.create(
        teacher=teacher,
        school_class=school_class,
        period=period,
        status='draft',
        total_students_end=0,
        has_movement=False
    )

    #print(f"DEBUG wizard_start: report.id = {report.id}, created = True")

    # Сохраняем ID отчета в сессии
    request.session['wizard_report_id'] = report.id
    request.session['wizard_step'] = 1
    request.session['wizard_period_id'] = period.id
    request.session['wizard_class_id'] = class_id

    return redirect('wizard_step1', report_id=report.id)


# wizard_views.py - полная исправленная функция wizard_step1

@login_required
def wizard_step1(request, report_id):
    """Шаг 1: Основные данные и движение учеников"""
    report = get_object_or_404(TeacherReport, id=report_id)

    #print(f"\n=== DEBUG wizard_step1 ===")
    #print(f"Метод запроса: {request.method}")
    #print(f"report.id: {report.id}")
    #print(f"Тип периода: {report.period.period_type}")

    # Проверка прав
    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    # Загружаем предыдущий утвержденный отчет
    previous_report = None

    # Для 1 четверти загружаем из начала года
    if report.period.period_type == 'quarter1':
        start_year_period = ReportPeriod.objects.filter(
            period_type='start_year',
            academic_year=report.period.academic_year,
            is_active=True
        ).first()

        if start_year_period:
            previous_report = TeacherReport.objects.filter(
                teacher=report.teacher,
                school_class=report.school_class,
                period=start_year_period,
                status='approved'
            ).prefetch_related('movements').first()

            # if previous_report:
            #     #print(f"Загружен отчет за начало года ID={previous_report.id}")
            #     #print(f"  - Всего учеников: {previous_report.total_students_end}")
            #     #print(f"  - Движение: {previous_report.movements.count()} записей")

    # Для остальных периодов (кроме start_year и quarter1) используем предыдущий период
    elif report.period.period_type not in ['start_year']:
        previous_report = get_previous_approved_report(
            report.teacher,
            report.school_class,
            report.period
        )

        # if previous_report:
        #     #print(f"Загружен предыдущий отчет ID={previous_report.id} за период {previous_report.period.period_type}")

    if request.method == 'POST':
        #print("\n--- Обработка POST запроса ---")
        #print(f"POST данные: {request.POST}")

        form = TeacherReportForm(request.POST, instance=report, prefix='main')
        movement_formset = StudentMovementFormSet(request.POST, prefix='movement')

        has_movement = request.POST.get('main-has_movement') == 'on'
        #print(f"has_movement из POST: {has_movement}")

        forms_valid = form.is_valid()

        if has_movement:
            for movement_form in movement_formset:
                movement_form.fields['order_number'].required = False
                movement_form.fields['order_date'].required = False

            #print(f"movement_formset.is_valid(): {movement_formset.is_valid()}")
            forms_valid = forms_valid and movement_formset.is_valid()

        if forms_valid:
            #print("Формы валидны, начинаем сохранение...")
            try:
                with transaction.atomic():
                    report = form.save(commit=False)
                    report.has_movement = has_movement
                    report.save()

                    report.movements.all().delete()

                    if has_movement:
                        saved_count = 0
                        for movement_form in movement_formset:
                            if movement_form.cleaned_data and not movement_form.cleaned_data.get('DELETE'):
                                student_name = movement_form.cleaned_data.get('student_name')
                                if student_name:
                                    movement_type = movement_form.cleaned_data.get('movement_type')
                                    movement = StudentMovement(
                                        report=report,
                                        movement_type=movement_type,
                                        student_name=student_name,
                                        order_number=movement_form.cleaned_data.get('order_number', ''),
                                        order_date=movement_form.cleaned_data.get('order_date'),
                                    )

                                    # Добавляем специфичные поля в зависимости от типа
                                    if movement_type == 'out':
                                        movement.moved_to_another_class = movement_form.cleaned_data.get(
                                            'moved_to_another_class', False)
                                        movement.moved_to_another_school = movement_form.cleaned_data.get(
                                            'moved_to_another_school', False)
                                        target_class_obj = movement_form.cleaned_data.get('target_class')
                                        if target_class_obj and isinstance(target_class_obj, SchoolClass):
                                            movement.target_class_id = target_class_obj.id
                                        else:
                                            movement.target_class_id = target_class_obj
                                        movement.target_school = movement_form.cleaned_data.get('target_school', '')
                                    else:
                                        movement.came_from_another_class = movement_form.cleaned_data.get(
                                            'came_from_another_class', False)
                                        movement.came_from_another_school = movement_form.cleaned_data.get(
                                            'came_from_another_school', False)
                                        source_class_obj = movement_form.cleaned_data.get('source_class')
                                        if source_class_obj and isinstance(source_class_obj, SchoolClass):
                                            movement.source_class_id = source_class_obj.id
                                        else:
                                            movement.source_class_id = source_class_obj
                                        movement.source_school = movement_form.cleaned_data.get('source_school', '')

                                    movement.save()
                                    saved_count += 1
                        #print(f"Сохранено записей движения: {saved_count}")

                    messages.success(request, 'Шаг 1 сохранен')
                    request.session['wizard_step'] = 2
                    return redirect('wizard_step2', report_id=report.id)

            except Exception as e:
                #print(f"ОШИБКА при сохранении: {str(e)}")
                traceback.print_exc()
                messages.error(request, f'Ошибка при сохранении: {str(e)}')
        else:
            #print("Формы не валидны")
            messages.error(request, 'Исправьте ошибки в форме')

            # В случае ошибки валидации нужно подготовить формсеты для повторного отображения
            classes = SchoolClass.objects.filter(is_active=True)

            context = {
                'form': form,
                'movement_formset': movement_formset,
                'report': report,
                'step': 1,
                'total_steps': 5,
                'step_title': 'Основные данные и движение учеников',
                'classes': classes,
                'previous_report': previous_report,
                'is_prefilled': False,
                'is_quarter1': report.period.period_type == 'quarter1',
            }

            return render(request, 'reports/wizard/step1.html', context)

    else:
        # GET запрос - инициализация с существующими данными
        #print("\n--- Обработка GET запроса ---")

        # Если есть предыдущий отчет и текущий отчет пустой, предзаполняем
        if previous_report and report.total_students_end == 0 and not report.has_movement:
            #print("Предзаполняем данными из предыдущего отчета")

            # Предзаполняем основную форму
            form = TeacherReportForm(instance=report, prefix='main', initial={
                'total_students_end': previous_report.total_students_end,
                'has_movement': previous_report.has_movement
            })

            # Предзаполняем движение учеников
            movement_initial = []
            for movement in previous_report.movements.all():
                movement_data = {
                    'movement_type': movement.movement_type,
                    'student_name': movement.student_name,
                    'order_number': movement.order_number,
                    'order_date': movement.order_date,
                }
                if movement.movement_type == 'out':
                    movement_data.update({
                        'moved_to_another_class': movement.moved_to_another_class,
                        'moved_to_another_school': movement.moved_to_another_school,
                        'target_class': movement.target_class_id,
                        'target_school': movement.target_school,
                    })
                else:
                    movement_data.update({
                        'came_from_another_class': movement.came_from_another_class,
                        'came_from_another_school': movement.came_from_another_school,
                        'source_class': movement.source_class_id,
                        'source_school': movement.source_school,
                    })
                movement_initial.append(movement_data)

            movement_formset = StudentMovementFormSet(prefix='movement', initial=movement_initial)

        else:
            # Используем данные текущего отчета
            form = TeacherReportForm(instance=report, prefix='main')

            movement_initial = []
            for movement in report.movements.all():
                movement_data = {
                    'movement_type': movement.movement_type,
                    'student_name': movement.student_name,
                    'order_number': movement.order_number,
                    'order_date': movement.order_date,
                }
                if movement.movement_type == 'out':
                    movement_data.update({
                        'moved_to_another_class': movement.moved_to_another_class,
                        'moved_to_another_school': movement.moved_to_another_school,
                        'target_class': movement.target_class_id,
                        'target_school': movement.target_school,
                    })
                else:
                    movement_data.update({
                        'came_from_another_class': movement.came_from_another_class,
                        'came_from_another_school': movement.came_from_another_school,
                        'source_class': movement.source_class_id,
                        'source_school': movement.source_school,
                    })
                movement_initial.append(movement_data)

            movement_formset = StudentMovementFormSet(prefix='movement', initial=movement_initial)

    classes = SchoolClass.objects.filter(is_active=True)

    context = {
        'form': form,
        'movement_formset': movement_formset,
        'report': report,
        'step': 1,
        'total_steps': 5,
        'step_title': 'Основные данные и движение учеников',
        'classes': classes,
        'previous_report': previous_report,
        'is_prefilled': bool(previous_report and report.total_students_end == 0),
        'is_quarter1': report.period.period_type == 'quarter1',
    }

    return render(request, 'reports/wizard/step1.html', context)


# wizard_views.py - полная исправленная функция wizard_step2

@login_required
def wizard_step2(request, report_id):
    """Шаг 2: Семейное обучение и возрастные группы"""
    report = get_object_or_404(TeacherReport, id=report_id)

    #print(f"\n=== DEBUG wizard_step2 ===")
    #print(f"report.id: {report.id}")
    #print(f"report.period.period_type: {report.period.period_type}")

    # Проверка прав
    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    # Загружаем предыдущий утвержденный отчет
    previous_report = None

    # Для 1 четверти загружаем из начала года
    if report.period.period_type == 'quarter1':
        start_year_period = ReportPeriod.objects.filter(
            period_type='start_year',
            academic_year=report.period.academic_year,
            is_active=True
        ).first()

        if start_year_period:
            previous_report = TeacherReport.objects.filter(
                teacher=report.teacher,
                school_class=report.school_class,
                period=start_year_period,
                status='approved'
            ).select_related('family_education').prefetch_related(
                'age_groups',
                'family_education__students'
            ).first()

            # if previous_report:
            #     #print(f"Загружен отчет за начало года ID={previous_report.id}")
            #     if hasattr(previous_report, 'family_education'):
            #         #print(f"  - Семейное обучение: {previous_report.family_education}")
            #     #print(f"  - Возрастных групп: {previous_report.age_groups.count()}")

    # Для остальных периодов (кроме start_year) используем предыдущий период
    elif report.period.period_type not in ['start_year']:
        previous_report = get_previous_approved_report(
            report.teacher,
            report.school_class,
            report.period
        )

        # if previous_report:
        #     #print(f"Загружен предыдущий отчет ID={previous_report.id}")

    # Получаем форму для доступа к полю total_students_end
    form = TeacherReportForm(instance=report, prefix='main')

    if request.method == 'POST':
        #print("\n--- Обработка POST запроса шага 2 ---")
        #print(f"POST data: {request.POST}")

        family_education_form = FamilyEducationForm(request.POST, prefix='family',
                                                    instance=getattr(report, 'family_education', None))
        family_students_formset = FamilyEducationStudentFormSet(request.POST, prefix='family_students')
        age_groups_formset = StudentAgeGroupFormSet(request.POST, prefix='age')

        forms_valid = family_education_form.is_valid()
        forms_valid = forms_valid and family_students_formset.is_valid()
        forms_valid = forms_valid and age_groups_formset.is_valid()

        if forms_valid:
            #print("Формы валидны, начинаем сохранение...")
            try:
                with transaction.atomic():
                    # Сохраняем семейное обучение
                    if hasattr(report, 'family_education'):
                        report.family_education.students.all().delete()
                        report.family_education.delete()

                    family_education = family_education_form.save(commit=False)
                    family_education.report = report
                    family_education.save()

                    if family_education.has_family_education and family_education.count > 0:
                        saved_students = 0
                        for student_form in family_students_formset:
                            if student_form.cleaned_data and not student_form.cleaned_data.get('DELETE'):
                                if student_form.cleaned_data.get('full_name'):
                                    student = student_form.save(commit=False)
                                    student.family_education = family_education
                                    student.save()
                                    saved_students += 1
                        #print(f"Сохранено учеников на семейном обучении: {saved_students}")

                    # Сохраняем возрастные группы
                    report.age_groups.all().delete()
                    saved_age_groups = 0
                    for age_form in age_groups_formset:
                        if age_form.cleaned_data and not age_form.cleaned_data.get('DELETE'):
                            birth_year = age_form.cleaned_data.get('birth_year')
                            boys_count = age_form.cleaned_data.get('boys_count')
                            girls_count = age_form.cleaned_data.get('girls_count')

                            if birth_year or boys_count or girls_count:
                                age_group = age_form.save(commit=False)
                                age_group.report = report
                                age_group.save()
                                saved_age_groups += 1
                    #print(f"Сохранено возрастных групп: {saved_age_groups}")

                    messages.success(request, 'Шаг 2 сохранен')
                    request.session['wizard_step'] = 3
                    return redirect('wizard_step3', report_id=report.id)

            except Exception as e:
                #print(f"ОШИБКА при сохранении шага 2: {str(e)}")
                traceback.print_exc()
                messages.error(request, f'Ошибка при сохранении: {str(e)}')
        else:
            #print("Формы шага 2 не валидны")
            messages.error(request, 'Исправьте ошибки в форме')

            # В случае ошибки валидации нужно подготовить контекст для повторного отображения
            context = {
                'form': form,
                'family_education_form': family_education_form,
                'family_students_formset': family_students_formset,
                'age_groups_formset': age_groups_formset,
                'report': report,
                'step': 2,
                'total_steps': 5,
                'step_title': 'Семейное обучение и возрастные группы',
                'previous_report': previous_report,
                'is_prefilled': False,
                'is_quarter1': report.period.period_type == 'quarter1',
            }

            return render(request, 'reports/wizard/step2.html', context)

    else:
        # GET запрос - инициализация с существующими данными
        #print("\n--- Обработка GET запроса шага 2 ---")

        # Проверяем, нужно ли предзаполнить из предыдущего отчета
        if previous_report and not hasattr(report, 'family_education') and report.age_groups.count() == 0:
            #print("Предзаполняем данными из предыдущего отчета")

            # Семейное обучение
            if hasattr(previous_report, 'family_education') and previous_report.family_education:
                family_education_form = FamilyEducationForm(
                    prefix='family',
                    instance=previous_report.family_education
                )

                # Ученики на семейном обучении
                family_students_initial = []
                for student in previous_report.family_education.students.all():
                    family_students_initial.append({'full_name': student.full_name})
                family_students_formset = FamilyEducationStudentFormSet(
                    prefix='family_students',
                    initial=family_students_initial
                )
            else:
                family_education_form = FamilyEducationForm(prefix='family', instance=None)
                family_students_formset = FamilyEducationStudentFormSet(prefix='family_students', initial=[])

            # Возрастные группы
            age_groups_initial = []
            for age_group in previous_report.age_groups.all():
                age_groups_initial.append({
                    'birth_year': age_group.birth_year,
                    'boys_count': age_group.boys_count,
                    'girls_count': age_group.girls_count,
                })
            age_groups_formset = StudentAgeGroupFormSet(prefix='age', initial=age_groups_initial)

        else:
            # Используем данные текущего отчета
            family_education_form = FamilyEducationForm(prefix='family',
                                                        instance=getattr(report, 'family_education', None))

            family_students_initial = []
            if hasattr(report, 'family_education') and report.family_education:
                for student in report.family_education.students.all():
                    family_students_initial.append({'full_name': student.full_name})
            family_students_formset = FamilyEducationStudentFormSet(prefix='family_students',
                                                                    initial=family_students_initial)

            age_groups_initial = []
            for age_group in report.age_groups.all():
                age_groups_initial.append({
                    'birth_year': age_group.birth_year,
                    'boys_count': age_group.boys_count,
                    'girls_count': age_group.girls_count,
                })
            age_groups_formset = StudentAgeGroupFormSet(prefix='age', initial=age_groups_initial)

    context = {
        'form': form,
        'family_education_form': family_education_form,
        'family_students_formset': family_students_formset,
        'age_groups_formset': age_groups_formset,
        'report': report,
        'step': 2,
        'total_steps': 5,
        'step_title': 'Семейное обучение и возрастные группы',
        'previous_report': previous_report,
        'is_prefilled': bool(
            previous_report and not hasattr(report, 'family_education') and report.age_groups.count() == 0),
        'is_quarter1': report.period.period_type == 'quarter1',
    }

    return render(request, 'reports/wizard/step2.html', context)

# wizard_views.py - обновленный wizard_step3

# wizard_views.py - полная исправленная функция wizard_step3

@login_required
def wizard_step3(request, report_id):
    """Шаг 3: Дополнительные сведения"""
    report = get_object_or_404(TeacherReport, id=report_id)

    #print(f"\n=== DEBUG wizard_step3 для периода {report.period.period_type} ===")

    # Проверка прав
    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    # Получаем форму для доступа к полю total_students_end
    form = TeacherReportForm(instance=report, prefix='main')
    family_education_form = FamilyEducationForm(prefix='family', instance=getattr(report, 'family_education', None))

    # Загружаем предыдущий утвержденный отчет
    previous_report = None

    # Для 1 четверти загружаем из начала года
    if report.period.period_type == 'quarter1':
        start_year_period = ReportPeriod.objects.filter(
            period_type='start_year',
            academic_year=report.period.academic_year,
            is_active=True
        ).first()

        if start_year_period:
            previous_report = TeacherReport.objects.filter(
                teacher=report.teacher,
                school_class=report.school_class,
                period=start_year_period,
                status='approved'
            ).select_related(
                'health_groups', 'phys_ed_groups', 'special_needs'
            ).prefetch_related(
                'phys_ed_groups__exempt_students',
                'special_needs__students'
            ).first()

            # if previous_report:
            #     #print(f"Загружен отчет за начало года ID={previous_report.id}")
            #     if hasattr(previous_report, 'health_groups'):
            #         #print(f"  - Группы здоровья: {previous_report.health_groups}")
            #     if hasattr(previous_report, 'phys_ed_groups'):
            #         #print(f"  - Физкультурные группы: {previous_report.phys_ed_groups}")
            #     if hasattr(previous_report, 'special_needs'):
            #         #print(f"  - Спец. потребности: {previous_report.special_needs}")

    # Для остальных периодов (кроме start_year) используем предыдущий период
    elif report.period.period_type != 'start_year':
        previous_report = get_previous_approved_report(
            report.teacher,
            report.school_class,
            report.period
        )

        # if previous_report:
        #     #print(f"Загружен предыдущий отчет ID={previous_report.id}")

    if request.method == 'POST':
        #print("\n--- Обработка POST запроса шага 3 ---")
        #print(f"POST data: {request.POST}")

        health_form = HealthGroupForm(request.POST, prefix='health', instance=getattr(report, 'health_groups', None))
        phys_ed_form = PhysicalEducationGroupForm(request.POST, prefix='phys_ed',
                                                  instance=getattr(report, 'phys_ed_groups', None))
        exempt_students_formset = ExemptStudentFormSet(request.POST, prefix='exempt')
        special_needs_form = SpecialNeedsForm(request.POST, prefix='special',
                                              instance=getattr(report, 'special_needs', None))
        special_needs_students_formset = SpecialNeedsStudentFormSet(request.POST, prefix='special_students')

        #print(f"health_form.is_valid(): {health_form.is_valid()}")
        #print(f"phys_ed_form.is_valid(): {phys_ed_form.is_valid()}")
        #print(f"exempt_students_formset.is_valid(): {exempt_students_formset.is_valid()}")
        #print(f"special_needs_form.is_valid(): {special_needs_form.is_valid()}")
        #print(f"special_needs_students_formset.is_valid(): {special_needs_students_formset.is_valid()}")

        forms_valid = health_form.is_valid()
        forms_valid = forms_valid and phys_ed_form.is_valid()
        forms_valid = forms_valid and exempt_students_formset.is_valid()
        forms_valid = forms_valid and special_needs_form.is_valid()
        forms_valid = forms_valid and special_needs_students_formset.is_valid()

        if forms_valid:
            #print("Формы валидны, начинаем сохранение...")
            try:
                with transaction.atomic():
                    # Удаляем старые данные
                    if hasattr(report, 'health_groups'):
                        report.health_groups.delete()
                    if hasattr(report, 'phys_ed_groups'):
                        report.phys_ed_groups.exempt_students.all().delete()
                        report.phys_ed_groups.delete()
                    if hasattr(report, 'special_needs'):
                        report.special_needs.students.all().delete()
                        report.special_needs.delete()

                    # Сохраняем группы здоровья
                    health = health_form.save(commit=False)
                    health.report = report
                    health.save()
                    #print(f"Группы здоровья сохранены")

                    # Сохраняем физкультурные группы
                    phys_ed = phys_ed_form.save(commit=False)
                    phys_ed.report = report
                    phys_ed.save()
                    #print(f"Физкультурные группы сохранены")

                    # Сохраняем освобожденных учеников
                    if phys_ed.exempt_count > 0:
                        saved_exempt = 0
                        for exempt_form in exempt_students_formset:
                            if exempt_form.cleaned_data and not exempt_form.cleaned_data.get('DELETE'):
                                full_name = exempt_form.cleaned_data.get('full_name')
                                if full_name and full_name.strip():
                                    exempt = ExemptStudent(
                                        phys_ed_group=phys_ed,
                                        full_name=full_name.strip()
                                    )
                                    exempt.save()
                                    saved_exempt += 1
                                    #print(f"Сохранен освобожденный ученик: {full_name}")
                        #print(f"Сохранено освобожденных учеников: {saved_exempt}")
                    else:
                        phys_ed.exempt_students.all().delete()

                    # Сохраняем специальные потребности
                    special = special_needs_form.save(commit=False)
                    special.report = report
                    special.save()
                    #print(f"Сохранены специальные потребности")

                    # Сохраняем учеников особых категорий
                    if special_needs_students_formset.total_form_count() > 0:
                        saved_special = 0
                        for special_form in special_needs_students_formset:
                            if special_form.cleaned_data and not special_form.cleaned_data.get('DELETE'):
                                full_name = special_form.cleaned_data.get('full_name')
                                student_type = special_form.cleaned_data.get('student_type')

                                if full_name and full_name.strip() and student_type:
                                    special_student = SpecialNeedsStudent(
                                        special_needs=special,
                                        student_type=student_type,
                                        full_name=full_name.strip()
                                    )
                                    special_student.save()
                                    saved_special += 1
                                    #print(f"Сохранен специальный ученик: {full_name}, тип={student_type}")

                        #print(f"Сохранено специальных учеников: {saved_special}")

                    messages.success(request, 'Шаг 3 сохранен')
                    request.session['wizard_step'] = 4
                    return redirect('wizard_step4', report_id=report.id)

            except Exception as e:
                #print(f"ОШИБКА при сохранении шага 3: {str(e)}")
                traceback.print_exc()
                messages.error(request, f'Ошибка при сохранении: {str(e)}')
        else:
            #print("Формы шага 3 не валидны")
            messages.error(request, 'Исправьте ошибки в форме')

            # В случае ошибки валидации нужно подготовить контекст для повторного отображения
            context = {
                'form': form,
                'family_education_form': family_education_form,
                'health_form': health_form,
                'phys_ed_form': phys_ed_form,
                'exempt_students_formset': exempt_students_formset,
                'special_needs_form': special_needs_form,
                'special_needs_students_formset': special_needs_students_formset,
                'report': report,
                'step': 3,
                'total_steps': 5,
                'step_title': 'Дополнительные сведения',
                'previous_report': previous_report,
                'is_prefilled': False,
                'is_quarter1': report.period.period_type == 'quarter1',
            }

            return render(request, 'reports/wizard/step3.html', context)

    else:
        # GET запрос - инициализация с существующими данными
        #print("\n--- Обработка GET запроса шага 3 ---")

        # Проверяем, нужно ли предзаполнить из предыдущего отчета
        if previous_report and not hasattr(report, 'health_groups') and not hasattr(report, 'phys_ed_groups'):
            #print("Предзаполняем данными из предыдущего отчета")

            # Группы здоровья
            if hasattr(previous_report, 'health_groups') and previous_report.health_groups:
                health_form = HealthGroupForm(prefix='health', instance=previous_report.health_groups)
            else:
                health_form = HealthGroupForm(prefix='health', instance=None)

            # Физкультурные группы
            if hasattr(previous_report, 'phys_ed_groups') and previous_report.phys_ed_groups:
                phys_ed_form = PhysicalEducationGroupForm(prefix='phys_ed', instance=previous_report.phys_ed_groups)

                # Освобожденные ученики
                exempt_initial = []
                for student in previous_report.phys_ed_groups.exempt_students.all():
                    exempt_initial.append({'full_name': student.full_name})
                exempt_students_formset = ExemptStudentFormSet(prefix='exempt', initial=exempt_initial)
            else:
                phys_ed_form = PhysicalEducationGroupForm(prefix='phys_ed', instance=None)
                exempt_students_formset = ExemptStudentFormSet(prefix='exempt', initial=[])

            # Специальные потребности
            if hasattr(previous_report, 'special_needs') and previous_report.special_needs:
                special_needs_form = SpecialNeedsForm(prefix='special', instance=previous_report.special_needs)

                # Ученики особых категорий
                special_needs_initial = []
                for student in previous_report.special_needs.students.all():
                    special_needs_initial.append({
                        'student_type': student.student_type,
                        'full_name': student.full_name,
                    })
                special_needs_students_formset = SpecialNeedsStudentFormSet(
                    prefix='special_students',
                    initial=special_needs_initial
                )
            else:
                special_needs_form = SpecialNeedsForm(prefix='special', instance=None)
                special_needs_students_formset = SpecialNeedsStudentFormSet(prefix='special_students', initial=[])

        else:
            # Используем существующие данные отчета
            #print("Используем существующие данные отчета")

            health_form = HealthGroupForm(prefix='health', instance=getattr(report, 'health_groups', None))
            phys_ed_form = PhysicalEducationGroupForm(prefix='phys_ed',
                                                      instance=getattr(report, 'phys_ed_groups', None))

            exempt_initial = []
            if hasattr(report, 'phys_ed_groups') and report.phys_ed_groups:
                for student in report.phys_ed_groups.exempt_students.all():
                    exempt_initial.append({'full_name': student.full_name})
            exempt_students_formset = ExemptStudentFormSet(prefix='exempt', initial=exempt_initial)

            special_needs_form = SpecialNeedsForm(prefix='special', instance=getattr(report, 'special_needs', None))

            special_needs_initial = []
            if hasattr(report, 'special_needs') and report.special_needs:
                for student in report.special_needs.students.all():
                    special_needs_initial.append({
                        'student_type': student.student_type,
                        'full_name': student.full_name,
                    })
            special_needs_students_formset = SpecialNeedsStudentFormSet(prefix='special_students',
                                                                        initial=special_needs_initial)

    context = {
        'form': form,
        'family_education_form': family_education_form,
        'health_form': health_form,
        'phys_ed_form': phys_ed_form,
        'exempt_students_formset': exempt_students_formset,
        'special_needs_form': special_needs_form,
        'special_needs_students_formset': special_needs_students_formset,
        'report': report,
        'step': 3,
        'total_steps': 5,
        'step_title': 'Дополнительные сведения',
        'previous_report': previous_report,
        'is_prefilled': bool(previous_report and not hasattr(report, 'health_groups')),
        'is_quarter1': report.period.period_type == 'quarter1',
    }

    return render(request, 'reports/wizard/step3.html', context)


@login_required
def wizard_step4(request, report_id):
    """Шаг 4: Успеваемость (для всех периодов кроме начала года)"""
    report = get_object_or_404(TeacherReport, id=report_id)

    #print(f"\n=== DEBUG wizard_step4 для периода {report.period.period_type} ===")

    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    if report.period.period_type == 'start_year':
        return redirect('wizard_step5', report_id=report.id)

    form = TeacherReportForm(instance=report, prefix='main')

    previous_report = None
    if report.period.period_type not in ['start_year', 'quarter1']:
        previous_report = get_previous_approved_report(
            report.teacher,
            report.school_class,
            report.period
        )

        # if previous_report:
        #     #print(f"Загружен предыдущий отчет ID={previous_report.id} за период {previous_report.period.period_type}")

    if request.method == 'POST':
        #print("\n--- Обработка POST запроса шага 4 ---")
        #print(f"POST data: {request.POST}")

        academic_form = AcademicPerformanceForm(
            request.POST,
            prefix='academic',
            instance=getattr(report, 'academic_performance', None)
        )
        excellent_formset = ExcellentStudentFormSet(request.POST, prefix='excellent')
        one_four_formset = OneFourStudentFormSet(request.POST, prefix='one_four')
        one_three_formset = OneThreeStudentFormSet(request.POST, prefix='one_three')
        poor_formset = PoorStudentFormSet(request.POST, prefix='poor')
        not_attested_formset = NotAttestedStudentFormSet(request.POST, prefix='not_attested')

        if report.period.period_type == 'year':
            retained_formset = RetainedStudentFormSet(request.POST, prefix='retained')
            conditionally_formset = ConditionallyPromotedStudentFormSet(request.POST, prefix='conditionally')

        #print(f"academic_form.is_valid(): {academic_form.is_valid()}")
        # if not academic_form.is_valid():
        #     #print(f"Ошибки academic_form: {academic_form.errors}")

        forms_valid = academic_form.is_valid()
        forms_valid = forms_valid and excellent_formset.is_valid()
        forms_valid = forms_valid and one_four_formset.is_valid()
        forms_valid = forms_valid and one_three_formset.is_valid()
        forms_valid = forms_valid and poor_formset.is_valid()
        forms_valid = forms_valid and not_attested_formset.is_valid()

        if report.period.period_type == 'year':
            forms_valid = forms_valid and retained_formset.is_valid()
            forms_valid = forms_valid and conditionally_formset.is_valid()

        if forms_valid:
            #print("Формы валидны, начинаем сохранение...")
            try:
                with transaction.atomic():
                    if hasattr(report, 'academic_performance'):
                        perf = report.academic_performance
                        perf.excellent_students.all().delete()
                        perf.one_four_students.all().delete()
                        perf.one_three_students.all().delete()
                        perf.poor_students.all().delete()
                        perf.not_attested_students.all().delete()
                        if hasattr(perf, 'retained_students'):
                            perf.retained_students.all().delete()
                        if hasattr(perf, 'conditionally_promoted_students'):
                            perf.conditionally_promoted_students.all().delete()
                        perf.delete()

                    academic = academic_form.save(commit=False)
                    academic.report = report
                    academic.save()
                    #print(
                    #     f"Успеваемость сохранена: "
                    #     f"excellent={academic.excellent_count}, good={academic.good_count}"
                    # )

                    if academic.excellent_count > 0:
                        saved_count = 0
                        for excellent_form in excellent_formset:
                            if excellent_form.cleaned_data and not excellent_form.cleaned_data.get('DELETE'):
                                if excellent_form.cleaned_data.get('full_name'):
                                    excellent = excellent_form.save(commit=False)
                                    excellent.performance = academic
                                    excellent.save()
                                    saved_count += 1
                        #print(f"Сохранено отличников: {saved_count}")

                    if academic.one_four_count > 0:
                        saved_count = 0
                        for one_four_form in one_four_formset:
                            if one_four_form.cleaned_data and not one_four_form.cleaned_data.get('DELETE'):
                                if one_four_form.cleaned_data.get('full_name'):
                                    subject_choice = one_four_form.cleaned_data.get('subject_choice')
                                    custom_subject = one_four_form.cleaned_data.get('custom_subject')

                                    if subject_choice == 'other' and custom_subject:
                                        subject = custom_subject.strip()
                                        subject_code = 'other'
                                    elif subject_choice:
                                        subject_dict = dict(settings.SCHOOL_SUBJECTS)
                                        subject = subject_dict.get(subject_choice, '')
                                        subject_code = subject_choice
                                    else:
                                        subject = ''
                                        subject_code = ''

                                    one_four = one_four_form.save(commit=False)
                                    one_four.performance = academic
                                    one_four.subject = subject
                                    one_four.subject_code = subject_code
                                    one_four.save()
                                    saved_count += 1
                        #print(f"Сохранено учеников с одной 4: {saved_count}")

                    if academic.one_three_count > 0:
                        saved_count = 0
                        for one_three_form in one_three_formset:
                            if one_three_form.cleaned_data and not one_three_form.cleaned_data.get('DELETE'):
                                if one_three_form.cleaned_data.get('full_name'):
                                    subject_choice = one_three_form.cleaned_data.get('subject_choice')
                                    custom_subject = one_three_form.cleaned_data.get('custom_subject')

                                    if subject_choice == 'other' and custom_subject:
                                        subject = custom_subject.strip()
                                        subject_code = 'other'
                                    elif subject_choice:
                                        subject_dict = dict(settings.SCHOOL_SUBJECTS)
                                        subject = subject_dict.get(subject_choice, '')
                                        subject_code = subject_choice
                                    else:
                                        subject = ''
                                        subject_code = ''

                                    one_three = one_three_form.save(commit=False)
                                    one_three.performance = academic
                                    one_three.subject = subject
                                    one_three.subject_code = subject_code
                                    one_three.save()
                                    saved_count += 1
                        #print(f"Сохранено учеников с одной 3: {saved_count}")

                    if academic.poor_count > 0:
                        saved_count = 0
                        for poor_form in poor_formset:
                            if poor_form.cleaned_data and not poor_form.cleaned_data.get('DELETE'):
                                full_name = poor_form.cleaned_data.get('full_name')
                                if full_name:
                                    subject_choice = poor_form.cleaned_data.get('subject_choice')
                                    custom_subject = poor_form.cleaned_data.get('custom_subject')

                                    if subject_choice == 'other' and custom_subject:
                                        subject = custom_subject.strip()
                                        subject_code = 'other'
                                    elif subject_choice:
                                        subject_dict = dict(settings.SCHOOL_SUBJECTS)
                                        subject = subject_dict.get(subject_choice, '')
                                        subject_code = subject_choice
                                    else:
                                        subject = ''
                                        subject_code = ''

                                    is_recurring = check_recurring_poor_student(
                                        full_name=full_name,
                                        school_class=report.school_class,
                                        current_period=report.period,
                                        subject_code=subject_code,
                                    )

                                    poor = poor_form.save(commit=False)
                                    poor.performance = academic
                                    poor.subject = subject
                                    poor.subject_code = subject_code
                                    poor.is_recurring = is_recurring
                                    poor.save()
                                    saved_count += 1

                                    # if is_recurring:
                                    #     #print(f"✓ Сквозной двоечник: {poor.full_name} - {subject}")

                        #print(f"Сохранено двоечников: {saved_count}")

                    if academic.not_attested_count > 0:
                        saved_count = 0
                        for not_attested_form in not_attested_formset:
                            if not_attested_form.cleaned_data and not not_attested_form.cleaned_data.get('DELETE'):
                                if not_attested_form.cleaned_data.get('full_name'):
                                    not_attested = not_attested_form.save(commit=False)
                                    not_attested.performance = academic
                                    not_attested.save()
                                    saved_count += 1
                        #print(f"Сохранено неаттестованных: {saved_count}")

                    if report.period.period_type == 'year':
                        if academic.retained_count > 0:
                            saved_count = 0
                            for retained_form in retained_formset:
                                if retained_form.cleaned_data and not retained_form.cleaned_data.get('DELETE'):
                                    if retained_form.cleaned_data.get('full_name'):
                                        retained = retained_form.save(commit=False)
                                        retained.performance = academic
                                        retained.save()
                                        saved_count += 1
                            #print(f"Сохранено оставленных на повторный год: {saved_count}")

                        if academic.conditionally_promoted_count > 0:
                            saved_count = 0
                            for conditionally_form in conditionally_formset:
                                if conditionally_form.cleaned_data and not conditionally_form.cleaned_data.get('DELETE'):
                                    if conditionally_form.cleaned_data.get('full_name'):
                                        conditionally = conditionally_form.save(commit=False)
                                        conditionally.performance = academic
                                        conditionally.save()
                                        saved_count += 1
                            #print(f"Сохранено переведенных условно: {saved_count}")

                    messages.success(request, 'Шаг 4 сохранен')
                    request.session['wizard_step'] = 5
                    return redirect('wizard_step5', report_id=report.id)

            except Exception as e:
                #print(f"ОШИБКА при сохранении шага 4: {str(e)}")
                traceback.print_exc()
                messages.error(request, f'Ошибка при сохранении: {str(e)}')
        else:
            #print("Формы шага 4 не валидны")
            messages.error(request, 'Исправьте ошибки в форме')

            context = {
                'form': form,
                'academic_form': academic_form,
                'excellent_formset': excellent_formset,
                'one_four_formset': one_four_formset,
                'one_three_formset': one_three_formset,
                'poor_formset': poor_formset,
                'not_attested_formset': not_attested_formset,
                'report': report,
                'step': 4,
                'total_steps': 5,
                'step_title': 'Успеваемость',
                'subjects': settings.SCHOOL_SUBJECTS,
                'previous_report': previous_report,
                'is_prefilled': False,
            }

            if report.period.period_type == 'year':
                context.update({
                    'retained_formset': retained_formset,
                    'conditionally_formset': conditionally_formset,
                    'is_year': True,
                })

            if report.period.period_type == 'year':
                template_name = 'reports/wizard/step4_year.html'
            elif report.period.period_type in ['half1', 'half2']:
                template_name = 'reports/wizard/step4_half.html'
            else:
                template_name = 'reports/wizard/step4_quarter.html'

            return render(request, template_name, context)

    else:
        #print("\n--- Обработка GET запроса шага 4 ---")

        if previous_report and not hasattr(report, 'academic_performance'):
            #print("Предзаполняем данными из предыдущего отчета")

            if hasattr(previous_report, 'academic_performance') and previous_report.academic_performance:
                perf = previous_report.academic_performance
                academic_form = AcademicPerformanceForm(prefix='academic', instance=perf)

                excellent_initial = []
                for student in perf.excellent_students.all():
                    excellent_initial.append({'full_name': student.full_name})
                excellent_formset = ExcellentStudentFormSet(prefix='excellent', initial=excellent_initial)

                one_four_initial = []
                for student in perf.one_four_students.all():
                    one_four_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                    })
                one_four_formset = OneFourStudentFormSet(prefix='one_four', initial=one_four_initial)

                one_three_initial = []
                for student in perf.one_three_students.all():
                    one_three_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                    })
                one_three_formset = OneThreeStudentFormSet(prefix='one_three', initial=one_three_initial)

                poor_initial = []
                for student in perf.poor_students.all():
                    poor_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                    })
                poor_formset = PoorStudentFormSet(prefix='poor', initial=poor_initial)

                not_attested_initial = []
                for student in perf.not_attested_students.all():
                    not_attested_initial.append({
                        'full_name': student.full_name,
                        'subjects': student.subjects,
                    })
                not_attested_formset = NotAttestedStudentFormSet(
                    prefix='not_attested',
                    initial=not_attested_initial
                )

                if report.period.period_type == 'year':
                    retained_initial = []
                    for student in perf.retained_students.all():
                        retained_initial.append({'full_name': student.full_name})
                    retained_formset = RetainedStudentFormSet(prefix='retained', initial=retained_initial)

                    conditionally_initial = []
                    for student in perf.conditionally_promoted_students.all():
                        conditionally_initial.append({'full_name': student.full_name})
                    conditionally_formset = ConditionallyPromotedStudentFormSet(
                        prefix='conditionally',
                        initial=conditionally_initial
                    )
            else:
                academic_form = AcademicPerformanceForm(prefix='academic', instance=None)
                excellent_formset = ExcellentStudentFormSet(prefix='excellent', initial=[])
                one_four_formset = OneFourStudentFormSet(prefix='one_four', initial=[])
                one_three_formset = OneThreeStudentFormSet(prefix='one_three', initial=[])
                poor_formset = PoorStudentFormSet(prefix='poor', initial=[])
                not_attested_formset = NotAttestedStudentFormSet(prefix='not_attested', initial=[])

                if report.period.period_type == 'year':
                    retained_formset = RetainedStudentFormSet(prefix='retained', initial=[])
                    conditionally_formset = ConditionallyPromotedStudentFormSet(
                        prefix='conditionally',
                        initial=[]
                    )
        else:
            #print("Используем данные текущего отчета")
            academic_form = AcademicPerformanceForm(
                prefix='academic',
                instance=getattr(report, 'academic_performance', None)
            )

            excellent_initial = []
            one_four_initial = []
            one_three_initial = []
            poor_initial = []
            not_attested_initial = []
            retained_initial = []
            conditionally_initial = []

            if hasattr(report, 'academic_performance') and report.academic_performance:
                perf = report.academic_performance

                for student in perf.excellent_students.all():
                    excellent_initial.append({'full_name': student.full_name})

                for student in perf.one_four_students.all():
                    one_four_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                    })

                for student in perf.one_three_students.all():
                    one_three_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                    })

                for student in perf.poor_students.all():
                    poor_initial.append({
                        'full_name': student.full_name,
                        'subject': student.subject,
                        'subject_code': student.subject_code,
                        'teacher': student.teacher,
                        'is_recurring': student.is_recurring,
                    })

                for student in perf.not_attested_students.all():
                    not_attested_initial.append({
                        'full_name': student.full_name,
                        'subjects': student.subjects,
                    })

                if report.period.period_type == 'year':
                    for student in perf.retained_students.all():
                        retained_initial.append({'full_name': student.full_name})

                    for student in perf.conditionally_promoted_students.all():
                        conditionally_initial.append({'full_name': student.full_name})

            excellent_formset = ExcellentStudentFormSet(prefix='excellent', initial=excellent_initial)
            one_four_formset = OneFourStudentFormSet(prefix='one_four', initial=one_four_initial)
            one_three_formset = OneThreeStudentFormSet(prefix='one_three', initial=one_three_initial)
            poor_formset = PoorStudentFormSet(prefix='poor', initial=poor_initial)
            not_attested_formset = NotAttestedStudentFormSet(
                prefix='not_attested',
                initial=not_attested_initial
            )

            if report.period.period_type == 'year':
                retained_formset = RetainedStudentFormSet(prefix='retained', initial=retained_initial)
                conditionally_formset = ConditionallyPromotedStudentFormSet(
                    prefix='conditionally',
                    initial=conditionally_initial
                )

    context = {
        'form': form,
        'academic_form': academic_form,
        'excellent_formset': excellent_formset,
        'one_four_formset': one_four_formset,
        'one_three_formset': one_three_formset,
        'poor_formset': poor_formset,
        'not_attested_formset': not_attested_formset,
        'report': report,
        'step': 4,
        'total_steps': 5,
        'step_title': 'Успеваемость',
        'subjects': settings.SCHOOL_SUBJECTS,
        'previous_report': previous_report,
        'is_prefilled': bool(previous_report and not hasattr(report, 'academic_performance')),
    }

    if report.period.period_type == 'year':
        context.update({
            'retained_formset': retained_formset,
            'conditionally_formset': conditionally_formset,
            'is_year': True,
        })

    if report.period.period_type == 'year':
        template_name = 'reports/wizard/step4_year.html'
    elif report.period.period_type in ['half1', 'half2']:
        template_name = 'reports/wizard/step4_half.html'
    else:
        template_name = 'reports/wizard/step4_quarter.html'

    return render(request, template_name, context)


@login_required
def wizard_step5(request, report_id):
    """Шаг 5: Завершение и просмотр"""
    report = get_object_or_404(TeacherReport, id=report_id)

    # Проверка прав
    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    # Очищаем данные сессии
    if 'wizard_report_id' in request.session:
        del request.session['wizard_report_id']
    if 'wizard_step' in request.session:
        del request.session['wizard_step']

    return render(request, 'reports/wizard/step5.html', {'report': report})


@login_required
def wizard_cancel(request, report_id):
    """Отмена и возврат к дашборду"""
    report = get_object_or_404(TeacherReport, id=report_id)

    # Проверка прав
    if request.user.is_teacher():
        try:
            teacher = Teacher.objects.get(user=request.user)
            if report.teacher != teacher:
                messages.error(request, 'Доступ запрещен')
                return redirect('dashboard')
        except Teacher.DoesNotExist:
            messages.error(request, 'Профиль учителя не найден')
            return redirect('dashboard')

    if 'wizard_report_id' in request.session:
        del request.session['wizard_report_id']
    if 'wizard_step' in request.session:
        del request.session['wizard_step']

    messages.info(request, 'Заполнение отчета отменено')
    return redirect('dashboard')