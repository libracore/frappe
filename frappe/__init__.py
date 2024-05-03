# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt
"""
globals attached to frappe module
+ some utility functions that should probably be moved
"""
from __future__ import unicode_literals, print_function

from six import iteritems, binary_type, text_type, string_types
from werkzeug.local import Local, release_local
import os, sys, importlib, inspect, json
from past.builtins import cmp

from faker import Faker

# public
from .exceptions import *
from .utils.jinja import (get_jenv, get_template, render_template, get_email_from_template, get_jloader)

# Harmless for Python 3
# For Python 2 set default encoding to utf-8
if sys.version[0] == '2':
	reload(sys)
	sys.setdefaultencoding("utf-8")

__version__ = '2023.6.0'
__title__ = "Frappe Framework"

local = Local()

class _dict(dict):
	"""dict like object that exposes keys as attributes"""
	def __getattr__(self, key):
		ret = self.get(key)
		if not ret and key.startswith("__"):
			raise AttributeError()
		return ret
	def __setattr__(self, key, value):
		self[key] = value
	def __getstate__(self):
		return self
	def __setstate__(self, d):
		self.update(d)
	def update(self, d):
		"""update and return self -- the missing dict feature in python"""
		super(_dict, self).update(d)
		return self
	def copy(self):
		return _dict(dict(self).copy())

def _(msg, lang=None):
	"""Returns translated string in current lang, if exists."""
	from frappe.translate import get_full_dict
	from frappe.utils import strip_html_tags, is_html

	if not hasattr(local, 'lang'):
		local.lang = lang or 'en'

	if not lang:
		lang = local.lang

	non_translated_msg = msg

	if is_html(msg):
		msg = strip_html_tags(msg)

	# msg should always be unicode
	msg = as_unicode(msg).strip()

	# return lang_full_dict according to lang passed parameter
	return get_full_dict(lang).get(msg) or non_translated_msg

def as_unicode(text, encoding='utf-8'):
	'''Convert to unicode if required'''
	if isinstance(text, text_type):
		return text
	elif text==None:
		return ''
	elif isinstance(text, binary_type):
		return str(text, encoding)
	else:
		return str(text)

def get_lang_dict(fortype, name=None):
	"""Returns the translated language dict for the given type and name.

	 :param fortype: must be one of `doctype`, `page`, `report`, `include`, `jsfile`, `boot`
	 :param name: name of the document for which assets are to be returned."""
	from frappe.translate import get_dict
	return get_dict(fortype, name)

def set_user_lang(user, user_language=None):
	"""Guess and set user language for the session. `frappe.local.lang`"""
	from frappe.translate import get_user_lang
	local.lang = get_user_lang(user)

# local-globals
db = local("db")
conf = local("conf")
form = form_dict = local("form_dict")
request = local("request")
response = local("response")
session = local("session")
user = local("user")
flags = local("flags")

error_log = local("error_log")
debug_log = local("debug_log")
message_log = local("message_log")

lang = local("lang")

def init(site, sites_path=None, new_site=False):
	"""Initialize frappe for the current site. Reset thread locals `frappe.local`"""
	if getattr(local, "initialised", None):
		return

	if not sites_path:
		sites_path = '.'

	local.error_log = []
	local.message_log = []
	local.debug_log = []
	local.realtime_log = []
	local.flags = _dict({
		"ran_schedulers": [],
		"currently_saving": [],
		"redirect_location": "",
		"in_install_db": False,
		"in_install_app": False,
		"in_import": False,
		"in_test": False,
		"mute_messages": False,
		"ignore_links": False,
		"mute_emails": False,
		"has_dataurl": False,
		"new_site": new_site
	})
	local.rollback_observers = []
	local.test_objects = {}

	local.site = site
	local.sites_path = sites_path
	local.site_path = os.path.join(sites_path, site)

	local.request_ip = None
	local.response = _dict({"docs":[]})
	local.task_id = None

	local.conf = _dict(get_site_config())
	local.lang = local.conf.lang or "en"
	local.lang_full_dict = None

	local.module_app = None
	local.app_modules = None
	local.system_settings = _dict()

	local.user = None
	local.user_perms = None
	local.session = None
	local.role_permissions = {}
	local.valid_columns = {}
	local.new_doc_templates = {}
	local.link_count = {}

	local.jenv = None
	local.jloader =None
	local.cache = {}
	local.document_cache = {}
	local.meta_cache = {}
	local.form_dict = _dict()
	local.session = _dict()

	setup_module_map()

	local.initialised = True

def connect(site=None, db_name=None):
	"""Connect to site database instance.

	:param site: If site is given, calls `frappe.init`.
	:param db_name: Optional. Will use from `site_config.json`."""
	from frappe.database import get_db
	if site:
		init(site)

	local.db = get_db(user=db_name or local.conf.db_name)
	set_user("Administrator")

def connect_replica():
	from frappe.database import get_db
	user = local.conf.db_name
	password = local.conf.db_password

	if local.conf.different_credentials_for_replica:
		user = local.conf.replica_db_name
		password = local.conf.replica_db_password

	local.replica_db = get_db(host=local.conf.replica_host, user=user, password=password)

	# swap db connections
	local.primary_db = local.db
	local.db = local.replica_db

def get_site_config(sites_path=None, site_path=None):
	"""Returns `site_config.json` combined with `sites/common_site_config.json`.
	`site_config` is a set of site wide settings like database name, password, email etc."""
	config = {}

	sites_path = sites_path or getattr(local, "sites_path", None)
	site_path = site_path or getattr(local, "site_path", None)

	if sites_path:
		common_site_config = os.path.join(sites_path, "common_site_config.json")
		if os.path.exists(common_site_config):
			config.update(get_file_json(common_site_config))

	if site_path:
		site_config = os.path.join(site_path, "site_config.json")
		if os.path.exists(site_config):
			config.update(get_file_json(site_config))
		elif local.site and not local.flags.new_site:
			print("{0} does not exist".format(local.site))
			sys.exit(1)
			#raise IncorrectSitePath, "{0} does not exist".format(site_config)

	return _dict(config)

def get_conf(site=None):
	if hasattr(local, 'conf'):
		return local.conf

	else:
		# if no site, get from common_site_config.json
		with init_site(site):
			return local.conf

