// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Patch Log", {
	refresh: function (frm) {
		frm.disable_save();
	},
});
