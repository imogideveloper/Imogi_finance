import frappe
from frappe.utils import flt

def before_insert(doc, method):
    if not doc.get("items"):
        return
    
    # Ambil sales_order dari item pertama
    sales_order = None
    for item in doc.items:
        if item.get("sales_order"):
            sales_order = item.sales_order
            break
    
    if not sales_order:
        return
    
    # Cek apakah SO ini punya DO Towing yang Done
    do_list = frappe.get_all(
        "Delivery Order Towing",
        filters={
            "sales_order": sales_order,
            "status": "Done",
            "docstatus": 1
        },
        fields=[
            "name",
            "nomor_mesin",
            "nomor_polisi", 
            "tipe_kendaraan",
            "merk_kendaraan",
            "lokasi_pickup",
            "lokasi_tujuan",
            "harga_jasa",
            "sales_order"
        ],
        order_by="name asc"
    )
    
    if not do_list:
        return
    
    # Ambil so_item_code dari child table SO Towing Kendaraan
    so_kendaraan = frappe.get_all(
        "SO Towing Kendaraan",
        filters={"parent": sales_order},
        fields=["delivery_order", "so_item_code", "nomor_mesin"],
        order_by="idx asc"
    )
    
    # Buat mapping: delivery_order -> so_item_code
    do_item_map = {k.delivery_order: k.so_item_code for k in so_kendaraan}
    
    # Default fallback item code
    default_item = "JASA-TOWING-001"
    income_account = frappe.db.get_value(
                        "Account",
                        {
                            "account_name": "Sales",
                            "company": doc.company,
                            "root_type": "Income"
                        },
                        "name"
                    ) or frappe.get_cached_value("Company", doc.company, "default_income_account")
    cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
    
    # Clear existing items
    doc.set("items", [])
    
    for do in do_list:
        nomor_mesin = do.get("nomor_mesin") or do.get("nomor_polisi") or "N/A"
        tipe = do.get("tipe_kendaraan") or ""
        merk = do.get("merk_kendaraan") or ""
        kendaraan = f"{merk} {tipe}".strip() or "Kendaraan"
        rute = f"{do.get('lokasi_pickup') or '-'} → {do.get('lokasi_tujuan') or '-'}"
        
        item_code = do_item_map.get(do.name) or default_item
        
        description = f"Jasa Towing - {nomor_mesin}\n{kendaraan} | {rute}\n{do.name}"
        
        doc.append("items", {
            "item_code": item_code,
            "item_name": f"Jasa Towing - {nomor_mesin}",
            "description": description,
            "qty": 1,
            "rate": flt(do.get("harga_jasa") or 0),
            "uom": "Nos",
            "income_account": income_account,
            "cost_center": cost_center,
            "conversion_factor": 1,
            "sales_order": sales_order,
        })
    
    frappe.msgprint(
        f"✅ {len(do_list)} item towing berhasil di-generate dari DO Towing",
        indicator="green"
    )