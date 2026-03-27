from django.db.models import Prefetch

from ..models import SchoolClass, Teacher, TeacherClassAssignment


def replace_teacher_assignments_for_year(*, teacher, academic_year, class_ids):
    TeacherClassAssignment.objects.filter(
        teacher=teacher,
        academic_year=academic_year
    ).delete()

    classes = SchoolClass.objects.filter(
        id__in=class_ids,
        is_active=True
    ).order_by('parallel', 'name')

    assignments = [
        TeacherClassAssignment(
            teacher=teacher,
            school_class=school_class,
            academic_year=academic_year,
            is_active=True,
        )
        for school_class in classes
    ]

    if assignments:
        TeacherClassAssignment.objects.bulk_create(assignments)

    return assignments


def sync_legacy_homeroom_classes(teacher, academic_year):
    current_classes = SchoolClass.objects.filter(
        teacher_assignments__teacher=teacher,
        teacher_assignments__academic_year=academic_year,
        teacher_assignments__is_active=True,
        is_active=True,
    ).distinct()

    teacher.homeroom_classes.set(current_classes)


def get_teacher_assignment_ids_for_year(teacher, academic_year):
    return list(
        TeacherClassAssignment.objects.filter(
            teacher=teacher,
            academic_year=academic_year,
            is_active=True
        ).values_list('school_class_id', flat=True)
    )


def get_teacher_rows_for_year(academic_year):
    assignments_qs = TeacherClassAssignment.objects.filter(
        academic_year=academic_year,
        is_active=True,
        school_class__is_active=True,
    ).select_related('school_class')

    teachers = Teacher.objects.select_related('user').prefetch_related(
        Prefetch(
            'class_assignments',
            queryset=assignments_qs,
            to_attr='current_year_assignments'
        )
    ).order_by('full_name')

    teacher_rows = []
    with_class = 0

    for teacher in teachers:
        assignments = getattr(teacher, 'current_year_assignments', [])
        class_names = [assignment.school_class.name for assignment in assignments]

        if class_names:
            with_class += 1

        teacher_rows.append({
            'teacher': teacher,
            'assignments': assignments,
            'class_names': class_names,
        })

    total_teachers = len(teacher_rows)
    without_class = total_teachers - with_class

    return {
        'teacher_rows': teacher_rows,
        'total_teachers': total_teachers,
        'with_class': with_class,
        'without_class': without_class,
    }


def get_teacher_classes_for_year(teacher, academic_year):
    return SchoolClass.objects.filter(
        teacher_assignments__teacher=teacher,
        teacher_assignments__academic_year=academic_year,
        teacher_assignments__is_active=True,
        is_active=True,
    ).distinct().order_by('parallel', 'name')