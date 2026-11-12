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

  // The "status" field only flips from Approved to "PI Created" once the
  // Purchase Invoice is actually submitted (see
  // imogi_finance.events.purchase_invoice._handle_expense_request_submit) -
  // a Draft PI created from this request still shows as plain "Approved"
  // here, indistinguishable from a request nobody has acted on yet. Staff
  // asked to see that distinction from the list, without opening every row.
  //
  // The badge shown for this case reuses the same "📄 PI Created" label/blue
  // color as the real PI Created status, rather than inventing a separate
  // "Draft" look - staff just wants to see a PI already exists, the tooltip
  // carries the "not submitted yet" nuance.
  //
  // This list is also re-rendered on its own timers by several unrelated
  // DB Client Scripts (Group By widget, scroll fix, column rename), each
  // wrapping/re-running render() independently. A one-shot DOM patch lost
  // that race (got overwritten, or patched a row that was about to be
  // replaced) and calling listview.render() ourselves to force a fresh pass
  // corrupted the list's own column layout. So instead: cache which
  // Approved requests already have an active PI, let the "status" formatter
  // below consult it on whatever render happens to run next, AND keep a
  // MutationObserver on the result list that reapplies the pill patch after
  // every one of those competing re-renders settles - idempotent, so it's
  // harmless to run it more often than strictly needed.
  const draftPiCache = {};

  const applyPillPatches = (listview) => {
    if (!listview.$result) {
      return;
    }
    Object.keys(draftPiCache).forEach((erName) => {
      const pi = draftPiCache[erName];
      const $row = listview.$result
        .find(`.list-row-checkbox[data-name="${frappe.utils.escape_html(erName)}"]`)
        .closest(".list-row-container");
      if (!$row.length) {
        return;
      }
      $row.find(".indicator-pill").each(function () {
        const $pill = $(this);
        if ($pill.text().trim() === "Approved") {
          $pill
            .attr("class", "indicator-pill blue")
            .attr("title", __("Purchase Invoice {0} (belum disubmit)", [pi.name]))
            .text(__("📄 PI Created"));
        }
      });

      // garage/public/js/expense_request_list.js replaces this row with its
      // own card (.exr-card) and its own status badge (.exr-c-badge),
      // appended inside the same .list-row-container - patch that one too
      // so the change shows up under garage's card-list skin as well.
      $row.find(".exr-c-badge").each(function () {
        const $badge = $(this);
        if ($badge.text().trim() === "Approved") {
          $badge
            .css({ background: "#dbeafe", color: "#1d4ed8" })
            .attr("title", __("Purchase Invoice {0} (belum disubmit)", [pi.name]))
            .text(__("📄 PI Created"));
        }
      });
    });
  };

  const refreshDraftPiCache = async (listview) => {
    const docs = listview.data || [];
    const candidates = docs.filter(
      (d) => d.status === "Approved" && Number(d.docstatus) === 1
    );
    if (!candidates.length) {
      return;
    }

    const names = candidates.map((d) => d.name);
    let piRows;
    try {
      piRows = await frappe.db.get_list("Purchase Invoice", {
        filters: { imogi_expense_request: ["in", names], docstatus: ["!=", 2] },
        fields: ["name", "imogi_expense_request"],
        limit: names.length,
      });
    } catch (error) {
      return;
    }
    piRows = piRows || [];

    const foundFor = new Set(piRows.map((pi) => pi.imogi_expense_request));
    names.forEach((erName) => {
      if (draftPiCache[erName] && !foundFor.has(erName)) {
        delete draftPiCache[erName];
      }
    });
    piRows.forEach((pi) => {
      draftPiCache[pi.imogi_expense_request] = pi;
    });

    applyPillPatches(listview);
  };

  const watchForRerenders = (listview) => {
    if (listview.__draftPiObserverSet || !listview.$result || !listview.$result[0]) {
      return;
    }
    listview.__draftPiObserverSet = true;

    let timer = null;
    const observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => applyPillPatches(listview), 150);
    });
    observer.observe(listview.$result[0], { childList: true, subtree: true });
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
  const previousRefresh = existing.refresh;

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

        const draftPi = draftPiCache[doc.name];
        if (real_status === "Approved" && draftPi) {
          return `<span class="indicator-pill blue" title="${frappe.utils.escape_html(
            __("Purchase Invoice {0} (belum disubmit)", [draftPi.name])
          )}">${__("📄 PI Created")}</span>`;
        }

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
      watchForRerenders(listview);
    },

    // Unlike listview.on("refresh", ...) above (which this version of the
    // framework never actually fires for ListView), `settings.refresh` is
    // called by BaseList.refresh() right after every render - see
    // frappe/public/js/frappe/list/base_list.js - so this is the one hook
    // that reliably re-runs the Draft-PI lookup on load, pagination, filter
    // and sort changes alike.
    refresh(listview) {
      if (typeof previousRefresh === "function") {
        try {
          previousRefresh.call(this, listview);
        } catch (e) {
          console.error("[Expense Request] refresh sebelumnya gagal:", e);
        }
      }
      watchForRerenders(listview);
      applyPillPatches(listview);
      refreshDraftPiCache(listview);
    },
  });
})();
