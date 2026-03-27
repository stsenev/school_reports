# reports/forms.py

from typing import Optional, Dict, Any
from datetime import date, datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, HTML, Field
from crispy_forms.bootstrap import FormActions, PrependedText, AppendedText

from .models import Report, Subject, ClassGroup

User = get_user_model()


# ============================================================
# Кастомные виджеты
# ============================================================

class DatePickerInput(forms.DateInput):
    """
    Кастомный виджет для выбора даты с HTML5 date picker.
    """
    input_type = 'date'

    def __init__(self, attrs=None):
        default_attrs = {'class': 'form-control datepicker'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class RichTextarea(forms.Textarea):
    """
    Улучшенный текстовый виджет с поддержкой базового форматирования.
    """

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control rich-textarea',
            'rows': 4,
            'placeholder': 'Введите текст...',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


# ============================================================
# Базовый класс для всех форм с Crispy Forms
# ============================================================

class BaseCrispyForm(forms.Form):
    """
    Базовый класс для всех форм с настройками Crispy Forms.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = True
        self.helper.label_class = 'form-label fw-semibold'
        self.helper.field_class = 'mb-3'

        # Применяем класс form-control ко всем полям по умолчанию
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput,
                                         forms.NumberInput, forms.PasswordInput,
                                         forms.DateInput, forms.DateTimeInput,
                                         forms.Select, forms.SelectMultiple)):
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'form-control'

            # Добавляем placeholder из label
            if field.label and not field.widget.attrs.get('placeholder'):
                field.widget.attrs['placeholder'] = field.label


# ============================================================
# Форма отчета
# ============================================================

class ReportForm(BaseCrispyForm, forms.ModelForm):
    """
    Форма для создания и редактирования отчета.
    """

    # Дополнительные поля для удобства
    confirm_status = forms.BooleanField(
        required=False,
        label='Отправить на проверку',
        help_text='Отметьте, чтобы отправить отчет на проверку после сохранения',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = Report
        fields = ['subject', 'class_group', 'date', 'topic', 'homework', 'notes']
        widgets = {
            'date': DatePickerInput(),
            'topic': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Тема урока',
            }),
            'homework': RichTextarea(attrs={
                'rows': 3,
                'placeholder': 'Опишите домашнее задание...',
            }),
            'notes': RichTextarea(attrs={
                'rows': 3,
                'placeholder': 'Дополнительные заметки...',
            }),
        }

    def __init__(self, *args, **kwargs):
        # Извлекаем пользователя, если передан
        self.user = kwargs.pop('user', None)
        self.is_update = kwargs.pop('is_update', False)

        super().__init__(*args, **kwargs)

        # Настройка Crispy Layout
        self.helper.layout = Layout(
            Row(
                Column('subject', css_class='col-md-6'),
                Column('class_group', css_class='col-md-6'),
                css_class='row'
            ),
            Row(
                Column('date', css_class='col-md-6'),
                css_class='row'
            ),
            'topic',
            'homework',
            'notes',
            HTML("""
                <div class="alert alert-info small mt-2">
                    <i class="fas fa-info-circle"></i> 
                    После создания отчет можно будет отправить на проверку или сохранить как черновик.
                </div>
            """),
            FormActions(
                Submit('submit', 'Сохранить', css_class='btn-primary'),
                HTML('<a href="{% url "reports:report_list" %}" class="btn btn-secondary">Отмена</a>'),
                css_class='mt-3'
            )
        )

        # Ограничиваем выбор классов для учителя (если не админ)
        if self.user and not self.user.is_superuser:
            # Учитель может выбирать только свои классы
            self.fields['class_group'].queryset = ClassGroup.objects.filter(
                class_teacher=self.user
            )

        # Добавляем пустую опцию для полей с выбором
        if not self.instance.pk:
            self.fields['subject'].empty_label = 'Выберите предмет'
            self.fields['class_group'].empty_label = 'Выберите класс'

    def clean_date(self):
        """
        Валидация даты: нельзя создавать отчеты на будущие даты.
        """
        report_date = self.cleaned_data.get('date')
        if report_date and report_date > timezone.now().date():
            raise ValidationError('Нельзя создавать отчеты на будущие даты.')
        return report_date

    def clean_topic(self):
        """
        Валидация темы: минимальная длина.
        """
        topic = self.cleaned_data.get('topic', '').strip()
        if len(topic) < 3:
            raise ValidationError('Тема урока должна содержать минимум 3 символа.')
        if len(topic) > 200:
            raise ValidationError('Тема урока не должна превышать 200 символов.')
        return topic

    def clean(self):
        """
        Общая валидация формы.
        """
        cleaned_data = super().clean()

        # Проверка на дублирование: нельзя создать два отчета за один день
        # по одному предмету и классу
        if not self.is_update:
            subject = cleaned_data.get('subject')
            class_group = cleaned_data.get('class_group')
            report_date = cleaned_data.get('date')

            if subject and class_group and report_date:
                existing_report = Report.objects.filter(
                    subject=subject,
                    class_group=class_group,
                    date=report_date,
                    teacher=self.user
                ).exclude(pk=self.instance.pk if self.instance.pk else None)

                if existing_report.exists():
                    raise ValidationError(
                        f'Отчет по предмету "{subject}" для класса "{class_group}" '
                        f'за {report_date.strftime("%d.%m.%Y")} уже существует.'
                    )

        return cleaned_data

    def save(self, commit=True):
        """
        Сохранение формы с дополнительной логикой.
        """
        instance = super().save(commit=False)

        if commit:
            instance.save()

            # Если отмечена отправка на проверку, меняем статус
            if self.cleaned_data.get('confirm_status'):
                instance.status = 'submitted'
                instance.save()

        return instance


# ============================================================
# Форма фильтрации отчетов
# ============================================================

class ReportFilterForm(BaseCrispyForm):
    """
    Форма для фильтрации списка отчетов.
    """

    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        required=False,
        label='Предмет',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class_group = forms.ModelChoiceField(
        queryset=ClassGroup.objects.all(),
        required=False,
        label='Класс',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    status = forms.ChoiceField(
        choices=[('', 'Все')] + list(Report.STATUS_CHOICES),
        required=False,
        label='Статус',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    date_from = forms.DateField(
        required=False,
        label='Дата от',
        widget=DatePickerInput()
    )

    date_to = forms.DateField(
        required=False,
        label='Дата до',
        widget=DatePickerInput()
    )

    teacher = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name='teachers'),
        required=False,
        label='Учитель',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # Настройка Crispy Layout для фильтров
        self.helper.form_method = 'get'
        self.helper.form_tag = True
        self.helper.layout = Layout(
            Row(
                Column('subject', css_class='col-md-3'),
                Column('class_group', css_class='col-md-3'),
                Column('status', css_class='col-md-3'),
                css_class='row'
            ),
            Row(
                Column('date_from', css_class='col-md-3'),
                Column('date_to', css_class='col-md-3'),
                Column('teacher', css_class='col-md-3'),
                css_class='row'
            ),
            Row(
                Column(
                    HTML("""
                        <div class="d-flex gap-2 mt-3">
                            <button type="submit" class="btn btn-primary">
                                <i class="fas fa-filter"></i> Применить
                            </button>
                            <a href="{% url 'reports:report_list' %}" class="btn btn-secondary">
                                <i class="fas fa-undo"></i> Сбросить
                            </a>
                        </div>
                    """),
                    css_class='col-12'
                )
            )
        )

        # Если пользователь не админ, убираем фильтр по учителю
        if self.user and not self.user.is_superuser:
            self.fields.pop('teacher', None)

        # Сортировка выпадающих списков
        self.fields['subject'].queryset = Subject.objects.all().order_by('name')
        self.fields['class_group'].queryset = ClassGroup.objects.all().order_by('name')

    def clean(self):
        """
        Валидация диапазона дат.
        """
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')

        if date_from and date_to and date_from > date_to:
            raise ValidationError('Дата "от" не может быть позже даты "до".')

        return cleaned_data


# ============================================================
# Форма быстрого создания отчета (минимальная версия)
# ============================================================

class QuickReportForm(BaseCrispyForm, forms.ModelForm):
    """
    Упрощенная форма для быстрого создания отчета.
    Используется на дашборде или в виджетах.
    """

    class Meta:
        model = Report
        fields = ['subject', 'class_group', 'topic']
        widgets = {
            'topic': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Тема урока',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            'subject',
            'class_group',
            'topic',
            FormActions(
                Submit('submit', 'Быстрый отчет', css_class='btn-success btn-sm'),
                css_class='mt-2'
            )
        )

        if self.user and not self.user.is_superuser:
            self.fields['class_group'].queryset = ClassGroup.objects.filter(
                class_teacher=self.user
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.teacher = self.user
        instance.date = timezone.now().date()

        if commit:
            instance.save()

        return instance


# ============================================================
# Форма массового импорта отчетов
# ============================================================

class BulkReportImportForm(forms.Form):
    """
    Форма для массового импорта отчетов из CSV/Excel.
    """

    csv_file = forms.FileField(
        label='CSV файл',
        help_text='Загрузите CSV файл с отчетами. Формат: дата, предмет, класс, тема, дз, примечания',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv,.xlsx'
        })
    )

    override_existing = forms.BooleanField(
        required=False,
        label='Перезаписывать существующие отчеты',
        help_text='Если отмечено, существующие отчеты за ту же дату будут заменены',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.enctype = 'multipart/form-data'
        self.helper.layout = Layout(
            'csv_file',
            'override_existing',
            HTML("""
                <div class="alert alert-info mt-3">
                    <strong>Инструкция по импорту:</strong>
                    <ol class="mb-0 mt-2">
                        <li>Скачайте <a href="{% url 'reports:export_template' %}">шаблон CSV</a></li>
                        <li>Заполните файл данными</li>
                        <li>Загрузите файл с помощью формы выше</li>
                    </ol>
                </div>
            """),
            FormActions(
                Submit('submit', 'Импортировать', css_class='btn-primary'),
                HTML('<a href="{% url "reports:report_list" %}" class="btn btn-secondary">Отмена</a>'),
                css_class='mt-3'
            )
        )

    def clean_csv_file(self):
        """
        Валидация загруженного файла.
        """
        csv_file = self.cleaned_data.get('csv_file')

        if csv_file:
            # Проверка размера файла (макс 5 МБ)
            if csv_file.size > 5 * 1024 * 1024:
                raise ValidationError('Размер файла не должен превышать 5 МБ.')

            # Проверка расширения
            file_name = csv_file.name.lower()
            if not (file_name.endswith('.csv') or file_name.endswith('.xlsx')):
                raise ValidationError('Поддерживаются только файлы форматов CSV и XLSX.')

        return csv_file


# ============================================================
# Форма для статистики (выбор периода)
# ============================================================

class StatisticsFilterForm(BaseCrispyForm):
    """
    Форма для выбора периода статистики.
    """

    PERIOD_CHOICES = [
        ('week', 'Последняя неделя'),
        ('month', 'Последний месяц'),
        ('quarter', 'Последний квартал'),
        ('year', 'Последний год'),
        ('custom', 'Произвольный период'),
    ]

    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        initial='month',
        label='Период',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    date_from = forms.DateField(
        required=False,
        label='Дата от',
        widget=DatePickerInput()
    )

    date_to = forms.DateField(
        required=False,
        label='Дата до',
        widget=DatePickerInput()
    )

    teacher = forms.ModelChoiceField(
        queryset=User.objects.filter(groups__name='teachers'),
        required=False,
        label='Учитель',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            Row(
                Column('period', css_class='col-md-4'),
                Column('date_from', css_class='col-md-4'),
                Column('date_to', css_class='col-md-4'),
                css_class='row'
            ),
            Row(
                Column('teacher', css_class='col-md-6'),
                css_class='row'
            ),
            FormActions(
                Submit('submit', 'Показать статистику', css_class='btn-primary'),
                css_class='mt-3'
            )
        )

        if self.user and not self.user.is_superuser:
            self.fields.pop('teacher', None)

    def clean(self):
        cleaned_data = super().clean()
        period = cleaned_data.get('period')
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')

        if period == 'custom':
            if not date_from:
                self.add_error('date_from', 'Укажите начальную дату')
            if not date_to:
                self.add_error('date_to', 'Укажите конечную дату')
            if date_from and date_to and date_from > date_to:
                raise ValidationError('Дата "от" не может быть позже даты "до".')

        return cleaned_data

    def get_date_range(self):
        """
        Возвращает кортеж (date_from, date_to) на основе выбранного периода.
        """
        period = self.cleaned_data.get('period')
        today = timezone.now().date()

        if period == 'week':
            return (today - timedelta(days=7), today)
        elif period == 'month':
            return (today - timedelta(days=30), today)
        elif period == 'quarter':
            return (today - timedelta(days=90), today)
        elif period == 'year':
            return (today - timedelta(days=365), today)
        elif period == 'custom':
            return (self.cleaned_data.get('date_from'), self.cleaned_data.get('date_to'))

        return (None, None)


# ============================================================
# Форма для обратной связи
# ============================================================

class FeedbackForm(BaseCrispyForm):
    """
    Форма для отправки обратной связи.
    """

    name = forms.CharField(
        max_length=100,
        label='Ваше имя',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    email = forms.EmailField(
        label='Email для ответа',
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    subject = forms.CharField(
        max_length=200,
        label='Тема',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    message = forms.CharField(
        label='Сообщение',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Опишите ваш вопрос или предложение...'
        })
    )

    rating = forms.ChoiceField(
        choices=[(i, f'{i} ★') for i in range(1, 6)],
        label='Оценка',
        widget=forms.RadioSelect(attrs={'class': 'form-check-inline'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper.layout = Layout(
            Row(
                Column('name', css_class='col-md-6'),
                Column('email', css_class='col-md-6'),
                css_class='row'
            ),
            'subject',
            'message',
            'rating',
            FormActions(
                Submit('submit', 'Отправить', css_class='btn-primary'),
                css_class='mt-3'
            )
        )