class init_site:
	def __init__(self, site=None):
		'''If site==None, initialize it for empty site ('') to load common_site_config.json'''
		self.site = site or ''

	def __enter__(self):
		init(self.site)
		return local

	def __exit__(self, type, value, traceback):
		destroy()

def destroy():
	"""Closes connection and releases werkzeug local."""
	if db:
		db.close()

	release_local(local)

# memcache
redis_server = None
def cache():
	"""Returns memcache connection."""
	global redis_server
	if not redis_server:
		from frappe.utils.redis_wrapper import RedisWrapper
		redis_server = RedisWrapper.from_url(conf.get('redis_cache')
			or "redis://localhost:11311")
	return redis_server

def get_traceback():
	"""Returns error traceback."""
	from frappe.utils import get_traceback
	return get_traceback()

def errprint(msg):
	"""Log error. This is sent back as `exc` in response.

	:param msg: Message."""
	msg = as_unicode(msg)
	if not request or (not "cmd" in local.form_dict) or conf.developer_mode:
		print(msg)

	error_log.append({"exc": msg})

def log(msg):
	"""Add to `debug_log`.

	:param msg: Message."""
	if not request:
		if conf.get("logging") or False:
			print(repr(msg))

	debug_log.append(as_unicode(msg))

def msgprint(msg, title=None, raise_exception=0, as_table=False, indicator=None, alert=False):
	"""Print a message to the user (via HTTP response).
	Messages are sent in the `__server_messages` property in the
	response JSON and shown in a pop-up / modal.

	:param msg: Message.
	:param title: [optional] Message title.
	:param raise_exception: [optional] Raise given exception and show message.
	:param as_table: [optional] If `msg` is a list of lists, render as HTML table.
	"""
	from frappe.utils import encode

	msg = safe_decode(msg)
	out = _dict(message=msg)

	def _raise_exception():
		if raise_exception:
			if flags.rollback_on_exception:
				db.rollback()
			import inspect

			if inspect.isclass(raise_exception) and issubclass(raise_exception, Exception):
				raise raise_exception(msg)
			else:
				raise ValidationError(msg)

	if flags.mute_messages:
		_raise_exception()
		return

	if as_table and type(msg) in (list, tuple):
		out.msg = '<table border="1px" style="border-collapse: collapse" cellpadding="2px">' + ''.join(['<tr>'+''.join(['<td>%s</td>' % c for c in r])+'</tr>' for r in msg]) + '</table>'

	if flags.print_messages and out.msg:
		print("Message: " + repr(out.msg).encode("utf-8"))

	if title:
		out.title = title

	if not indicator and raise_exception:
		indicator = 'red'

	if indicator:
		out.indicator = indicator

	if alert:
		out.alert = 1

	message_log.append(json.dumps(out))

	if raise_exception and hasattr(raise_exception, '__name__'):
		local.response['exc_type'] = raise_exception.__name__

	_raise_exception()

def clear_messages():
	local.message_log = []

def clear_last_message():
	if len(local.message_log) > 0:
		local.message_log = local.message_log[:-1]

def throw(msg, exc=ValidationError, title=None):
	"""Throw execption and show message (`msgprint`).

	:param msg: Message.
	:param exc: Exception class. Default `frappe.ValidationError`"""
	msgprint(msg, raise_exception=exc, title=title, indicator='red')

def emit_js(js, user=False, **kwargs):
	from frappe.realtime import publish_realtime
	if user == False:
		user = session.user
	publish_realtime('eval_js', js, user=user, **kwargs)

def create_folder(path, with_init=False):
	"""Create a folder in the given path and add an `__init__.py` file (optional).

	:param path: Folder path.
	:param with_init: Create `__init__.py` in the new folder."""
	from frappe.utils import touch_file
	if not os.path.exists(path):
		os.makedirs(path)

		if with_init:
			touch_file(os.path.join(path, "__init__.py"))

def set_user(username):
	"""Set current user.

	:param username: **User** name to set as current user."""
	local.session.user = username
	local.session.sid = username
	local.cache = {}
	local.form_dict = _dict()
	local.jenv = None
	local.session.data = _dict()
	local.role_permissions = {}
	local.new_doc_templates = {}
	local.user_perms = None

def get_user():
	from frappe.utils.user import UserPermissions
	if not local.user_perms:
		local.user_perms = UserPermissions(local.session.user)
	return local.user_perms

def get_roles(username=None):
	"""Returns roles of current user."""
	if not local.session:
		return ["Guest"]

	if username:
		import frappe.permissions
		return frappe.permissions.get_roles(username)
	else:
		return get_user().get_roles()

def get_request_header(key, default=None):
	"""Return HTTP request header.

	:param key: HTTP header key.
	:param default: Default value."""
	return request.headers.get(key, default)

def sendmail(recipients=[], sender="", subject="No Subject", message="No Message",
		as_markdown=False, delayed=True, reference_doctype=None, reference_name=None,
		unsubscribe_method=None, unsubscribe_params=None, unsubscribe_message=None,
		attachments=None, content=None, doctype=None, name=None, reply_to=None,
		cc=[], bcc=[], message_id=None, in_reply_to=None, send_after=None, expose_recipients=None,
		send_priority=1, communication=None, retry=1, now=None, read_receipt=None, is_notification=False,
		inline_images=None, template=None, args=None, header=None, print_letterhead=False):
	"""Send email using user's default **Email Account** or global default **Email Account**.


	:param recipients: List of recipients.
	:param sender: Email sender. Default is current user.
	:param subject: Email Subject.
	:param message: (or `content`) Email Content.
	:param as_markdown: Convert content markdown to HTML.
	:param delayed: Send via scheduled email sender **Email Queue**. Don't send immediately. Default is true
	:param send_priority: Priority for Email Queue, default 1.
	:param reference_doctype: (or `doctype`) Append as communication to this DocType.
	:param reference_name: (or `name`) Append as communication to this document name.
	:param unsubscribe_method: Unsubscribe url with options email, doctype, name. e.g. `/api/method/unsubscribe`
	:param unsubscribe_params: Unsubscribe paramaters to be loaded on the unsubscribe_method [optional] (dict).
	:param attachments: List of attachments.
	:param reply_to: Reply-To Email Address.
	:param message_id: Used for threading. If a reply is received to this email, Message-Id is sent back as In-Reply-To in received email.
	:param in_reply_to: Used to send the Message-Id of a received email back as In-Reply-To.
	:param send_after: Send after the given datetime.
	:param expose_recipients: Display all recipients in the footer message - "This email was sent to"
	:param communication: Communication link to be set in Email Queue record
	:param inline_images: List of inline images as {"filename", "filecontent"}. All src properties will be replaced with random Content-Id
	:param template: Name of html template from templates/emails folder
	:param args: Arguments for rendering the template
	:param header: Append header in email
	"""

	text_content = None
	if template:
		message, text_content = get_email_from_template(template, args)

	message = content or message

	if as_markdown:
		message = frappe.utils.md_to_html(message)

	if not delayed:
		now = True

	from frappe.email import queue
	queue.send(recipients=recipients, sender=sender,
		subject=subject, message=message, text_content=text_content,
		reference_doctype = doctype or reference_doctype, reference_name = name or reference_name,
		unsubscribe_method=unsubscribe_method, unsubscribe_params=unsubscribe_params, unsubscribe_message=unsubscribe_message,
		attachments=attachments, reply_to=reply_to, cc=cc, bcc=bcc, message_id=message_id, in_reply_to=in_reply_to,
		send_after=send_after, expose_recipients=expose_recipients, send_priority=send_priority,
		communication=communication, now=now, read_receipt=read_receipt, is_notification=is_notification,
		inline_images=inline_images, header=header, print_letterhead=print_letterhead)

