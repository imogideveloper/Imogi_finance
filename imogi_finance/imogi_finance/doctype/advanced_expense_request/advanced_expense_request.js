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
  'status',
  'notes',
  'duplicate_flag',
  'npwp_match',
];
const DEFAULT_ER_FIELDS = {
  fp_no: 'ti_fp_no',
  fp_date: 'ti_fp_date',
  npwp: 'ti_fp_npwp',
  dpp: 'ti_fp_dpp',
  ppn: 'ti_fp_ppn',
  ppnbm: 'ti_fp_ppnbm',
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
  status: 'verification_status',
  notes: 'verification_notes',
  duplicate_flag: 'duplicate_flag',
  npwp_match: 'npwp_match',
  ocr_status: 'ocr_status',
  ocr_confidence: 'ocr_confidence',
  ocr_raw_json: 'ocr_raw_json',
  tax_invoice_pdf: 'tax_invoice_pdf',
};

const ER_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Advanced Expense Request')) || DEFAULT_ER_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Tax Invoice OCR Upload')) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS = (TAX_INVOICE_MODULE.getSharedCopyKeys && TAX_INVOICE_MODULE.getSharedCopyKeys('Tax Invoice OCR Upload', 'Advanced Expense Request'))
  || DEFAULT_COPY_KEYS;

async function syncErUpload(frm) {
  if (!frm.doc.ti_tax_invoice_upload) {
    return;
  }

  if (frm.doc.docstatus !== 0) {
    return;
  }

  const cachedUpload = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
  const upload = cachedUpload || await frappe.db.get_doc('Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
  const updates = {};
  COPY_KEYS.forEach((key) => {
    const sourceField = UPLOAD_TAX_INVOICE_FIELDS[key];
    const targetField = ER_TAX_INVOICE_FIELDS[key];
    if (!sourceField || !targetField) {
      return;
    }
    updates[targetField] = upload[sourceField] ?? null;
  });
  await frm.set_value(updates);
}

function lockErTaxInvoiceFields(frm) {
  Object.values(ER_TAX_INVOICE_FIELDS).forEach((field) => {
    frm.set_df_property(field, 'read_only', true);
  });
}

function hideErOcrStatus(frm) {
  if (frm.fields_dict?.ti_ocr_status) {
    frm.set_df_property('ti_ocr_status', 'hidden', true);
  }
}

function formatApprovalTimestamps(frm) {
  for (let level = 1; level <= 3; level++) {
    const userField = `level_${level}_user`;
    const approvedField = `level_${level}_approved_on`;
    const rejectedField = `level_${level}_rejected_on`;

    if (!frm.doc[userField]) {
      continue;
    }

    if (frm.doc[approvedField]) {
      const formattedTime = frappe.datetime.str_to_user(frm.doc[approvedField]);
      frm.set_df_property(approvedField, 'description', `✅ Approved at ${formattedTime}`);
    }

    if (frm.doc[rejectedField]) {
      const formattedTime = frappe.datetime.str_to_user(frm.doc[rejectedField]);
      frm.set_df_property(rejectedField, 'description', `❌ Rejected at ${formattedTime}`);
    }
  }
}

function setExpenseAccountQuery(frm) {
  const filters = { root_type: 'Expense', is_group: 0 };
  frm.set_query('expense_account', () => ({ filters }));
  frm.set_query('expense_account', 'items', () => ({ filters }));
}

function setItemCostCenterQuery(frm) {
  // Optionally filter cost_center on items by company
  frm.set_query('cost_center', 'items', () => {
    const filters = { is_group: 0 };
    return { filters };
  });
}

function formatCurrency(frm, value) {
  return frappe.format(value, { fieldtype: 'Currency', options: frm.doc.currency });
}

async function setPphRate(frm) {
  if (!frm.doc.pph_type) {
    frm._pph_rate = 0;
    return;
  }

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.imogi_finance.doctype.advanced_expense_request.advanced_expense_request.get_pph_rate',
      args: { pph_type: frm.doc.pph_type },
    });
    frm._pph_rate = message?.rate || 0;
  } catch (error) {
    frm._pph_rate = 0;
  }
}

