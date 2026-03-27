# reports/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import FamilyEducationStudent, FamilyEducation


@receiver(post_save, sender=FamilyEducationStudent)
@receiver(post_delete, sender=FamilyEducationStudent)
def update_family_education_count(sender, instance, **kwargs):
    """
    Сигнал для автоматического обновления поля count
    при добавлении или удалении ученика
    """
    family_education = instance.family_education
    if family_education:
        new_count = family_education.students.count()
        if family_education.count != new_count:
            family_education.count = new_count
            family_education.save(update_fields=['count'])


@receiver(post_save, sender=FamilyEducation)
def update_has_family_education(sender, instance, **kwargs):
    """
    Сигнал для автоматического обновления флага has_family_education
    """
    if instance.count > 0 and not instance.has_family_education:
        instance.has_family_education = True
        instance.save(update_fields=['has_family_education'])
    elif instance.count == 0 and instance.has_family_education:
        instance.has_family_education = False
        instance.save(update_fields=['has_family_education'])