# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
import frappe.defaults
from frappe.modules.import_file import get_file_path, read_doc_from_file
from frappe.translate import send_translations
from frappe.core.doctype.doctype.doctype import (clear_permissions_cache,
	validate_permissions_for_doctype)
from frappe.permissions import (reset_perms, get_linked_doctypes, get_all_perms,
	setup_custom_perms, add_permission, update_permission_property)
from frappe.utils.user import get_users_with_role as _get_user_with_role

not_allowed_in_permission_manager = ["DocType", "Patch Log", "Module Def", "Transaction Log"]

@frappe.whitelist()
def get_roles_and_doctypes():
	frappe.only_for("System Manager")
	send_translations(frappe.get_lang_dict("doctype", "DocPerm"))

	active_domains = frappe.get_active_domains()

	doctypes = frappe.get_all("DocType", filters={
		"istable": 0,
		"name": ("not in", ",".join(not_allowed_in_permission_manager)),
	}, or_filters={
		"ifnull(restrict_to_domain, '')": "",
		"restrict_to_domain": ("in", active_domains)
	}, fields=["name"])

	roles = frappe.get_all("Role", filters={
		"name": ("not in", "Administrator"),
		"disabled": 0,
	}, or_filters={
		"ifnull(restrict_to_domain, '')": "",
		"restrict_to_domain": ("in", active_domains)
	}, fields=["name"])

	doctypes_list = [ {"label":_(d.get("name")), "value":d.get("name")} for d in doctypes]
	roles_list = [ {"label":_(d.get("name")), "value":d.get("name")} for d in roles]

	return {
		"doctypes": sorted(doctypes_list, key=lambda d: d['label']),
		"roles": sorted(roles_list, key=lambda d: d['label'])
	}

@frappe.whitelist()
def get_permissions(doctype=None, role=None):
	frappe.only_for("System Manager")
	if role:
		out = get_all_perms(role)
		if doctype:
			out = [p for p in out if p.parent == doctype]
	else:
		out = frappe.get_all('Custom DocPerm', fields='*', filters=dict(parent = doctype), order_by="permlevel")
		if not out:
			out = frappe.get_all('DocPerm', fields='*', filters=dict(parent = doctype), order_by="permlevel")

	linked_doctypes = {}
	for d in out:
		if not d.parent in linked_doctypes:
			linked_doctypes[d.parent] = get_linked_doctypes(d.parent)
		d.linked_doctypes = linked_doctypes[d.parent]
		meta = frappe.get_meta(d.parent)
		if meta:
			d.is_submittable = meta.is_submittable

	return out

@frappe.whitelist()
def add(parent, role, permlevel):
	frappe.only_for("System Manager")
	add_permission(parent, role, permlevel)

@frappe.whitelist()
def update(doctype, role, permlevel, ptype, value=None):
	frappe.only_for("System Manager")
	out = update_permission_property(doctype, role, permlevel, ptype, value)
	return 'refresh' if out else None

@frappe.whitelist()
def remove(doctype, role, permlevel):
	frappe.only_for("System Manager")
	setup_custom_perms(doctype)

	frappe.db.delete("Custom DocPerm", {'parent': doctype, 'role': role, 'permlevel': permlevel})

	if not frappe.get_all('Custom DocPerm', dict(parent=doctype)):
		frappe.throw(_('There must be atleast one permission rule.'), title=_('Cannot Remove'))

	validate_permissions_for_doctype(doctype, for_remove=True)

@frappe.whitelist()
def reset(doctype):
	frappe.only_for("System Manager")
	reset_perms(doctype)
	clear_permissions_cache(doctype)

@frappe.whitelist()
def get_users_with_role(role):
	frappe.only_for("System Manager")
	return _get_user_with_role(role)

@frappe.whitelist()
def get_standard_permissions(doctype):
	frappe.only_for("System Manager")
	meta = frappe.get_meta(doctype)
	if meta.custom:
		doc = frappe.get_doc('DocType', doctype)
		return [p.as_dict() for p in doc.permissions]
	else:
		# also used to setup permissions via patch
		path = get_file_path(meta.module, "DocType", doctype)
		return read_doc_from_file(path).get("permissions")
