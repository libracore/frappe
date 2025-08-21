// Copyright (c) 2019, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Google Settings', {
	refresh: function(frm) {
		frm.dashboard.set_headline(__("For more information, {0}.", [`<a href='https://docs.libracore.io/index.php?title=ERPNext_Integration/Google_Settings'>${__('Click here')}</a>`]));
	}
});
