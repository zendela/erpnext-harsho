# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt, getdate
from frappe.utils.pdf import get_pdf
from frappe.utils.user import is_website_user
from frappe.www.printview import get_letter_head, get_print_style

from erpnext.selling.doctype.customer.customer import get_credit_limit, get_customer_outstanding


def execute(filters=None):
	filters = validate_filters(filters)
	validate_statement_access(filters.customer)
	validate_company_access(filters.customer, filters.company)

	data = get_item_summary(filters)
	balances = get_balance_summary(filters.customer, filters.company)

	return get_columns(), data, None, None, get_report_summary(balances)


def validate_filters(filters=None):
	filters = frappe._dict(filters or {})
	for fieldname in ("company", "customer", "from_date", "to_date"):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is required").format(_(frappe.unscrub(fieldname))))

	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))

	if not frappe.db.exists("Company", filters.company):
		frappe.throw(_("Company {0} does not exist").format(frappe.bold(filters.company)))
	if not frappe.db.exists("Customer", filters.customer):
		frappe.throw(_("Customer {0} does not exist").format(frappe.bold(filters.customer)))

	if filters.get("letter_head"):
		validate_letter_head(filters.letter_head)
	if filters.get("print_format"):
		validate_print_format(filters.print_format)

	return filters


def validate_letter_head(letter_head):
	if not frappe.db.exists("Letter Head", letter_head):
		frappe.throw(_("Letter Head {0} does not exist").format(frappe.bold(letter_head)))
	if frappe.get_cached_value("Letter Head", letter_head, "disabled"):
		frappe.throw(_("Letter Head {0} is disabled").format(frappe.bold(letter_head)))


def validate_print_format(print_format):
	print_format_doc = frappe.get_cached_doc("Print Format", print_format)
	if print_format_doc.disabled:
		frappe.throw(_("Print Format {0} is disabled").format(frappe.bold(print_format)))
	if print_format_doc.print_format_for != "Report" or print_format_doc.report != "Customer Purchase Statement":
		frappe.throw(
			_("Print Format {0} is not configured for the Customer Purchase Statement report").format(
				frappe.bold(print_format)
			)
		)
	if print_format_doc.print_format_type != "Jinja":
		frappe.throw(_("Only Jinja Print Formats are supported for this statement"))
	if not print_format_doc.html:
		frappe.throw(_("Print Format {0} does not contain an HTML template").format(frappe.bold(print_format)))

	return print_format_doc


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Purchased Qty"),
			"fieldname": "purchased_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Returned Qty"),
			"fieldname": "returned_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{"label": _("Net Qty"), "fieldname": "net_qty", "fieldtype": "Float", "width": 110},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"label": _("Net Purchase Value"),
			"fieldname": "net_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_item_summary(filters):
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

	purchased_qty = Sum(
		Case().when(sales_invoice_item.stock_qty > 0, sales_invoice_item.stock_qty).else_(0)
	).as_("purchased_qty")
	returned_qty = (
		-1 * Sum(Case().when(sales_invoice_item.stock_qty < 0, sales_invoice_item.stock_qty).else_(0))
	).as_("returned_qty")
	net_qty = Sum(sales_invoice_item.stock_qty).as_("net_qty")
	net_amount = Sum(sales_invoice_item.base_net_amount).as_("net_amount")

	query = (
		frappe.qb.from_(sales_invoice)
		.inner_join(sales_invoice_item)
		.on(sales_invoice.name == sales_invoice_item.parent)
		.select(
			sales_invoice_item.item_code,
			sales_invoice_item.item_name,
			sales_invoice_item.stock_uom,
			purchased_qty,
			returned_qty,
			net_qty,
			net_amount,
		)
		.where(sales_invoice.docstatus == 1)
		.where(sales_invoice.customer == filters.customer)
		.where(sales_invoice.company == filters.company)
		.where(sales_invoice.posting_date >= filters.from_date)
		.where(sales_invoice.posting_date <= filters.to_date)
		.groupby(
			sales_invoice_item.item_code,
			sales_invoice_item.item_name,
			sales_invoice_item.stock_uom,
		)
		.orderby(sales_invoice_item.item_name)
	)

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	data = query.run(as_dict=True)
	for row in data:
		row.currency = currency

	return data


def get_balance_summary(customer, company):
	ledger_balance = flt(
		frappe.db.get_value(
			"GL Entry",
			{
				"party_type": "Customer",
				"party": customer,
				"company": company,
				"is_cancelled": 0,
			},
			"sum(debit) - sum(credit)",
		)
	)
	bypass_sales_order_check = cint(
		frappe.db.get_value(
			"Customer Credit Limit",
			{"parent": customer, "parenttype": "Customer", "company": company},
			"bypass_credit_limit_check",
		)
	)
	exposure = flt(
		get_customer_outstanding(
			customer,
			company,
			ignore_outstanding_sales_order=bypass_sales_order_check,
		)
	)
	credit_limit = flt(get_credit_limit(customer, company))

	return frappe._dict(
		{
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"credit_limit": credit_limit,
			"amount_due": max(ledger_balance, 0),
			"advance_balance": max(-ledger_balance, 0),
			"committed_amount": max(exposure - ledger_balance, 0),
			"total_exposure": exposure,
			"available_balance": credit_limit - exposure,
		}
	)


