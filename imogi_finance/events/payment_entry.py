import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_er_doctype,
    get_expense_request_links,
    get_expense_request_status,
)


def _is_bank_payment(doc) -> bool:
    """Return True if Payment Entry uses a Bank account."""
    account_to_check = None

    if doc.payment_type == "Pay":
        account_to_check = doc.paid_from
    elif doc.payment_type == "Receive":
        account_to_check = doc.paid_to

    if not account_to_check:
        return False

    account_type = frappe.db.get_value("Account", account_to_check, "account_type")
    return account_type == "Bank"


def _resolve_expense_request(doc) -> str | None:
    """Resolve Expense Request from document field or linked Purchase Invoice references."""
    expense_request = doc.get("imogi_expense_request") or doc.get("expense_request")
    if expense_request:
        return expense_request

    references = doc.get("references") or []
    for ref in references:
        if ref.get("reference_doctype") != "Purchase Invoice":
            continue

        reference_name = ref.get("reference_name")
        if not reference_name:
            continue

        try:
            values = frappe.db.get_value(
                "Purchase Invoice",
                reference_name,
                ["imogi_expense_request", "expense_request"],
                as_dict=True,
            )
        except Exception:
            values = None

        if values:
            return values.get("imogi_expense_request") or values.get("expense_request")

    return None


def _ensure_expense_request_reference(doc, expense_request: str | None) -> None:
    """Ensure imogi_expense_request is set on Payment Entry."""
    if not expense_request or doc.get("imogi_expense_request"):
        return

    if hasattr(doc, "db_set"):
        try:
            doc.db_set("imogi_expense_request", expense_request, update_modified=False)
            return
        except Exception:
            pass

    setattr(doc, "imogi_expense_request", expense_request)


def _validate_expense_request_link(doc, request, request_name: str) -> None:
    """Reserved for future validation.

    Multiple Payment Entry per Expense Request is allowed.
    """
    pass


def _sync_expense_request_link(
    doc,
    expense_request: str | None,
    *,
    allowed_statuses: frozenset[str] | set[str] | None = None,
):
    """Sync Payment Entry to Expense Request."""
    if not expense_request:
        frappe.logger().info(f"[_sync_expense_request_link] No request for PE: {doc.name}")
        return None

    frappe.logger().info(
        f"[_sync_expense_request_link] Syncing PE {doc.name} to ER {expense_request}"
    )

    _ensure_expense_request_reference(doc, expense_request)

    request = get_approved_expense_request(
        expense_request,
        _("Payment Entry"),
        allowed_statuses=allowed_statuses,
    )

    frappe.logger().info(
        f"[_sync_expense_request_link] Successfully synced PE {doc.name} to ER {expense_request}"
    )
    return request


def sync_expense_request_reference(doc, method=None):
    """Auto-populate imogi_expense_request from references during validate."""
    if doc.get("imogi_expense_request"):
        return

    expense_request = _resolve_expense_request(doc)

    frappe.logger().info(
        f"[Payment Entry validate] PE: {getattr(doc, 'name', 'NEW')}, Resolved ER: {expense_request}"
    )
    frappe.logger().info(
        f"[Payment Entry validate] References count: {len(doc.get('references') or [])}"
    )

    if expense_request:
        doc.imogi_expense_request = expense_request
        frappe.logger().info(
            f"[Payment Entry validate] Set imogi_expense_request to {expense_request}"
        )


def on_change_expense_request(doc, method=None):
    """Auto-populate amount and remarks from selected Expense Request."""
    expense_request = doc.get("imogi_expense_request")
    if not expense_request:
        return

    try:
        er_doctype = get_er_doctype(expense_request) or "Expense Request"
        request = frappe.get_doc(er_doctype, expense_request)
    except frappe.DoesNotExistError:
        frappe.msgprint(
            _("Expense Request {0} not found").format(expense_request),
            alert=True,
            indicator="orange",
        )
        return

    try:
        amount = getattr(request, "total_amount", None)
        if amount:
            doc.paid_amount = amount
            doc.received_amount = amount

        if request.get("name"):
            existing_remarks = doc.get("remarks") or ""
            if er_doctype not in existing_remarks:
                doc.remarks = _("Payment for {0} {1} - {2}").format(
                    er_doctype,
                    request.name,
                    request.get("description", request.get("purpose", request.get("request_type", ""))),
                )
    except Exception:
        pass



