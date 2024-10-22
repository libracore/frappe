frappe.user_info = function (uid) {
	if (!uid) uid = frappe.session.user;

	let user_info;
	if (!(frappe.boot.user_info && frappe.boot.user_info[uid])) {
		user_info = { fullname: uid || "Unknown" };
	} else {
		user_info = frappe.boot.user_info[uid];
	}

	user_info.abbr = frappe.get_abbr(user_info.fullname);
	user_info.color = frappe.get_palette(user_info.fullname);

	return user_info;
};

frappe.update_user_info = function (user_info) {
	for (let user in user_info) {
		if (frappe.boot.user_info[user]) {
			Object.assign(frappe.boot.user_info[user], user_info[user]);
		} else {
			frappe.boot.user_info[user] = user_info[user];
		}
	}
};

frappe.provide("frappe.user");

$.extend(frappe.user, {
	name: "Guest",
	full_name: function (uid) {
		return uid === frappe.session.user
			? __(
					"You",
					null,
					"Name of the current user. For example: You edited this 5 hours ago."
			  )
			: frappe.user_info(uid).fullname;
	},
	image: function (uid) {
		return frappe.user_info(uid).image;
	},
	abbr: function (uid) {
		return frappe.user_info(uid).abbr;
	},
	has_role: function (rl) {
		if (typeof rl == "string") rl = [rl];
		for (var i in rl) {
			if ((frappe.boot ? frappe.boot.user.roles : ["Guest"]).indexOf(rl[i]) != -1)
				return true;
		}
	},
	get_desktop_items: function () {
		// hide based on permission
		var modules_list = $.map(frappe.boot.allowed_modules, function (icon) {
			var m = icon.module_name;
			var type = frappe.modules[m] && frappe.modules[m].type;

			if (frappe.boot.user.allow_modules.indexOf(m) === -1) return null;

			var ret = null;
			if (type === "module") {
				if (frappe.boot.user.allow_modules.indexOf(m) != -1 || frappe.modules[m].is_help)
					ret = m;
			} else if (type === "page") {
				if (frappe.boot.allowed_pages.indexOf(frappe.modules[m].link) != -1) ret = m;
			} else if (type === "list") {
				if (frappe.model.can_read(frappe.modules[m]._doctype)) ret = m;
			} else if (type === "view") {
				ret = m;
			} else if (type === "setup") {
				if (
					frappe.user.has_role("System Manager") ||
					frappe.user.has_role("Administrator")
				)
					ret = m;
			} else {
				ret = m;
			}

			return ret;
		});

		return modules_list;
	},

	is_report_manager: function () {
		return frappe.user.has_role(["Administrator", "System Manager", "Report Manager"]);
	},

	get_formatted_email: function (email) {
		var fullname = frappe.user.full_name(email);

		if (!fullname) {
			return email;
		} else {
			// to quote or to not
			var quote = "";

			// only if these special characters are found
			// why? To make the output same as that in python!
			if (fullname.search(/[\[\]\\()<>@,:;".]/) !== -1) {
				quote = '"';
			}

			return repl("%(quote)s%(fullname)s%(quote)s <%(email)s>", {
				fullname: fullname,
				email: email,
				quote: quote,
			});
		}
	},

	get_emails: () => {
		return Object.keys(frappe.boot.user_info).map((key) => frappe.boot.user_info[key].email);
	},

	/* Normally frappe.user is an object
	 * having properties and methods.
	 * But in the following case
	 *
	 * if (frappe.user === 'Administrator')
	 *
	 * frappe.user will cast to a string
	 * returning frappe.user.name
	 */
	toString: function () {
		return this.name;
	},
});

frappe.session_alive = true;
$(document).bind("mousemove", function () {
	if (frappe.session_alive === false) {
		$(document).trigger("session_alive");
	}
	frappe.session_alive = true;
	if (frappe.session_alive_timeout) clearTimeout(frappe.session_alive_timeout);
	frappe.session_alive_timeout = setTimeout("frappe.session_alive=false;", 30000);
});
