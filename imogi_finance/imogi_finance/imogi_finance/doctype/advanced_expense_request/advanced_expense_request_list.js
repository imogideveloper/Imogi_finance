(() => {
  frappe.listview_settings["Advanced Expense Request"] = {
    add_fields: ["status", "docstatus", "supplier", "total_amount"],

    get_indicator(doc) {
      if (doc.status === "Paid") {
        return [__("💰 Paid"), "green", "status,=,Paid"];
      }
      if (doc.status === "Return") {
        return [__("🔄 Return"), "purple", "status,=,Return"];
      }
      if (doc.status === "PI Created") {
        return [__("📄 PI Created"), "blue", "status,=,PI Created"];
      }
      if (doc.status === "Approved") {
        return [__("✅ Approved"), "green", "status,=,Approved"];
      }
      if (doc.status === "Pending Review") {
        return [__("⏳ Pending Review"), "orange", "status,=,Pending Review"];
      }
      if (doc.status === "Rejected") {
        return [__("❌ Rejected"), "red", "status,=,Rejected"];
      }
      if (doc.status === "Cancelled") {
        return [__("🚫 Cancelled"), "darkgrey", "status,=,Cancelled"];
      }

      return [__(doc.status || "📝 Draft"), "blue", "status,=," + (doc.status || "Draft")];
    },
  };
})();
