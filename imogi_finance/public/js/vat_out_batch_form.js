frappe.ui.form.on('VAT OUT Batch', {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__('📥 Upload Hasil Coretax (CSV + ZIP)'), () => {
            const dialog = new frappe.ui.Dialog({
                title: __('Upload Hasil Faktur Pajak dari Coretax'),
                fields: [
                    {
                        fieldname: 'info',
                        fieldtype: 'HTML',
                        options: '<div class="alert alert-info"><b>Petunjuk:</b><br>1. Download CSV dan ZIP dari Coretax<br>2. Upload CSV (mapping FP ke Sales Invoice)<br>3. Upload ZIP (semua PDF faktur pajak)<br>4. Klik Proses</div>'
                    },
                    {
                        fieldname: 'csv_file',
                        fieldtype: 'Attach',
                        label: 'File CSV atau Excel dari Coretax',
                        reqd: 1,
                        description: 'Format: .csv atau .xlsx — kolom: fp_number, sales_invoice, dpp, ppn, fp_date, customer_npwp'
                    },
                    {
                        fieldname: 'zip_file',
                        fieldtype: 'Attach',
                        label: 'File ZIP (berisi semua PDF Faktur Pajak)',
                        reqd: 1,
                        description: 'Nama file PDF di dalam ZIP harus sama dengan nomor FP (16 digit)'
                    },
                    {
                        fieldname: 'section_options',
                        fieldtype: 'Section Break',
                        label: 'Opsi'
                    },
                    {
                        fieldname: 'overwrite_existing',
                        fieldtype: 'Check',
                        label: 'Timpa data yang sudah ada',
                        default: 0
                    },
                    {
                        fieldname: 'require_all_csv_have_pdf',
                        fieldtype: 'Check',
                        label: 'Wajib semua FP di CSV ada PDF-nya',
                        default: 0
                    },
                ],
                primary_action_label: '🚀 Proses Upload',
                primary_action: async (values) => {
                    dialog.hide();
                    try {
                        const r = await frappe.call({
                            method: 'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api.bulk_create_from_csv',
                            args: {
                                batch_name: frm.doc.name,
                                zip_url: values.zip_file,
                                csv_url: values.csv_file,
                                require_all_batch_invoices: 0,
                                require_all_csv_have_pdf: values.require_all_csv_have_pdf ? 1 : 0,
                                overwrite_existing: values.overwrite_existing ? 1 : 0,
                            },
                            freeze: true,
                            freeze_message: 'Memproses faktur pajak...',
                        });

                        const result = r.message;

                        if (result.queued) {
                            frappe.msgprint({
                                title: 'Diproses di Background',
                                message: 'Data terlalu banyak, diproses di background. Job ID: ' + result.job_id,
                                indicator: 'blue'
                            });
                            return;
                        }

                        let msg = '<b>Hasil Upload:</b><br>'
                            + '✅ Berhasil dibuat: <b>' + result.created + '</b><br>'
                            + '🔄 Diupdate: <b>' + result.updated + '</b><br>'
                            + '⏭️ Dilewati: <b>' + result.skipped + '</b><br>';

                        if (result.row_errors && result.row_errors.length > 0) {
                            msg += '<br><b>⚠️ Error (' + result.row_errors.length + ' baris):</b><br>';
                            result.row_errors.slice(0, 5).forEach(e => {
                                msg += '• Baris ' + e.row + ' (' + e.fp_number + '): ' + e.reason + '<br>';
                            });
                        }

                        if (result.csv_missing_pdf && result.csv_missing_pdf.length > 0) {
                            msg += '<br><b>⚠️ FP tanpa PDF (' + result.csv_missing_pdf.length + '):</b><br>';
                            result.csv_missing_pdf.slice(0, 3).forEach(fp => { msg += '• ' + fp + '<br>'; });
                        }

                        frappe.msgprint({
                            title: result.status === 'success' ? 'Upload Berhasil' : 'Upload Selesai dengan Peringatan',
                            message: msg,
                            indicator: result.status === 'success' ? 'green' : 'orange'
                        });

                        frm.reload_doc();

                    } catch (err) {
                        frappe.msgprint({
                            title: 'Error',
                            message: err.message || 'Terjadi kesalahan saat memproses upload',
                            indicator: 'red'
                        });
                    }
                }
            });
            dialog.show();
        }, __('Coretax'));
    }
});
