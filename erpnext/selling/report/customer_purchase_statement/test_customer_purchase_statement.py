# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
from erpnext.accounts.test.accounts_mixin import AccountsTestMixin
from erpnext.selling.report.customer_purchase_statement.customer_purchase_statement import (
	execute,
	get_balance_summary,
	render_statement,
	validate_print_format,
)


class TestCustomerPurchaseStatement(AccountsTestMixin, FrappeTestCase):
	def setUp(self):
		self.create_company()
		self.create_customer()
		self.create_item()
		self.clear_old_entries()

	def tearDown(self):
		frappe.db.rollback()

	def make_invoice(self, qty=1, rate=100, submit=True):
		invoice = create_sales_invoice(
			item=self.item,
			company=self.company,
			customer=self.customer,
			debit_to=self.debit_to,
			posting_date=today(),
			parent_cost_center=self.cost_center,
			cost_center=self.cost_center,
			qty=qty,
			rate=rate,
			price_list_rate=rate,
			do_not_save=1,
		).save()
		if submit:
			invoice.submit()
		return invoice

	def test_aggregates_submitted_invoice_items(self):
		self.make_invoice(qty=2, rate=50)
		self.make_invoice(qty=3, rate=60)
		self.make_invoice(qty=10, rate=10, submit=False)

		_columns, data, _message, _chart, _summary = execute(
			{
				"company": self.company,
				"customer": self.customer,
				"from_date": today(),
				"to_date": today(),
			}
		)

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0].item_code, self.item)
		self.assertEqual(data[0].purchased_qty, 5)
		self.assertEqual(data[0].returned_qty, 0)
		self.assertEqual(data[0].net_qty, 5)
		self.assertEqual(data[0].net_amount, 280)

	def test_balance_summary_uses_limit_and_exposure(self):
		self.make_invoice(rate=100)
		customer = frappe.get_doc("Customer", self.customer)
		customer.credit_limits = []
		customer.append("credit_limits", {"company": self.company, "credit_limit": 500})
		customer.save()

		balances = get_balance_summary(self.customer, self.company)

		self.assertEqual(balances.credit_limit, 500)
		self.assertEqual(balances.amount_due, 100)
		self.assertEqual(balances.available_balance, 400)

	def test_returns_are_reported_separately(self):
		invoice = self.make_invoice(qty=5, rate=20)
		credit_note = make_sales_return(invoice.name)
		credit_note.items[0].qty = -2
		credit_note.save().submit()

		_columns, data, _message, _chart, _summary = execute(
			{
				"company": self.company,
				"customer": self.customer,
				"from_date": today(),
				"to_date": today(),
			}
		)

		self.assertEqual(data[0].purchased_qty, 5)
		self.assertEqual(data[0].returned_qty, 2)
		self.assertEqual(data[0].net_qty, 3)

	def test_print_format_must_belong_to_statement_report(self):
		print_format = frappe._dict(
			{
				"name": "Wrong Report Format",
				"disabled": 0,
				"print_format_for": "Report",
				"report": "General Ledger",
				"print_format_type": "Jinja",
			}
		)
		with patch.object(frappe, "get_cached_doc", return_value=print_format):
			with self.assertRaises(frappe.ValidationError):
				validate_print_format(print_format.name)

	def test_custom_print_format_is_used_for_pdf(self):
		print_format = frappe._dict(
			{
				"name": "Customer Statement Custom",
				"html": "<div>Custom statement</div>",
			}
		)
		context = {"filters": frappe._dict({"print_format": print_format.name})}

		def render_template(template, template_context):
			if template == print_format.html:
				return "custom-body"
			return f"wrapped:{template_context['body']}:{template_context['css']}"

		with (
			patch(
				"erpnext.selling.report.customer_purchase_statement.customer_purchase_statement.validate_print_format",
				return_value=print_format,
			),
			patch(
				"erpnext.selling.report.customer_purchase_statement.customer_purchase_statement.get_print_style",
				return_value="custom-css",
			),
			patch.object(frappe, "render_template", side_effect=render_template),
		):
			html = render_statement(context)

		self.assertEqual(html, "wrapped:custom-body:custom-css")