whitelisted = []
guest_methods = []
xss_safe_methods = []
def whitelist(allow_guest=False, xss_safe=False):
	"""
	Decorator for whitelisting a function and making it accessible via HTTP.
	Standard request will be `/api/method/[path.to.method]`

	:param allow_guest: Allow non logged-in user to access this method.

	Use as:

		@frappe.whitelist()
		def myfunc(param1, param2):
			pass
	"""
	def innerfn(fn):
		global whitelisted, guest_methods, xss_safe_methods
		whitelisted.append(fn)

		if allow_guest:
			guest_methods.append(fn)

			if xss_safe:
				xss_safe_methods.append(fn)

		return fn

	return innerfn

def read_only():
	def innfn(fn):
		def wrapper_fn(*args, **kwargs):
			if conf.read_from_replica:
				connect_replica()

			try:
				retval = fn(*args, **get_newargs(fn, kwargs))
			except:
				raise
			finally:
				if local and hasattr(local, 'primary_db'):
					local.db.close()
					local.db = local.primary_db

			return retval
		return wrapper_fn
	return innfn

def only_for(roles):
	"""Raise `frappe.PermissionError` if the user does not have any of the given **Roles**.

	:param roles: List of roles to check."""
	if local.flags.in_test:
		return

	if not isinstance(roles, (tuple, list)):
		roles = (roles,)
	roles = set(roles)
	myroles = set(get_roles())
	if not roles.intersection(myroles):
		raise PermissionError

def get_domain_data(module):
	try:
		domain_data = get_hooks('domains')
		if module in domain_data:
			return _dict(get_attr(get_hooks('domains')[module][0] + '.data'))
		else:
			return _dict()
	except ImportError:
		if local.flags.in_test:
			return _dict()
		else:
			raise


def clear_cache(user=None, doctype=None):
	"""Clear **User**, **DocType** or global cache.

	:param user: If user is given, only user cache is cleared.
	:param doctype: If doctype is given, only DocType cache is cleared."""
	import frappe.cache_manager
	if doctype:
		frappe.cache_manager.clear_doctype_cache(doctype)
		reset_metadata_version()
	elif user:
		frappe.cache_manager.clear_user_cache(user)
	else: # everything
		from frappe import translate
		frappe.cache_manager.clear_user_cache()
		translate.clear_cache()
		reset_metadata_version()
		local.cache = {}
		local.new_doc_templates = {}

		for fn in get_hooks("clear_cache"):
			get_attr(fn)()

	local.role_permissions = {}

def has_permission(doctype=None, ptype="read", doc=None, user=None, verbose=False, throw=False):
	"""Raises `frappe.PermissionError` if not permitted.

	:param doctype: DocType for which permission is to be check.
	:param ptype: Permission type (`read`, `write`, `create`, `submit`, `cancel`, `amend`). Default: `read`.
	:param doc: [optional] Checks User permissions for given doc.
	:param user: [optional] Check for given user. Default: current user."""
	if not doctype and doc:
		doctype = doc.doctype

	import frappe.permissions
	out = frappe.permissions.has_permission(doctype, ptype, doc=doc, verbose=verbose, user=user)
	if throw and not out:
		if doc:
			frappe.throw(_("No permission for {0}").format(doc.doctype + " " + doc.name))
		else:
			frappe.throw(_("No permission for {0}").format(doctype))

	return out

def has_website_permission(doc=None, ptype='read', user=None, verbose=False, doctype=None):
	"""Raises `frappe.PermissionError` if not permitted.

	:param doctype: DocType for which permission is to be check.
	:param ptype: Permission type (`read`, `write`, `create`, `submit`, `cancel`, `amend`). Default: `read`.
	:param doc: Checks User permissions for given doc.
	:param user: [optional] Check for given user. Default: current user."""

	if not user:
		user = session.user

	if doc:
		if isinstance(doc, string_types):
			doc = get_doc(doctype, doc)

		doctype = doc.doctype

		if doc.flags.ignore_permissions:
			return True

		# check permission in controller
		if hasattr(doc, 'has_website_permission'):
			return doc.has_website_permission(ptype, user, verbose=verbose)

	hooks = (get_hooks("has_website_permission") or {}).get(doctype, [])
	if hooks:
		for method in hooks:
			result = call(method, doc=doc, ptype=ptype, user=user, verbose=verbose)
			# if even a single permission check is Falsy
			if not result:
				return False

		# else it is Truthy
		return True

	else:
		return False

def is_table(doctype):
	"""Returns True if `istable` property (indicating child Table) is set for given DocType."""
	def get_tables():
		return db.sql_list("select name from tabDocType where istable=1")

	tables = cache().get_value("is_table", get_tables)
	return doctype in tables

def get_precision(doctype, fieldname, currency=None, doc=None):
	"""Get precision for a given field"""
	from frappe.model.meta import get_field_precision
	return get_field_precision(get_meta(doctype).get_field(fieldname), doc, currency)

def generate_hash(txt=None, length=None):
	"""Generates random hash for given text + current timestamp + random string."""
	import hashlib, time
	from .utils import random_string
	digest = hashlib.sha224(((txt or "") + repr(time.time()) + repr(random_string(8))).encode()).hexdigest()
	if length:
		digest = digest[:length]
	return digest

