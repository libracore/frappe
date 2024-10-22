import importlib
import json
import os
import traceback
import warnings
from pathlib import Path
from textwrap import dedent

import click

import frappe
import frappe.utils

click.disable_unicode_literals_warning = True


def main():
	commands = get_app_groups()
	commands.update({"get-frappe-commands": get_frappe_commands, "get-frappe-help": get_frappe_help})
	click.Group(commands=commands)(prog_name="bench")


def get_app_groups() -> dict[str, click.Group]:
	"""Get all app groups, put them in main group "frappe" since bench is
	designed to only handle that"""
	commands = {}
	for app in get_apps():
		if app_commands := get_app_commands(app):
			commands |= app_commands
	return dict(frappe=click.group(name="frappe", commands=commands)(app_group))


def get_app_group(app: str) -> click.Group:
	if app_commands := get_app_commands(app):
		return click.group(name=app, commands=app_commands)(app_group)


@click.option("--site")
@click.option("--profile", is_flag=True, default=False, help="Profile")
@click.option("--verbose", is_flag=True, default=False, help="Verbose")
@click.option("--force", is_flag=True, default=False, help="Force")
@click.pass_context
def app_group(ctx, site=False, force=False, verbose=False, profile=False):
	ctx.obj = {"sites": get_sites(site), "force": force, "verbose": verbose, "profile": profile}
	if ctx.info_name == "frappe":
		ctx.info_name = ""


def get_sites(site_arg: str) -> list[str]:
	if site_arg == "all":
		return frappe.utils.get_sites()
	elif site_arg:
		return [site_arg]
	elif os.environ.get("FRAPPE_SITE"):
		return [os.environ.get("FRAPPE_SITE")]
	elif default_site := frappe.get_conf().default_site:
		return [default_site]
	# This is not supported, just added here for warning.
	elif (site := frappe.read_file("currentsite.txt")) and site.strip():
		click.secho(
			dedent(
				f"""
			WARNING: currentsite.txt is not supported anymore for setting default site. Use following command to set it as default site.
			$ bench use {site}"""
			),
			fg="red",
		)

	return []


def get_app_commands(app: str) -> dict:
	ret = {}
	try:
		app_command_module = importlib.import_module(f"{app}.commands")
	except ModuleNotFoundError as e:
		if e.name == f"{app}.commands":
			return ret
		traceback.print_exc()
		return ret
	except Exception:
		traceback.print_exc()
		return ret
	for command in getattr(app_command_module, "commands", []):
		ret[command.name] = command
	return ret


@click.command("get-frappe-commands")
def get_frappe_commands():
	commands = list(get_app_commands("frappe"))

	for app in get_apps():
		app_commands = get_app_commands(app)
		if app_commands:
			commands.extend(list(app_commands))

	print(json.dumps(commands))


@click.command("get-frappe-help")
def get_frappe_help():
	print(click.Context(get_app_groups()["frappe"]).get_help())


def get_apps():
	return frappe.get_all_apps(with_internal_apps=False, sites_path=".")


if __name__ == "__main__":
	if not frappe._dev_server:
		warnings.simplefilter("ignore")

	main()