function computeTotals(frm) {
  const flt = (frappe.utils && frappe.utils.flt) || window.flt || ((value) => parseFloat(value) || 0);
  const totalExpense = flt(frm.doc.amount || 0);

  const varianceTotal = (frm.doc.items || []).reduce(
    (sum, row) => sum + (row.is_variance_item ? flt(row.amount || 0) : 0),
    0,
  );

  const itemPphTotal = (frm.doc.items || []).reduce(
    (sum, row) => sum + (row.is_pph_applicable && !row.is_variance_item ? flt(row.pph_base_amount || 0) : 0),
    0,
  );

  let totalPpn = 0;
  if (frm.doc.docstatus === 0) {
    if (frm.doc.is_ppn_applicable) {
      const ppnRate = flt(frm._ppn_rate || 0);
      totalPpn = (totalExpense * ppnRate) / 100;
    }
  } else {
    totalPpn = flt(frm.doc.total_ppn || 0);
  }

  const totalPpnbm = flt(frm.doc.ti_fp_ppnbm || frm.doc.ppnbm || 0);
  const pphBaseTotal = itemPphTotal
    || (frm.doc.is_pph_applicable ? flt(frm.doc.pph_base_amount || 0) : 0);
  const pphRate = flt(frm._pph_rate || 0);
  const totalPph = Math.abs(pphRate ? (pphBaseTotal * pphRate) / 100 : pphBaseTotal);
  const totalAmount = totalExpense + totalPpn + totalPpnbm - totalPph + varianceTotal;

  return {
    totalExpense,
    totalPpn,
    totalPpnbm,
    pphBaseTotal,
    totalPph,
    varianceTotal,
    totalAmount,
  };
}

function renderTotalsHtml(frm, totals) {
  const format = (value) =>
    frappe.format(value, { fieldtype: 'Currency', options: frm.doc.currency });

  const rows = [
    ['Total Expense', format(totals.totalExpense)],
    ['Total PPN', format(totals.totalPpn)],
    ['Total PPnBM', format(totals.totalPpnbm)],
    [
      'Total PPh',
      totals.totalPph
        ? `<span style="color:#c0392b;font-weight:500">${format(totals.totalPph)}</span>`
        : format(0),
    ],
  ];

  if (totals.varianceTotal && Math.abs(totals.varianceTotal) > 0.001) {
    const varianceColor = totals.varianceTotal > 0 ? '#27ae60' : '#e67e22';
    rows.push([
      'PPN Variance',
      `<span style="color:${varianceColor};font-weight:500">${format(totals.varianceTotal)}</span>`,
    ]);
  }

  rows.push(['Total', format(totals.totalAmount)]);

  const cells = rows
    .map(
      ([label, value]) => `
        <tr>
          <td>${frappe.utils.escape_html(label)}</td>
          <td class="text-right">${value}</td>
        </tr>
      `
    )
    .join('');

  return `<table class="table table-bordered table-sm"><tbody>${cells}</tbody></table>`;
}

let ppnRateCache = {};

async function getPpnRate(frm) {
  if (!frm.doc.ppn_template) {
    frm.doc.__ppn_rate = 0;
    return 0;
  }

  const cacheKey = frm.doc.ppn_template;
  if (ppnRateCache[cacheKey] !== undefined) {
    frm.doc.__ppn_rate = ppnRateCache[cacheKey];
    return ppnRateCache[cacheKey];
  }

  try {
    const template = await frappe.db.get_doc('Purchase Taxes and Charges Template', frm.doc.ppn_template);
    const rate = (template.taxes && template.taxes[0] && template.taxes[0].rate) || 0;
    ppnRateCache[cacheKey] = rate;
    frm.doc.__ppn_rate = rate;
    return rate;
  } catch (error) {
    console.error('Error fetching PPN rate:', error);
    frm.doc.__ppn_rate = 0;
    return 0;
  }
}

