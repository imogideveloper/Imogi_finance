(function () {
	const METHOD =
		"imogi_finance.payroll.salary_structure_assignment.get_current_user_assignment_contract_reminders";
	const SESSION_KEY = "imogi_finance:ssa_contract_reminder_toast";

	function can_show_reminder() {
		return (
			window.frappe &&
			frappe.session &&
			frappe.session.user !== "Guest" &&
			frappe.user &&
			(frappe.user.has_role("HR Manager") || frappe.user.has_role("HR User"))
		);
	}

	function get_seen_reminders() {
		try {
			return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]");
		} catch (e) {
			return [];
		}
	}

	function set_seen_reminders(names) {
		try {
			sessionStorage.setItem(SESSION_KEY, JSON.stringify(names));
		} catch (e) {
			// Ignore private browsing/session storage restrictions.
		}
	}

	function show_assignment_contract_reminders() {
		if (!can_show_reminder()) {
			return;
		}

		frappe.call({
			method: METHOD,
			args: { limit: 5 },
			callback: (r) => {
				const reminders = r.message || [];
				if (!reminders.length) {
					return;
				}

				const seen = new Set(get_seen_reminders());
				const shown = [];
				reminders.forEach((item) => {
					if (!item.name || seen.has(item.name)) {
						return;
					}

					const contract = frappe.utils.escape_html(item.reference_name || "");
					const message = frappe.utils.escape_html(
						item.message || __("Ada Assignment Contract yang perlu diperbarui.")
					);
					const indicator = item.priority === "High" ? "red" : "orange";

					frappe.show_alert(
						{
							message: `${message} <a class="text-muted" href="/app/salary-structure-assignment/${encodeURIComponent(
								item.reference_name || ""
							)}">${__("Buka Contract")} ${contract}</a>`,
							indicator,
						},
						12
					);
					shown.push(item.name);
				});

				if (shown.length) {
					set_seen_reminders([...seen, ...shown]);
				}
			},
		});
	}

	if (typeof frappe.ready === "function") {
		frappe.ready(() => {
			setTimeout(show_assignment_contract_reminders, 1500);
		});
	} else {
		setTimeout(show_assignment_contract_reminders, 2500);
	}
})();
