import frappe
from frappe.core.doctype.data_import.data_import import download_template as core_download_template
from frappe.core.doctype.data_import.exporter import Exporter


def format_idr_number(value):
	"""Format a number as Indonesian-style grouped text, e.g. 1000000 -> '1.000.000'."""
	try:
		value = float(value)
	except (TypeError, ValueError):
		return value

	if value == int(value):
		text = f"{int(value):,}"
	else:
		text = f"{value:,.2f}"

	# swap "," and "." to match Indonesian grouping (dot thousands, comma decimals)
	return text.replace(",", "X").replace(".", ",").replace("X", ".")


class SalesInvoiceExporter(Exporter):
	def add_data_row(self, doctype, parentfield, doc, rows, row_idx):
		rows = super().add_data_row(doctype, parentfield, doc, rows, row_idx)
		row = rows[row_idx]

		for i, df in enumerate(self.fields):
			if df.parent != doctype:
				continue
			if df.is_child_table_field and df.child_table_df.fieldname != parentfield:
				continue
			if df.fieldtype == "Currency" and row[i] not in (None, ""):
				row[i] = format_idr_number(row[i])

		return rows


@frappe.whitelist()
def download_template(doctype, export_fields=None, export_records=None, export_filters=None, file_type="CSV"):
	if doctype != "Sales Invoice":
		return core_download_template(
			doctype,
			export_fields=export_fields,
			export_records=export_records,
			export_filters=export_filters,
			file_type=file_type,
		)

	frappe.has_permission(doctype, "read", throw=True)

	export_fields = frappe.parse_json(export_fields)
	export_filters = frappe.parse_json(export_filters)
	export_data = export_records != "blank_template"

	e = SalesInvoiceExporter(
		doctype,
		export_fields=export_fields,
		export_data=export_data,
		export_filters=export_filters,
		file_type=file_type,
		export_page_length=5 if export_records == "5_records" else None,
	)
	e.build_response()