def reset_metadata_version():
	"""Reset `metadata_version` (Client (Javascript) build ID) hash."""
	v = generate_hash()
	cache().set_value("metadata_version", v)
	return v

def new_doc(doctype, parent_doc=None, parentfield=None, as_dict=False):
	"""Returns a new document of the given DocType with defaults set.

	:param doctype: DocType of the new document.
	:param parent_doc: [optional] add to parent document.
	:param parentfield: [optional] add against this `parentfield`."""
	from frappe.model.create_new import get_new_doc
	return get_new_doc(doctype, parent_doc, parentfield, as_dict=as_dict)

def set_value(doctype, docname, fieldname, value=None):
	"""Set document value. Calls `frappe.client.set_value`"""
	import frappe.client
	return frappe.client.set_value(doctype, docname, fieldname, value)

def get_cached_doc(*args, **kwargs):
	if args and len(args) > 1 and isinstance(args[1], text_type):
		key = get_document_cache_key(args[0], args[1])
		# local cache
		doc = local.document_cache.get(key)
		if doc:
			return doc

		# redis cache
		doc = cache().hget('document_cache', key)
		if doc:
			doc = get_doc(doc)
			local.document_cache[key] = doc
			return doc

	# database
	doc = get_doc(*args, **kwargs)

	return doc

def get_document_cache_key(doctype, name):
	return '{0}::{1}'.format(doctype, name)

def clear_document_cache(doctype, name):
	cache().hdel("last_modified", doctype)
	key = get_document_cache_key(doctype, name)
	if key in local.document_cache:
		del local.document_cache[key]
	cache().hdel('document_cache', key)

def get_cached_value(doctype, name, fieldname, as_dict=False):
	doc = get_cached_doc(doctype, name)
	if isinstance(fieldname, string_types):
		if as_dict:
			throw('Cannot make dict for single fieldname')
		return doc.get(fieldname)

	values = [doc.get(f) for f in fieldname]
	if as_dict:
		return _dict(zip(fieldname, values))
	return values

def get_doc(*args, **kwargs):
	"""Return a `frappe.model.document.Document` object of the given type and name.

	:param arg1: DocType name as string **or** document JSON.
	:param arg2: [optional] Document name as string.

	Examples:

		# insert a new document
		todo = frappe.get_doc({"doctype":"ToDo", "description": "test"})
		tood.insert()

		# open an existing document
		todo = frappe.get_doc("ToDo", "TD0001")

	"""
	import frappe.model.document
	doc = frappe.model.document.get_doc(*args, **kwargs)

	# set in cache
	if args and len(args) > 1:
		key = get_document_cache_key(args[0], args[1])
		local.document_cache[key] = doc
		cache().hset('document_cache', key, doc.as_dict())

	return doc

def get_last_doc(doctype):
	"""Get last created document of this type."""
	d = get_all(doctype, ["name"], order_by="creation desc", limit_page_length=1)
	if d:
		return get_doc(doctype, d[0].name)
	else:
		raise DoesNotExistError

def get_single(doctype):
	"""Return a `frappe.model.document.Document` object of the given Single doctype."""
	return get_doc(doctype, doctype)

def get_meta(doctype, cached=True):
	"""Get `frappe.model.meta.Meta` instance of given doctype name."""
	import frappe.model.meta
	return frappe.model.meta.get_meta(doctype, cached=cached)

def get_meta_module(doctype):
	import frappe.modules
	return frappe.modules.load_doctype_module(doctype)

def delete_doc(doctype=None, name=None, force=0, ignore_doctypes=None, for_reload=False,
	ignore_permissions=False, flags=None, ignore_on_trash=False, ignore_missing=True):
	"""Delete a document. Calls `frappe.model.delete_doc.delete_doc`.

	:param doctype: DocType of document to be delete.
	:param name: Name of document to be delete.
	:param force: Allow even if document is linked. Warning: This may lead to data integrity errors.
	:param ignore_doctypes: Ignore if child table is one of these.
	:param for_reload: Call `before_reload` trigger before deleting.
	:param ignore_permissions: Ignore user permissions."""
	import frappe.model.delete_doc
	frappe.model.delete_doc.delete_doc(doctype, name, force, ignore_doctypes, for_reload,
		ignore_permissions, flags, ignore_on_trash, ignore_missing)

def delete_doc_if_exists(doctype, name, force=0):
	"""Delete document if exists."""
	if db.exists(doctype, name):
		delete_doc(doctype, name, force=force)

def reload_doctype(doctype, force=False, reset_permissions=False):
	"""Reload DocType from model (`[module]/[doctype]/[name]/[name].json`) files."""
	reload_doc(scrub(db.get_value("DocType", doctype, "module")), "doctype", scrub(doctype),
		force=force, reset_permissions=reset_permissions)

def reload_doc(module, dt=None, dn=None, force=False, reset_permissions=False):
	"""Reload Document from model (`[module]/[doctype]/[name]/[name].json`) files.

	:param module: Module name.
	:param dt: DocType name.
	:param dn: Document name.
	:param force: Reload even if `modified` timestamp matches.
	"""

	import frappe.modules
	return frappe.modules.reload_doc(module, dt, dn, force=force, reset_permissions=reset_permissions)

def rename_doc(*args, **kwargs):
	"""Rename a document. Calls `frappe.model.rename_doc.rename_doc`"""
	from frappe.model.rename_doc import rename_doc
	return rename_doc(*args, **kwargs)

def get_module(modulename):
	"""Returns a module object for given Python module name using `importlib.import_module`."""
	return importlib.import_module(modulename)

def scrub(txt):
	"""Returns sluggified string. e.g. `Sales Order` becomes `sales_order`."""
	return txt.replace(' ','_').replace('-', '_').lower()

def unscrub(txt):
	"""Returns titlified string. e.g. `sales_order` becomes `Sales Order`."""
	return txt.replace('_',' ').replace('-', ' ').title()

def get_module_path(module, *joins):
	"""Get the path of the given module name.

	:param module: Module name.
	:param *joins: Join additional path elements using `os.path.join`."""
	module = scrub(module)
	return get_pymodule_path(local.module_app[module] + "." + module, *joins)

def get_app_path(app_name, *joins):
	"""Return path of given app.

	:param app: App name.
	:param *joins: Join additional path elements using `os.path.join`."""
	return get_pymodule_path(app_name, *joins)

