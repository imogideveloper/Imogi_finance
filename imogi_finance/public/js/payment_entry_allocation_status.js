// Payment Entry: always show Allocated / Unallocated (never ERPNext "Submitted" badge).

function imogi_pe_allocation_indicator(doc) {
	if (!doc || doc.doctype !== "Payment Entry") {
		return null;
	}
	if (doc.docstatus == 2) {
		return [__("Cancelled"), "red", "docstatus,=,2"];
	}
	if (doc.docstatus == 0) {
		return [__("Draft"), "grey", "docstatus,=,0"];
	}
	const unalloc = parseFloat(doc.unallocated_amount || 0);
	if (unalloc > 0) {
		return [__("Unallocated"), "orange", "unallocated_amount,>,0"];
	}
	if (doc.payment_status === "Unallocated") {
		return [__("Unallocated"), "orange", "payment_status,=,Unallocated"];
	}
	return [__("Allocated"), "green", "unallocated_amount,=,0"];
}

(function () {
	if (frappe._imogi_pe_indicator_patched) {
		return;
	}
	frappe._imogi_pe_indicator_patched = true;

	const _get_indicator = frappe.get_indicator;
	frappe.get_indicator = function (doc, doctype, show_workflow_state) {
		const dt = doctype || (doc && doc.doctype);
		if (dt === "Payment Entry") {
			const custom = imogi_pe_allocation_indicator(doc);
			if (custom) {
				return custom;
			}
		}
		return _get_indicator(doc, doctype, show_workflow_state);
	};
})();
