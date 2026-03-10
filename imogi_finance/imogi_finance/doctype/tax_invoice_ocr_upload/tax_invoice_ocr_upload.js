const TAX_INVOICE_OCR_GROUP = __('Tax Invoice OCR');

async function refreshUploadStatus(frm) {
	if (frm.is_new()) return;

	const callMonitor = () =>
		frappe.call({
			method: 'imogi_finance.api.tax_invoice.monitor_tax_invoice_ocr',
			args: { docname: frm.doc.name, doctype: 'Tax Invoice OCR Upload' },
		});

	const isTimestampMismatch = (error) => {
		const excType = error?.exc_type || error?.exc?.exc_type;
		const exceptionText = error?.exception || error?.exc;
		return (
			excType === 'TimestampMismatchError' ||
			(typeof exceptionText === 'string' && exceptionText.includes('TimestampMismatchError'))
		);
	};

	try {
		await callMonitor();
	} catch (error) {
		if (!isTimestampMismatch(error)) throw error;
		await frm.reload_doc();
		await callMonitor();
	}
	await frm.reload_doc();
}

frappe.ui.form.on('Tax Invoice OCR Upload', {
	async refresh(frm) {
		let providerReady = true;
		let providerError = null;
		let enabled = false;

		try {
			const { message } = await frappe.call({
				method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
				args: { target_doctype: 'Tax Invoice OCR Upload', target_name: frm.doc.name },
			});
			enabled = Boolean(message?.enable_tax_invoice_ocr);
			providerReady = Boolean(message?.provider_ready ?? true);
			providerError = message?.provider_error || null;
		} catch (error) {
			enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
		}

		// Only skip if OCR is disabled (removed frm.is_new() check to support autoname behavior)
		if (!enabled) {
			return;
		}

		if (providerReady === false) {
			const message = providerError
				? __('OCR cannot run: {0}', [providerError])
				: __('OCR provider is not configured.');
			frm.dashboard.set_headline(`<span class="indicator red">${message}</span>`);
		}

		// 🔥 Show OCR failure error prominently
		if (frm.doc.ocr_status === 'Failed' && frm.doc.ocr_error_log) {
			frm.dashboard.set_headline_alert(
				__('❌ OCR Failed: {0}', [frm.doc.ocr_error_log]),
				'red'
			);
		}

		// Only show buttons for saved documents (after autoname creates permanent name)
		if (!frm.is_new()) {
			frm.add_custom_button(__('Refresh OCR Status'), async () => {
				await refreshUploadStatus(frm);
			}, TAX_INVOICE_OCR_GROUP);
		}

		// Run OCR button: Show when OCR not yet run, failed, or pending (works even after autoname save)
		const ocrNotDone = !frm.doc.ocr_status || 
			frm.doc.ocr_status === 'Not Started' || 
			frm.doc.ocr_status === 'Failed' || 
			frm.doc.ocr_status === 'Pending';
		
		if (!frm.is_new() && frm.doc.tax_invoice_pdf && providerReady !== false) {
			if (ocrNotDone) {
				// Show "Run OCR" button when OCR not yet completed
				frm.add_custom_button(__('Run OCR'), async () => {
					await frappe.call({
						method: 'imogi_finance.api.tax_invoice.run_ocr_for_upload',
						args: { upload_name: frm.doc.name },
						freeze: true,
						freeze_message: __('Queueing OCR...'),
					});
					frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
					await refreshUploadStatus(frm);
				}, TAX_INVOICE_OCR_GROUP);
			} else {
				// Show "Re-Run OCR" button when OCR already done (for re-processing)
				frm.add_custom_button(__('🔄 Re-Run OCR'), async () => {
					await frappe.call({
						method: 'imogi_finance.api.tax_invoice.run_ocr_for_upload',
						args: { upload_name: frm.doc.name },
						freeze: true,
						freeze_message: __('Queueing OCR...'),
					});
					frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
					await refreshUploadStatus(frm);
				}, TAX_INVOICE_OCR_GROUP);
			}
		}

		// Add Manual Approval button if verification needed
		if (frm.doc.verification_status === 'Needs Review' && frm.doc.fp_no) {
			frm.add_custom_button(__('✅ Approve Manually'), async () => {
				await frappe.call({
					method: 'imogi_finance.api.tax_invoice.verify_tax_invoice_upload',
					args: { upload_name: frm.doc.name, force: true },
					freeze: true,
					freeze_message: __('Verifying tax invoice...'),
				});
				frappe.show_alert({ message: __('Tax invoice verified successfully.'), indicator: 'green' });
				await frm.reload_doc();
			}, TAX_INVOICE_OCR_GROUP);
		}
	},

	// 🆕 Real-time validation when PPN Type is changed
	ppn_type(frm) {
		if (!frm.doc.ppn_type || !frm.doc.dpp || !frm.doc.ppn) return;

		const dpp = parseFloat(frm.doc.dpp || 0);
		const ppn = parseFloat(frm.doc.ppn || 0);
		const ppn_type = frm.doc.ppn_type;

		let warnings = [];

		// Validate based on selected PPN Type
		if (ppn_type.includes('Standard 11%')) {
			const expected_rate = 0.11;
			if (ppn === 0 && dpp > 0) {
				warnings.push(__('⚠️ PPN Type is "11%" but PPN amount is 0. Should this be Zero Rated?'));
			} else if (dpp > 0) {
				const actual_rate = ppn / dpp;
				if (Math.abs(actual_rate - expected_rate) > 0.02) {
					warnings.push(
						__('⚠️ PPN Type is "Standard 11%" but actual rate is {0}%. Please verify.', 
						   [(actual_rate * 100).toFixed(2)])
					);
				}
			}
		} else if (ppn_type.includes('Standard 12%')) {
			const expected_rate = 0.12;
			if (ppn === 0 && dpp > 0) {
				warnings.push(__('⚠️ PPN Type is "12%" but PPN amount is 0. Should this be Zero Rated?'));
			} else if (dpp > 0) {
				const actual_rate = ppn / dpp;
				if (Math.abs(actual_rate - expected_rate) > 0.02) {
					warnings.push(
						__('⚠️ PPN Type is "Standard 12%" but actual rate is {0}%. Please verify.',
						   [(actual_rate * 100).toFixed(2)])
					);
				}
			}
		} else if (ppn_type.includes('Zero Rated') || ppn_type.includes('Ekspor')) {
			if (ppn > 0) {
				warnings.push(
					__('⚠️ PPN Type is "Zero Rated (Ekspor)" but PPN amount is Rp {0}. Zero Rated should have PPN = 0.',
					   [ppn.toLocaleString('id-ID', {minimumFractionDigits: 2})])
				);
			}
		} else if (ppn_type.includes('Tidak Dipungut') || ppn_type.includes('Dibebaskan')) {
			if (ppn > 0) {
				warnings.push(
					__('⚠️ PPN Type is "{0}" but PPN amount is Rp {1}. This type should have PPN = 0.',
					   [ppn_type, ppn.toLocaleString('id-ID', {minimumFractionDigits: 2})])
				);
			}
		} else if (ppn_type.includes('Bukan Objek PPN')) {
			if (ppn > 0) {
				warnings.push(
					__('⚠️ PPN Type is "Bukan Objek PPN" but PPN amount is Rp {0}. Non-PPN should have PPN = 0.',
					   [ppn.toLocaleString('id-ID', {minimumFractionDigits: 2})])
				);
			}
		} else if (ppn_type.includes('Digital 1.1%') || ppn_type.includes('PMSE')) {
			const expected_rate = 0.011;
			if (dpp > 0) {
				const actual_rate = ppn / dpp;
				if (Math.abs(actual_rate - expected_rate) > 0.005) {
					warnings.push(
						__('⚠️ PPN Type is "Digital 1.1%" but actual rate is {0}%. Please verify.',
						   [(actual_rate * 100).toFixed(2)])
					);
				}
			}
		} else if (ppn_type.includes('Custom') || ppn_type.includes('Other')) {
			// ✅ Custom tariff - show actual rate for reference
			if (dpp > 0 && ppn > 0) {
				const actual_rate = ppn / dpp;
				frappe.show_alert({
					message: __('Custom PPN Type: Actual rate is {0}%', [(actual_rate * 100).toFixed(2)]),
					indicator: 'blue'
				}, 5);
			}
		}

		// Show warnings to user
		if (warnings.length > 0) {
			frappe.msgprint({
				title: __('PPN Type Verification'),
				indicator: 'orange',
				message: warnings.join('<br><br>')
			});
		} else if (ppn > 0 && dpp > 0) {
			frappe.show_alert({
				message: __('✅ PPN Type matches the invoice amounts'),
				indicator: 'green'
			}, 3);
		}
	}
});