async function updateTotalsSummary(frm) {
  if (frm.doc.is_ppn_applicable && frm.doc.ppn_template) {
    await getPpnRate(frm);
  }

  const totals = computeTotals(frm);
  const fields = {
    total_expense: totals.totalExpense,
    total_ppn: totals.totalPpn,
    total_ppnbm: totals.totalPpnbm,
    pph_base_amount: totals.pphBaseTotal,
    total_pph: totals.totalPph,
    total_amount: totals.totalAmount,
  };

  if (frm.doc.docstatus === 0) {
    Object.entries(fields).forEach(([field, value]) => {
      if (!frm.fields_dict[field]) {
        return;
      }
      if (frm.doc[field] !== value) {
        frm.doc[field] = value;
        frm.refresh_field(field);
      }
    });
  }

  const html = renderTotalsHtml(frm, totals);
  ['items_totals_html'].forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    if (field?.$wrapper) {
      field.$wrapper.html(html);
    }
  });

  updatePphBaseFieldState(frm, totals);
}

function updatePphBaseFieldState(frm, totals) {
  const items = frm.doc.items || [];
  const anyItemPph = items.some((row) => Boolean(row.is_pph_applicable));
  const headerPphFlag = Boolean(frm.doc.is_pph_applicable);

  const useItemMode = anyItemPph;
  const headerShouldBeReadOnly = useItemMode;

  if (frm.fields_dict?.pph_base_amount) {
    frm.set_df_property('pph_base_amount', 'read_only', headerShouldBeReadOnly);
  }

  const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
  if (grid && typeof grid.update_docfield_property === 'function') {
    const lockItemBase = headerPphFlag && !useItemMode;
    grid.update_docfield_property('pph_base_amount', 'read_only', lockItemBase);
  }
}

function canSubmitExpenseRequest(frm) {
  if (frm.is_new()) {
    return false;
  }

  if (frm.doc.docstatus !== 0) {
    return false;
  }

  return frappe.user.has_role('Expense Request Submitter');
}

function maybeRenderPrimarySubmitButton(frm) {
  frm.remove_custom_button(__('Submit'));

  if (!canSubmitExpenseRequest(frm)) {
    return;
  }

  const submitBtn = frm.add_custom_button(__('Submit'), () => frm.save('Submit'));
  submitBtn.addClass('btn-primary');
}

async function checkOcrEnabled(frm) {
  try {
    const ocrEnabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
    frm.doc.__ocr_enabled = Boolean(ocrEnabled);
    frm.refresh_fields();
  } catch (error) {
    frm.doc.__ocr_enabled = false;
  }
}

async function setErUploadQuery(frm) {
  let usedUploads = [];
  let verifiedUploads = [];
  let providerReady = true;
  let providerError = null;

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
      args: { target_doctype: 'Advanced Expense Request', target_name: frm.doc.name },
    });
    usedUploads = message?.used_uploads || [];
    verifiedUploads = message?.verified_uploads || [];
    providerReady = Boolean(message?.provider_ready ?? true);
    providerError = message?.provider_error || null;
  } catch (error) {
    // Silent fail
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

async function loadDeferrableAccounts(frm) {
  if (frm.deferrableAccountsLoaded) {
    return;
  }

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.get_deferrable_accounts',
    });

    const accounts = message?.accounts || [];
    frm.deferrableAccountMap = accounts.reduce((acc, row) => {
      if (row.prepaid_account) {
        acc[row.prepaid_account] = row;
      }
      return acc;
    }, {});
    frm.deferrableAccountsLoaded = true;
  } catch (error) {
    // Silent fail
  }
}