def _generate_towing_remarks(doc) -> None:
    """Auto-generate remarks untuk Payment Entry towing."""
    do_name = doc.get("delivery_order_towing")
    if not do_name:
        return

    try:
        do = frappe.get_doc("Delivery Order Towing", do_name)
        rute = f"{do.kota_pickup or '-'} -> {do.kota_tujuan or '-'}"
        kendaraan = do.kendaraan_towing or '-'
        driver = do.driver_nama or '-'
        doc.remarks = (
            f"Uang jalan driver towing {do_name} | "
            f"Rute: {rute} | "
            f"Kendaraan: {kendaraan} | "
            f"Driver: {driver}."
        )
    except Exception as e:
        frappe.log_error(str(e), "Generate Towing Remarks Error")


def generate_towing_remarks(doc, method=None) -> None:
    """Hook: Auto-generate remarks untuk Payment Entry towing."""
    _generate_towing_remarks(doc)

def after_insert(doc, method=None):
    """Auto-populate Detail Kendaraan Towing jika PE linked ke DO atau via PI/PO."""
    # Prioritas 1: field delivery_order_towing langsung
    if doc.get("delivery_order_towing"):
        _populate_towing_from_do(doc, "delivery_order_towing")
        return

    # Prioritas 2: cari DO via Purchase Invoice / Purchase Order di references
    _populate_towing_from_references(doc)


def _populate_towing_from_do(doc, do_field: str):
    """Helper: ambil data kendaraan langsung dari DO (bukan dari SO)."""
    do_name = doc.get(do_field)
    if not do_name:
        return
    try:
        do = frappe.get_doc("Delivery Order Towing", do_name)

        # Ambil so_item_code dari SO Towing Kendaraan yang linked ke DO ini
        item_code = frappe.db.get_value(
            "SO Towing Kendaraan",
            {"delivery_order": do_name},
            "so_item_code"
        )

        rows = [{
            "so_item_code": item_code or "",
            "nomor_rangka": do.nomor_rangka or "",
            "nomor_polisi": do.nomor_polisi or "",
            "tipe_model"  : do.tipe_kendaraan or "",
            "nomor_mesin" : do.nomor_mesin or "",
        }]

        linked = frappe.get_doc(doc.doctype, doc.name)
        linked.set("custom_towing_kendaraan", [])
        for row in rows:
            linked.append("custom_towing_kendaraan", {
                "so_item_code": row["so_item_code"],
                "nomor_rangka": row["nomor_rangka"],
                "nomor_polisi": row["nomor_polisi"],
                "tipe_model"  : row["tipe_model"],
                "nomor_mesin" : row["nomor_mesin"],
            })
        linked.save(ignore_permissions=True)
        frappe.logger().info(
            f"[Towing] {doc.doctype} {doc.name}: 1 baris diisi dari DO {do_name}"
        )
    except Exception as exc:
        frappe.log_error(
            f"[Towing] Error {doc.doctype} after_insert {doc.name}: {exc}",
            "Auto Populate Towing",
        )

def _populate_towing_from_references(doc):
    """
    Cari DO via references PE (Purchase Invoice atau Purchase Order),
    lalu isi Detail Kendaraan Towing dari DO yang ditemukan.
    """
    do_name = None

    for ref in doc.get("references") or []:
        ref_doctype = ref.get("reference_doctype")
        ref_name    = ref.get("reference_name")

        if ref_doctype == "Purchase Invoice":
            do_name = frappe.db.get_value(
                "Purchase Invoice", ref_name, "custom_delivery_order"
            )
        elif ref_doctype == "Purchase Order":
            do_name = frappe.db.get_value(
                "Purchase Order", ref_name, "custom_delivery_order"
            )

        if do_name:
            break

    if not do_name:
        return

    # Simpan link DO ke PE, lalu populate
    try:
        frappe.db.set_value(doc.doctype, doc.name, "delivery_order_towing", do_name)
        frappe.db.commit()
        # Reload doc agar field ter-update
        doc_reloaded = frappe.get_doc(doc.doctype, doc.name)
        _populate_towing_from_do(doc_reloaded, "delivery_order_towing")
    except Exception as exc:
        frappe.log_error(
            f"[Towing] Error populate via references PE {doc.name}: {exc}",
            "Auto Populate Towing",
        )


