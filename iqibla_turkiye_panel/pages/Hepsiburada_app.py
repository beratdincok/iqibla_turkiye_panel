import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import glob
import os
import re
import unicodedata

st.set_page_config(page_title="SMARTEK360 | Hepsiburada Dashboard", layout="wide")
st.title("🟠 SMARTEK360: Hepsiburada Dashboard")
st.caption(
    "English-only dashboard for Hepsiburada sales, store traffic, cost table, manual inventory, and optional marketing files. "
    "Defaults to All Time and supports an optional custom date range when dated datasets exist."
)

DATA_DIR = Path(__file__).resolve().parent

MANUAL_INVENTORY = {
    "j01t green": 102,
    "j01t camel": 102,
    "j01 blue": 60,
    "j01 grey": 47,
    "j03 pro titanium": 541,
    "j01t black": 266,
    "salat counter": 35,
    "premium black gold 22mm": 9,
    "premium rose gold 20mm": 7,
    "premium black gray 22mm": 7,
    "j01 pink": 120,
    "j01 green": 120,
    "j01 black": 160,
}


def to_float(val) -> float:
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    s = (
        s.replace("TL", "")
        .replace("₺", "")
        .replace("%", "")
        .replace('"', "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    if s in {"-", "nan", "None", "null", "Henüzfaturakesilmemiştir."}:
        return 0.0

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 1 and all(part.isdigit() for part in parts):
            if all(len(part) == 3 for part in parts[1:]):
                s = "".join(parts)

    try:
        return float(s)
    except Exception:
        cleaned = re.sub(r"[^0-9.\-]", "", s)
        try:
            return float(cleaned)
        except Exception:
            return 0.0


def normalize_text(value: str) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower().strip()
    replacements = {
        "?": "",
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
        "â": "a",
        "î": "i",
        "û": "u",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_col(df: pd.DataFrame, candidates: list[str]):
    normalized = {normalize_text(col): col for col in df.columns}
    for candidate in candidates:
        target = normalize_text(candidate)
        for norm_col, raw_col in normalized.items():
            if target == norm_col or target in norm_col:
                return raw_col
    return None


def read_csv_flexible(path: Path) -> pd.DataFrame:
    for enc in ["utf-8", "utf-8-sig", "iso-8859-9", "cp1254"]:
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
    return pd.DataFrame()


def classify_inventory_key(title: str, variant: str) -> str:
    title_n = normalize_text(title)
    variant_n = normalize_text(variant)
    text = f"{title_n} {variant_n}"

    if "salat counter" in text or "sc01" in text or "rekat sayaci" in text:
        return "salat counter"
    if "j01t" in text:
        if "camel" in text or "kum beji" in text or "bej" in text:
            return "j01t camel"
        if "yesil" in text or "green" in text:
            return "j01t green"
        if "siyah" in text or "black" in text:
            return "j01t black"
    if "j03 pro" in text:
        if "titanyum" in text or "titanium" in text:
            return "j03 pro titanium"
        if "siyah" in text or "black" in text:
            return "j03 pro black"
    if "j01" in text:
        if "pembe" in text or "pink" in text:
            return "j01 pink"
        if "gri" in text or "grey" in text or "gray" in text:
            return "j01 grey"
        if "yesil" in text or "green" in text:
            return "j01 green"
        if "siyah" in text or "black" in text:
            return "j01 black"
        if "mavi" in text or "blue" in text:
            return "j01 blue"
    if "premium" in text:
        if "rose gold" in text and "20mm" in text:
            return "premium rose gold 20mm"
        if ("black gold" in text or ("black" in text and "gold" in text)) and "22mm" in text:
            return "premium black gold 22mm"
        if ("black gray" in text or "black grey" in text) and "22mm" in text:
            return "premium black gray 22mm"
    return ""


@st.cache_data(show_spinner=False)
def load_sales_exports() -> tuple[pd.DataFrame, dict]:
    files = sorted(DATA_DIR.glob("hepsiburada*.csv"))
    sales_candidates = []
    snapshots = []

    for path in files:
        df = read_csv_flexible(path)
        if df.empty:
            continue
        sku_col = find_col(df, ["SKU"])
        rev_col = find_col(df, ["Toplam Satis Tutari", "Total Sales Amount"])
        qty_col = find_col(df, ["Toplam Satis Adedi", "Total Sales Qty", "Toplam Satis Miktari"])
        title_col = find_col(df, ["Urun Adi", "Product Name"])
        if sku_col and rev_col and qty_col and title_col:
            work = df.copy()
            work["sku"] = work[sku_col].astype(str).str.strip()
            work["product_name"] = work[title_col].fillna("")
            variant_col = find_col(df, ["Varyant", "Variant"])
            seller_sku_col = find_col(df, ["SaticiSKU", "Seller SKU"])
            avg_price_col = find_col(df, ["Ortalama Satis Fiyat", "Average Sales Price"])
            commission_pct_col = find_col(df, ["Komisyon(%)", "Komisyon", "Commission(%)"])
            commission_amt_col = find_col(df, ["Komisyon Tutar", "Commission Amount"])

            work["variant"] = work[variant_col].fillna("") if variant_col else ""
            work["seller_sku"] = work[seller_sku_col].fillna("") if seller_sku_col else ""
            work["avg_sales_price"] = work[avg_price_col].apply(to_float) if avg_price_col else 0.0
            work["qty"] = work[qty_col].apply(to_float)
            work["revenue"] = work[rev_col].apply(to_float)
            work["commission_pct"] = work[commission_pct_col].apply(to_float) / (100.0 if work[commission_pct_col].astype(str).str.contains('%').any() or work[commission_pct_col].apply(to_float).max() > 1.0 else 1.0) if commission_pct_col else 0.0
            work["commission_amount_export"] = work[commission_amt_col].apply(to_float) if commission_amt_col else 0.0
            work["source_file"] = path.name
            snapshots.append({
                "file": path.name,
                "rows": len(work),
                "revenue": float(work["revenue"].sum()),
                "qty": float(work["qty"].sum()),
            })
            sales_candidates.append(work[["sku", "seller_sku", "product_name", "variant", "avg_sales_price", "qty", "revenue", "commission_pct", "commission_amount_export", "source_file"]])

    if not sales_candidates:
        return pd.DataFrame(), {"snapshots": [], "selected_snapshot": None, "method": "none"}

    # These exports are aggregate snapshots without reliable dates. Use the snapshot with the highest total revenue.
    snapshot_totals = [(df["revenue"].sum(), df) for df in sales_candidates]
    selected_df = max(snapshot_totals, key=lambda x: x[0])[1].copy()
    selected_file = selected_df["source_file"].iloc[0]

    meta = {
        "snapshots": snapshots,
        "selected_snapshot": selected_file,
        "method": "highest_revenue_snapshot",
    }
    return selected_df, meta


@st.cache_data(show_spinner=False)
def load_costs() -> pd.DataFrame:
    path = DATA_DIR / "Hepsiburada Maliyet Tablosu(Sayfa1).csv"
    if not path.exists():
        return pd.DataFrame()
    df = read_csv_flexible(path)
    if df.empty:
        return pd.DataFrame()

    sku_col = find_col(df, ["SKU"])
    cost_col = find_col(df, ["Maliyet", "Cost"])
    comm_col = find_col(df, ["Komisyon oran", "Commission Rate"])
    ship_col = find_col(df, ["Kargo", "Shipping"])
    vat_col = find_col(df, ["KDV", "VAT"])

    if not sku_col:
        return pd.DataFrame()

    out = pd.DataFrame()
    out["sku"] = df[sku_col].astype(str).str.strip()
    out["cost"] = df[cost_col].apply(to_float) if cost_col else 0.0
    out["commission_rate_cost_table"] = df[comm_col].apply(to_float) if comm_col else 0.0
    out["shipping_cost"] = df[ship_col].apply(to_float) if ship_col else 0.0
    out["vat_rate"] = df[vat_col].apply(to_float) if vat_col else 0.0
    return out


@st.cache_data(show_spinner=False)
def load_traffic() -> pd.DataFrame:
    candidates = list(DATA_DIR.glob("hepsiburada03*.csv")) + list(DATA_DIR.glob("*hepsiburada*trafik*.csv"))
    for path in candidates:
        df = read_csv_flexible(path)
        if df.empty:
            continue
        sku_col = find_col(df, ["SKU"])
        views_col = find_col(df, ["Toplam Goruntulenme Sayisi", "Total Views"])
        visitors_col = find_col(df, ["Goruntuleyen Musteri Sayisi", "Unique Visitors"])
        carts_col = find_col(df, ["Sepete Eklenme Sayisi", "Added To Cart"])
        sales_qty_col = find_col(df, ["Satis Miktari", "Sales Qty"])
        conv_col = find_col(df, ["Satisa Donme Orani", "Conversion Rate"])
        wish_col = find_col(df, ["Listelere Eklenme Sayisi", "Wishlist"])
        if sku_col and views_col:
            out = pd.DataFrame()
            out["sku"] = df[sku_col].astype(str).str.strip()
            out["views"] = df[views_col].apply(to_float)
            out["visitors"] = df[visitors_col].apply(to_float) if visitors_col else 0.0
            out["added_to_lists"] = df[wish_col].apply(to_float) if wish_col else 0.0
            out["added_to_cart"] = df[carts_col].apply(to_float) if carts_col else 0.0
            out["traffic_sales_qty"] = df[sales_qty_col].apply(to_float) if sales_qty_col else 0.0
            out["conversion_rate"] = df[conv_col].apply(to_float) / 100.0 if conv_col else 0.0
            return out
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_marketing() -> pd.DataFrame:
    rows = []
    patterns = ["*meta*.csv", "*facebook*.csv", "*fb_ads*.csv", "*hb_ads*.csv", "*hepsiburada*reklam*.csv"]
    for pattern in patterns:
        for path in DATA_DIR.glob(pattern):
            df = read_csv_flexible(path)
            if df.empty:
                continue
            date_col = find_col(df, ["date", "tarih", "day"])
            spend_col = find_col(df, ["spend", "harcama", "cost", "budget", "harcanan butce"])
            revenue_col = find_col(df, ["purchase conversion value", "revenue", "ciro", "sales", "satisa donusen deger"])
            source = "Meta Ads" if any(k in path.name.lower() for k in ["meta", "facebook", "fb_ads"]) else "Hepsiburada Ads"
            if date_col and spend_col:
                tmp = pd.DataFrame()
                tmp["date"] = pd.to_datetime(df[date_col], errors="coerce")
                tmp["spend"] = df[spend_col].apply(to_float)
                tmp["attributed_revenue"] = df[revenue_col].apply(to_float) if revenue_col else 0.0
                tmp["source"] = source
                rows.append(tmp.dropna(subset=["date"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "spend", "attributed_revenue", "source"])


@st.cache_data(show_spinner=False)
def build_model() -> dict:
    sales, sales_meta = load_sales_exports()
    costs = load_costs()
    traffic = load_traffic()
    marketing = load_marketing()

    if sales.empty:
        return {
            "sales": pd.DataFrame(),
            "traffic": traffic,
            "marketing": marketing,
            "sales_meta": sales_meta,
            "warnings": ["No Hepsiburada sales export was found."],
        }

    model = sales.merge(costs, on="sku", how="left") if not costs.empty else sales.copy()
    for col in ["cost", "commission_rate_cost_table", "shipping_cost", "vat_rate"]:
        if col not in model.columns:
            model[col] = 0.0

    model["inventory_key"] = model.apply(lambda r: classify_inventory_key(r.get("product_name", ""), r.get("variant", "")), axis=1)
    model["stock_units"] = model["inventory_key"].map(MANUAL_INVENTORY)

    model["commission_pct_effective"] = model["commission_pct"]
    need_fill = model["commission_pct_effective"].fillna(0).eq(0) & model["commission_rate_cost_table"].fillna(0).gt(0)
    model.loc[need_fill, "commission_pct_effective"] = model.loc[need_fill, "commission_rate_cost_table"]

    model["commission_amount"] = model["commission_amount_export"]
    no_comm_amt = model["commission_amount"].fillna(0).eq(0)
    model.loc[no_comm_amt, "commission_amount"] = model.loc[no_comm_amt, "revenue"] * model.loc[no_comm_amt, "commission_pct_effective"]

    model["cogs_total"] = model["qty"] * model["cost"]
    model["shipping_total"] = model["qty"] * model["shipping_cost"]
    model["gross_profit_before_ads"] = model["revenue"] - model["commission_amount"] - model["cogs_total"] - model["shipping_total"]

    traffic_cols = ["sku", "views", "visitors", "added_to_lists", "added_to_cart", "traffic_sales_qty", "conversion_rate"]
    if not traffic.empty:
        model = model.merge(traffic[traffic_cols], on="sku", how="left")
    else:
        for col in traffic_cols[1:]:
            model[col] = 0.0

    warnings = []
    snapshot_mode = True
    sales_date_supported = False
    marketing_date_supported = not marketing.empty
    if len(sales_meta.get("snapshots", [])) > 1:
        warnings.append(
            f"Multiple aggregate sales snapshots found. Using '{sales_meta.get('selected_snapshot')}' because it has the highest revenue. "
            "Other snapshots were not added to avoid double counting."
        )
    warnings.append(
        "The current Hepsiburada sales files are aggregate snapshots without a reliable sales date column. Sales-side custom date filtering, daily trend, and monthly trend will become available after you upload an order-level export with a date field."
    )
    if marketing.empty:
        warnings.append("No dated marketing file was found yet. The Marketing tab is ready and will populate after you upload Meta Ads or Hepsiburada Ads exports.")

    model["stock_status"] = pd.cut(
        model["stock_units"],
        bins=[-1, 0, 10, 30, 1e9],
        labels=["Missing", "Low", "Medium", "Healthy"],
    )

    return {
        "sales": model,
        "traffic": traffic,
        "marketing": marketing,
        "sales_meta": sales_meta,
        "warnings": warnings,
        "snapshot_mode": snapshot_mode,
        "sales_date_supported": sales_date_supported,
        "marketing_date_supported": marketing_date_supported,
    }


model = build_model()
sales = model["sales"]
marketing = model["marketing"]

with st.sidebar:
    st.header("Filters")
    date_filter_available = bool(model.get("sales_date_supported", False) or model.get("marketing_date_supported", False))
    toggle_label = "Use custom date range" if date_filter_available else "Use custom date range (available after uploading dated sales or ads files)"
    use_custom_range = st.toggle(toggle_label, value=False, disabled=not date_filter_available)
    today = pd.Timestamp.today().normalize().date()
    default_range = (today.replace(day=1), today)
    selected_range = st.date_input("Date range", value=default_range, disabled=(not use_custom_range) or (not date_filter_available))
    low_stock_threshold = st.number_input("Low stock threshold", min_value=0, value=20, step=1)

    st.markdown("---")
    st.subheader("Manual inventory seed")
    st.caption("Edit the MANUAL_INVENTORY dictionary in the code when stock changes.")
    inv_df = pd.DataFrame(
        [{"inventory_key": k, "stock_units": v} for k, v in MANUAL_INVENTORY.items()]
    ).sort_values("inventory_key")
    st.dataframe(inv_df, use_container_width=True, hide_index=True)

period_label = "All Time"
start_date = None
end_date = None
if use_custom_range:
    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date = pd.to_datetime(selected_range[0])
        end_date = pd.to_datetime(selected_range[1])
        period_label = f"Custom Range: {start_date.date()} → {end_date.date()}"
    else:
        st.sidebar.warning("Please select both a start date and an end date.")

sales_view = sales.copy()
marketing_view = marketing.copy()
if use_custom_range and start_date is not None and end_date is not None and not marketing_view.empty:
    marketing_view = marketing_view[(marketing_view["date"] >= start_date) & (marketing_view["date"] <= end_date)]

if sales.empty:
    st.stop()

# Overview metrics
summary = {}
summary["total_revenue"] = float(sales_view["revenue"].sum())
summary["units_sold"] = float(sales_view["qty"].sum())
summary["gross_profit_before_ads"] = float(sales_view["gross_profit_before_ads"].sum())
summary["avg_selling_price"] = summary["total_revenue"] / summary["units_sold"] if summary["units_sold"] else 0.0
summary["commission_total"] = float(sales_view["commission_amount"].sum())
summary["cogs_total"] = float(sales_view["cogs_total"].sum())
summary["shipping_total"] = float(sales_view["shipping_total"].sum())
summary["total_stock_units"] = float(sales_view["stock_units"].dropna().sum())
summary["low_stock_skus"] = int(sales_view["stock_units"].fillna(0).le(low_stock_threshold).sum())
summary["marketing_spend"] = float(marketing_view["spend"].sum()) if not marketing_view.empty else 0.0
summary["marketing_revenue"] = float(marketing_view["attributed_revenue"].sum()) if not marketing_view.empty else 0.0
summary["roas"] = summary["marketing_revenue"] / summary["marketing_spend"] if summary["marketing_spend"] else 0.0
summary["net_profit_after_ads"] = summary["gross_profit_before_ads"] - summary["marketing_spend"]

cards = st.columns(6)
cards[0].metric("Total Revenue", f"{summary['total_revenue']:,.2f} TL")
cards[1].metric("Units Sold", f"{summary['units_sold']:,.0f}")
cards[2].metric("Avg Selling Price", f"{summary['avg_selling_price']:,.2f} TL")
cards[3].metric("Gross Profit (Before Ads)", f"{summary['gross_profit_before_ads']:,.2f} TL")
cards[4].metric("Ad Spend", f"{summary['marketing_spend']:,.2f} TL")
cards[5].metric("ROAS", f"{summary['roas']:,.2f}")

cards2 = st.columns(4)
cards2[0].metric("Net Profit (After Ads)", f"{summary['net_profit_after_ads']:,.2f} TL")
cards2[1].metric("Total Inventory Units", f"{summary['total_stock_units']:,.0f}")
cards2[2].metric("Low Stock Products", f"{summary['low_stock_skus']}")
cards2[3].metric("Snapshot Source", model["sales_meta"].get("selected_snapshot") or "N/A")

# Hero product cards
product_perf = sales_view.copy()
product_perf["display_name"] = product_perf["product_name"].fillna("") + " | " + product_perf["variant"].fillna("")
qty_leader = product_perf.loc[product_perf["qty"].idxmax()] if not product_perf.empty else None
rev_leader = product_perf.loc[product_perf["revenue"].idxmax()] if not product_perf.empty else None
profit_leader = product_perf.loc[product_perf["gross_profit_before_ads"].idxmax()] if not product_perf.empty else None

leader_cols = st.columns(3)
if qty_leader is not None:
    leader_cols[0].metric("Best Seller by Units", qty_leader["display_name"][:45], f"{qty_leader['qty']:,.0f} units")
if rev_leader is not None:
    leader_cols[1].metric("Top Product by Revenue", rev_leader["display_name"][:45], f"{rev_leader['revenue']:,.2f} TL")
if profit_leader is not None:
    leader_cols[2].metric("Top Product by Profit", profit_leader["display_name"][:45], f"{profit_leader['gross_profit_before_ads']:,.2f} TL")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Overview",
    "Product Profitability",
    "Store Traffic",
    "Marketing",
    "Data Quality",
])

with tab1:
    st.subheader("Profit Bridge")
    bridge_df = pd.DataFrame(
        {
            "Metric": [
                "Revenue",
                "Commission",
                "COGS",
                "Shipping",
                "Gross Profit Before Ads",
                "Ad Spend",
                "Net Profit After Ads",
            ],
            "Amount": [
                summary["total_revenue"],
                -summary["commission_total"],
                -summary["cogs_total"],
                -summary["shipping_total"],
                summary["gross_profit_before_ads"],
                -summary["marketing_spend"],
                summary["net_profit_after_ads"],
            ],
        }
    )
    fig_bridge = px.bar(bridge_df, x="Metric", y="Amount", title="Profit Waterfall View")
    st.plotly_chart(fig_bridge, use_container_width=True)

    st.subheader("Top 10 Products by Revenue")
    top10 = product_perf.sort_values("revenue", ascending=False).head(10)
    fig_top10 = px.bar(top10, x="display_name", y="revenue", title="Top 10 Products by Revenue")
    st.plotly_chart(fig_top10, use_container_width=True)
    st.dataframe(
        top10[["sku", "product_name", "variant", "qty", "revenue", "gross_profit_before_ads", "stock_units"]]
        .rename(columns={"qty": "units_sold"})
        .style.format({
            "revenue": "{:,.2f} TL",
            "gross_profit_before_ads": "{:,.2f} TL",
            "stock_units": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.subheader("Product Profitability Table")
    prod = product_perf[[
        "sku",
        "seller_sku",
        "product_name",
        "variant",
        "qty",
        "revenue",
        "commission_pct_effective",
        "commission_amount",
        "cost",
        "shipping_cost",
        "gross_profit_before_ads",
        "inventory_key",
        "stock_units",
        "stock_status",
    ]].copy()
    prod = prod.rename(columns={
        "qty": "units_sold",
        "cost": "unit_cost",
        "shipping_cost": "unit_shipping_cost",
    }).sort_values("gross_profit_before_ads", ascending=False)
    st.dataframe(
        prod.style.format({
            "revenue": "{:,.2f} TL",
            "commission_pct_effective": "{:.2%}",
            "commission_amount": "{:,.2f} TL",
            "unit_cost": "{:,.2f} TL",
            "unit_shipping_cost": "{:,.2f} TL",
            "gross_profit_before_ads": "{:,.2f} TL",
            "stock_units": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Low Stock List")
    low_stock = prod[prod["stock_units"].fillna(0) <= low_stock_threshold].sort_values("stock_units", ascending=True)
    st.dataframe(
        low_stock.style.format({
            "revenue": "{:,.2f} TL",
            "commission_amount": "{:,.2f} TL",
            "unit_cost": "{:,.2f} TL",
            "unit_shipping_cost": "{:,.2f} TL",
            "gross_profit_before_ads": "{:,.2f} TL",
            "stock_units": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    if product_perf[["views", "visitors", "added_to_cart"]].fillna(0).sum().sum() == 0:
        st.info("No Hepsiburada traffic export was found.")
    else:
        traffic_view = product_perf[[
            "sku",
            "product_name",
            "variant",
            "views",
            "visitors",
            "added_to_lists",
            "added_to_cart",
            "traffic_sales_qty",
            "conversion_rate",
        ]].copy()
        traffic_view["display_name"] = traffic_view["product_name"].fillna("") + " | " + traffic_view["variant"].fillna("")
        tcols = st.columns(4)
        tcols[0].metric("Total Views", f"{traffic_view['views'].sum():,.0f}")
        tcols[1].metric("Unique Visitors", f"{traffic_view['visitors'].sum():,.0f}")
        tcols[2].metric("Add to Cart", f"{traffic_view['added_to_cart'].sum():,.0f}")
        weighted_conv = traffic_view["traffic_sales_qty"].sum() / traffic_view["visitors"].sum() if traffic_view["visitors"].sum() else 0.0
        tcols[3].metric("Weighted Conversion", f"{weighted_conv:.2%}")

        top_views = traffic_view.sort_values("views", ascending=False).head(10)
        fig_views = px.bar(top_views, x="display_name", y="views", title="Top 10 Products by Views")
        st.plotly_chart(fig_views, use_container_width=True)
        st.dataframe(
            traffic_view[["sku", "product_name", "variant", "views", "visitors", "added_to_lists", "added_to_cart", "traffic_sales_qty", "conversion_rate"]]
            .sort_values("views", ascending=False)
            .style.format({"conversion_rate": "{:.2%}"}),
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    if marketing_view.empty:
        st.info("No marketing file found yet. Upload a Meta Ads or Hepsiburada Ads export with a date column and spend column to activate this tab.")
    else:
        mcols = st.columns(4)
        mcols[0].metric("Ad Spend", f"{marketing_view['spend'].sum():,.2f} TL")
        mcols[1].metric("Attributed Revenue", f"{marketing_view['attributed_revenue'].sum():,.2f} TL")
        mcols[2].metric("ROAS", f"{(marketing_view['attributed_revenue'].sum() / marketing_view['spend'].sum()) if marketing_view['spend'].sum() else 0:,.2f}")
        mcols[3].metric("Sources", ", ".join(marketing_view['source'].dropna().unique().tolist()))

        daily_m = marketing_view.groupby([marketing_view["date"].dt.date, "source"], as_index=False)[["spend", "attributed_revenue"]].sum()
        fig_spend = px.line(daily_m, x="date", y="spend", color="source", title="Daily Ad Spend")
        fig_attr = px.line(daily_m, x="date", y="attributed_revenue", color="source", title="Daily Attributed Revenue")
        st.plotly_chart(fig_spend, use_container_width=True)
        st.plotly_chart(fig_attr, use_container_width=True)
        st.dataframe(marketing_view.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Notes and Reporting Scope")
    for warning in model["warnings"]:
        st.info(warning)
    st.info(f"Reporting period: {period_label}")

    st.subheader("Snapshot Selection")
    snapshot_df = pd.DataFrame(model["sales_meta"].get("snapshots", []))
    if not snapshot_df.empty:
        st.dataframe(
            snapshot_df.style.format({"revenue": "{:,.2f} TL", "qty": "{:,.0f}"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No sales snapshot metadata available.")

    st.subheader("Field Coverage")
    coverage = pd.DataFrame({
        "field": sales_view.columns,
        "non_null_ratio": [sales_view[c].notna().mean() for c in sales_view.columns],
        "non_zero_ratio": [sales_view[c].fillna(0).ne(0).mean() if pd.api.types.is_numeric_dtype(sales_view[c]) else None for c in sales_view.columns],
    })
    st.dataframe(
        coverage.style.format({"non_null_ratio": "{:.1%}", "non_zero_ratio": "{:.1%}"}),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Cost Match Quality")
    cost_match_ratio = sales_view["cost"].fillna(0).gt(0).mean() if "cost" in sales_view.columns else 0.0
    inventory_match_ratio = sales_view["stock_units"].notna().mean() if "stock_units" in sales_view.columns else 0.0
    qcols = st.columns(2)
    qcols[0].metric("Cost Match Ratio", f"{cost_match_ratio:.1%}")
    qcols[1].metric("Inventory Match Ratio", f"{inventory_match_ratio:.1%}")

    unmatched = sales_view[sales_view["stock_units"].isna()][["sku", "product_name", "variant"]]
    if not unmatched.empty:
        st.write("Products missing manual inventory mapping")
        st.dataframe(unmatched, use_container_width=True, hide_index=True)