async function setDeferredExpenseQueries(frm) {
  await loadDeferrableAccounts(frm);

  frm.set_query('prepaid_account', 'items', () => {
    const filters = {
      account_type: 'Current Asset',
      is_group: 0,
    };
    if (frm.doc.company) {
      filters.company = frm.doc.company;
    }
    return { filters };
  });
}

async function showDeferredScheduleForItem(row) {
  if (!row.deferred_start_date) {
    frappe.msgprint(__('Deferred Start Date is required to generate the amortization schedule.'));
    return;
  }

  if (!row.deferred_periods || row.deferred_periods <= 0) {
    frappe.msgprint(__('Deferred Periods must be greater than zero to generate the amortization schedule.'));
    return;
  }

  const { message } = await frappe.call({
    method: 'imogi_finance.services.deferred_expense.generate_amortization_schedule',
    args: {
      amount: row.amount,
      periods: row.deferred_periods,
      start_date: row.deferred_start_date,
    },
  });

  const schedule = message || [];
  const pretty = Array.isArray(schedule) ? JSON.stringify(schedule, null, 2) : String(schedule);
  frappe.msgprint({
    title: __('Amortization Schedule'),
    message: `<pre style="white-space: pre-wrap;">${pretty}</pre>`,
    indicator: 'blue',
  });
}

function addDeferredExpenseItemActions(frm) {
  const grid = frm.fields_dict.items?.grid;
  if (!grid) {
    return;
  }

  grid.grid_rows.forEach((row) => {
    if (!row?.doc?.is_deferred_expense) {
      return;
    }

    const hasAction = row.__hasDeferredAction;
    if (hasAction) {
      return;
    }

    const addButton = row.add_custom_button || row.grid_form?.add_custom_button;
    if (typeof addButton !== 'function') {
      return;
    }

    addButton.call(row, __('Show Amortization Schedule'), () => showDeferredScheduleForItem(row.doc));
    row.__hasDeferredAction = true;
  });
}

function updateDeferredExpenseIndicators(frm) {
  const grid = frm.fields_dict.items?.grid;
  if (!grid) {
    return;
  }

  grid.grid_rows.forEach((row) => {
    const indicator = row.$row?.find('.grid-static-col[data-fieldname=\"is_deferred_expense\"] .static-text');
    if (!indicator?.length) {
      return;
    }
    indicator.text(row.doc?.is_deferred_expense ? '📅' : '');
  });
}

function lockVarianceItemRows(frm) {
  const items = frm.doc.items || [];

  if (!frm.fields_dict?.items?.grid) {
    return;
  }

  const grid = frm.fields_dict.items.grid;

  if (!grid.grid_rows || !Array.isArray(grid.grid_rows)) {
    return;
  }

  items.forEach((item, idx) => {
    if (!item || !item.is_variance_item) {
      return;
    }

    const row = grid.grid_rows[idx];

    if (!row) {
      return;
    }

    if (row.docfields && Array.isArray(row.docfields)) {
      row.docfields.forEach((df) => {
        if (!df || !df.fieldname) return;

        const field = row.fields_dict?.[df.fieldname];
        if (field && field.$input) {
          field.$input.prop('disabled', true);
        }
      });
    }

    if (row.row && typeof row.row.find === 'function') {
      const deleteBtn = row.row.find('.grid-delete-row');
      if (deleteBtn && deleteBtn.length) {
        deleteBtn.hide();
      }
    }

    if (row.row && row.row.length) {
      row.row.css({
        'background-color': '#fff3cd !important',
        'border-left': '3px solid #ffc107 !important'
      });

      row.row.find('input, textarea, select, .static-area').css({
        'color': '#856404 !important',
        'font-style': 'italic'
      });

      const descField = row.row.find('[data-fieldname="description"]');
      if (descField.length) {
        descField.css({
          'color': '#856404 !important',
          'font-weight': '500'
        });
      }

      const amountField = row.row.find('[data-fieldname="amount"]');
      if (amountField.length) {
        amountField.css({
          'color': '#856404 !important',
          'font-weight': 'bold'
        });
      }
    }
  });
}

