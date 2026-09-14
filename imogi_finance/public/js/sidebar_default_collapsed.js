// Collapses the page-level right sidebar by default on Form and List views
// (the "Assigned To / Attachments / Tags / Share" panel on a document, and
// the filters/saved-filters panel on a list — both are the same
// `.layout-side-section` element, just filled with different content) so the
// content area uses the full width. Users can still open it via the existing
// "Toggle Sidebar" button; this only changes what happens on first load of
// each document/list, since Frappe doesn't persist that toggle by itself.
//
// We patch frappe.ui.Page.prototype.setup_sidebar_toggle (called once per
// Page instance, i.e. once per document/list route) instead of editing core
// files, and only act on Form/List routes so Workspace and other pages that
// also use `.layout-side-section` for navigation are left untouched.
(function () {
	function is_form_or_list_route() {
		const route = frappe.get_route();
		return !!route && (route[0] === "Form" || route[0] === "List");
	}

	frappe.after_ajax(function () {
		if (!frappe.ui || !frappe.ui.Page) return;

		const original = frappe.ui.Page.prototype.setup_sidebar_toggle;
		frappe.ui.Page.prototype.setup_sidebar_toggle = function (...args) {
			const result = original.apply(this, args);

			if (
				!this.disable_sidebar_toggle &&
				is_form_or_list_route() &&
				!frappe.utils.is_xs() &&
				!frappe.utils.is_sm()
			) {
				const sidebar_wrapper = this.wrapper.find(".layout-side-section");
				if (sidebar_wrapper.length) {
					sidebar_wrapper.hide();
					this.update_sidebar_icon();
				}
			}

			return result;
		};
	});
})();