def on_update(doc, method=None):
    """Sync Expense Request link on update for draft Payment Entry."""
    if doc.get("docstatus") == 2:
        return

    if doc.get("imogi_expense_request"):
        return

    expense_request = _resolve_expense_request(doc)

    frappe.logger().info(
        f"[Payment Entry on_update] PE: {doc.name}, Resolved ER: {expense_request}"
    )

    if not expense_request:
        return

    _sync_expense_request_link(doc, expense_request)


def clean_payment_ledger(doc, method=None):
    """Delete Payment Ledger Entry rows linked to this Payment Entry."""
    if not doc.name:
        return

    ple_names = frappe.get_all(
        "Payment Ledger Entry",
        filters={"voucher_no": doc.name},
        pluck="name",
    )

    if not ple_names:
        frappe.logger().info(f"[PE clean_payment_ledger] No PLE found for {doc.name}")
        return

    frappe.logger().info(
        f"[PE clean_payment_ledger] Deleting {len(ple_names)} PLE for {doc.name}: {ple_names}"
    )

    frappe.db.delete("Payment Ledger Entry", {"voucher_no": doc.name})
    frappe.db.commit()


def on_submit(doc, method=None):
    """Handle Payment Entry submit."""
    # Update DO Towing dulu — selalu dipanggil apapun tipe payment-nya
    _update_do_towing_payment_status(doc)
    
    # Lanjut logic expense request seperti biasa
    expense_request = _resolve_expense_request(doc)
    if not expense_request:
        return
    _handle_expense_request_submit(doc, expense_request)
    if getattr(doc, "awaiting_bank_reconciliation", 0):
        _revert_pi_status_for_bank_payment(doc)


def _update_do_towing_payment_status(doc):
    """Update status uang jalan di DO Towing saat payment dibuat."""
    try:
        from imogi_finance.overrides.delivery_order_towing import update_do_payment_status
        update_do_payment_status(doc)
    except Exception as e:
        import frappe
        frappe.log_error(str(e), "DO Towing Payment Status Update Error")

def _handle_expense_request_submit(doc, expense_request):
    """Handle Expense Request logic on Payment Entry submit."""
    request = _sync_expense_request_link(
        doc,
        expense_request,
        allowed_statuses=frozenset({"PI Created", "Paid"}),
    )
    if not request:
        return

    has_purchase_invoice = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": request.name, "docstatus": 1},
        "name",
    )

    if not has_purchase_invoice:
        frappe.throw(
            _("Expense Request must be linked to a submitted Purchase Invoice before submitting Payment Entry.")
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Payment Entry"),
        )

    if _is_bank_payment(doc):
        frappe.logger().info(
            f"[PE on_submit] PE {doc.name} submitted for ER {request.name} via Bank account. "
            f"PI {has_purchase_invoice} will remain Unpaid until bank transaction is reconciled."
        )
        doc.awaiting_bank_reconciliation = 1
    else:
        frappe.logger().info(
            f"[PE on_submit] PE {doc.name} submitted for ER {request.name} via Cash. "
            f"PI {has_purchase_invoice} will be marked as Paid immediately."
        )


