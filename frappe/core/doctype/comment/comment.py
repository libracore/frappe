# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals, absolute_import
import frappe
from frappe import _
import json
from frappe.model.document import Document
from frappe.core.doctype.user.user import extract_mentions
from frappe.utils import get_fullname, get_link_to_form
from frappe.website.render import clear_cache
from frappe.database.schema import add_column
from frappe.exceptions import ImplicitCommitError

class Comment(Document):
	def after_insert(self):
		self.notify_mentions()

		frappe.publish_realtime('new_communication', self.as_dict(),
			doctype=self.reference_doctype, docname=self.reference_name,
			after_commit=True)

	def validate(self):
		if not self.comment_email:
			self.comment_email = frappe.session.user
		
		# Hot fix "<li >" / "<li>" Issue
		self.list_fix()

	def on_update(self):
		update_comment_in_doc(self)

	def on_trash(self):
		self.remove_comment_from_cache()
		frappe.publish_realtime('delete_communication', self.as_dict(),
			doctype= self.reference_doctype, docname = self.reference_name,
			after_commit=True)

	def remove_comment_from_cache(self):
		_comments = get_comments_from_parent(self)
		for c in _comments:
			if c.get("name")==self.name:
				_comments.remove(c)

		update_comments_in_parent(self.reference_doctype, self.reference_name, _comments)

	def notify_mentions(self):
		if self.reference_doctype and self.reference_name and self.content:
			mentions = extract_mentions(self.content)

			if not mentions:
				return

			sender_fullname = get_fullname(frappe.session.user)
			title_field = frappe.get_meta(self.reference_doctype).get_title_field()
			title = self.reference_name if title_field == "name" else \
				frappe.db.get_value(self.reference_doctype, self.reference_name, title_field)

			if title != self.reference_name:
				parent_doc_label = "{0}: {1} (#{2})".format(_(self.reference_doctype),
					title, self.reference_name)
			else:
				parent_doc_label = "{0}: {1}".format(_(self.reference_doctype),
					self.reference_name)

			subject = _("{0} mentioned you in a comment in {1}").format(sender_fullname, parent_doc_label)

			recipients = [frappe.db.get_value("User", {"enabled": 1, "name": name, "user_type": "System User", "allowed_in_mentions": 1}, "email")
				for name in mentions]
			link = get_link_to_form(self.reference_doctype, self.reference_name, label=parent_doc_label)

			frappe.sendmail(
				recipients = recipients,
				sender = frappe.session.user,
				subject = subject,
				template = "mentioned_in_comment",
				args = {
					"body_content": _("{0} mentioned you in a comment in {1}").format(sender_fullname, link),
					"comment": self,
					"link": link
				},
				header = [_('New Mention'), 'orange']
			)
	
	def list_fix(self):
		# Hot fix "<li >" / "<li>" Issue
		if '<li >' in (self.content or ""):
			self.content = self.content.replace("<li >", "<li>")


def on_doctype_update():
	frappe.db.add_index("Comment", ["reference_doctype", "reference_name"])
	frappe.db.add_index("Comment", ["link_doctype", "link_name"])


def update_comment_in_doc(doc):
	"""Updates `_comments` (JSON) property in parent Document.
	Creates a column `_comments` if property does not exist.

	Only user created Communication or Comment of type Comment are saved.

	`_comments` format

		{
			"comment": [String],
			"by": [user],
			"name": [Comment Document name]
		}"""

	# only comments get updates, not likes, assignments etc.
	if doc.doctype == 'Comment' and doc.comment_type != 'Comment':
		return

	def get_truncated(content):
		return (content[:97] + '...') if len(content) > 100 else content

	if doc.reference_doctype and doc.reference_name and doc.content:
		_comments = get_comments_from_parent(doc)

		updated = False
		for c in _comments:
			if c.get("name")==doc.name:
				c["comment"] = get_truncated(doc.content)
				updated = True

		if not updated:
			_comments.append({
				"comment": get_truncated(doc.content),

				# "comment_email" for Comment and "sender" for Communication
				"by": getattr(doc, 'comment_email', None) or getattr(doc, 'sender', None) or doc.owner,
				"name": doc.name
			})

		update_comments_in_parent(doc.reference_doctype, doc.reference_name, _comments)


def get_comments_from_parent(doc):
	'''
	get the list of comments cached in the document record in the column
	`_comments`
	'''
	try:
		_comments = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "_comments") or "[]"

	except Exception as e:
		if frappe.db.is_missing_table_or_column(e):
			_comments = "[]"

		else:
			raise

	try:
		return json.loads(_comments)
	except ValueError:
		return []

def update_comments_in_parent(reference_doctype, reference_name, _comments):
	"""Updates `_comments` property in parent Document with given dict.

	:param _comments: Dict of comments."""
	if not reference_doctype or frappe.db.get_value("DocType", reference_doctype, "issingle"):
		return

	try:
		# use sql, so that we do not mess with the timestamp
		frappe.db.sql("""update `tab{0}` set `_comments`=%s where name=%s""".format(reference_doctype), # nosec
			(json.dumps(_comments[-50:]), reference_name))

	except Exception as e:
		if frappe.db.is_column_missing(e) and getattr(frappe.local, 'request', None):
			# missing column and in request, add column and update after commit
			frappe.local._comments = (getattr(frappe.local, "_comments", [])
				+ [(reference_doctype, reference_name, _comments)])

		elif frappe.db.is_data_too_long(e):
			raise frappe.DataTooLongException

		else:
			raise ImplicitCommitError

	else:
		if not frappe.flags.in_patch:
			reference_doc = frappe.get_doc(reference_doctype, reference_name)
			if getattr(reference_doc, "route", None):
				clear_cache(reference_doc.route)

def update_comments_in_parent_after_request():
	"""update _comments in parent if _comments column is missing"""
	if hasattr(frappe.local, "_comments"):
		for (reference_doctype, reference_name, _comments) in frappe.local._comments:
			add_column(reference_doctype, "_comments", "Text")
			update_comments_in_parent(reference_doctype, reference_name, _comments)

		frappe.db.commit()
