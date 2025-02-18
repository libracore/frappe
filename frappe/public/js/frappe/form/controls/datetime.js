frappe.ui.form.ControlDatetime = frappe.ui.form.ControlDate.extend({
	set_date_options: function() {
		this._super();
		this.today_text = __("Now");
		this.expected_format += " " + frappe.defaultTimeFormat;
		this.date_format = frappe.defaultDatetimeFormat;
		$.extend(this.datepicker_options, {
			timepicker: true,
			timeFormat: "hh:ii:ss"
		});
	},
	get_now_date: function() {
		return frappe.datetime.now_datetime(true);
	},
	set_description: function() {
		const { description } = this.df;
		const { time_zone } = frappe.sys_defaults;
		if (!frappe.datetime.is_timezone_same()) {
			if (!description) {
				this.df.description = time_zone;
			} else if (!description.includes(time_zone)) {
				this.df.description += '<br>' + time_zone;
			}
		}
		this._super();
	},
	parse: function(value) {
		if(value) {
			// If only a time is given, set date to today
			if(value.includes(':') && value.length <= 8) {
				return frappe.datetime.now_date(false) + " " + frappe.datetime.user_to_str(value, true);
			} else {
				return frappe.datetime.user_to_str(value);
			}
		}
	},
});
