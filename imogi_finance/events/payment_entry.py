def set_payment_status(doc, method=None):
    if doc.docstatus == 0:
        status = "Draft"
    elif doc.docstatus == 2:
        status = "Cancelled"
    elif (doc.unallocated_amount or 0) > 0:
        status = "Unallocated"
    else:
        status = "Allocated"
    doc.db_set("payment_status", status, update_modified=False)
