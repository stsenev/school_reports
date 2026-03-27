from django.db.models import Prefetch

from ..models import TeacherReport, PoorStudent


def normalize_text(value: str) -> str:
    """
    Нормализация текста для устойчивого сравнения:
    - trim
    - lowercase
    - ё -> е
    - схлопывание лишних пробелов
    """
    if not value:
        return ''
    return ' '.join(str(value).strip().lower().replace('ё', 'е').split())


def check_recurring_poor_student(full_name, school_class, current_period, subject_code):
    """
    Проверяет, является ли ученик сквозным двоечником.

    Сквозной двоечник = ученик, у которого уже была двойка
    по тому же предмету в любом утвержденном предыдущем периоде
    этого же учебного года, в этом же классе.

    Сравнение идет по:
    - ФИО
    - subject_code

    Текущий период исключается.
    """
    normalized_full_name = normalize_text(full_name)
    normalized_subject_code = normalize_text(subject_code)

    if not normalized_full_name or not normalized_subject_code:
        return False

    approved_reports = (
        TeacherReport.objects
        .filter(
            school_class=school_class,
            status='approved',
            period__academic_year=current_period.academic_year,
            period__is_active=True,
        )
        .exclude(period=current_period)
        .select_related('period')
        .prefetch_related(
            Prefetch(
                'academic_performance__poor_students',
                queryset=PoorStudent.objects.all()
            )
        )
    )

    for report in approved_reports:
        academic_performance = getattr(report, 'academic_performance', None)
        if not academic_performance:
            continue

        for student in academic_performance.poor_students.all():
            if (
                normalize_text(student.full_name) == normalized_full_name
                and normalize_text(student.subject_code) == normalized_subject_code
            ):
                return True

    return False