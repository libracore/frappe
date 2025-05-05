# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _, msgprint
from frappe.utils import cint, cstr, get_url, now_datetime
from frappe.utils.data import getdate
from frappe.utils.verified_command import get_signed_params, verify_request

# After this percent of failures in every batch, entire batch is aborted.
# This usually indicates a systemic failure so we shouldn't keep trying to send emails.
EMAIL_QUEUE_BATCH_FAILURE_THRESHOLD_PERCENT = 0.33
EMAIL_QUEUE_BATCH_FAILURE_THRESHOLD_COUNT = 10


def get_emails_sent_this_month(email_account=None):
	"""Get count of emails sent from a specific email account.

	:param email_account: name of the email account used to send mail

	if email_account=None, email account filter is not applied while counting
	"""
	today = getdate()
	month_start = today.replace(day=1)

	filters = {
		"status": "Sent",
		"creation": [">=", str(month_start)],
	}
	if email_account:
		filters["email_account"] = email_account

	return frappe.db.count("Email Queue", filters=filters)


def get_emails_sent_today(email_account=None):
	"""Get count of emails sent from a specific email account.

	:param email_account: name of the email account used to send mail

	if email_account=None, email account filter is not applied while counting
	"""
	q = """
		SELECT
			COUNT(`name`)
		FROM
			`tabEmail Queue`
		WHERE
			`status` in ('Sent', 'Not Sent', 'Sending')
			AND
			`creation` > (NOW() - INTERVAL '24' HOUR)
	"""

	q_args = {}
	if email_account is not None:
		if email_account:
			q += " AND email_account = %(email_account)s"
			q_args["email_account"] = email_account
		else:
			q += " AND (email_account is null OR email_account='')"

	return frappe.db.sql(q, q_args)[0][0]


def get_unsubscribe_message(unsubscribe_message: str, expose_recipients: str) -> "frappe._dict[str, str]":
	unsubscribe_message = unsubscribe_message or _("Unsubscribe")
	unsubscribe_link = f'<a href="<!--unsubscribe_url-->" target="_blank">{unsubscribe_message}</a>'
	unsubscribe_html = _("{0} to stop receiving emails of this type").format(unsubscribe_link)
	html = f"""<div class="email-unsubscribe">
			<!--cc_message-->
			<div>
				{unsubscribe_html}
			</div>
		</div>"""

	text = f"\n\n{unsubscribe_message}: <!--unsubscribe_url-->\n"
	if expose_recipients == "footer":
		text = f"\n<!--cc_message-->{text}"

	return frappe._dict(html=html, text=text)


def get_unsubcribed_url(reference_doctype, reference_name, email, unsubscribe_method, unsubscribe_params):
	params = {
		"email": cstr(email),
		"doctype": cstr(reference_doctype),
		"name": cstr(reference_name),
	}
	if unsubscribe_params:
		params.update(unsubscribe_params)

	return get_url(unsubscribe_method + "?" + get_signed_params(params))


@frappe.whitelist(allow_guest=True)
def unsubscribe(doctype, name, email):
	# unsubsribe from comments and communications
	if not frappe.flags.in_test and not verify_request():
		return

	try:
		frappe.get_doc(
			{
				"doctype": "Email Unsubscribe",
				"email": email,
				"reference_doctype": doctype,
				"reference_name": name,
			}
		).insert(ignore_permissions=True)

	except frappe.DuplicateEntryError:
		frappe.db.rollback()

	else:
		frappe.db.commit()

	return_unsubscribed_page(email, doctype, name)


def return_unsubscribed_page(email, doctype, name):
	frappe.respond_as_web_page(
		_("Unsubscribed"),
		_("{0} has left the conversation in {1} {2}").format(email, _(doctype), name),
		indicator_color="green",
	)


def flush():
	"""flush email queue, every time: called from scheduler.

	This should not be called outside of background jobs.
	"""
	from frappe.email.doctype.email_queue.email_queue import EmailQueue

	# To avoid running jobs inside unit tests
	if frappe.are_emails_muted():
		msgprint(_("Emails are muted"))

	if cint(frappe.db.get_default("suspend_email_queue")) == 1:
		return

	email_queue_batch = get_queue()
	if not email_queue_batch:
		return

	failed_email_queues = []
	for row in email_queue_batch:
		try:
			email_queue: EmailQueue = frappe.get_doc("Email Queue", row.name)
			email_queue.send()
		except Exception:
			frappe.get_doc("Email Queue", row.name).log_error()
			failed_email_queues.append(row.name)

			if (
				len(failed_email_queues) / len(email_queue_batch)
				> EMAIL_QUEUE_BATCH_FAILURE_THRESHOLD_PERCENT
				and len(failed_email_queues) > EMAIL_QUEUE_BATCH_FAILURE_THRESHOLD_COUNT
			):
				frappe.throw(_("Email Queue flushing aborted due to too many failures."))


