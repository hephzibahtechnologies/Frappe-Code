// Global dd-MMM-yyyy (05-Nov-2026) support for the Frappe desk -- SBIQC Core.
(function () {
	"use strict";

	// The desk's calendar picker (air-datepicker) does not use moment's tokens: "M" is the
	// abbreviated month name, and a token only counts when it is a whole word between
	// separators. Frappe hands the picker the System Settings format unchanged, so
	// "dd-MMM-yyyy" would be written as "05-MMM-2026" and then fail to parse.
	// "dd-M-yyyy" is the picker's spelling of the same format. Every other format is
	// passed through exactly as it is.
	function to_picker_format(format) {
		if (typeof format !== "string") return format;
		return format.replace(/(^|[^A-Za-z])MMM(?![A-Za-z])/g, "$1M");
	}

	// Wraps set_date_options() of a date control so the picker gets the spelling above.
	// Controls that extend it and call super (Datetime) are covered by patching the base.
	function patch_date_control(ControlClass) {
		if (!ControlClass || !ControlClass.prototype) return;
		const proto = ControlClass.prototype;
		const original = proto.set_date_options;
		if (typeof original !== "function" || original.__sbiqc_core_patched) return;

		const patched = function () {
			const result = original.apply(this, arguments);
			if (this.datepicker_options && this.datepicker_options.dateFormat) {
				this.datepicker_options.dateFormat = to_picker_format(this.datepicker_options.dateFormat);
			}
			return result;
		};
		patched.__sbiqc_core_patched = true;
		proto.set_date_options = patched;
	}

	// Only two places in all installed apps hand the system format to a date picker:
	// the Date control (Datetime extends it) and the Date Range control.
	if (typeof frappe !== "undefined" && frappe.ui && frappe.ui.form) {
		patch_date_control(frappe.ui.form.ControlDate);
		patch_date_control(frappe.ui.form.ControlDateRange);
	}

	if (typeof module !== "undefined" && module.exports) {
		module.exports = { to_picker_format, patch_date_control };
	}
})();
