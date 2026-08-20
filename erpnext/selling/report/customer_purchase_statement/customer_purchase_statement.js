// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Customer Purchase Statement"] = {
	onload(report) {
		report.page.add_inner_button(__("Download PDF"), () => {
			const values = report.get_values();
			const required_filters = ["company", "customer", "from_date", "to_date"];
			if (required_filters.some((fieldname) => !values[fieldname])) {
				frappe.msgprint(__("Please set Company, Customer, From Date, and To Date first."));
				return;
			}

			const query = new URLSearchParams({
				customer: values.customer,
				company: values.company,
				from_date: values.from_date,
				to_date: values.to_date,
			});
			if (values.letter_head) query.set("letter_head", values.letter_head);
			if (values.print_format) query.set("print_format", values.print_format);

			window.open(
				frappe.urllib.get_full_url(
					"/api/method/erpnext.selling.report.customer_purchase_statement.customer_purchase_statement.download_statement?" +
						query.toString()
				),
				"_blank"
			);
		});
	},
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "letter_head",
			label: __("Letter Head"),
			fieldtype: "Link",
			options: "Letter Head",
			get_query: () => ({ filters: { disabled: 0 } }),
		},
		{
			fieldname: "print_format",
			label: __("Print Format"),
			fieldtype: "Link",
			options: "Print Format",
			get_query: () => ({
				filters: {
					disabled: 0,
					print_format_for: "Report",
					report: "Customer Purchase Statement",
					print_format_type: "Jinja",
				},
			}),
		},
	],
};