def _revert_pi_status_for_bank_payment(doc):
    """Revert linked Purchase Invoice status to Unpaid for bank payments."""
    linked_pis = []

    for ref in doc.get("references") or []:
        if ref.reference_doctype == "Purchase Invoice":
            linked_pis.append(ref.reference_name)

    if not linked_pis:
        return

    frappe.logger().info(
        f"[PE on_submit] Bank payment detected. Reverting PI status to Unpaid for {len(linked_pis)} invoices"
    )

    for pi_name in linked_pis:
        pi_status = frappe.db.get_value("Purchase Invoice", pi_name, "status")

        if pi_status != "Paid":
            continue

        frappe.logger().info(
            f"[PE on_submit] Reverting PI {pi_name} from Paid to Unpaid"
        )

        frappe.db.set_value(
            "Purchase Invoice",
            pi_name,
            "status",
            "Unpaid",
            update_modified=False,
        )

        expense_request = frappe.db.get_value(
            "Purchase Invoice",
            pi_name,
            "imogi_expense_request",
        )

        if expense_request:
            er_doctype = get_er_doctype(expense_request) or "Expense Request"
            frappe.db.set_value(
                er_doctype,
                expense_request,
                {"workflow_state": "PI Created", "status": "PI Created"},
                update_modified=False,
            )
            frappe.logger().info(
                f"[PE on_submit] Reverted ER {expense_request} status to PI Created"
            )

    frappe.db.set_value(
        "Payment Entry",
        doc.name,
        "awaiting_bank_reconciliation",
        1,
        update_modified=False,
    )


def on_update_after_submit(doc, method=None):
    """Handle updates after submit for bank reconciliation flow."""
    if not getattr(doc, "awaiting_bank_reconciliation", 0):
        return

    _revert_pi_status_for_bank_payment(doc)


def before_cancel(doc, method=None):
    frappe.logger().info(f"[PE before_cancel] Triggered for {doc.name}")

    if _check_linked_to_printed_report(doc):
        frappe.throw(
            _(
                "Cannot cancel Payment Entry {0} because it is included in a printed Cash/Bank Daily Report. "
                "Use the 'Reverse Payment Entry' button instead to create a reversal entry at today's date."
            ).format(doc.name),
            title=_("Cancellation Blocked"),
        )

    doc.flags.ignore_links = True
    doc.flags.ignore_link_validation = True
    doc.flags.skip_link_doctypes = True

    clean_payment_ledger(doc)


def clean_gl_entries(doc):
    if not doc.name:
        return

    gl_names = frappe.get_all(
        "GL Entry",
        filters={
            "voucher_type": "Payment Entry",
            "voucher_no": doc.name,
        },
        pluck="name",
    )

    if not gl_names:
        frappe.logger().info(f"[PE clean_gl_entries] No GL Entry found for {doc.name}")
        return

    frappe.logger().info(
        f"[PE clean_gl_entries] Deleting {len(gl_names)} GL Entry for {doc.name}: {gl_names}"
    )

    frappe.db.delete(
        "GL Entry",
        {
            "voucher_type": "Payment Entry",
            "voucher_no": doc.name,
        },
    )
    frappe.db.commit()


def before_delete(doc, method=None):
    frappe.logger().info(f"[PE before_delete] Triggered for {doc.name}")

    doc.flags.ignore_links = True
    doc.flags.ignore_link_validation = True
    doc.flags.skip_link_doctypes = True

    clean_payment_ledger(doc)
    clean_gl_entries(doc)


def on_cancel(doc, method=None):
    """Handle Payment Entry cancellation and sync Expense Request status."""
    expense_request_name = doc.get("imogi_expense_request")
    if not expense_request_name:
        return

    er_doctype = get_er_doctype(expense_request_name) or "Expense Request"
    request_links = get_expense_request_links(expense_request_name)
    next_status = get_expense_request_status(request_links)

    frappe.db.set_value(
        er_doctype,
        expense_request_name,
        {"workflow_state": next_status, "status": next_status},
        update_modified=False,
    )

    frappe.logger().info(
        f"[PE on_cancel] PE {doc.name} cancelled. "
        f"ER {expense_request_name} status updated to: {next_status} (based on PI status)"
    )


def _check_linked_to_printed_report(payment_entry) -> bool:
    """Return True if Payment Entry is included in a submitted Cash/Bank Daily Report."""
    if not getattr(frappe, "db", None):
        return False

    posting_date = getattr(payment_entry, "posting_date", None)
    if not posting_date:
        return False

    printed_reports = frappe.get_all(
        "Cash Bank Daily Report",
        filters={
            "report_date": posting_date,
            "docstatus": 1,
        },
        fields=["name", "cash_account", "bank_account"],
    )

    if not printed_reports:
        return False

    pe_account = getattr(payment_entry, "paid_from", None) or getattr(payment_entry, "paid_to", None)

    for report in printed_reports:
        if report.get("cash_account") == pe_account or report.get("bank_account") == pe_account:
            return True

    return False


