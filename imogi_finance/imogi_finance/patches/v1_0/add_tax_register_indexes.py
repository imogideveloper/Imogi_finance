"""
Migration Patch: Add Database Indexes for Tax Registers

Adds composite indexes to optimize query performance for:
- VAT Input Register (Purchase Invoice queries with GL Entry JOINs)
- VAT Output Register (Sales Invoice queries with GL Entry JOINs)  
- Withholding Register (GL Entry queries by account and date)

Safe to run multiple times (uses IF NOT EXISTS pattern).
"""

import frappe
from frappe.utils import cint


def execute():
	"""Create indexes for tax register reports performance."""
	
	frappe.logger().info("Starting tax register index creation...")
	
	# Only proceed if database supports indexes (MariaDB/MySQL)
	if not frappe.db.db_type in ["mariadb", "mysql"]:
		frappe.logger().info(f"Skipping index creation for {frappe.db.db_type}")
		return
	
	# Check if we should skip (useful for development)
	skip_index = cint(frappe.conf.get("skip_tax_register_indexes", 0))
	if skip_index:
		frappe.logger().info("Skipping tax register indexes (configured in site_config)")
		return
	
	try:
		create_purchase_invoice_indexes()
		create_sales_invoice_indexes()
		create_gl_entry_indexes()
		frappe.logger().info("Tax register indexes created successfully")
	except Exception as e:
		frappe.logger().error(f"Error creating tax register indexes: {str(e)}")
		# Don't fail the patch - indexes are optimization only
		pass


def create_purchase_invoice_indexes():
	"""
	Create indexes for Purchase Invoice to optimize VAT Input Register queries.
	
	Query pattern:
	- Filter by docstatus, ti_verification_status, posting_date, company, supplier
	- JOIN with GL Entry on voucher_no
	"""
	frappe.logger().info("Creating Purchase Invoice indexes...")
	
	# Composite index for VAT Input Register main query
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_pi_vat_register
		ON `tabPurchase Invoice` (docstatus, ti_verification_status, posting_date, company)
	""")
	
	# Index for supplier filtering
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_pi_supplier_date
		ON `tabPurchase Invoice` (supplier, posting_date, docstatus)
	""")
	
	frappe.db.commit()
	frappe.logger().info("Purchase Invoice indexes created")


def create_sales_invoice_indexes():
	"""
	Create indexes for Sales Invoice to optimize VAT Output Register queries.
	
	Query pattern:
	- Filter by docstatus, out_fp_status, posting_date, company, customer
	- JOIN with GL Entry on voucher_no
	"""
	frappe.logger().info("Creating Sales Invoice indexes...")
	
	# Composite index for VAT Output Register main query
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_si_vat_register
		ON `tabSales Invoice` (docstatus, out_fp_status, posting_date, company)
	""")
	
	# Index for customer filtering
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_si_customer_date
		ON `tabSales Invoice` (customer, posting_date, docstatus)
	""")
	
	frappe.db.commit()
	frappe.logger().info("Sales Invoice indexes created")


def create_gl_entry_indexes():
	"""
	Create indexes for GL Entry to optimize:
	1. JOINs with Purchase/Sales Invoice (voucher_type, voucher_no)
	2. Withholding Register queries (company, account, posting_date, is_cancelled)
	
	Note: GL Entry already has some indexes from ERPNext core,
	but we add specific ones for our tax register query patterns.
	"""
	frappe.logger().info("Creating GL Entry indexes...")
	
	# Composite index for Withholding Register queries
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_gl_withholding_register
		ON `tabGL Entry` (company, is_cancelled, account, posting_date)
	""")
	
	# Covering index for voucher lookups (used in JOINs)
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_gl_voucher_lookup
		ON `tabGL Entry` (voucher_type, voucher_no, company, is_cancelled)
	""")
	
	# Index for party-based filtering
	frappe.db.sql("""
		CREATE INDEX IF NOT EXISTS idx_gl_party_date
		ON `tabGL Entry` (party_type, party, posting_date, is_cancelled)
	""")
	
	frappe.db.commit()
	frappe.logger().info("GL Entry indexes created")


def get_index_info(table_name):
	"""
	Get information about existing indexes on a table (for debugging).
	
	Args:
		table_name: Name of the table (e.g., 'Purchase Invoice')
		
	Returns:
		List of index information dictionaries
	"""
	return frappe.db.sql(f"""
		SHOW INDEX FROM `tab{table_name}`
	""", as_dict=True)


def analyze_table(table_name):
	"""
	Run ANALYZE TABLE to update index statistics (optional optimization).
	
	Args:
		table_name: Name of the table to analyze
	"""
	try:
		frappe.db.sql(f"""
			ANALYZE TABLE `tab{table_name}`
		""")
		frappe.logger().info(f"Analyzed table: {table_name}")
	except Exception as e:
		frappe.logger().error(f"Error analyzing table {table_name}: {str(e)}")


def verify_indexes():
	"""
	Verify that all required indexes exist (for testing/validation).
	
	Returns:
		Dictionary with verification results
	"""
	results = {
		"purchase_invoice": [],
		"sales_invoice": [],
		"gl_entry": []
	}
	
	# Check Purchase Invoice indexes
	pi_indexes = get_index_info("Purchase Invoice")
	pi_index_names = [idx.get("Key_name") for idx in pi_indexes]
	results["purchase_invoice"] = {
		"idx_pi_vat_register": "idx_pi_vat_register" in pi_index_names,
		"idx_pi_supplier_date": "idx_pi_supplier_date" in pi_index_names
	}
	
	# Check Sales Invoice indexes
	si_indexes = get_index_info("Sales Invoice")
	si_index_names = [idx.get("Key_name") for idx in si_indexes]
	results["sales_invoice"] = {
		"idx_si_vat_register": "idx_si_vat_register" in si_index_names,
		"idx_si_customer_date": "idx_si_customer_date" in si_index_names
	}
	
	# Check GL Entry indexes
	gl_indexes = get_index_info("GL Entry")
	gl_index_names = [idx.get("Key_name") for idx in gl_indexes]
	results["gl_entry"] = {
		"idx_gl_withholding_register": "idx_gl_withholding_register" in gl_index_names,
		"idx_gl_voucher_lookup": "idx_gl_voucher_lookup" in gl_index_names,
		"idx_gl_party_date": "idx_gl_party_date" in gl_index_names
	}
	
	return results
