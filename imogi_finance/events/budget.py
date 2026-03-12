def set_budget_display_fields(doc, method=None):
    
    if not getattr(doc, "accounts", None):
        doc.custom_akun = None
        doc.custom_budget_amount = 0
        return

    # ambil akun pertama
    first_row = doc.accounts[0] if doc.accounts else None
    doc.custom_akun = first_row.account if first_row else None

    # hitung total budget
    total_budget = 0
    for row in doc.accounts:
        total_budget += row.budget_amount or 0

    doc.custom_budget_amount = total_budget