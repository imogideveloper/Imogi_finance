/* Open Finance Monitor query report (charts + KPI) from workspace sidebar. */
(function () {
	const REPORT = "Finance Monitor Dashboard";
	const WORKSPACE_SLUG = "finance-monitor";

	function open_finance_monitor_report() {
		const route = frappe.get_route() || [];
		if (route[0] !== WORKSPACE_SLUG) {
			return;
		}
		frappe.set_route("query-report", REPORT);
	}

	frappe.router.on("change", () => {
		open_finance_monitor_report();
	});
})();