frappe.ui.form.on('Advanced Expense Request', {
  async refresh(frm) {
    hideErOcrStatus(frm);
    lockErTaxInvoiceFields(frm);
    setExpenseAccountQuery(frm);
    setItemCostCenterQuery(frm);
    formatApprovalTimestamps(frm);
    frm.dashboard.clear_headline();
    await setErUploadQuery(frm);
    await checkOcrEnabled(frm);
    await syncErUpload(frm);
    await setPphRate(frm);
    await setDeferredExpenseQueries(frm);
    addDeferredExpenseItemActions(frm);
    updateDeferredExpenseIndicators(frm);
    lockVarianceItemRows(frm);
    maybeRenderPrimarySubmitButton(frm);
    updateTotalsSummary(frm);

    const isDraft = frm.doc.docstatus === 0;

    const addCheckRouteButton = () => {
      if (!frm.doc.approval_cost_center) {
        return;
      }

      const routeBtn = frm.add_custom_button(__('Check Approval Route'), async () => {
        const stringify = (value) => JSON.stringify(value || []);

        try {
          routeBtn?.prop?.('disabled', true);
        } catch (error) {
          // ignore
        }

        try {
          const { message } = await frappe.call({
            method: 'imogi_finance.approval.check_expense_request_route',
            args: {
              cost_center: frm.doc.approval_cost_center,
              items: stringify(frm.doc.items),
              expense_accounts: stringify(frm.doc.expense_accounts),
              amount: frm.doc.amount,
              docstatus: frm.doc.docstatus,
            },
          });

          if (message?.ok) {
            const route = message.route || {};
            const rows = ['1', '2', '3']
              .map((level) => {
                const info = route[`level_${level}`] || {};
                if (!info.role && !info.user) {
                  return null;
                }
                const role = info.role ? __('Role: {0}', [info.role]) : '';
                const user = info.user ? __('User: {0}', [info.user]) : '';
                const details = [role, user].filter(Boolean).join(' | ');
                return `<li>${__('Level {0}', [level])}: ${details}</li>`;
              })
              .filter(Boolean)
              .join('');

            let messageContent = rows
              ? `<ul>${rows}</ul>`
              : __('No approver configured for the current route.');

            frappe.msgprint({
              title: __('Approval Route'),
              message: messageContent,
              indicator: 'green',
            });
            return;
          }

          let indicator = 'orange';
          let errorMessage = message?.message
            ? message.message
            : __('Approval route could not be determined. Please ask your System Manager to configure an Expense Approval Setting.');

          if (message?.user_validation && !message.user_validation.valid) {
            indicator = 'red';

            const details = [];

            if (message.user_validation.invalid_users?.length) {
              details.push(
                '<strong>' + __('Users not found:') + '</strong><ul>' +
                message.user_validation.invalid_users.map(u =>
                  `<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
                ).join('') +
                '</ul>'
              );
            }

            if (message.user_validation.disabled_users?.length) {
              details.push(
                '<strong>' + __('Users disabled:') + '</strong><ul>' +
                message.user_validation.disabled_users.map(u =>
                  `<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
                ).join('') +
                '</ul>'
              );
            }

            if (details.length) {
              errorMessage = details.join('<br>') +
                '<br><br>' + __('Please update the Expense Approval Setting to use valid, active users.');
            }
          }
          frappe.msgprint({
            title: __('Approval Route'),
            message: errorMessage,
            indicator: indicator,
          });
        } catch (error) {
          frappe.msgprint({
            title: __('Approval Route'),
            message: error?.message
              ? error.message
              : __('Unable to check approval route right now. Please try again.'),
            indicator: 'red',
          });
        } finally {
          try {
            routeBtn?.prop?.('disabled', false);
          } catch (error) {
            // ignore
          }
        }
      }, __('Actions'));
    };

    addCheckRouteButton();

    if (isDraft) {
      return;
    }

    const isSubmitted = frm.doc.docstatus === 1;
    if (frm.doc.status === 'Approved') {
      frm.dashboard.set_headline(
        '<span class="indicator orange">' +
        __('Advanced Expense Request is Approved. Ready to create Purchase Invoice.') +
        '</span>'
      );
    } else if (frm.doc.status === 'PI Created') {
      frm.dashboard.set_headline(
        '<span class="indicator blue">' +
        __('Purchase Invoice {0} created. Awaiting payment.', [frm.doc.linked_purchase_invoice]) +
        '</span>'
      );
    } else if (frm.doc.status === 'Paid') {
      frm.dashboard.set_headline(
        '<span class="indicator green">' +
        __('Advanced Expense Request completed and paid.') +
        '</span>'
      );
    }

    if (isSubmitted && (frm.doc.workflow_state === 'Pending Review' || frm.doc.status === 'Pending Review')) {
      await maybeRenderApprovalButtons(frm);
    }

    if (isSubmitted && (frm.doc.workflow_state === 'Approved' || frm.doc.status === 'Approved') && !frm.doc.linked_purchase_invoice) {
      await maybeRenderPurchaseInvoiceButton(frm);
    }
  },

  items_add(frm) {
    addDeferredExpenseItemActions(frm);
    updateDeferredExpenseIndicators(frm);
    updateTotalsSummary(frm);
  },

  items_remove(frm) {
    updateDeferredExpenseIndicators(frm);
    updateTotalsSummary(frm);
  },

  async supplier(frm) {
    if (frm.doc.supplier && !frm.doc.supplier_tax_id) {
      try {
        const { message } = await frappe.db.get_value('Supplier', frm.doc.supplier, 'tax_id');
        if (message?.tax_id) {
          frm.set_value('supplier_tax_id', message.tax_id);
        }
      } catch (error) {
        // Ignore errors
      }
    }
  },

  ti_fp_ppn(frm) {
    updateTotalsSummary(frm);
  },

  ti_fp_ppnbm(frm) {
    updateTotalsSummary(frm);
  },

  async pph_type(frm) {
    await setPphRate(frm);
    updateTotalsSummary(frm);
  },

  pph_base_amount(frm) {
    updateTotalsSummary(frm);
  },

  async is_ppn_applicable(frm) {
    await checkOcrEnabled(frm);
    updateTotalsSummary(frm);
  },

  async ppn_template(frm) {
    const oldTemplate = frm.doc.ppn_template;
    if (oldTemplate && ppnRateCache[oldTemplate] !== undefined) {
      delete ppnRateCache[oldTemplate];
    }
    await updateTotalsSummary(frm);
  },

  async ti_tax_invoice_upload(frm) {
    await syncErUpload(frm);
  },
});