def get_report_summary(balances):
	def summary(label, value, indicator="Blue"):
		return {
			"label": label,
			"value": value,
			"datatype": "Currency",
			"currency": balances.currency,
			"indicator": indicator,
		}

	return [
		summary(_("Credit Limit"), balances.credit_limit),
		summary(_("Amount Due"), balances.amount_due, "Orange" if balances.amount_due else "Green"),
		summary(_("Advance Balance"), balances.advance_balance, "Green"),
		summary(_("Committed Amount"), balances.committed_amount),
		summary(
			_("Available Balance"),
			balances.available_balance,
			"Green" if balances.available_balance >= 0 else "Red",
		),
	]


def validate_statement_access(customer):
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to view your statement"), frappe.PermissionError)

	if is_website_user():
		from erpnext.controllers.website_list_for_contact import get_parents_for_user

		if customer not in get_parents_for_user("Customer"):
			frappe.throw(_("You are not permitted to view this customer statement"), frappe.PermissionError)
	elif not frappe.has_permission("Customer", "read", doc=frappe.get_doc("Customer", customer)):
		frappe.throw(_("You are not permitted to view this customer statement"), frappe.PermissionError)


def get_available_companies(customer):
	companies = set(
		frappe.get_all(
			"Customer Credit Limit",
			filters={"parent": customer, "parenttype": "Customer"},
			pluck="company",
		)
	)
	companies.update(
		frappe.get_all("Sales Invoice", filters={"customer": customer, "docstatus": 1}, pluck="company")
	)
	companies.update(
		frappe.get_all(
			"GL Entry",
			filters={"party_type": "Customer", "party": customer, "is_cancelled": 0},
			pluck="company",
		)
	)
	return sorted(company for company in companies if company)


def get_available_letter_heads():
	return frappe.get_all("Letter Head", filters={"disabled": 0}, pluck="name", order_by="name")


def get_available_print_formats():
	return frappe.get_all(
		"Print Format",
		filters={
			"disabled": 0,
			"print_format_for": "Report",
			"report": "Customer Purchase Statement",
			"print_format_type": "Jinja",
		},
		pluck="name",
		order_by="name",
	)


def get_statement_context(filters):
	filters = validate_filters(filters)
	validate_statement_access(filters.customer)
	validate_company_access(filters.customer, filters.company)

	company = frappe.get_cached_doc("Company", filters.company)
	letter_head_name = filters.get("letter_head") or company.default_letter_head
	letter_head = None
	if letter_head_name:
		validate_letter_head(letter_head_name)
		filters.letter_head = letter_head_name
		letter_head = get_letter_head(
			frappe._dict({"company": filters.company, "letter_head": letter_head_name}),
			no_letterhead=0,
			letterhead=letter_head_name,
		)

	columns = get_columns()
	return {
		"filters": filters,
		"customer": frappe.get_cached_doc("Customer", filters.customer),
		"company": company,
		"report": frappe._dict(
			{"report_name": "Customer Purchase Statement", "columns": columns}
		),
		"columns": columns,
		"data": get_item_summary(filters),
		"balances": get_balance_summary(filters.customer, filters.company),
		"letter_head": letter_head,
	}


def validate_company_access(customer, company):
	if is_website_user() and company not in get_available_companies(customer):
		frappe.throw(_("You are not permitted to view a statement for this company"), frappe.PermissionError)


def render_statement(context):
	print_format_doc = None
	if context["filters"].get("print_format"):
		print_format_doc = validate_print_format(context["filters"].print_format)
		body = frappe.render_template(print_format_doc.html, context)
	else:
		body = frappe.render_template(
			"erpnext/selling/report/customer_purchase_statement/customer_purchase_statement.html",
			context,
		)

	return frappe.render_template(
		"frappe/www/printview.html",
		{
			"body": body,
			"css": get_print_style(None, print_format_doc),
			"title": _("Customer Purchase Statement"),
		},
	)


@frappe.whitelist()
def download_statement(customer, company, from_date, to_date, letter_head=None, print_format=None):
	context = get_statement_context(
		{
			"customer": customer,
			"company": company,
			"from_date": from_date,
			"to_date": to_date,
			"letter_head": letter_head,
			"print_format": print_format,
		}
	)
	html = render_statement(context)

	frappe.local.response.filename = f"{frappe.scrub(customer)}-purchase-statement.pdf"
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download"
