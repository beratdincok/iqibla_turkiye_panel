
from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
from common.analytics import *

APP_DIR = Path(__file__).resolve().parent
PLATFORM = "Trendyol"
TITLE = "🟠 Trendyol Paneli"

st.title(TITLE)
st.caption("Trendyol siparişleri + maliyet + reklam + manuel günlük giriş.")

manual_input_ui(st, BASE_DIR, PLATFORM)

@st.cache_data(show_spinner=False)
def load_platform_data():
    rows = []
    ad_rows = []
    debug = []
    costs = load_cost_table(APP_DIR)

    for p in sorted(APP_DIR.glob("*")):
        if p.suffix.lower() not in [".csv", ".xlsx", ".xls"]:
            continue
        n = normalize_text(p.name)

        if "maliyet" in n or "cost" in n:
            continue

        df, enc, sep = read_table_flexible(p)
        if df.empty:
            debug.append({"file": p.name, "type": "unknown", "status": "ERROR", "rows": 0, "notes": "okunamadı"})
            continue

        if any(x in n for x in ["reklam", "ads", "campaign"]):
            spend_col = find_col(df, ["Harcanan Tutar", "Amount spent", "Spend", "Harcama", "Tutar"])
            revenue_col = find_col(df, ["Reklam Geliri", "Total Ad Revenue", "Revenue", "Dönüşüm değeri", "Donusum degeri", "Satış Tutarı", "Satis Tutari"])
            purchase_col = find_col(df, ["Alışverişler", "Alisverisler", "Purchases", "Sipariş", "Orders"])
            if spend_col:
                tmp = pd.DataFrame({
                    "date": pd.NaT,
                    "ad_spend": df[spend_col].apply(to_float),
                    "ad_revenue": df[revenue_col].apply(to_float) if revenue_col else 0.0,
                    "ad_purchases": df[purchase_col].apply(to_float) if purchase_col else 0.0,
                    "source_file": p.name,
                })
                ad_rows.append(tmp)
                debug.append({"file": p.name, "type": "ad_report", "status": "OK", "rows": len(tmp), "notes": f"spend={spend_col}"})
                continue

        date_col = find_col(df, ["Sipariş Tarihi", "Siparis Tarihi", "Tarih", "Order Date", "Date"])
        order_col = find_col(df, ["Sipariş Numarası", "Siparis Numarasi", "Sipariş No", "Siparis No", "Order Number", "Order", "Paket No"])
        product_col = find_col(df, ["Ürün Adı", "Urun Adi", "Ürün Ad", "Urun Ad", "Product Name", "Product", "SKU"])
        sku_col = find_col(df, ["Barkod", "Barcode", "SKU", "Stok Kodu", "Merchant SKU"])
        qty_col = find_col(df, ["Adet", "Miktar", "Quantity", "Ürün Adedi", "Urun Adedi", "Satış Miktarı", "Satis Miktari"])
        revenue_col = find_col(df, [
            "Faturalanacak Tutar", "Net Satış Tutarı", "Net Satis Tutari", "Satış Tutarı", "Satis Tutari",
            "Ürün Tutarı", "Urun Tutari", "Sipariş Tutarı", "Siparis Tutari", "Toplam Satış Tutarı",
            "Toplam Satis Tutari", "Mağazanın Brüt Cirosu", "Magazanin Brut Cirosu", "Toplam Brüt Ciro",
            "Toplam Brut Ciro", "Ciro", "Tutar", "Amount", "Revenue"
        ])
        status_col = find_col(df, ["Sipariş Statüsü", "Siparis Statusu", "Durum", "Status"])

        if not revenue_col:
            debug.append({"file": p.name, "type": "not_sales", "status": "SKIPPED", "rows": len(df), "notes": "ciro/tutar kolonu yok"})
            continue

        tmp = pd.DataFrame({
            "platform": PLATFORM,
            "order_name": df[order_col].astype(str) if order_col else p.stem,
            "order_date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True) if date_col else pd.NaT,
            "product_name": df[product_col].astype(str) if product_col else PLATFORM + " Product",
            "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
            "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
            "line_revenue": df[revenue_col].apply(to_float),
            "status": df[status_col].astype(str) if status_col else "",
            "source_file": p.name,
        })
        tmp["is_cancelled_or_returned"] = tmp["status"].str.contains("iptal|iade|cancel|return|red|reddedildi", case=False, na=False)
        tmp.loc[tmp["is_cancelled_or_returned"], ["qty", "line_revenue"]] = 0.0
        tmp = tmp[tmp["line_revenue"].fillna(0) >= 0].copy()

        rows.append(tmp)
        debug.append({"file": p.name, "type": "sales", "status": "OK", "rows": len(tmp), "notes": f"revenue={revenue_col}, enc={enc}, sep={sep}"})

    lines = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["platform", "order_name", "order_date", "product_name", "sku_key", "qty", "line_revenue", "status", "source_file"])
    ads = pd.concat(ad_rows, ignore_index=True) if ad_rows else pd.DataFrame(columns=["date", "ad_spend", "ad_revenue", "ad_purchases", "source_file"])
    return lines, ads, costs, pd.DataFrame(debug)

