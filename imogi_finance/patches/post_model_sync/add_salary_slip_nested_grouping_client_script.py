"""Tambah Client Script list-view Salary Slip dengan grouping bertingkat
(Year/Month/Day/Status/Company), adaptasi persis dari script yang sama
dipakai Payroll Entry ("Client Script Payroll Entry") - lihat juga
patch_so_nested_period_status_grouping.py untuk versi Sales Order.
"""

import frappe

SCRIPT_NAME = "Client Script Salary Slip Grouping"

SCRIPT = r"""frappe.listview_settings["Salary Slip"] = {
    add_fields: ["name", "docstatus", "posting_date", "end_date", "start_date", "net_pay", "company"],

    onload: function(listview) {
        var DATE_FIELD = "posting_date";
        var GROUP_OPTIONS = ["Year", "Month", "Day", "Status", "Company"];
        var selected_groups = ["Month"];
        var collapsed_groups = {}, apply_timer = null, is_rendering = false;

        if (!document.getElementById("ss-erg-style")) {
            var s = document.createElement("style"); s.id = "ss-erg-style";
            s.textContent = ".standard-filter-section.flex{display:flex!important;flex-wrap:wrap!important;align-items:center!important;gap:8px!important}"
                + "#ss-erg-wrap{position:relative;flex:0 0 auto!important;min-width:140px;max-width:180px;margin:0!important;align-self:center!important}"
                + "#ss-erg-select{width:100%;height:28px;padding:0 28px 0 10px;border:none;border-radius:6px;background:#f3f4f6;font-size:13px;color:#36414c;display:flex;align-items:center;cursor:pointer;box-sizing:border-box}"
                + "#ss-erg-select:hover{background:#eaecef}"
                + "#ss-erg-text{display:block;width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1}"
                + "#ss-erg-text.is-placeholder{color:#8d99a6}"
                + "#ss-erg-chevron{position:absolute;right:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#8d99a6;display:flex;align-items:center;z-index:2}"
                + "#ss-erg-clr{display:none;position:absolute;right:24px;top:50%;transform:translateY(-50%);cursor:pointer;color:#8d99a6;font-size:13px;z-index:3;line-height:1}"
                + "#ss-erg-dd{display:none;position:absolute;top:calc(100% + 6px);left:0;background:#fff;border:1px solid #d1d8dd;border-radius:8px;min-width:200px;z-index:9999;padding:8px 0;box-shadow:0 4px 16px rgba(0,0,0,.12)}"
                + ".ss-erg-dd-title{padding:0 12px 8px;font-size:11px;font-weight:600;color:#8d99a6;border-bottom:1px solid #f0f4f7;margin-bottom:6px}"
                + ".ss-erg-opt{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;font-size:13px;color:#36414c}"
                + ".ss-erg-opt:hover{background:#f5f7fa}"
                + ".ss-erg-opt input{margin:0}"
                + ".ss-erg-dd-actions{display:flex;justify-content:space-between;gap:8px;padding:8px 12px 0;border-top:1px solid #f0f4f7;margin-top:6px;flex-wrap:wrap}"
                + ".ss-erg-dd-btn{flex:1;border:1px solid #d1d8dd;background:#fff;color:#36414c;font-size:11px;border-radius:6px;padding:6px 8px;cursor:pointer}"
                + ".ss-erg-dd-btn.primary{background:#2490ef;color:#fff;border-color:#2490ef}"
                + ".ss-erg-dd-btn:hover{background:#f5f7fa}"
                + ".ss-erg-dd-btn.primary:hover{background:#1a7fd4}"
                + ".ss-erg-group-separator{margin:20px 0 8px;border-top:2px solid #dbe3ea}"
                + ".ss-erg-group-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;margin:0 0 6px;background:#f7f9fb;border:1px solid #e3e8ee;border-radius:8px;cursor:pointer;user-select:none}"
                + ".ss-erg-group-header:hover{background:#f2f6fa}"
                + ".ss-erg-group-left{display:flex;align-items:center;gap:10px;min-width:0}"
                + ".ss-erg-group-toggle{width:18px;text-align:center;color:#8d99a6;font-size:12px;flex:0 0 auto}"
                + ".ss-erg-group-title{font-size:12px;font-weight:700;color:#36414c;line-height:1.3}"
                + ".ss-erg-group-sub{font-size:11px;color:#8d99a6;line-height:1.3;margin-top:2px}"
                + ".ss-erg-group-right{display:flex;align-items:center;gap:8px;flex-shrink:0}"
                + ".ss-erg-group-count{font-size:11px;color:#68717d;background:#edf2f7;border:1px solid #dde5ee;border-radius:999px;padding:2px 8px;white-space:nowrap}"
                + ".ss-erg-group-badge{flex:0 0 auto;font-size:10px;font-weight:600;color:#68717d;background:#edf2f7;border:1px solid #dde5ee;border-radius:999px;padding:3px 8px}"
                + ".ss-erg-lvl-1{margin-top:10px}"
                + ".ss-erg-lvl-2{margin-left:18px;background:#fbfcfd}"
                + ".ss-erg-lvl-3{margin-left:36px;background:#fcfdfe}"
                + ".ss-erg-lvl-4{margin-left:54px;background:#fff}"
                + ".ss-erg-lvl-5{margin-left:72px;background:#fff}"
                + ".ss-erg-hidden-by-collapse{display:none!important}";
            document.head.appendChild(s);
        }

        var MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

        function pd(s) { return s ? frappe.datetime.str_to_obj(s) : null; }

        function gvDoc(doc, mode) {
            if (mode === "Status") {
                var s = doc.docstatus === 2 ? "Cancelled" : doc.docstatus === 1 ? "Submitted" : "Draft";
                return { key: s, label: s };
            }
            if (mode === "Company") return { key: doc.company || "No Company", label: doc.company || "No Company" };
            var d = pd(doc[DATE_FIELD] || doc.end_date || doc.start_date);
            if (!d) return { key: "NO_DATE", label: "No Date" };
            var y = d.getFullYear(), m = d.getMonth(), day = d.getDate();
            if (mode === "Year")  return { key: y+"", label: y+"" };
            if (mode === "Month") return { key: y+"-"+String(m+1).padStart(2,"0"), label: MN[m]+" "+y };
            if (mode === "Day")   return { key: y+"-"+String(m+1).padStart(2,"0")+"-"+String(day).padStart(2,"0"), label: String(day).padStart(2,"0")+" "+MN[m]+" "+y };
            return { key: "X", label: "Unknown" };
        }

        function esc(t) { return frappe.utils.escape_html(t == null ? "" : String(t)); }
        function getRows() { return listview.$result ? listview.$result.find(".list-row-container").filter(function() { return !!getDN($(this)); }) : $(); }
        function getDN($r) { return $r.attr("data-name") || $r.find("[data-name]").first().attr("data-name") || null; }
        function getDoc(n) { return Array.isArray(listview.data) ? listview.data.find(function(d) { return d.name === n; }) || null : null; }
        function rmv() {
            if (!listview.$result) return;
            listview.$result.find(".ss-erg-group-header,.ss-erg-group-separator").remove();
            listview.$result.find(".ss-erg-hidden-by-collapse").removeClass("ss-erg-hidden-by-collapse");
        }
        function mkSep() { return $('<div class="ss-erg-group-separator">'); }
        function mkHdr(lv, mode, label, sub, ck, count) {
            var ic = !!collapsed_groups[ck];
            var countLabel = count === 1 ? "1 entry" : count + " entries";
            return $('<div class="ss-erg-group-header ss-erg-lvl-'+lv+'" data-group-level="'+lv+'" data-chain-key="'+esc(ck)+'" data-collapsed="'+(ic?"1":"0")+'">'
                +'<div class="ss-erg-group-left"><div class="ss-erg-group-toggle">'+(ic?"&#9658;":"&#9660;")+'</div>'
                +'<div class="ss-erg-group-text"><div class="ss-erg-group-title">'+esc(label)+'</div><div class="ss-erg-group-sub">'+esc(sub||"")+' </div></div></div>'
                +'<div class="ss-erg-group-right">'
                +'<div class="ss-erg-group-count">'+esc(countLabel)+'</div>'
                +'<div class="ss-erg-group-badge">'+esc(mode)+'</div>'
                +'</div></div>');
        }

        function doCollapse($h) {
            var lv = parseInt($h.attr("data-group-level"), 10);
            collapsed_groups[$h.attr("data-chain-key")] = true;
            $h.attr("data-collapsed","1").find(".ss-erg-group-toggle").html("&#9658;");
            var $n = $h.next();
            while ($n.length) { if ($n.hasClass("ss-erg-group-header") && parseInt($n.attr("data-group-level"),10) <= lv) break; $n.addClass("ss-erg-hidden-by-collapse"); $n = $n.next(); }
        }
        function doExpand($h) {
            var lv = parseInt($h.attr("data-group-level"), 10);
            delete collapsed_groups[$h.attr("data-chain-key")];
            $h.attr("data-collapsed","0").find(".ss-erg-group-toggle").html("&#9660;");
            var $n = $h.next();
            while ($n.length) {
                if ($n.hasClass("ss-erg-group-header")) {
                    var nl = parseInt($n.attr("data-group-level"),10); if (nl <= lv) break;
                    $n.removeClass("ss-erg-hidden-by-collapse");
                    if ($n.attr("data-collapsed") === "1") { var $s = $n.next(); while ($s.length) { if ($s.hasClass("ss-erg-group-header") && parseInt($s.attr("data-group-level"),10) <= nl) break; $s.addClass("ss-erg-hidden-by-collapse"); $s = $s.next(); } }
                } else { $n.removeClass("ss-erg-hidden-by-collapse"); }
                $n = $n.next();
            }
            listview.$result.find(".ss-erg-group-header[data-collapsed='1']").each(function() { doCollapse($(this)); });
        }
        function bindEv() {
            listview.$result.find(".ss-erg-group-header").off("click.ss-erg").on("click.ss-erg", function(e) {
                e.stopPropagation();
                $(this).attr("data-collapsed") === "1" ? doExpand($(this)) : doCollapse($(this));
            });
        }

        function applyGrouping() {
            if (is_rendering || !listview.$result) return;
            if (!selected_groups.length) { rmv(); return; }
            is_rendering = true;
            try {
                rmv();
                var rs = [];
                getRows().each(function() {
                    var $r = $(this), n = getDN($r);
                    if (!n) return;
                    var d = getDoc(n), dv = d ? (d[DATE_FIELD] || d.end_date || d.start_date) : null, dObj = pd(dv);
                    rs.push({ $r: $r, n: n, doc: d, dObj: dObj, ts: dObj ? dObj.getTime() : 0 });
                });
                rs.sort(function(a, b) { return a.ts !== b.ts ? a.ts - b.ts : a.n.localeCompare(b.n); });
                if (rs.length) { var $p = rs[0].$r.parent(); rs.forEach(function(r) { $p.append(r.$r); }); }

                var countMap = {};
                rs.forEach(function(item) {
                    var chain = selected_groups.map(function(mode) { var g = gvDoc(item.doc, mode); return { mode: mode, key: String(g.key), label: g.label }; });
                    chain.forEach(function(g, idx) {
                        var ck = chain.slice(0, idx+1).map(function(x) { return x.mode+":"+x.key; }).join("||");
                        countMap[ck] = (countMap[ck] || 0) + 1;
                    });
                });

                var pk = [], pt = null;
                rs.forEach(function(item) {
                    var chain = selected_groups.map(function(mode) { var g = gvDoc(item.doc, mode); return { mode: mode, key: String(g.key), label: g.label }; });
                    if (!chain.length) return;
                    var tk = chain[0].mode+":"+chain[0].key;
                    chain.forEach(function(g, idx) {
                        var lv = idx+1, ck = chain.slice(0,lv).map(function(x) { return x.mode+":"+x.key; }).join("||");
                        if (pk[idx] !== ck) {
                            if (idx === 0 && pt !== null && tk !== pt) item.$r.before(mkSep());
                            var sub = idx === 0 ? "Group by "+g.mode : chain.slice(0,idx).map(function(x) { return x.label; }).join(" / ");
                            var count = countMap[ck] || 0;
                            item.$r.before(mkHdr(lv, g.mode, g.label, sub, ck, count));
                            pk[idx] = ck; for (var j = idx+1; j < pk.length; j++) pk[j] = null;
                        }
                    });
                    pt = tk;
                });
                bindEv();
                if (!Object.keys(collapsed_groups).length) listview.$result.find(".ss-erg-group-header").each(function() { doCollapse($(this)); });
                else listview.$result.find(".ss-erg-group-header[data-collapsed='1']").each(function() { doCollapse($(this)); });
            } finally { is_rendering = false; }
        }

        function sched(d) { clearTimeout(apply_timer); apply_timer = setTimeout(applyGrouping, d || 400); }
        function updDisp() {
            if (selected_groups.length) { $("#ss-erg-text").text(selected_groups.join(" + ")).removeClass("is-placeholder"); $("#ss-erg-clr").show(); }
            else { $("#ss-erg-text").text("Group By").addClass("is-placeholder"); $("#ss-erg-clr").hide(); }
        }
        function syncChk() { $("#ss-erg-dd .ss-erg-opt-check").each(function() { $(this).prop("checked", selected_groups.indexOf($(this).val()) > -1); }); }

        function buildUI() {
            var opts = GROUP_OPTIONS.map(function(o) {
                return '<label class="ss-erg-opt"><input type="checkbox" class="ss-erg-opt-check" value="'+o+'"><span>'+o+'</span></label>';
            }).join("");
            return $('<div id="ss-erg-wrap">'
                +'<div id="ss-erg-select"><span id="ss-erg-text" class="is-placeholder">Group By</span></div>'
                +'<div id="ss-erg-chevron"><svg class="icon icon-xs" aria-hidden="true"><use href="#icon-select"></use></svg></div>'
                +'<span id="ss-erg-clr">&times;</span>'
                +'<div id="ss-erg-dd"><div class="ss-erg-dd-title">Pilih level grouping</div>'+opts
                +'<div class="ss-erg-dd-actions">'
                +'<button class="ss-erg-dd-btn" id="ss-erg-sa">All</button>'
                +'<button class="ss-erg-dd-btn" id="ss-erg-ca">Clear</button>'
                +'<button class="ss-erg-dd-btn primary" id="ss-erg-ap">Apply</button>'
                +'</div></div></div>');
        }

        function attachUI($w) {
            $w.on("click","#ss-erg-select",function(e){e.stopPropagation();syncChk();$("#ss-erg-dd").toggle();});
            $w.on("click","#ss-erg-sa",function(e){e.stopPropagation();$("#ss-erg-dd .ss-erg-opt-check").prop("checked",true);});
            $w.on("click","#ss-erg-ca",function(e){e.stopPropagation();$("#ss-erg-dd .ss-erg-opt-check").prop("checked",false);});
            $w.on("click","#ss-erg-ap",function(e){
                e.stopPropagation();
                selected_groups = GROUP_OPTIONS.filter(function(o){return $("#ss-erg-dd .ss-erg-opt-check[value='"+o+"']").prop("checked");});
                collapsed_groups={};updDisp();$("#ss-erg-dd").hide();sched(300);
            });
            $w.on("click","#ss-erg-clr",function(e){e.stopPropagation();selected_groups=[];collapsed_groups={};updDisp();rmv();syncChk();});
            $(document).off("click.ss-erg").on("click.ss-erg",function(){$("#ss-erg-dd").hide();});
            $w.on("click","#ss-erg-dd",function(e){e.stopPropagation();});
        }

        function injectUI() {
            $("#ss-erg-wrap").remove();
            var $anchor = listview.page.wrapper.find(".standard-filter-section .frappe-control").last();
            if (!$anchor.length) return false;
            var $w = buildUI(); $anchor.after($w); attachUI($w); updDisp(); syncChk(); return true;
        }

        if (!listview.__ss_erg_patched) {
            listview.__ss_erg_patched = true;
            var oR = listview.render, oRf = listview.refresh;
            listview.render = function() { var r = oR.apply(this, arguments); sched(500); return r; };
            listview.refresh = function() { var r = oRf.apply(this, arguments); sched(600); return r; };
        }

        frappe.after_ajax(function() {
            if (!injectUI()) { var n = 0; var iv = setInterval(function() { n++; if (injectUI() || n > 20) clearInterval(iv); }, 200); }
            sched(700);
        });
    }
};
"""


def execute():
	if frappe.db.exists("Client Script", SCRIPT_NAME):
		frappe.db.set_value("Client Script", SCRIPT_NAME, "script", SCRIPT, update_modified=False)
	else:
		frappe.get_doc(
			{
				"doctype": "Client Script",
				"name": SCRIPT_NAME,
				"dt": "Salary Slip",
				"view": "List",
				"enabled": 1,
				"script": SCRIPT,
			}
		).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Salary Slip")
