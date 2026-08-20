from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from erpnext.controllers.website_list_for_contact import get_parents_for_user
from erpnext.selling.report.customer_purchase_statement.customer_purchase_statement import (
	get_available_companies,
	get_available_letter_heads,
	get_available_print_formats,
	get_statement_context,
)

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view your statement"), frappe.PermissionError)

	customers = get_parents_for_user("Customer")
	if not customers:
		frappe.throw(_("Your user is not linked to a Customer"), frappe.PermissionError)

	selected_customer = frappe.form_dict.get("customer") or customers[0]
	if selected_customer not in customers:
		frappe.throw(_("You are not permitted to view this customer statement"), frappe.PermissionError)

	companies = get_available_companies(selected_customer)
	selected_company = frappe.form_dict.get("company") or (companies[0] if companies else None)
	from_date = getdate(frappe.form_dict.get("from_date") or add_months(today(), -12))
	to_date = getdate(frappe.form_dict.get("to_date") or today())
	selected_letter_head = frappe.form_dict.get("letter_head")
	selected_print_format = frappe.form_dict.get("print_format")

	context.no_cache = 1
	context.title = _("My Statement")
	context.customers = customers
	context.companies = companies
	context.selected_customer = selected_customer
	context.selected_company = selected_company
	context.from_date = from_date
	context.to_date = to_date
	context.letter_heads = get_available_letter_heads()
	context.print_formats = get_available_print_formats()
	context.selected_letter_head = selected_letter_head
	context.selected_print_format = selected_print_format
	context.statement = None

	if selected_company:
		context.statement = get_statement_context(
			{
				"customer": selected_customer,
				"company": selected_company,
				"from_date": from_date,
				"to_date": to_date,
				"letter_head": selected_letter_head,
				"print_format": selected_print_format,
			}
		)
		context.selected_letter_head = context.statement.filters.get("letter_head")
		download_query = urlencode(
			{
				"customer": selected_customer,
				"company": selected_company,
				"from_date": from_date,
				"to_date": to_date,
				"letter_head": selected_letter_head or "",
				"print_format": selected_print_format or "",
			}
		)
		context.download_url = (
			"/api/method/erpnext.selling.report.customer_purchase_statement."
			f"customer_purchase_statement.download_statement?{download_query}"
		)

	return context
