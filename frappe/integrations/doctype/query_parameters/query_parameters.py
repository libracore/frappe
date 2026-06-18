# Copyright (c) 2020, Frappe Technologies and contributors
# License: MIT. See LICENSE

# import frappe
from frappe.model.document import Document


class QueryParameters(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		key = None  # type: DF.Data
		parent = None  # type: DF.Data
		parentfield = None  # type: DF.Data
		parenttype = None  # type: DF.Data
		value = None  # type: DF.Data
	# end: auto-generated types

	pass