frappe.ui.form.on('Advanced Expense Request Item', {
  async prepaid_account(frm, cdt, cdn) {
    await loadDeferrableAccounts(frm);
    const row = frappe.get_doc(cdt, cdn);
    const mapping = frm.deferrableAccountMap?.[row.prepaid_account];
    if (!mapping) {
      return;
    }

    if (mapping.expense_account && row.expense_account !== mapping.expense_account) {
      frappe.model.set_value(cdt, cdn, 'expense_account', mapping.expense_account);
    }
    if (mapping.default_periods && !row.deferred_periods) {
      frappe.model.set_value(cdt, cdn, 'deferred_periods', mapping.default_periods);
    }
  },

  is_deferred_expense(frm) {
    addDeferredExpenseItemActions(frm);
    updateDeferredExpenseIndicators(frm);
  },

  deferred_start_date(frm) {
    addDeferredExpenseItemActions(frm);
  },

  deferred_periods(frm) {
    addDeferredExpenseItemActions(frm);
  },

  amount(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const amount = flt(row.amount) || 0;
    const discount = flt(row.discount_amount) || 0;
    frappe.model.set_value(cdt, cdn, 'net_amount', amount - discount);

    if (frm.doc.docstatus === 0 && row?.is_pph_applicable) {
      frappe.model.set_value(cdt, cdn, 'pph_base_amount', row.amount || 0);
    }
    updateTotalsSummary(frm);
  },

  discount_amount(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const amount = flt(row.amount) || 0;
    const discount = flt(row.discount_amount) || 0;
    frappe.model.set_value(cdt, cdn, 'net_amount', amount - discount);
    updateTotalsSummary(frm);
  },

  pph_base_amount(frm) {
    updateTotalsSummary(frm);
  },

  is_pph_applicable(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const baseAmount = row?.is_pph_applicable ? (row.amount || 0) : 0;
    if (frm.doc.docstatus === 0) {
      frappe.model.set_value(cdt, cdn, 'pph_base_amount', baseAmount);
    }
    updateTotalsSummary(frm);
  },
});