@frappe.whitelist()
def reverse_payment_entry(payment_entry_name: str, reversal_date: str | None = None):
    """Create a reversal Payment Entry."""
    original_pe = frappe.get_doc("Payment Entry", payment_entry_name)

    if original_pe.docstatus != 1:
        frappe.throw(_("Can only reverse submitted Payment Entries"))

    if not reversal_date:
        reversal_date = frappe.utils.today()

    reversal_pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "posting_date": reversal_date,
        "payment_type": original_pe.payment_type,
        "company": original_pe.company,
        "paid_from": original_pe.paid_to,
        "paid_to": original_pe.paid_from,
        "paid_amount": original_pe.paid_amount,
        "received_amount": original_pe.received_amount,
        "paid_from_account_currency": getattr(original_pe, "paid_to_account_currency", None),
        "paid_to_account_currency": getattr(original_pe, "paid_from_account_currency", None),
        "source_exchange_rate": original_pe.source_exchange_rate,
        "target_exchange_rate": original_pe.target_exchange_rate,
        "mode_of_payment": original_pe.mode_of_payment,
        "party_type": original_pe.party_type,
        "party": original_pe.party,
        "party_account": getattr(original_pe, "party_account", None),
        "branch": original_pe.branch if hasattr(original_pe, "branch") else None,
        "remarks": _("Reversal of Payment Entry {0} (original date: {1})").format(
            original_pe.name,
            frappe.utils.format_date(original_pe.posting_date),
        ),
        "references": [
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "total_amount": ref.total_amount,
                "outstanding_amount": ref.outstanding_amount,
                "allocated_amount": -ref.allocated_amount,
            }
            for ref in (original_pe.references or [])
        ] if original_pe.get("references") else [],
        "is_reversal": 1,
        "reversed_entry": original_pe.name,
    })

    reversal_pe.insert()

    frappe.msgprint(
        _(
            "Reversal Payment Entry {0} created for date {1}. "
            "Please review and submit it."
        ).format(reversal_pe.name, frappe.utils.format_date(reversal_date)),
        indicator="green",
        title=_("Reversal Created"),
    )

    frappe.db.set_value(
        "Payment Entry",
        payment_entry_name,
        {
            "is_reversed": 1,
            "reversal_entry": reversal_pe.name,
        },
    )

    expense_request = _resolve_expense_request(original_pe)
    if expense_request:
        er_doctype = get_er_doctype(expense_request) or "Expense Request"
        request_links = get_expense_request_links(expense_request)
        next_status = get_expense_request_status(request_links)

        frappe.db.set_value(
            er_doctype,
            expense_request,
            {"workflow_state": next_status, "status": next_status},
            update_modified=False,
        )

        frappe.logger().info(
            f"[PE reversal] PE {payment_entry_name} reversed. "
            f"ER {expense_request} status updated to: {next_status} (based on PI status)"
        )

    return reversal_pe.as_dict()


def on_trash(doc, method=None):
    """Clear Expense Request links before deleting Payment Entry."""
    expense_request = _resolve_expense_request(doc)
    if not expense_request:
        return

    er_doctype = get_er_doctype(expense_request)
    if not er_doctype:
        return

    updates = {}

    current_linked = frappe.db.get_value(er_doctype, expense_request, "linked_payment_entry")
    if current_linked == doc.name:
        updates["linked_payment_entry"] = None

    request_links = get_expense_request_links(expense_request)
    next_status = get_expense_request_status(request_links)
    updates["workflow_state"] = next_status
    updates["status"] = next_status

    frappe.db.set_value(er_doctype, expense_request, updates)
    frappe.db.commit()

    frappe.logger().info(
        f"[PE trash] PE {doc.name} deleted. Updated ER {expense_request} status to {next_status}"
    )