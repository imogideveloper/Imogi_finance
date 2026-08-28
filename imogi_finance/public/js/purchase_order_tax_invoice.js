frappe.provide('imogi_finance');
frappe.require('/assets/imogi_finance/js/tax_invoice_fields.js');

const TAX_INVOICE_MODULE = imogi_finance?.tax_invoice || {};
const DEFAULT_PO_FIELDS = {
  fp_no: 'ti_fp_no',
  fp_date: 'ti_fp_date',
  npwp: 'ti_fp_npwp',
  dpp: 'ti_fp_dpp',
  ppn: 'ti_fp_ppn',
  ppnbm: 'ti_fp_ppnbm',
  ppn_type: 'ti_fp_ppn_type',
  status: 'ti_verification_status',
  notes: 'ti_verification_notes',
  duplicate_flag: 'ti_duplicate_flag',
  npwp_match: 'ti_npwp_match',
};
const DEFAULT_UPLOAD_FIELDS = {
  fp_no: 'fp_no',
  fp_date: 'fp_date',
  npwp: 'npwp',
  dpp: 'dpp',
  ppn: 'ppn',
  ppnbm: 'ppnbm',
  ppn_type: 'ppn_type',
  status: 'verification_status',
  notes: 'verification_notes',
  duplicate_flag: 'duplicate_flag',
  npwp_match: 'npwp_match',
};

const PO_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Purchase Order')) || DEFAULT_PO_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Tax Invoice OCR Upload')) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS = (TAX_INVOICE_MODULE.getSharedCopyKeys && TAX_INVOICE_MODULE.getSharedCopyKeys('Tax Invoice OCR Upload', 'Purchase Order'))
  || Object.keys(DEFAULT_PO_FIELDS);

async function syncPoUpload(frm) {
  if (!frm.doc.ti_tax_invoice_upload) {
    return;
  }

  // Same guard as purchase_invoice_tax_invoice.js's syncPiUpload(): don't
  // dirty an already-saved, non-new form just from refresh.
  if (!frm.doc.__islocal && !frm.is_dirty()) {
    return;
  }

  const cachedUpload = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
  const upload = cachedUpload || await frappe.db.get_doc('Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
  const updates = {};

  const normalizeValue = (value) => {
    if (value === undefined || value === null || value === '') {
      return null;
    }
    return value;
  };

  COPY_KEYS.forEach((key) => {
    const sourceField = UPLOAD_TAX_INVOICE_FIELDS[key];
    const targetField = PO_TAX_INVOICE_FIELDS[key];
    if (!sourceField || !targetField) {
      return;
    }

    const nextValue = normalizeValue(upload[sourceField]);
    const currentValue = normalizeValue(frm.doc[targetField]);

    if (currentValue !== nextValue) {
      updates[targetField] = nextValue;
    }
  });

  if (Object.keys(updates).length) {
    await frm.set_value(updates);
  }
}

function lockPoTaxInvoiceFields(frm) {
  Object.values(PO_TAX_INVOICE_FIELDS).forEach((field) => {
    frm.set_df_property(field, 'read_only', true);
  });
}

async function setPoUploadQuery(frm) {
  let usedUploads = [];
  let verifiedUploads = [];

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
      args: { target_doctype: 'Purchase Order', target_name: frm.doc.name },
    });
    usedUploads = message?.used_uploads || [];
    verifiedUploads = message?.verified_uploads || [];
  } catch (error) {
    console.error('Unable to load available Tax Invoice uploads', error);
  }

  frm.taxInvoiceUploadCache = (verifiedUploads || []).reduce((acc, upload) => {
    acc[upload.name] = upload;
    return acc;
  }, {});

  frm.set_query('ti_tax_invoice_upload', () => ({
    filters: {
      verification_status: 'Verified',
      ...(usedUploads.length ? { name: ['not in', usedUploads] } : {}),
    },
  }));
}

frappe.ui.form.on('Purchase Order', {
  async refresh(frm) {
    lockPoTaxInvoiceFields(frm);
    await setPoUploadQuery(frm);

    if (frm.doc.ti_tax_invoice_upload) {
      frm.add_custom_button(__('Open Tax Invoice Upload'), () => {
        frappe.set_route('Form', 'Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
      }, __('Tax Invoice'));
    }

    await syncPoUpload(frm);
  },

  async ti_tax_invoice_upload(frm) {
    await syncPoUpload(frm);
    if (frm.doc.ti_tax_invoice_upload) {
      await frm.set_value({ ppn_exclude: 1, ppn_include: 0, ppn_non: 0 });
    }
  },
});
