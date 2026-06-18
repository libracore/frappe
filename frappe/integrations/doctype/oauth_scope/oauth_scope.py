# Copyright (c) 2020, Frappe Technologies and contributors
# License: MIT. See LICENSE

# import frappe
from frappe.model.document import Document


class OAuthScope(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		parent = None # type: DF.Data
		parentfield = None # type: DF.Data
		parenttype = None # type: DF.Data
		scope = None # type: DF.Data | None
	# end: auto-generated types

	pass
