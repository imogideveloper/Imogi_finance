(() => {
  const ACTION_LABEL_CREATE_PI = __("Create PI");

  const getSelectedItems = (listview) => listview.get_checked_items?.() || [];

  const shouldShowCreatePi = (selectedItems) => {
    if (!selectedItems.length) {
      return false;
    }

    return selectedItems.every(
      (item) => item.docstatus === 1 && item.status === "Approved"
    );
  };

  const toggleCreatePiAction = (listview) => {
    const selectedItems = getSelectedItems(listview);
    const showAction = shouldShowCreatePi(selectedItems);
    const $actions =
      listview?.page?.actions || listview?.page?.page_actions || listview?.page?.wrapper;

    if (!$actions?.find) {
      return;
    }

    $actions
      .find("a")
      .filter(function () {
        return $(this).text().trim() === ACTION_LABEL_CREATE_PI;
      })
      .each(function () {
        $(this).toggle(showAction);
      });
  };

  // Three different places assign frappe.listview_settings["Expense Request"]: this file, the
  // doctype's form script, and the "Filter Date Expense Req" Client Script - and that last one
  // mounts the Group By widget from its onload. A plain assignment means whichever happens to
  // run last silently wins and the others vanish, which is exactly how Group By went missing
  // here: the winner was a copy that had no onload at all. So merge into whatever is already
  // registered and chain onload, and the order stops mattering.
  const existing = frappe.listview_settings["Expense Request"] || {};
  const previousOnload = existing.onload;

  frappe.listview_settings["Expense Request"] = Object.assign({}, existing, {
    add_fields: [
      ...new Set([
        ...(existing.add_fields || []),
        "status",
        "docstatus",
        "request_type",
        "supplier",
        "total_amount",
      ]),
    ],

    get_indicator(doc) {
      // Status-based indicators
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

    // Moved here from expense_request.js, which used to carry its own full copy of
    // listview_settings purely to register these.
    formatters: Object.assign({}, existing.formatters, {
      custom_expense_account_display(value) {
        if (!value) return "";
        return `<span style="color:#2563eb;font-weight:600">${value}</span>`;
      },
      status(value, df, doc) {
        // Kolom status mengikuti field status custom, bukan docstatus
        const color_map = {
          Draft: "grey",
          Pending: "orange",
          Submitted: "blue",
          Approved: "green",
          Rejected: "red",
          "PI Created": "blue",
          Paid: "green",
          Cancelled: "red",
        };
        const real_status = doc.status || value;
        const color = color_map[real_status] || "grey";
        return `<span class="indicator-pill ${color}">${real_status || ""}</span>`;
      },
    }),

    onload(listview) {
      // jalankan dulu onload milik pendaftar sebelumnya (mis. widget Group By)
      if (typeof previousOnload === "function") {
        try {
          previousOnload.call(this, listview);
        } catch (e) {
          console.error("[Expense Request] onload sebelumnya gagal:", e);
        }
      }

      const refreshActions = () => toggleCreatePiAction(listview);

      listview.page.wrapper.on(
        "change",
        'input[type="checkbox"]',
        refreshActions
      );
      listview.page.wrapper.on("click", ".list-row, .list-check-all", refreshActions);
      if (listview.on) {
        listview.on("refresh", refreshActions);
      }

      refreshActions();
    },
  });
})();
