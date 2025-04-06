# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE


class DocStatus(int):
	def is_draft(self):
<<<<<<< HEAD
		return self == self.draft()

	def is_submitted(self):
		return self == self.submitted()

	def is_cancelled(self):
		return self == self.cancelled()

	@classmethod
	def draft(cls):
		return cls(0)

	@classmethod
	def submitted(cls):
		return cls(1)

	@classmethod
	def cancelled(cls):
		return cls(2)
=======
		return self == DocStatus.DRAFT

	def is_submitted(self):
		return self == DocStatus.SUBMITTED

	def is_cancelled(self):
		return self == DocStatus.CANCELLED

	# following methods have been kept for backwards compatibility

	@staticmethod
	def draft():
		return DocStatus.DRAFT

	@staticmethod
	def submitted():
		return DocStatus.SUBMITTED

	@staticmethod
	def cancelled():
		return DocStatus.CANCELLED


DocStatus.DRAFT = DocStatus(0)
DocStatus.SUBMITTED = DocStatus(1)
DocStatus.CANCELLED = DocStatus(2)
>>>>>>> version-15
