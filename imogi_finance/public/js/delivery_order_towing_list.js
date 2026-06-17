// List view Delivery Order Towing — indicator mengikuti field status

const DO_TOWING_STATUS_COLORS = {
	Draft: "red",
	Assigned: "orange",
	"Pick Up": "purple",
	Delivered: "green",
	"Awaiting Dokument": "yellow",
	Done: "darkgreen",
	Cancelled: "gray",
};

frappe.listview_settings["Delivery Order Towing"] = {
	get_indicator(doc) {
		if (doc.status) {
			return [
				__(doc.status),
				DO_TOWING_STATUS_COLORS[doc.status] || "gray",
				"status,=," + doc.status,
			];
		}
		if (doc.docstatus === 0) {
			return [__("Draft"), "red", "docstatus,=,0"];
		}
		if (doc.docstatus === 2) {
			return [__("Cancelled"), "gray", "docstatus,=,2"];
		}
		return [__("Draft"), "red", "docstatus,=,0"];
	},
};
