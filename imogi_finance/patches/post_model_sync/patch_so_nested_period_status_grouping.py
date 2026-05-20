"""Nest Status grouping inside Period grouping on Sales Order list (like Sales Invoice)."""

import frappe

MARKER = "__activeGroups = activeGroups()"

NEW_HELPERS = r"""
    window.__imogi_so_status_group_on = false;
    window.__imogi_so_cs_sched = function(d) { sched(d); };

    const SO_NESTED_STATUS_ORDER = ["Draft","Submitted","SI Created","Outstanding Invoice","Paid","Cancelled"];
    function activeGroups() {
      const groups = selected_groups.slice();
      if (window.__imogi_so_status_group_on) groups.push("Status");
      return groups;
    }
    function statusRankSo(label) {
      const idx = SO_NESTED_STATUS_ORDER.indexOf(label);
      return idx >= 0 ? idx : 999;
    }
    function groupRowValue(item, mode) {
      if (mode === "Status") {
        const doc = item.doc;
        let label = "Submitted";
        if (doc) {
          if (typeof get_so_business_status === "function") label = get_so_business_status(doc);
          else if (cint_so(doc.docstatus) === 2) label = "Cancelled";
          else if (cint_so(doc.docstatus) === 0) label = "Draft";
          else label = (doc.custom_payment_status || "Submitted").trim() || "Submitted";
        }
        return { mode: "Status", key: String(label), label: label };
      }
      const g = gv(item.dObj, mode);
      return { mode: mode, key: String(g.key), label: g.label };
    }
    function compareRows(a, b) {
      const groups = activeGroups();
      for (let i = 0; i < groups.length; i++) {
        const mode = groups[i];
        const ga = groupRowValue(a, mode);
        const gb = groupRowValue(b, mode);
        if (ga.key !== gb.key) {
          if (mode === "Status") return statusRankSo(ga.key) - statusRankSo(gb.key);
          return String(ga.key).localeCompare(String(gb.key));
        }
      }
      if (a.ts !== b.ts) return a.ts - b.ts;
      return a.n.localeCompare(b.n);
    }
"""

NEW_APPLY_GROUPING = r"""function applyGrouping() {
      if (is_rendering || !listview.$result) return;
      const __activeGroups = activeGroups();
      if (!__activeGroups.length) { rmv(); return; }
      is_rendering = true;
      try {
        rmv();
        const rs = [];
        getRows().each(function() {
          const $r = $(this), n = getDN($r);
          if (!n) return;
          const d = getDoc(n), dObj = pd(d ? d[DATE_FIELD] : null);
          rs.push({ $r, n, doc: d, dObj, ts: dObj ? dObj.getTime() : 0 });
        });
        rs.sort(compareRows);
        if (rs.length) { const $p = rs[0].$r.parent(); rs.forEach(r => $p.append(r.$r)); }

        const countMap = {};
        rs.forEach(item => {
          const chain = __activeGroups.map(mode => groupRowValue(item, mode));
          chain.forEach((g, idx) => {
            const ck = chain.slice(0, idx + 1).map(x => x.mode + ":" + x.key).join("||");
            countMap[ck] = (countMap[ck] || 0) + 1;
          });
        });

        let pk = [], pt = null;
        rs.forEach(item => {
          const chain = __activeGroups.map(mode => groupRowValue(item, mode));
          if (!chain.length) return;
          const tk = chain[0].mode + ":" + chain[0].key;
          chain.forEach((g, idx) => {
            const lv = idx + 1;
            const ck = chain.slice(0, lv).map(x => x.mode + ":" + x.key).join("||");
            if (pk[idx] !== ck) {
              if (idx === 0 && pt !== null && tk !== pt) item.$r.before(mkSep());
              const sub = g.mode === "Status"
                ? (idx === 0 ? "Group by Status" : chain.slice(0, idx).map(x => x.label).join(" / "))
                : (idx === 0 ? "Group by " + g.mode : chain.slice(0, idx).map(x => x.label).join(" / "));
              item.$r.before(mkHdr(lv, g.mode, g.label, sub, ck, countMap[ck] || 0));
              pk[idx] = ck;
              for (let j = idx + 1; j < pk.length; j++) pk[j] = null;
            }
          });
          pt = tk;
        });

        bindEv();
        if (!Object.keys(collapsed_groups).length) {
          listview.$result.find(".erg-group-header").each(function() { doCollapse($(this)); });
        } else {
          listview.$result.find(".erg-group-header[data-collapsed='1']").each(function() { doCollapse($(this)); });
        }
      } finally { is_rendering = false; }
    }"""


def execute():
	for row in frappe.get_all(
		"Client Script",
		filters={"dt": "Sales Order", "enabled": 1, "view": "List"},
		fields=["name", "script"],
	):
		script = row.script or ""
		if MARKER in script:
			continue

		updated = _patch_script(script)
		if updated != script:
			frappe.db.set_value("Client Script", row.name, "script", updated, update_modified=True)
		else:
			frappe.log_error(
				title="patch_so_nested_period_status_grouping",
				message=f"Could not patch Client Script {row.name}",
			)

	frappe.clear_cache(doctype="Client Script")


def _patch_script(script: str) -> str:
	import re

	if MARKER in script:
		return script

	# helpers after is_rendering
	for needle, insert in [
		(
			"    let is_rendering     = false;\r\n\r\n    // ── Inject CSS",
			"    let is_rendering     = false;\r\n\r\n" + NEW_HELPERS.replace("\n", "\r\n") + "\r\n    // ── Inject CSS",
		),
		(
			"    let is_rendering     = false;\n\n    // ── Inject CSS",
			"    let is_rendering     = false;\n\n" + NEW_HELPERS + "\n    // ── Inject CSS",
		),
	]:
		if needle in script:
			if "function activeGroups()" not in script:
				script = script.replace(needle, insert, 1)
			break
	else:
		if "function activeGroups()" not in script:
			return script

	script = script.replace(
		'listview.$result.find(".erg-group-header,.erg-group-separator").remove();',
		'listview.$result.find(".erg-group-header,.so-group-header,.erg-group-separator,.so-group-separator").remove();',
	)

	# replace entire applyGrouping function
	if "// ── Left ID Inject" in script:
		tail = "    // ── Left ID Inject"
		pattern = re.compile(
			r"function applyGrouping\(\) \{[\s\S]*?\r?\n    \}\r?\n\r?\n    // ── Left ID Inject",
			re.DOTALL,
		)
	elif "// ── Left ID" in script:
		tail = "    // ── Left ID"
		pattern = re.compile(
			r"function applyGrouping\(\) \{[\s\S]*?\r?\n    \}\r?\n\r?\n    // ── Left ID",
			re.DOTALL,
		)
	else:
		return script

	repl = (
		NEW_APPLY_GROUPING.replace("\n", "\r\n")
		if "\r\n" in script
		else NEW_APPLY_GROUPING
	) + ("\r\n\r\n" if "\r\n" in script else "\n\n") + tail

	if pattern.search(script):
		script = pattern.sub(repl, script, count=1)

	return script
