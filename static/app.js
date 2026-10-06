document.addEventListener("DOMContentLoaded", () => {
    const constraintController = document.querySelector("[data-constraint-controller]");
    if (constraintController) {
        const radios = constraintController.querySelectorAll('input[name="constraint_mode"]');
        const fields = constraintController.querySelectorAll("[data-mode-field]");

        const updateConstraint = () => {
            const selected = constraintController.querySelector('input[name="constraint_mode"]:checked')?.value;
            fields.forEach((field) => {
                const active = field.dataset.modeField === selected;
                field.hidden = !active;
                field.querySelectorAll("input").forEach((input) => {
                    input.disabled = !active;
                    input.required = active;
                });
            });
        };

        radios.forEach((radio) => radio.addEventListener("change", updateConstraint));
        updateConstraint();
    }

    const selector = document.querySelector("[data-product-selector]");
    if (selector) {
        const rows = [...selector.querySelectorAll("[data-product-row]")];
        const count = selector.querySelector("[data-selected-count]");

        const updateRow = (row) => {
            const checkbox = row.querySelector("[data-product-checkbox]");
            const minimum = row.querySelector("[data-min-input]");
            const maximum = row.querySelector("[data-max-input]");
            if (!checkbox || !minimum || !maximum) return;
            [minimum, maximum].forEach((input) => {
                input.disabled = !checkbox.checked;
                input.required = checkbox.checked;
            });
            row.classList.toggle("selected-product-row", checkbox.checked);
        };

        const validateRange = (row) => {
            const minimum = row.querySelector("[data-min-input]");
            const maximum = row.querySelector("[data-max-input]");
            if (!minimum || !maximum) return;
            const invalid = Number(minimum.value) > Number(maximum.value);
            minimum.setCustomValidity(invalid ? "O mínimo não pode ser maior que o máximo." : "");
        };

        const updateCount = () => {
            if (count) {
                count.textContent = rows.filter((row) => row.querySelector("[data-product-checkbox]")?.checked).length;
            }
        };

        rows.forEach((row) => {
            const checkbox = row.querySelector("[data-product-checkbox]");
            checkbox?.addEventListener("change", () => {
                updateRow(row);
                updateCount();
            });
            row.querySelectorAll("[data-min-input], [data-max-input]").forEach((input) => {
                input.addEventListener("input", () => validateRange(row));
            });
            updateRow(row);
            validateRange(row);
        });

        selector.querySelector("[data-select-all]")?.addEventListener("click", () => {
            const enabledRows = rows.filter((row) => !row.querySelector("[data-product-checkbox]")?.disabled);
            const shouldSelect = enabledRows.some((row) => !row.querySelector("[data-product-checkbox]")?.checked);
            enabledRows.forEach((row) => {
                row.querySelector("[data-product-checkbox]").checked = shouldSelect;
                updateRow(row);
            });
            updateCount();
        });
        updateCount();
    }
});