async function maybeRenderApprovalButtons(frm) {
  // Show Approve/Reject buttons only to the designated approver(s)
  const currentUser = frappe.session.user;
  const approvers = [frm.doc.level_1_user, frm.doc.level_2_user, frm.doc.level_3_user].filter(Boolean);

  // System Manager or Expense Approver role can always approve
  // Also show if user is explicitly named as an approver in the route
  const isPrivileged = frappe.user.has_role('System Manager') || frappe.user.has_role('Expense Approver');
  if (!isPrivileged && approvers.length > 0 && !approvers.includes(currentUser)) {
    return;
  }
  // If no approvers set (old doc before fix) show only to privileged roles
  if (!isPrivileged && approvers.length === 0) {
    return;
  }

  const approveBtn = frm.add_custom_button(__('Approve'), async () => {
    frappe.confirm(
      __('Are you sure you want to approve this expense request?'),
      async () => {
        try {
          const r = await frappe.call({
            method: 'imogi_finance.imogi_finance.doctype.advanced_expense_request.advanced_expense_request.apply_expense_action',
            args: { docname: frm.doc.name, action: 'Approve' },
            freeze: true,
            freeze_message: __('Approving...'),
          });
          frm.reload_doc();
        } catch (error) {
          frappe.msgprint({
            title: __('Error'),
            message: error?.message || __('Failed to approve'),
            indicator: 'red',
          });
        }
      }
    );
  });
  approveBtn.addClass('btn-success');

  frm.add_custom_button(__('Reject'), async () => {
    frappe.prompt(
      { fieldtype: 'Small Text', fieldname: 'reason', label: __('Reason for Rejection'), reqd: 1 },
      async (values) => {
        try {
          const r = await frappe.call({
            method: 'imogi_finance.imogi_finance.doctype.advanced_expense_request.advanced_expense_request.apply_expense_action',
            args: { docname: frm.doc.name, action: 'Reject' },
            freeze: true,
            freeze_message: __('Rejecting...'),
          });
          frm.reload_doc();
        } catch (error) {
          frappe.msgprint({
            title: __('Error'),
            message: error?.message || __('Failed to reject'),
            indicator: 'red',
          });
        }
      },
      __('Reject Expense Request'),
      __('Reject')
    );
  });
}

