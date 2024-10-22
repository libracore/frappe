import click

from frappe.commands import get_site, pass_context
from frappe.exceptions import SiteNotSpecifiedError


# translation
@click.command("build-message-files")
@pass_context
def build_message_files(context):
	"Build message files for translation"
	import frappe.translate

	for site in context.sites:
		try:
			frappe.init(site=site)
			frappe.connect()
			frappe.translate.rebuild_all_translation_files()
		finally:
			frappe.destroy()
	if not context.sites:
		raise SiteNotSpecifiedError


@click.command("new-language")  # , help="Create lang-code.csv for given app")
@pass_context
@click.argument("lang_code")  # , help="Language code eg. en")
@click.argument("app")  # , help="App name eg. frappe")
def new_language(context, lang_code, app):
	"""Create lang-code.csv for given app"""
	import frappe.translate

	if not context["sites"]:
		raise Exception("--site is required")

	# init site
	frappe.init(site=context["sites"][0])
	frappe.connect()
	frappe.translate.write_translations_file(app, lang_code)

	print(f"File created at ./apps/{app}/{app}/translations/{lang_code}.csv")
	print("You will need to add the language in frappe/geo/languages.json, if you haven't done it already.")


@click.command("get-untranslated")
@click.option("--app", default="_ALL_APPS")
@click.argument("lang")
@click.argument("untranslated_file")
@click.option("--all", default=False, is_flag=True, help="Get all message strings")
@pass_context
def get_untranslated(context, lang, untranslated_file, app="_ALL_APPS", all=None):
	"Get untranslated strings for language"
	import frappe.translate

	site = get_site(context)
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.translate.get_untranslated(lang, untranslated_file, get_all=all, app=app)
	finally:
		frappe.destroy()


@click.command("update-translations")
@click.option("--app", default="_ALL_APPS")
@click.argument("lang")
@click.argument("untranslated_file")
@click.argument("translated-file")
@pass_context
def update_translations(context, lang, untranslated_file, translated_file, app="_ALL_APPS"):
	"Update translated strings"
	import frappe.translate

	site = get_site(context)
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.translate.update_translations(lang, untranslated_file, translated_file, app=app)
	finally:
		frappe.destroy()


@click.command("import-translations")
@click.argument("lang")
@click.argument("path")
@pass_context
def import_translations(context, lang, path):
	"Update translated strings"
	import frappe.translate

	site = get_site(context)
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.translate.import_translations(lang, path)
	finally:
		frappe.destroy()


@click.command("migrate-translations")
@click.argument("source-app")
@click.argument("target-app")
@pass_context
def migrate_translations(context, source_app, target_app):
	"Migrate target-app-specific translations from source-app to target-app"
	import frappe.translate

	site = get_site(context)
	try:
		frappe.init(site=site)
		frappe.connect()
		frappe.translate.migrate_translations(source_app, target_app)
	finally:
		frappe.destroy()


commands = [
	build_message_files,
	get_untranslated,
	import_translations,
	new_language,
	update_translations,
	migrate_translations,
]