def get_queue():
	batch_size = cint(frappe.conf.email_queue_batch_size) or 500

	return frappe.db.sql(
		f"""select
			name, sender
		from
			`tabEmail Queue`
		where
			(status='Not Sent' or status='Partially Sent') and
			(send_after is null or send_after < %(now)s)
		order
			by priority desc, retry asc, creation asc
		limit {batch_size}""",
		{"now": now_datetime()},
		as_dict=True,
	)



def send(recipients=None, sender=None, subject=None, message=None, text_content=None, reference_doctype=None,
		reference_name=None, unsubscribe_method=None, unsubscribe_params=None, unsubscribe_message=None,
		attachments=None, reply_to=None, cc=[], bcc=[], message_id=None, in_reply_to=None, send_after=None,
		expose_recipients=None, send_priority=1, communication=None, now=False, read_receipt=None,
		queue_separately=False, is_notification=False, add_unsubscribe_link=1, inline_images=None,
		header=None, print_letterhead=False):
	"""Add email to sending queue (Email Queue)

	:param recipients: List of recipients.
	:param sender: Email sender.
	:param subject: Email subject.
	:param message: Email message.
	:param text_content: Text version of email message.
	:param reference_doctype: Reference DocType of caller document.
	:param reference_name: Reference name of caller document.
	:param send_priority: Priority for Email Queue, default 1.
	:param unsubscribe_method: URL method for unsubscribe. Default is `/api/method/frappe.email.queue.unsubscribe`.
	:param unsubscribe_params: additional params for unsubscribed links. default are name, doctype, email
	:param attachments: Attachments to be sent.
	:param reply_to: Reply to be captured here (default inbox)
	:param in_reply_to: Used to send the Message-Id of a received email back as In-Reply-To.
	:param send_after: Send this email after the given datetime. If value is in integer, then `send_after` will be the automatically set to no of days from current date.
	:param communication: Communication link to be set in Email Queue record
	:param now: Send immediately (don't send in the background)
	:param queue_separately: Queue each email separately
	:param is_notification: Marks email as notification so will not trigger notifications from system
	:param add_unsubscribe_link: Send unsubscribe link in the footer of the Email, default 1.
	:param inline_images: List of inline images as {"filename", "filecontent"}. All src properties will be replaced with random Content-Id
	:param header: Append header in email (boolean)
	"""
	if not unsubscribe_method:
		unsubscribe_method = "/api/method/frappe.email.queue.unsubscribe"

	if not recipients and not cc:
		return

	if isinstance(recipients, string_types):
		recipients = split_emails(recipients)

	if isinstance(cc, string_types):
		cc = split_emails(cc)

	if isinstance(bcc, string_types):
		bcc = split_emails(bcc)

	if isinstance(send_after, int):
		send_after = add_days(nowdate(), send_after)

	email_account = get_outgoing_email_account(True, append_to=reference_doctype, sender=sender)
	if not sender or sender == "Administrator":
		sender = email_account.default_sender


	if not text_content:
		try:
			text_content = html2text(message)
		except HTMLParser.HTMLParseError:
			text_content = "See html attachment"

	recipients = list(set(recipients))
	cc = list(set(cc))

	all_ids = tuple(recipients + cc)

	unsubscribed = frappe.db.sql_list('''
		SELECT
			distinct email
		from
			`tabEmail Unsubscribe`
		where
			email in %(all_ids)s
			and (
				(
					reference_doctype = %(reference_doctype)s
					and reference_name = %(reference_name)s
				)
				or global_unsubscribe = 1
			)
	''', {
		'all_ids': all_ids,
		'reference_doctype': reference_doctype,
		'reference_name': reference_name,
	})

	recipients = [r for r in recipients if r and r not in unsubscribed]

	if cc:
		cc = [r for r in cc if r and r not in unsubscribed]

	if not recipients and not cc:
		# Recipients may have been unsubscribed, exit quietly
		return

	email_text_context = text_content

	should_append_unsubscribe = (add_unsubscribe_link
		and reference_doctype
		and (unsubscribe_message or reference_doctype=="Newsletter")
		and add_unsubscribe_link==1)

	unsubscribe_link = None
	if should_append_unsubscribe:
		unsubscribe_link = get_unsubscribe_message(unsubscribe_message, expose_recipients)
		email_text_context += unsubscribe_link.text

	email_content = get_formatted_html(subject, message,
		email_account=email_account, header=header,
		unsubscribe_link=unsubscribe_link)

	# add to queue
	add(recipients, sender, subject,
		formatted=email_content,
		text_content=email_text_context,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		attachments=attachments,
		reply_to=reply_to,
		cc=cc,
		bcc=bcc,
		message_id=message_id,
		in_reply_to=in_reply_to,
		send_after=send_after,
		send_priority=send_priority,
		email_account=email_account,
		communication=communication,
		add_unsubscribe_link=add_unsubscribe_link,
		unsubscribe_method=unsubscribe_method,
		unsubscribe_params=unsubscribe_params,
		expose_recipients=expose_recipients,
		read_receipt=read_receipt,
		queue_separately=queue_separately,
		is_notification = is_notification,
		inline_images = inline_images,
		header=header,
		now=now,
		print_letterhead=print_letterhead)
