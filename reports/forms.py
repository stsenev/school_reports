# reports/forms.py
from django import forms
from django.forms import formset_factory
from django.conf import settings
from .models import *


class TeacherReportForm(forms.ModelForm):
    class Meta:
        model = TeacherReport
        fields = ['total_students_end', 'has_movement']
        widgets = {
            'total_students_end': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'has_movement': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StudentMovementForm(forms.ModelForm):
    class Meta:
        model = StudentMovement
        fields = ['movement_type', 'student_name', 'moved_to_another_class',
                 'moved_to_another_school', 'target_class', 'target_school',
                 'came_from_another_class', 'came_from_another_school',
                 'source_class', 'source_school', 'order_number', 'order_date']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-control'}),
            'student_name': forms.TextInput(attrs={'class': 'form-control'}),
            'moved_to_another_class': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'moved_to_another_school': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'target_class': forms.Select(attrs={'class': 'form-control'}),
            'target_school': forms.TextInput(attrs={'class': 'form-control'}),
            'came_from_another_class': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'came_from_another_school': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'source_class': forms.Select(attrs={'class': 'form-control'}),
            'source_school': forms.TextInput(attrs={'class': 'form-control'}),
            'order_number': forms.TextInput(attrs={'class': 'form-control'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_class'].queryset = SchoolClass.objects.filter(is_active=True)
        self.fields['source_class'].queryset = SchoolClass.objects.filter(is_active=True)
        self.fields['target_class'].required = False
        self.fields['source_class'].required = False
        self.fields['order_number'].required = False  # Делаем необязательным
        self.fields['order_date'].required = False    # Делаем необязательным

# reports/forms.py - обновленная форма FamilyEducationForm

class FamilyEducationForm(forms.ModelForm):
    class Meta:
        model = FamilyEducation
        fields = ['has_family_education', 'count']
        widgets = {
            'has_family_education': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'readonly': True,  # Делаем поле только для чтения
                'style': 'background-color: #e9ecef;'
            }),
        }
        labels = {
            'has_family_education': 'Есть ученики на семейном обучении',
            'count': 'Количество учеников',
        }
        help_texts = {
            'count': 'Количество автоматически обновляется при добавлении учеников',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Убеждаемся, что поле count только для чтения
        self.fields['count'].disabled = True
        self.fields['count'].required = False

class FamilyEducationStudentForm(forms.ModelForm):
    class Meta:
        model = FamilyEducationStudent
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class StudentAgeGroupForm(forms.ModelForm):
    class Meta:
        model = StudentAgeGroup
        fields = ['birth_year', 'boys_count', 'girls_count']
        widgets = {
            'birth_year': forms.NumberInput(attrs={'class': 'form-control', 'min': 2000, 'max': 2030}),
            'boys_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'girls_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Устанавливаем значения по умолчанию
        if not self.initial.get('boys_count'):
            self.initial['boys_count'] = 0
        if not self.initial.get('girls_count'):
            self.initial['girls_count'] = 0

        # Делаем поля необязательными, если форма пустая
        if not self.instance.pk and not self.data:
            self.fields['birth_year'].required = False
            self.fields['boys_count'].required = False
            self.fields['girls_count'].required = False

    def clean(self):
        cleaned_data = super().clean()
        birth_year = cleaned_data.get('birth_year')
        boys_count = cleaned_data.get('boys_count')
        girls_count = cleaned_data.get('girls_count')

        # Если все поля пустые или нулевые, не валидируем
        if not birth_year and (not boys_count or boys_count == 0) and (not girls_count or girls_count == 0):
            return {}

        # Если есть данные, проверяем обязательные поля
        if birth_year:
            if boys_count is None:
                self.add_error('boys_count', 'Обязательное поле.')
            if girls_count is None:
                self.add_error('girls_count', 'Обязательное поле.')
        else:
            self.add_error('birth_year', 'Обязательное поле.')

        return cleaned_data


class HealthGroupForm(forms.ModelForm):
    class Meta:
        model = HealthGroup
        fields = ['group1', 'group2', 'group3', 'group4', 'group5']
        widgets = {
            'group1': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'group2': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'group3': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'group4': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'group5': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
        }


class PhysicalEducationGroupForm(forms.ModelForm):
    class Meta:
        model = PhysicalEducationGroup
        fields = ['main_group', 'preparatory_group', 'special_group', 'exempt_count']
        widgets = {
            'main_group': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'preparatory_group': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'special_group': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'exempt_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
        }


class ExemptStudentForm(forms.ModelForm):
    class Meta:
        model = ExemptStudent
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SpecialNeedsForm(forms.ModelForm):
    class Meta:
        model = SpecialNeeds
        fields = ['disabled_count', 'special_needs_count', 'disabled_special_needs_count',
                  'home_schooling_count', 'home_schooling_disabled_count', 'foster_care_count']
        widgets = {
            'disabled_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'special_needs_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'disabled_special_needs_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'home_schooling_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'home_schooling_disabled_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'foster_care_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
        }


class SpecialNeedsStudentForm(forms.ModelForm):
    class Meta:
        model = SpecialNeedsStudent
        fields = ['student_type', 'full_name']
        widgets = {
            'student_type': forms.Select(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите ФИО ученика'}),
        }


class AcademicPerformanceForm(forms.ModelForm):
    class Meta:
        model = AcademicPerformance
        fields = ['excellent_count', 'good_count', 'one_four_count', 'one_three_count',
                  'poor_count', 'not_attested_count', 'retained_count', 'conditionally_promoted_count',
                  'days_missed', 'days_missed_illness', 'lessons_missed', 'lessons_missed_illness',
                  'injury_school', 'injury_outside']
        widgets = {
            'excellent_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'good_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'one_four_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'one_three_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'poor_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'not_attested_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'retained_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'conditionally_promoted_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'days_missed': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'days_missed_illness': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'lessons_missed': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'lessons_missed_illness': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'injury_school': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
            'injury_outside': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'value': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Делаем поля необязательными, так как они будут автоматически рассчитываться
        self.fields['excellent_count'].required = False
        self.fields['one_four_count'].required = False
        self.fields['one_three_count'].required = False
        self.fields['poor_count'].required = False
        self.fields['not_attested_count'].required = False

        # Для не-годовых отчетов делаем эти поля необязательными
        self.fields['retained_count'].required = False
        self.fields['conditionally_promoted_count'].required = False

class SubjectChoiceField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        super().__init__(choices=settings.SCHOOL_SUBJECTS, *args, **kwargs)


class OneFourStudentForm(forms.ModelForm):
    subject_choice = SubjectChoiceField(label='Предмет', required=False)
    custom_subject = forms.CharField(
        label='Другой предмет',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите название предмета'})
    )

    class Meta:
        model = OneFourStudent
        fields = ['full_name', 'subject', 'subject_code', 'teacher']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'subject': forms.HiddenInput(),
            'subject_code': forms.HiddenInput(),
            'teacher': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        subject_choice = cleaned_data.get('subject_choice')
        custom_subject = cleaned_data.get('custom_subject')

        if subject_choice == 'other' and custom_subject:
            cleaned_data['subject'] = custom_subject
            cleaned_data['subject_code'] = 'other'
        elif subject_choice and subject_choice != 'other':
            subject_dict = dict(settings.SCHOOL_SUBJECTS)
            cleaned_data['subject'] = subject_dict.get(subject_choice, '')
            cleaned_data['subject_code'] = subject_choice
        else:
            self.add_error('subject_choice', 'Выберите предмет или укажите свой')

        return cleaned_data


class OneThreeStudentForm(OneFourStudentForm):
    class Meta(OneFourStudentForm.Meta):
        model = OneThreeStudent


class PoorStudentForm(OneFourStudentForm):
    class Meta(OneFourStudentForm.Meta):
        model = PoorStudent


class ExcellentStudentForm(forms.ModelForm):
    class Meta:
        model = ExcellentStudent
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class NotAttestedStudentForm(forms.ModelForm):
    class Meta:
        model = NotAttestedStudent
        fields = ['full_name', 'subjects']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'subjects': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class RetainedStudentForm(forms.ModelForm):
    class Meta:
        model = RetainedStudent
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class ConditionallyPromotedStudentForm(forms.ModelForm):
    class Meta:
        model = ConditionallyPromotedStudent
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

class TeacherRegistrationForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        label='Логин',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Пароль'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Подтверждение пароля'
    )
    email = forms.EmailField(
        required=False,
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        label='Роль',
        initial='teacher',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    academic_year = forms.CharField(
        max_length=9,
        label='Учебный год',
        initial='2025/2026',
        help_text='Например: 2025/2026',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '2025/2026'})
    )
    homeroom_classes = forms.ModelMultipleChoiceField(
        queryset=SchoolClass.objects.filter(is_active=True).order_by('parallel', 'name'),
        required=False,
        label='Классы классного руководства',
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Teacher
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'full_name': 'ФИО',
        }

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        username = cleaned_data.get('username')
        academic_year = cleaned_data.get('academic_year')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Пароли не совпадают')

        if username and User.objects.filter(username=username).exists():
            self.add_error('username', 'Пользователь с таким логином уже существует')

        if academic_year:
            parts = academic_year.split('/')
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                self.add_error('academic_year', 'Формат учебного года должен быть, например: 2025/2026')
            else:
                start_year = int(parts[0])
                end_year = int(parts[1])
                if end_year != start_year + 1:
                    self.add_error('academic_year', 'Учебный год должен состоять из двух последовательных лет')

        return cleaned_data

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password'],
            email=self.cleaned_data.get('email', ''),
            role=self.cleaned_data['role']
        )

        teacher = super().save(commit=False)
        teacher.user = user

        if commit:
            teacher.save()

        return teacher


# Формсеты - изменен StudentAgeGroupFormSet с extra=0
StudentMovementFormSet = formset_factory(StudentMovementForm, extra=0, can_delete=True)
FamilyEducationStudentFormSet = formset_factory(FamilyEducationStudentForm, extra=0, can_delete=True)
StudentAgeGroupFormSet = formset_factory(StudentAgeGroupForm, extra=0, can_delete=True, min_num=0, validate_min=False)
ExemptStudentFormSet = formset_factory(ExemptStudentForm, extra=0, can_delete=True)
SpecialNeedsStudentFormSet = formset_factory(SpecialNeedsStudentForm, extra=0, can_delete=True)
ExcellentStudentFormSet = formset_factory(ExcellentStudentForm, extra=0, can_delete=True)
OneFourStudentFormSet = formset_factory(OneFourStudentForm, extra=0, can_delete=True)
OneThreeStudentFormSet = formset_factory(OneThreeStudentForm, extra=0, can_delete=True)
PoorStudentFormSet = formset_factory(PoorStudentForm, extra=0, can_delete=True)
NotAttestedStudentFormSet = formset_factory(NotAttestedStudentForm, extra=0, can_delete=True)
RetainedStudentFormSet = formset_factory(RetainedStudentForm, extra=0, can_delete=True)
ConditionallyPromotedStudentFormSet = formset_factory(ConditionallyPromotedStudentForm, extra=0, can_delete=True)