frappe.query_reports["Customer Receipt Control Report"] = {
  filters: [
    { fieldname: "date_from", label: "From Date", fieldtype: "Date" },
    { fieldname: "date_to", label: "To Date", fieldtype: "Date" },
    { fieldname: "receipt_no", label: "Receipt No", fieldtype: "Link", options: "Customer Receipt" },
    { fieldname: "payment_status", label: "Payment Status", fieldtype: "Select", options: "\nDraft\nPending\nIn Progress\nDP/Partial\nFull Payment\nCancelled" },
    { fieldname: "customer", label: "Customer", fieldtype: "Link", options: "Customer" },
    { fieldname: "customer_reference_no", label: "Customer Ref No", fieldtype: "Data" },
    { fieldname: "sales_order_no", label: "Sales Order", fieldtype: "Link", options: "Sales Order" },
    { fieldname: "billing_no", label: "Sales Invoice", fieldtype: "Link", options: "Sales Invoice" },
    { fieldname: "sales_invoice_no", label: "Billing No (Alt)", fieldtype: "Link", options: "Sales Invoice" },
    {
      fieldname: "receipt_purpose",
      label: "Purpose",
      fieldtype: "Select",
      options: "\nBefore Billing (Sales Order)\nBilling (Sales Invoice)"
    },
    {
      fieldname: "stamp_mode",
      label: "Stamp Mode",
      fieldtype: "Select",
      options: "\nNone\nPhysical\nDigital"
    },
    {
      fieldname: "digital_stamp_status",
      label: "Digital Stamp Status",
      fieldtype: "Select",
      options: "\nDraft\nRequested\nIssued\nFailed\nCancelled"
    }
  ],
  formatter: function(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    // Color code Payment Status column
    if (column.fieldname === "payment_status") {
      if (data.payment_status === "DP/Partial") {
        value = `<span style="color: #e67e22; font-weight: bold;">${value}</span>`;
      } else if (data.payment_status === "Full Payment") {
        value = `<span style="color: #27ae60; font-weight: bold;">${value}</span>`;
      } else if (data.payment_status === "Pending") {
        value = `<span style="color: #3498db;">${value}</span>`;
      } else if (data.payment_status === "In Progress") {
        value = `<span style="color: #9b59b6;">${value}</span>`;
      } else if (data.payment_status === "Cancelled") {
        value = `<span style="color: #95a5a6;">${value}</span>`;
      }
    }

    // Highlight Ref Outstanding if > 0
    if (column.fieldname === "ref_outstanding" && data.ref_outstanding > 0) {
      value = `<span style="color: #e74c3c; font-weight: bold;">${value}</span>`;
    }

    return value;
  }
};
