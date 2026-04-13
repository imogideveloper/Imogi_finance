frappe.after_ajax(function() {
    const _original = frappe.views.ListView.prototype.setup_defaults;
    frappe.views.ListView.prototype.setup_defaults = async function() {
        await _original.call(this);
        this.page_length = 2500;
    };
});