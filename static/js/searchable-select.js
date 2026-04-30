/**
 * Alpine.js searchable select component.
 *
 * Usage:
 *   {% include "includes/_searchable_select.html" with name="skill" label="Skill" options=available_skills option_value="slug" option_label="name" current=current_skill placeholder="Type to filter..." %}
 *
 * Renders a text input that filters a dropdown list of options.
 * Selecting an option sets a hidden input value and triggers HTMX.
 */
document.addEventListener('alpine:init', () => {
    Alpine.data('searchableSelect', (config) => ({
        search: '',
        open: false,
        selectedLabel: config.selectedLabel || '',
        selectedValue: config.selectedValue || '',

        get filtered() {
            if (!this.search) return config.options;
            const q = this.search.toLowerCase();
            return config.options.filter(o => o.label.toLowerCase().includes(q));
        },

        select(value, label) {
            this.selectedValue = value;
            this.selectedLabel = label;
            this.search = '';
            this.open = false;
            // Update the hidden input and trigger HTMX
            this.$refs.hiddenInput.value = value;
            this.$refs.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        },

        clear() {
            this.selectedValue = '';
            this.selectedLabel = '';
            this.search = '';
            this.$refs.hiddenInput.value = '';
            this.$refs.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        },
    }));
});