lines, ads, costs, debug = load_platform_data()
manual = load_manual_entries(BASE_DIR, PLATFORM)

if not lines.empty:
    lines = lines.merge(costs, on="sku_key", how="left")
    for col in ["unit_cost", "unit_shipping", "commission_rate"]:
        lines[col] = lines[col].fillna(0.0)
    lines["matched_cost"] = lines["unit_cost"].gt(0)
    lines["gross_profit"] = lines["line_revenue"] - ((lines["unit_cost"] + lines["unit_shipping"]) * lines["qty"]) - (lines["line_revenue"] * lines["commission_rate"])
else:
    lines["matched_cost"] = []
    lines["gross_profit"] = []

orders = lines.groupby("order_name", as_index=False).agg(
    order_date=("order_date", "first"),
    net_sales=("line_revenue", "sum"),
    qty=("qty", "sum"),
    source_file=("source_file", "first"),
) if not lines.empty else pd.DataFrame(columns=["order_name", "order_date", "net_sales", "qty", "source_file"])
if not orders.empty:
    orders["order_count"] = orders["net_sales"].gt(0).astype(int)

manual_revenue = manual["total_revenue"].sum() if not manual.empty else 0.0
manual_orders = manual["order_count"].sum() if not manual.empty else 0.0
manual_units = manual["units_sold"].sum() if not manual.empty else 0.0
manual_ad_spend = manual["ad_spend"].sum() if not manual.empty else 0.0

total_revenue = (orders["net_sales"].sum() if not orders.empty else 0.0) + manual_revenue
order_count = (orders["order_count"].sum() if not orders.empty else 0.0) + manual_orders
units_sold = (lines["qty"].sum() if not lines.empty else 0.0) + manual_units
aov = safe_divide(total_revenue, order_count)
gross_profit_before_ads = (lines["gross_profit"].sum() if not lines.empty else 0.0) + manual_revenue
total_ad_spend = (ads["ad_spend"].sum() if not ads.empty else 0.0) + manual_ad_spend
total_ad_revenue = (ads["ad_revenue"].sum() if not ads.empty else 0.0)
ad_purchases = (ads["ad_purchases"].sum() if not ads.empty else 0.0)
roas = safe_divide(total_ad_revenue, total_ad_spend)
net_profit_after_ads = gross_profit_before_ads - total_ad_spend
mer = safe_divide(total_revenue, total_ad_spend)
cost_match_rate = float(lines["matched_cost"].mean()) if not lines.empty and "matched_cost" in lines else 0.0

metrics = {
    "total_revenue": total_revenue,
    "order_count": order_count,
    "units_sold": units_sold,
    "aov": aov,
    "gross_profit_before_ads": gross_profit_before_ads,
    "total_ad_spend": total_ad_spend,
    "total_ad_revenue": total_ad_revenue,
    "ad_purchases": ad_purchases,
    "roas": roas,
    "net_profit_after_ads": net_profit_after_ads,
    "mer": mer,
    "cost_match_rate": cost_match_rate,
}
save_panel_summary(APP_DIR, metrics)

st.subheader("Main Report")
kpi_block(st, metrics)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Satış", "📦 Ürün & Kâr", "📣 Reklam", "✍️ Manuel Girişler", "🧪 Data Quality"])

with tab1:
    by_file = orders.groupby("source_file", as_index=False).agg(order_count=("order_count", "sum"), total_revenue=("net_sales", "sum")) if not orders.empty else pd.DataFrame()
    st.dataframe(by_file, use_container_width=True, hide_index=True)
    st.dataframe(orders.sort_values("net_sales", ascending=False), use_container_width=True, hide_index=True)

with tab2:
    if lines.empty:
        st.info("Ürün satırı yok.")
    else:
        product = lines.groupby(["product_name", "sku_key"], as_index=False).agg(units_sold=("qty", "sum"), revenue=("line_revenue", "sum"), gross_profit=("gross_profit", "sum"), matched_cost=("matched_cost", "max"))
        st.dataframe(product.sort_values("revenue", ascending=False), use_container_width=True, hide_index=True)

with tab3:
    st.dataframe(ads, use_container_width=True, hide_index=True)

with tab4:
    st.dataframe(manual, use_container_width=True, hide_index=True)

with tab5:
    st.dataframe(debug, use_container_width=True, hide_index=True)
    st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)