async function maybeRenderPurchaseInvoiceButton(frm) {
  if (frm.doc.linked_purchase_invoice) {
    try {
      const piStatus = await frappe.db.get_value(
        'Purchase Invoice',
        frm.doc.linked_purchase_invoice,
        'docstatus'
      );
      if (piStatus?.message?.docstatus === 1) {
        return;
      }
    } catch (error) {
      // continue
    }
  }

  const [ocrEnabled] = await Promise.all([
    frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr'),
  ]);

  const isPpnApplicable = Boolean(frm.doc.is_ppn_applicable);
  const gateByVerification = Boolean(ocrEnabled && isPpnApplicable && frm.doc.ti_tax_invoice_upload);
  let isVerified = false;

  if (frm.doc.ti_tax_invoice_upload) {
    try {
      const cached = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
      let uploadStatus = cached?.verification_status;
      if (uploadStatus === undefined) {
        const result = await frappe.db.get_value(
          'Tax Invoice OCR Upload',
          frm.doc.ti_tax_invoice_upload,
          'verification_status'
        );
        uploadStatus = result?.verification_status || result?.message?.verification_status;
      }
      isVerified = (uploadStatus === 'Verified');
    } catch (error) {
      isVerified = (frm.doc.ti_verification_status === 'Verified');
    }
  } else {
    isVerified = (frm.doc.ti_verification_status === 'Verified');
  }

  const allowButton = !gateByVerification || isVerified;

  if (!allowButton) {
    frm.dashboard.add_indicator(__('Please verify Tax Invoice before creating Purchase Invoice'), 'orange');
    return;
  }

  frm.add_custom_button(__('Create Purchase Invoice'), async () => {
    const hasItemsWithWHT = frm.doc.items?.some(item => item.is_pph_applicable);

    if (hasItemsWithWHT && frm.doc.supplier) {
      const supplierData = await frappe.db.get_value('Supplier', frm.doc.supplier, 'tax_withholding_category');
      const supplierCategory = supplierData?.message?.tax_withholding_category;
      const erPphType = frm.doc.pph_type;

      if (supplierCategory && erPphType && supplierCategory !== erPphType) {
        frappe.confirm(
          __('<b>WHT Category Conflict Detected</b><br><br>' +
             'Supplier <b>{0}</b> has WHT Category: <b>{1}</b><br>' +
             'Advanced Expense Request has PPh Type: <b>{2}</b><br><br>' +
             '<b>Which category do you want to use?</b><br>' +
             '• Click <b>Yes</b> to use <b>{2}</b> (from Advanced Expense Request)<br>' +
             '• Click <b>No</b> to update to use <b>{1}</b> (from Supplier)',
            [frm.doc.supplier, supplierCategory, erPphType]
          ),
          async () => {
            proceedCreatePI(frm);
          },
          () => {
            frappe.confirm(
              __('Update PPh Type to <b>{0}</b>?', [supplierCategory]),
              async () => {
                try {
                  await frappe.call({
                    method: 'frappe.client.set_value',
                    args: {
                      doctype: 'Advanced Expense Request',
                      name: frm.doc.name,
                      fieldname: 'pph_type',
                      value: supplierCategory
                    }
                  });
                  frm.reload_doc();
                  frappe.show_alert({
                    message: __('PPh Type updated to {0}', [supplierCategory]),
                    indicator: 'green'
                  });
                } catch (error) {
                  frappe.msgprint({
                    title: __('Error'),
                    message: error?.message || __('Failed to update PPh Type'),
                    indicator: 'red'
                  });
                }
              }
            );
          }
        );
        return;
      }
    }

    proceedCreatePI(frm);
  }, __('Actions'));
}

async function proceedCreatePI(frm) {
  frappe.confirm(
    __('Are you sure you want to create a Purchase Invoice from this Advanced Expense Request?'),
    async () => {
      try {
        frappe.show_progress(__('Creating...'), 0, 100);

        const { message } = await frappe.call({
          method: 'imogi_finance.accounting.create_purchase_invoice_from_request',
          args: { expense_request_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Creating Purchase Invoice...'),
        });

        frappe.hide_progress();

        if (message) {
          frappe.show_alert({
            message: __('Purchase Invoice {0} created successfully!', [message]),
            indicator: 'green',
          }, 5);
          frm.reload_doc();
        }
      } catch (error) {
        frappe.hide_progress();
        frappe.msgprint({
          title: __('Error'),
          message: error?.message || __('Failed to create Purchase Invoice'),
          indicator: 'red',
        });
      }
    }
  );
}
