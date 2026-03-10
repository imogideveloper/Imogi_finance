frappe.provide('imogi_finance');
frappe.require('/assets/imogi_finance/js/tax_invoice_fields.js');

const TAX_INVOICE_MODULE = imogi_finance?.tax_invoice || {};
const DEFAULT_COPY_KEYS = [
  'fp_no',
  'fp_date',
  'npwp',
  'dpp',
  'ppn',
  'ppnbm',
  'ppn_type',
  'status',
  'notes',
  'duplicate_flag',
  'npwp_match',
];
const DEFAULT_PI_FIELDS = {
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
  ocr_status: 'ti_ocr_status',
  ocr_confidence: 'ti_ocr_confidence',
  ocr_raw_json: 'ti_ocr_raw_json',
  tax_invoice_pdf: 'ti_tax_invoice_pdf',
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
  ocr_status: 'ocr_status',
  ocr_confidence: 'ocr_confidence',
  ocr_raw_json: 'ocr_raw_json',
  tax_invoice_pdf: 'tax_invoice_pdf',
};

const PI_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Purchase Invoice')) || DEFAULT_PI_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Tax Invoice OCR Upload')) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS = (TAX_INVOICE_MODULE.getSharedCopyKeys && TAX_INVOICE_MODULE.getSharedCopyKeys('Tax Invoice OCR Upload', 'Purchase Invoice'))
  || DEFAULT_COPY_KEYS;

async function syncPiUpload(frm) {
  if (!frm.doc.ti_tax_invoice_upload) {
    return;
  }

  // IMPORTANT: Don't sync if document was just saved (not dirty) and not new
  // This prevents the form from becoming dirty after save, which would
  // hide the Submit button and show "Not Saved" status again
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
    const targetField = PI_TAX_INVOICE_FIELDS[key];
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

function lockPiTaxInvoiceFields(frm) {
  Object.values(PI_TAX_INVOICE_FIELDS).forEach((field) => {
    frm.set_df_property(field, 'read_only', true);
  });
}

async function setPiUploadQuery(frm) {
  let usedUploads = [];
  let verifiedUploads = [];
  let providerReady = true;
  let providerError = null;

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
      args: { target_doctype: 'Purchase Invoice', target_name: frm.doc.name },
    });
    usedUploads = message?.used_uploads || [];
    verifiedUploads = message?.verified_uploads || [];
    providerReady = Boolean(message?.provider_ready ?? true);
    providerError = message?.provider_error || null;
  } catch (error) {
    console.error('Unable to load available Tax Invoice uploads', error);
  }

  frm.taxInvoiceProviderReady = providerReady;
  frm.taxInvoiceProviderError = providerError;

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

frappe.ui.form.on('Purchase Invoice', {
  async refresh(frm) {
    lockPiTaxInvoiceFields(frm);
    await setPiUploadQuery(frm);

    // OCR button removed - OCR should only be triggered from Tax Invoice OCR Upload DocType
    // Users can click 'Open Tax Invoice Upload' button to access the Upload form and run OCR there

    const addOpenButton = () => {
      if (!frm.doc.ti_tax_invoice_upload) {
        return;
      }
      frm.add_custom_button(__('Open Tax Invoice Upload'), () => {
        frappe.set_route('Form', 'Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
      }, __('Tax Invoice'));
    };

    await syncPiUpload(frm);
    // addOcrButton(); // Removed - OCR only via Upload DocType
    addOpenButton();
  },

  async ti_tax_invoice_upload(frm) {
    await syncPiUpload(frm);
  },
});
