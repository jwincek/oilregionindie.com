/**
 * Alpine.js searchable select components.
 * Registered via alpine:init to ensure availability before DOM processing.
 */
document.addEventListener('alpine:init', function() {

    // Single-select searchable dropdown (used in directory filters)
    Alpine.data('searchableSelect', function(config) {
        return {
            search: '',
            open: false,
            selectedLabel: config.selectedLabel || '',
            selectedValue: config.selectedValue || '',

            get filtered() {
                if (!this.search) return config.options;
                var q = this.search.toLowerCase();
                return config.options.filter(function(o) {
                    return o.label.toLowerCase().indexOf(q) !== -1;
                });
            },

            select: function(value, label) {
                this.selectedValue = value;
                this.selectedLabel = label;
                this.search = '';
                this.open = false;
                this.$refs.hiddenInput.value = value;
                this.$refs.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
            },

            clear: function() {
                this.selectedValue = '';
                this.selectedLabel = '';
                this.search = '';
                this.$refs.hiddenInput.value = '';
                this.$refs.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        };
    });

    // Multi-select searchable input (used in profile forms)
    Alpine.data('multiSelect', function(config) {
        return {
            search: '',
            open: false,
            selectedValues: config.selectedValues || [],

            get filtered() {
                var self = this;
                var opts = config.allOptions.filter(function(o) {
                    return self.selectedValues.indexOf(o.value) === -1;
                });
                if (!this.search) return opts;
                var q = this.search.toLowerCase();
                return opts.filter(function(o) {
                    return o.label.toLowerCase().indexOf(q) !== -1;
                });
            },

            get selectedItems() {
                var self = this;
                return config.allOptions.filter(function(o) {
                    return self.selectedValues.indexOf(o.value) !== -1;
                });
            },

            get hasNoMatch() {
                return this.search.length > 1 && this.filtered.length === 0;
            },

            add: function(value) {
                if (this.selectedValues.indexOf(value) === -1) {
                    this.selectedValues.push(value);
                }
                this.search = '';
                this.syncHidden();
            },

            remove: function(value) {
                this.selectedValues = this.selectedValues.filter(function(v) {
                    return v !== value;
                });
                this.syncHidden();
            },

            syncHidden: function() {
                // Update the hidden checkboxes/select to match selectedValues
                var container = this.$refs.hiddenFields;
                if (container) {
                    var inputs = container.querySelectorAll('input[type=checkbox]');
                    var self = this;
                    inputs.forEach(function(input) {
                        input.checked = self.selectedValues.indexOf(input.value) !== -1;
                    });
                }
            }
        };
    });

});
