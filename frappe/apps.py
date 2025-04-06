# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import re

import frappe
from frappe import _
<<<<<<< HEAD
=======
from frappe.desk.utils import slug
>>>>>>> version-15


@frappe.whitelist()
def get_apps():
<<<<<<< HEAD
	apps = frappe.get_installed_apps()
	app_list = []
=======
	from frappe.desk.desktop import get_workspace_sidebar_items

	allowed_workspaces = get_workspace_sidebar_items().get("pages")

	apps = frappe.get_installed_apps()
	app_list = []

>>>>>>> version-15
	for app in apps:
		if app == "frappe":
			continue
		app_details = frappe.get_hooks("add_to_apps_screen", app_name=app)
		if not len(app_details):
			continue
		for app_detail in app_details:
			has_permission_path = app_detail.get("has_permission")
			if has_permission_path and not frappe.get_attr(has_permission_path)():
				continue
			app_list.append(
				{
					"name": app,
					"logo": app_detail.get("logo"),
					"title": _(app_detail.get("title")),
<<<<<<< HEAD
					"route": app_detail.get("route"),
=======
					"route": get_route(app_detail, allowed_workspaces),
>>>>>>> version-15
				}
			)
	return app_list


<<<<<<< HEAD
def get_route(app_name):
	apps = frappe.get_hooks("add_to_apps_screen", app_name=app_name)
	app = next((app for app in apps if app.get("name") == app_name), None)
	return app.get("route") if app and app.get("route") else "/apps"
=======
def get_route(app, allowed_workspaces=None):
	if not allowed_workspaces:
		return "/app"

	route = app.get("route") if app and app.get("route") else "/apps"

	# Check if user has access to default workspace, if not, pick first workspace user has access to
	if route.startswith("/app/"):
		ws = route.split("/")[2]

		for allowed_ws in allowed_workspaces:
			if allowed_ws.get("name").lower() == ws.lower():
				return route

		module_app = frappe.local.module_app
		for allowed_ws in allowed_workspaces:
			module = allowed_ws.get("module")
			if module and module_app.get(module.lower()) == app.get("name"):
				return f"/app/{slug(allowed_ws.name.lower())}"
		return f"/app/{slug(allowed_workspaces[0].get('name').lower())}"
	else:
		return route
>>>>>>> version-15


def is_desk_apps(apps):
	for app in apps:
		# check if route is /app or /app/* and not /app1 or /app1/*
		pattern = r"^/app(/.*)?$"
		route = app.get("route")
		if route and not re.match(pattern, route):
			return False
	return True


<<<<<<< HEAD
def get_default_path():
	apps = get_apps()
=======
def get_default_path(apps=None):
	if not apps:
		apps = get_apps()
>>>>>>> version-15
	_apps = [app for app in apps if app.get("name") != "frappe"]

	if len(_apps) == 0:
		return None

	system_default_app = frappe.get_system_settings("default_app")
	user_default_app = frappe.db.get_value("User", frappe.session.user, "default_app")
<<<<<<< HEAD
	if system_default_app and not user_default_app:
		return get_route(system_default_app)
	elif user_default_app:
		return get_route(user_default_app)
=======

	if system_default_app and not user_default_app:
		app = next((app for app in apps if app.get("name") == system_default_app), None)
		return app.get("route") if app else None
	elif user_default_app:
		app = next((app for app in apps if app.get("name") == user_default_app), None)
		return app.get("route") if app else None
>>>>>>> version-15

	if len(_apps) == 1:
		return _apps[0].get("route") or "/apps"
	elif is_desk_apps(_apps):
		return "/app"
	return "/apps"


@frappe.whitelist()
def set_app_as_default(app_name):
	if frappe.db.get_value("User", frappe.session.user, "default_app") == app_name:
		frappe.db.set_value("User", frappe.session.user, "default_app", "")
	else:
		frappe.db.set_value("User", frappe.session.user, "default_app", app_name)
