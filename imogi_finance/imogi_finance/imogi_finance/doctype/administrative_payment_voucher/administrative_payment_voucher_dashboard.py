def get_data():
    return {
        "heatmap": False,
        "fieldname": "imogi_administrative_payment_voucher",
        "transactions": [
            {"label": "Payment", "items": ["Payment Entry"]},
        ],
        "non_standard_fieldnames": {
            "Payment Entry": "imogi_administrative_payment_voucher",
        },
    }