def get_site_path(*joins):
	"""Return path of current site.

	:param *joins: Join additional path elements using `os.path.join`."""
	return os.path.join(local.site_path, *joins)

def get_pymodule_path(modulename, *joins):
	"""Return path of given Python module name.

	:param modulename: Python module name.
	:param *joins: Join additional path elements using `os.path.join`."""
	if not "public" in joins:
		joins = [scrub(part) for part in joins]
	return os.path.join(os.path.dirname(get_module(scrub(modulename)).__file__), *joins)

def get_module_list(app_name):
	"""Get list of modules for given all via `app/modules.txt`."""
	return get_file_items(os.path.join(os.path.dirname(get_module(app_name).__file__), "modules.txt"))

def get_all_apps(with_internal_apps=True, sites_path=None):
	"""Get list of all apps via `sites/apps.txt`."""
	if not sites_path:
		sites_path = local.sites_path

	apps = get_file_items(os.path.join(sites_path, "apps.txt"), raise_not_found=True)

	if with_internal_apps:
		for app in get_file_items(os.path.join(local.site_path, "apps.txt")):
			if app not in apps:
				apps.append(app)

	if "frappe" in apps:
		apps.remove("frappe")
	apps.insert(0, 'frappe')

	return apps

def get_installed_apps(sort=False, frappe_last=False):
	"""Get list of installed apps in current site."""
	if getattr(flags, "in_install_db", True):
		return []

	if not db:
		connect()

	installed = json.loads(db.get_global("installed_apps") or "[]")

	if sort:
		installed = [app for app in get_all_apps(True) if app in installed]

	if frappe_last:
		if 'frappe' in installed:
			installed.remove('frappe')
		installed.append('frappe')

	return installed

def get_doc_hooks():
	'''Returns hooked methods for given doc. It will expand the dict tuple if required.'''
	if not hasattr(local, 'doc_events_hooks'):
		hooks = get_hooks('doc_events', {})
		out = {}
		for key, value in iteritems(hooks):
			if isinstance(key, tuple):
				for doctype in key:
					append_hook(out, doctype, value)
			else:
				append_hook(out, key, value)

		local.doc_events_hooks = out

	return local.doc_events_hooks

def get_hooks(hook=None, default=None, app_name=None):
	"""Get hooks via `app/hooks.py`

	:param hook: Name of the hook. Will gather all hooks for this name and return as a list.
	:param default: Default if no hook found.
	:param app_name: Filter by app."""
	def load_app_hooks(app_name=None):
		hooks = {}
		for app in [app_name] if app_name else get_installed_apps(sort=True):
			app = "frappe" if app=="webnotes" else app
			try:
				app_hooks = get_module(app + ".hooks")
			except ImportError:
				if local.flags.in_install_app:
					# if app is not installed while restoring
					# ignore it
					pass
				print('Could not find app "{0}"'.format(app_name))
				if not request:
					sys.exit(1)
				raise
			for key in dir(app_hooks):
				if not key.startswith("_"):
					append_hook(hooks, key, getattr(app_hooks, key))
		return hooks

	no_cache = conf.developer_mode or False

	if app_name:
		hooks = _dict(load_app_hooks(app_name))
	else:
		if no_cache:
			hooks = _dict(load_app_hooks())
		else:
			hooks = _dict(cache().get_value("app_hooks", load_app_hooks))

	if hook:
		return hooks.get(hook) or (default if default is not None else [])
	else:
		return hooks

def append_hook(target, key, value):
	'''appends a hook to the the target dict.

	If the hook key, exists, it will make it a key.

	If the hook value is a dict, like doc_events, it will
	listify the values against the key.
	'''
	if isinstance(value, dict):
		# dict? make a list of values against each key
		target.setdefault(key, {})
		for inkey in value:
			append_hook(target[key], inkey, value[inkey])
	else:
		# make a list
		target.setdefault(key, [])
		if not isinstance(value, list):
			value = [value]
		target[key].extend(value)

def setup_module_map():
	"""Rebuild map of all modules (internal)."""
	_cache = cache()

	if conf.db_name:
		local.app_modules = _cache.get_value("app_modules")
		local.module_app = _cache.get_value("module_app")

	if not (local.app_modules and local.module_app):
		local.module_app, local.app_modules = {}, {}
		for app in get_all_apps(True):
			if app=="webnotes": app="frappe"
			local.app_modules.setdefault(app, [])
			for module in get_module_list(app):
				module = scrub(module)
				local.module_app[module] = app
				local.app_modules[app].append(module)

		if conf.db_name:
			_cache.set_value("app_modules", local.app_modules)
			_cache.set_value("module_app", local.module_app)

def get_file_items(path, raise_not_found=False, ignore_empty_lines=True):
	"""Returns items from text file as a list. Ignores empty lines."""
	import frappe.utils

	content = read_file(path, raise_not_found=raise_not_found)
	if content:
		content = frappe.utils.strip(content)

		return [p.strip() for p in content.splitlines() if (not ignore_empty_lines) or (p.strip() and not p.startswith("#"))]
	else:
		return []

def get_file_json(path):
	"""Read a file and return parsed JSON object."""
	with open(path, 'r') as f:
		return json.load(f)

def read_file(path, raise_not_found=False):
	"""Open a file and return its content as Unicode."""
	if isinstance(path, text_type):
		path = path.encode("utf-8")

	if os.path.exists(path):
		with open(path, "r") as f:
			return as_unicode(f.read())
	elif raise_not_found:
		raise IOError("{} Not Found".format(path))
	else:
		return None

def get_attr(method_string):
	"""Get python method object from its name."""
	app_name = method_string.split(".")[0]
	if not local.flags.in_install and app_name not in get_installed_apps():
		throw(_("App {0} is not installed").format(app_name), AppNotInstalledError)

	modulename = '.'.join(method_string.split('.')[:-1])
	methodname = method_string.split('.')[-1]
	return getattr(get_module(modulename), methodname)

def call(fn, *args, **kwargs):
	"""Call a function and match arguments."""
	if isinstance(fn, string_types):
		fn = get_attr(fn)

	newargs = get_newargs(fn, kwargs)

	return fn(*args, **newargs)

