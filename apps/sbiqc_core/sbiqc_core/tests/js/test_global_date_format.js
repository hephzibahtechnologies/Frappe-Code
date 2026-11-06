// Run with:  node --test apps/sbiqc_core/sbiqc_core/tests/js/
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { to_picker_format, patch_date_control } = require(path.join(
	__dirname,
	"..",
	"..",
	"public",
	"js",
	"global_date_format.js"
));

test("dd-MMM-yyyy becomes the date picker's short-month spelling", () => {
	assert.equal(to_picker_format("dd-MMM-yyyy"), "dd-M-yyyy");
	assert.equal(to_picker_format("dd-MMM-yyyy HH:mm:ss"), "dd-M-yyyy HH:mm:ss");
	assert.equal(to_picker_format("MMM dd, yyyy"), "M dd, yyyy");
});

test("every existing format is left exactly as it is", () => {
	for (const format of ["yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy", "dd.mm.yyyy", "mm/dd/yyyy", "mm-dd-yyyy"]) {
		assert.equal(to_picker_format(format), format);
	}
});

test("longer month tokens and non-strings are not touched", () => {
	assert.equal(to_picker_format("dd MMMM yyyy"), "dd MMMM yyyy");
	assert.equal(to_picker_format(undefined), undefined);
	assert.equal(to_picker_format(null), null);
});

class FakeDate {
	set_date_options() {
		this.datepicker_options = { dateFormat: FakeDate.system_format, autoClose: true };
	}
}
FakeDate.system_format = "dd-MMM-yyyy";

test("a patched Date control passes the picker format and keeps its other options", () => {
	class Control extends FakeDate {}
	patch_date_control(Control);
	const control = new Control();
	control.set_date_options();
	assert.equal(control.datepicker_options.dateFormat, "dd-M-yyyy");
	assert.equal(control.datepicker_options.autoClose, true);
});

test("a subclass that calls super (Datetime) is covered by patching the base class", () => {
	class Base extends FakeDate {}
	class Sub extends Base {
		set_date_options() {
			super.set_date_options();
			this.datepicker_options.timepicker = true;
		}
	}
	patch_date_control(Base);
	const control = new Sub();
	control.set_date_options();
	assert.equal(control.datepicker_options.dateFormat, "dd-M-yyyy");
	assert.equal(control.datepicker_options.timepicker, true);
});

test("existing formats pass through a patched control unchanged", () => {
	for (const format of ["yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy"]) {
		FakeDate.system_format = format;
		class Control extends FakeDate {}
		patch_date_control(Control);
		const control = new Control();
		control.set_date_options();
		assert.equal(control.datepicker_options.dateFormat, format);
	}
	FakeDate.system_format = "dd-MMM-yyyy";
});

test("patching twice does not wrap twice", () => {
	let calls = 0;
	class Control {
		set_date_options() {
			calls += 1;
			this.datepicker_options = { dateFormat: "dd-MMM-yyyy" };
		}
	}
	patch_date_control(Control);
	patch_date_control(Control);
	const control = new Control();
	control.set_date_options();
	assert.equal(calls, 1);
	assert.equal(control.datepicker_options.dateFormat, "dd-M-yyyy");
});

test("a missing control or a control without set_date_options is ignored safely", () => {
	assert.doesNotThrow(() => patch_date_control(undefined));
	assert.doesNotThrow(() => patch_date_control(class NoOptions {}));
});

test("a control that has not set any options yet does not throw", () => {
	class Control {
		set_date_options() {}
	}
	patch_date_control(Control);
	assert.doesNotThrow(() => new Control().set_date_options());
});
