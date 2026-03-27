// Обработка выбора предметов
document.addEventListener('DOMContentLoaded', function() {
    // Обработка изменения выбора предмета
    document.addEventListener('change', function(e) {
        if (e.target.matches('select[name$="-subject_choice"]')) {
            const row = e.target.closest('.dynamic-formset');
            const customRow = row.querySelector('.custom-subject-row');
            const subjectInput = row.querySelector('input[name$="-subject"]');
            const subjectCodeInput = row.querySelector('input[name$="-subject_code"]');

            if (e.target.value === 'other') {
                customRow.style.display = 'block';
                subjectInput.value = '';
                subjectCodeInput.value = 'other';
            } else {
                customRow.style.display = 'none';
                const selectedOption = e.target.options[e.target.selectedIndex];
                subjectInput.value = selectedOption.text;
                subjectCodeInput.value = e.target.value;

                const customInput = row.querySelector('input[name$="-custom_subject"]');
                if (customInput) customInput.value = '';
            }
        }

        if (e.target.matches('input[name$="-custom_subject"]')) {
            const row = e.target.closest('.dynamic-formset');
            const subjectInput = row.querySelector('input[name$="-subject"]');
            subjectInput.value = e.target.value;
        }
    });
});

function addStudentWithSubjectRow(prefix) {
    const container = document.getElementById(`${prefix}-students`);
    const index = Date.now();
    const subjects = window.subjects || [];

    let subjectOptions = '<option value="">---------</option>';
    subjects.forEach(subj => {
        subjectOptions += `<option value="${subj[0]}">${subj[1]}</option>`;
    });

    const template = `
        <div class="dynamic-formset ${prefix}-row card mb-2 p-2">
            <div class="mb-3">
                <label class="form-label">ФИО ученика</label>
                <input type="text" name="${prefix}-${index}-full_name" class="form-control">
            </div>

            <div class="row">
                <div class="col-md-8">
                    <div class="mb-3">
                        <label class="form-label">Предмет</label>
                        <select name="${prefix}-${index}-subject_choice" class="form-select">
                            ${subjectOptions}
                        </select>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="mb-3">
                        <label class="form-label">Учитель</label>
                        <input type="text" name="${prefix}-${index}-teacher" class="form-control">
                    </div>
                </div>
            </div>

            <div class="row custom-subject-row" style="display: none;">
                <div class="col-12">
                    <div class="mb-3">
                        <label class="form-label">Другой предмет (укажите)</label>
                        <input type="text" name="${prefix}-${index}-custom_subject" class="form-control">
                    </div>
                </div>
            </div>

            <input type="hidden" name="${prefix}-${index}-subject">
            <input type="hidden" name="${prefix}-${index}-subject_code">

            <div class="text-end">
                <button type="button" class="btn btn-danger btn-sm remove-row">
                    <i class="fas fa-trash"></i> Удалить
                </button>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', template);
}

function updateManagementForm(containerId, formsetPrefix) {
    const container = document.getElementById(containerId);
    const totalForms = container.querySelectorAll('.dynamic-formset').length;
    const managementInput = document.querySelector(`#id_${formsetPrefix}-TOTAL_FORMS`);
    if (managementInput) {
        managementInput.value = totalForms;
    }
}