def get_newargs(fn, kwargs):
	if hasattr(fn, 'fnargs'):
		fnargs = fn.fnargs
	else:
		try:
			fnargs, varargs, varkw, defaults = inspect.getargspec(fn)
		except ValueError:
			fnargs = inspect.getfullargspec(fn).args
			varargs = inspect.getfullargspec(fn).varargs
			varkw = inspect.getfullargspec(fn).varkw
			defaults = inspect.getfullargspec(fn).defaults

	newargs = {}
	for a in kwargs:
		if (a in fnargs) or varkw:
			newargs[a] = kwargs.get(a)

	if "flags" in newargs:
		del newargs["flags"]

	return newargs

def make_property_setter(args, ignore_validate=False, validate_fields_for_doctype=True):
	"""Create a new **Property Setter** (for overriding DocType and DocField properties).

	If doctype is not specified, it will create a property setter for all fields with the
	given fieldname"""
	args = _dict(args)
	if not args.doctype_or_field:
		args.doctype_or_field = 'DocField'
		if not args.property_type:
			args.property_type = db.get_value('DocField',
				{'parent': 'DocField', 'fieldname': args.property}, 'fieldtype') or 'Data'

	if not args.doctype:
		doctype_list = db.sql_list('select distinct parent from tabDocField where fieldname=%s', args.fieldname)
	else:
		doctype_list = [args.doctype]

	for doctype in doctype_list:
		if not args.property_type:
			args.property_type = db.get_value('DocField',
				{'parent': doctype, 'fieldname': args.fieldname}, 'fieldtype') or 'Data'

		ps = get_doc({
			'doctype': "Property Setter",
			'doctype_or_field': args.doctype_or_field,
			'doc_type': doctype,
			'field_name': args.fieldname,
			'property': args.property,
			'value': args.value,
			'property_type': args.property_type or "Data",
			'__islocal': 1
		})
		ps.flags.ignore_validate = ignore_validate
		ps.flags.validate_fields_for_doctype = validate_fields_for_doctype
		ps.validate_fieldtype_change()
		ps.insert()

def import_doc(path, ignore_links=False, ignore_insert=False, insert=False):
	"""Import a file using Data Import."""
	from frappe.core.doctype.data_import import data_import
	data_import.import_doc(path, ignore_links=ignore_links, ignore_insert=ignore_insert, insert=insert)

def copy_doc(doc, ignore_no_copy=True):
	""" No_copy fields also get copied."""
	import copy

	def remove_no_copy_fields(d):
		for df in d.meta.get("fields", {"no_copy": 1}):
			if hasattr(d, df.fieldname):
				d.set(df.fieldname, None)

	fields_to_clear = ['name', 'owner', 'creation', 'modified', 'modified_by']

	if not local.flags.in_test:
		fields_to_clear.append("docstatus")

	if not isinstance(doc, dict):
		d = doc.as_dict()
	else:
		d = doc

	newdoc = get_doc(copy.deepcopy(d))
	newdoc.set("__islocal", 1)
	for fieldname in (fields_to_clear + ['amended_from', 'amendment_date']):
		newdoc.set(fieldname, None)

	if not ignore_no_copy:
		remove_no_copy_fields(newdoc)

	for i, d in enumerate(newdoc.get_all_children()):
		d.set("__islocal", 1)

		for fieldname in fields_to_clear:
			d.set(fieldname, None)

		if not ignore_no_copy:
			remove_no_copy_fields(d)

	return newdoc

def compare(val1, condition, val2):
	"""Compare two values using `frappe.utils.compare`

	`condition` could be:
	- "^"
	- "in"
	- "not in"
	- "="
	- "!="
	- ">"
	- "<"
	- ">="
	- "<="
	- "not None"
	- "None"
	"""
	import frappe.utils
	return frappe.utils.compare(val1, condition, val2)

def respond_as_web_page(title, html, success=None, http_status_code=None,
	context=None, indicator_color=None, primary_action='/', primary_label = None, fullpage=False,
	width=None, template='message'):
	"""Send response as a web page with a message rather than JSON. Used to show permission errors etc.

	:param title: Page title and heading.
	:param message: Message to be shown.
	:param success: Alert message.
	:param http_status_code: HTTP status code
	:param context: web template context
	:param indicator_color: color of indicator in title
	:param primary_action: route on primary button (default is `/`)
	:param primary_label: label on primary button (default is "Home")
	:param fullpage: hide header / footer
	:param width: Width of message in pixels
	:param template: Optionally pass view template
	"""
	local.message_title = title
	local.message = html
	local.response['type'] = 'page'
	local.response['route'] = template
	local.no_cache = 1

	if http_status_code:
		local.response['http_status_code'] = http_status_code

	if not context:
		context = {}

	if not indicator_color:
		if success:
			indicator_color = 'green'
		elif http_status_code and http_status_code > 300:
			indicator_color = 'red'
		else:
			indicator_color = 'blue'

	context['indicator_color'] = indicator_color
	context['primary_label'] = primary_label
	context['primary_action'] = primary_action
	context['error_code'] = http_status_code
	context['fullpage'] = fullpage
	if width:
		context['card_width'] = width

	local.response['context'] = context

def redirect_to_message(title, html, http_status_code=None, context=None, indicator_color=None):
	"""Redirects to /message?id=random
	Similar to respond_as_web_page, but used to 'redirect' and show message pages like success, failure, etc. with a detailed message

	:param title: Page title and heading.
	:param message: Message to be shown.
	:param http_status_code: HTTP status code.

	Example Usage:
		frappe.redirect_to_message(_('Thank you'), "<div><p>You will receive an email at test@example.com</p></div>")

	"""

	message_id = generate_hash(length=8)
	message = {
		'context': context or {},
		'http_status_code': http_status_code or 200
	}
	message['context'].update({
		'header': title,
		'title': title,
		'message': html
	})

	if indicator_color:
		message['context'].update({
			"indicator_color": indicator_color
		})

	cache().set_value("message_id:{0}".format(message_id), message, expires_in_sec=60)
	location = '/message?id={0}'.format(message_id)

	if not getattr(local, 'is_ajax', False):
		local.response["type"] = "redirect"
		local.response["location"] = location

	else:
		return location

def build_match_conditions(doctype, as_condition=True):
	"""Return match (User permissions) for given doctype as list or SQL."""
	import frappe.desk.reportview
	return frappe.desk.reportview.build_match_conditions(doctype, as_condition=as_condition)

