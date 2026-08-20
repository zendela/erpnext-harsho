# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe


def execute():
	if not frappe.db.exists("Role", "Credit Limit Manager"):
		role = frappe.new_doc("Role")
		role.update({"role_name": "Credit Limit Manager", "desk_access": 1})
		role.insert(ignore_permissions=True)
