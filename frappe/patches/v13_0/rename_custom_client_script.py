import frappe
from frappe.model.rename_doc import rename_doc


def execute():
    if frappe.db.exists("DocType", "Client Script"):
        return

    # cleanup relics in case of an imported DB
    frappe.db.sql("""DROP TABLE `tabClient Script`;""")
    frappe.db.sql("""DELETE FROM `tabDocType` WHERE `name` = "Client Script";""")
    
    frappe.flags.ignore_route_conflict_validation = True
    rename_doc("DocType", "Custom Script", "Client Script")
    frappe.flags.ignore_route_conflict_validation = False

    frappe.reload_doctype("Client Script", force=True)