def get_list(doctype, *args, **kwargs):
	"""List database query via `frappe.model.db_query`. Will also check for permissions.

	:param doctype: DocType on which query is to be made.
	:param fields: List of fields or `*`.
	:param filters: List of filters (see example).
	:param order_by: Order By e.g. `modified desc`.
	:param limit_page_start: Start results at record #. Default 0.
	:param limit_page_length: No of records in the page. Default 20.

	Example usage:

		# simple dict filter
		frappe.get_list("ToDo", fields=["name", "description"], filters = {"owner":"test@example.com"})

		# filter as a list of lists
		frappe.get_list("ToDo", fields="*", filters = [["modified", ">", "2014-01-01"]])

		# filter as a list of dicts
		frappe.get_list("ToDo", fields="*", filters = {"description": ("like", "test%")})
	"""
	import frappe.model.db_query
	return frappe.model.db_query.DatabaseQuery(doctype).execute(None, *args, **kwargs)

def get_all(doctype, *args, **kwargs):
	"""List database query via `frappe.model.db_query`. Will **not** check for permissions.
	Parameters are same as `frappe.get_list`

	:param doctype: DocType on which query is to be made.
	:param fields: List of fields or `*`. Default is: `["name"]`.
	:param filters: List of filters (see example).
	:param order_by: Order By e.g. `modified desc`.
	:param limit_start: Start results at record #. Default 0.
	:param limit_page_length: No of records in the page. Default 20.

	Example usage:

		# simple dict filter
		frappe.get_all("ToDo", fields=["name", "description"], filters = {"owner":"test@example.com"})

		# filter as a list of lists
		frappe.get_all("ToDo", fields=["*"], filters = [["modified", ">", "2014-01-01"]])

		# filter as a list of dicts
		frappe.get_all("ToDo", fields=["*"], filters = {"description": ("like", "test%")})
	"""
	kwargs["ignore_permissions"] = True
	if not "limit_page_length" in kwargs:
		kwargs["limit_page_length"] = 0
	return get_list(doctype, *args, **kwargs)

def get_value(*args, **kwargs):
	"""Returns a document property or list of properties.

	Alias for `frappe.db.get_value`

	:param doctype: DocType name.
	:param filters: Filters like `{"x":"y"}` or name of the document. `None` if Single DocType.
	:param fieldname: Column name.
	:param ignore: Don't raise exception if table, column is missing.
	:param as_dict: Return values as dict.
	:param debug: Print query in error log.
	"""
	return db.get_value(*args, **kwargs)

def as_json(obj, indent=1):
	from frappe.utils.response import json_handler
	return json.dumps(obj, indent=indent, sort_keys=True, default=json_handler, separators=(',', ': '))

def are_emails_muted():
	from frappe.utils import cint
	return flags.mute_emails or cint(conf.get("mute_emails") or 0) or False

def get_test_records(doctype):
	"""Returns list of objects from `test_records.json` in the given doctype's folder."""
	from frappe.modules import get_doctype_module, get_module_path
	path = os.path.join(get_module_path(get_doctype_module(doctype)), "doctype", scrub(doctype), "test_records.json")
	if os.path.exists(path):
		with open(path, "r") as f:
			return json.loads(f.read())
	else:
		return []

def format_value(*args, **kwargs):
	"""Format value with given field properties.

	:param value: Value to be formatted.
	:param df: (Optional) DocField object with properties `fieldtype`, `options` etc."""
	import frappe.utils.formatters
	return frappe.utils.formatters.format_value(*args, **kwargs)

def format(*args, **kwargs):
	"""Format value with given field properties.

	:param value: Value to be formatted.
	:param df: (Optional) DocField object with properties `fieldtype`, `options` etc."""
	import frappe.utils.formatters
	return frappe.utils.formatters.format_value(*args, **kwargs)

def get_print(doctype=None, name=None, print_format=None, style=None, html=None, as_pdf=False, doc=None, output = None, no_letterhead = 0, password=None, ignore_zugferd=False):
	"""Get Print Format for given document.

	:param doctype: DocType of document.
	:param name: Name of document.
	:param print_format: Print Format name. Default 'Standard',
	:param style: Print Format style.
	:param as_pdf: Return as PDF. Default False.
	:param password: Password to encrypt the pdf with. Default None"""
	from frappe.website.render import build_page
	from frappe.utils.pdf import get_pdf

	local.form_dict.doctype = doctype
	local.form_dict.name = name
	local.form_dict.format = print_format
	local.form_dict.style = style
	local.form_dict.doc = doc
	local.form_dict.no_letterhead = no_letterhead

	options = None
	if password:
		options = {'password': password}

	if not html:
		html = build_page("printview")
	if as_pdf:
		if doctype == "Sales Invoice" and not ignore_zugferd:
			# include ZUGFeRD document creation when available
			from erpnextswiss.erpnextswiss.zugferd.zugferd import create_zugferd_pdf
			if not doc and name:
				doc = get_doc(doctype, name)
			return create_zugferd_pdf(docname=name, verify=True, format=print_format, doc=doc, doctype=doctype, no_letterhead=no_letterhead)
		else:
			return get_pdf(html, output=output, options=options, print_format=print_format)
	else:
		return html

def attach_print(doctype, name, file_name=None, print_format=None, style=None, html=None, doc=None, lang=None, print_letterhead=True, password=None):
	from frappe.utils import scrub_urls

	if not file_name: file_name = name
	file_name = file_name.replace(' ','').replace('/','-')

	print_settings = db.get_singles_dict("Print Settings")

	_lang = local.lang

	#set lang as specified in print format attachment
	if lang: local.lang = lang
	local.flags.ignore_print_permissions = True

	no_letterhead = not print_letterhead

	if int(print_settings.send_print_as_pdf or 0):
		out = {
			"fname": file_name + ".pdf",
			"fcontent": get_print(doctype, name, print_format=print_format, style=style, html=html, as_pdf=True, doc=doc, no_letterhead=no_letterhead, password=password)
		}
	else:
		out = {
			"fname": file_name + ".html",
			"fcontent": scrub_urls(get_print(doctype, name, print_format=print_format, style=style, html=html, doc=doc, no_letterhead=no_letterhead, password=password)).encode("utf-8")
		}

	local.flags.ignore_print_permissions = False
	#reset lang to original local lang
	local.lang = _lang

	return out

