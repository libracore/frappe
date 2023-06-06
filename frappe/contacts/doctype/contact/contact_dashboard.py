from frappe import _

def get_data():
    return {
        'fieldname': 'contact_person',
        'transactions': [
            {
                'label': _("Selling"),
                'items': ['Sales Order', 'Delivery Note', 'Sales Invoice']
            }
        ]
    }