def publish_progress(*args, **kwargs):
	"""Show the user progress for a long request

	:param percent: Percent progress
	:param title: Title
	:param doctype: Optional, for document type
	:param docname: Optional, for document name
	:param description: Optional description
	"""
	import frappe.realtime
	return frappe.realtime.publish_progress(*args, **kwargs)

def publish_realtime(*args, **kwargs):
	"""Publish real-time updates

	:param event: Event name, like `task_progress` etc.
	:param message: JSON message object. For async must contain `task_id`
	:param room: Room in which to publish update (default entire site)
	:param user: Transmit to user
	:param doctype: Transmit to doctype, docname
	:param docname: Transmit to doctype, docname
	:param after_commit: (default False) will emit after current transaction is committed
	"""
	import frappe.realtime

	return frappe.realtime.publish_realtime(*args, **kwargs)

def local_cache(namespace, key, generator, regenerate_if_none=False):
	"""A key value store for caching within a request

	:param namespace: frappe.local.cache[namespace]
	:param key: frappe.local.cache[namespace][key] used to retrieve value
	:param generator: method to generate a value if not found in store

	"""
	if namespace not in local.cache:
		local.cache[namespace] = {}

	if key not in local.cache[namespace]:
		local.cache[namespace][key] = generator()

	elif local.cache[namespace][key]==None and regenerate_if_none:
		# if key exists but the previous result was None
		local.cache[namespace][key] = generator()

	return local.cache[namespace][key]

def enqueue(*args, **kwargs):
	'''
		Enqueue method to be executed using a background worker

		:param method: method string or method object
		:param queue: (optional) should be either long, default or short
		:param timeout: (optional) should be set according to the functions
		:param event: this is passed to enable clearing of jobs from queues
		:param is_async: (optional) if is_async=False, the method is executed immediately, else via a worker
		:param job_name: (optional) can be used to name an enqueue call, which can be used to prevent duplicate calls
		:param kwargs: keyword arguments to be passed to the method
	'''
	import frappe.utils.background_jobs
	return frappe.utils.background_jobs.enqueue(*args, **kwargs)

def enqueue_doc(*args, **kwargs):
	'''
		Enqueue method to be executed using a background worker

		:param doctype: DocType of the document on which you want to run the event
		:param name: Name of the document on which you want to run the event
		:param method: method string or method object
		:param queue: (optional) should be either long, default or short
		:param timeout: (optional) should be set according to the functions
		:param kwargs: keyword arguments to be passed to the method
	'''
	import frappe.utils.background_jobs
	return frappe.utils.background_jobs.enqueue_doc(*args, **kwargs)

def get_doctype_app(doctype):
	def _get_doctype_app():
		doctype_module = local.db.get_value("DocType", doctype, "module")
		return local.module_app[scrub(doctype_module)]

	return local_cache("doctype_app", doctype, generator=_get_doctype_app)

loggers = {}
log_level = None
def logger(module=None, with_more_info=True):
	'''Returns a python logger that uses StreamHandler'''
	from frappe.utils.logger import get_logger
	return get_logger(module or 'default', with_more_info=with_more_info)

def log_error(message=None, title=None):
	'''Log error to Error Log'''
	return get_doc(dict(doctype='Error Log', error=as_unicode(message or get_traceback()),
		method=title)).insert(ignore_permissions=True)

def get_desk_link(doctype, name):
	return '<a href="#Form/{0}/{1}" style="font-weight: bold;">{2} {1}</a>'.format(doctype, name, _(doctype))

def bold(text):
	return '<b>{0}</b>'.format(text)

def safe_eval(code, eval_globals=None, eval_locals=None):
	'''A safer `eval`'''
	whitelisted_globals = {
		"int": int,
		"float": float,
		"long": int,
		"round": round
	}

	if '__' in code:
		throw('Illegal rule {0}. Cannot use "__"'.format(bold(code)))

	if not eval_globals:
		eval_globals = {}
	eval_globals['__builtins__'] = {}

	eval_globals.update(whitelisted_globals)

	return eval(code, eval_globals, eval_locals)

def get_system_settings(key):
	if key not in local.system_settings:
		local.system_settings.update({key: db.get_single_value('System Settings', key)})
	return local.system_settings.get(key)

def get_active_domains():
	from frappe.core.doctype.domain_settings.domain_settings import get_active_domains
	return get_active_domains()

def get_version(doctype, name, limit = None, head = False, raise_err = True):
	'''
	Returns a list of version information of a given DocType (Applicable only if DocType has changes tracked).

	Example
	>>> frappe.get_version('User', 'foobar@gmail.com')
	>>>
	[
		{
			 "version": [version.data], 	 # Refer Version DocType get_diff method and data attribute
			    "user": "admin@gmail.com"    # User that created this version
			"creation": <datetime.datetime>  # Creation timestamp of that object.
		}
	]
	'''
	meta  = get_meta(doctype)
	if meta.track_changes:
		names = db.sql("""
			SELECT name from tabVersion
			WHERE  ref_doctype = '{doctype}' AND docname = '{name}'
			{order_by}
			{limit}
		""".format(
			doctype  = doctype,
			name     = name,
			order_by = 'ORDER BY creation'	 			     if head  else '',
			limit    = 'LIMIT {limit}'.format(limit = limit) if limit else ''
		))

		from frappe.chat.util import squashify, dictify, safe_json_loads

		versions = [ ]

		for name in names:
			name = squashify(name)
			doc  = get_doc('Version', name)

			data = doc.data
			data = safe_json_loads(data)
			data = dictify(dict(
				version  = data,
				user 	 = doc.owner,
				creation = doc.creation
			))

			versions.append(data)

		return versions
	else:
		if raise_err:
			raise ValueError('{doctype} has no versions tracked.'.format(
				doctype = doctype
			))

@whitelist(allow_guest = True)
def ping():
	return "pong"


def safe_encode(param, encoding = 'utf-8'):
	try:
		param = param.encode(encoding)
	except Exception:
		pass
	return param


def safe_decode(param, encoding = 'utf-8'):
	try:
		param = param.decode(encoding)
	except Exception:
		pass
	return param

def parse_json(val):
	from frappe.utils import parse_json
	return parse_json(val)

def mock(type, size = 1, locale = 'en'):
	results = [ ]
	faker 	= Faker(locale)
	if not type in dir(faker):
		raise ValueError('Not a valid mock type.')
	else:
		for i in range(size):
			data = getattr(faker, type)()
			results.append(data)

	from frappe.chat.util import squashify

	results = squashify(results)

	return results
