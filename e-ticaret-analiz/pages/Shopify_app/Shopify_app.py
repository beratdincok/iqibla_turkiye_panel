
from __future__ import annotations

import csv
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# PAGE
# =========================================================
st.set_page_config(page_title="SMARTEK360 Shopify Dashboard", layout="wide")

if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🟣 SMARTEK360: Shopify Dashboard")
st.caption("Shopify satış, maliyet, funnel, şehir/bölge, Meta reklam ve fatura dosyalarını kendi klasöründen okur.")

DATA_DIR = Path(__file__).resolve().parent


# =========================================================
# HELPERS
# =========================================================
def normalize_text(text) -> str:
    if text is None or pd.isna(text):
        return ""
    s = str(text).lower().strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    })
    s = s.translate(tr_map)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def to_float(val) -> float:
    if val is None or pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    s = (
        s.replace("TL", "")
        .replace("TRY", "")
        .replace("₺", "")
        .replace("%", "")
        .replace('"', "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    if s.lower() in {"-", "nan", "none", "null", "sürekli", "surekli"}:
        return 0.0

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # 0,01 gibi oranları bozma
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


def clean_sku(val) -> str:
    if val is None or pd.isna(val) or val == "":
        return ""
    s = str(val).strip().replace(" ", "")
    s = s.replace("'", "")
    if s.startswith("6-"):
        s = s[2:]
    s = s.replace("-", "")
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    try:
        if "e+" in s.lower():
            s = str(int(float(s)))
    except Exception:
        pass
    return s


def find_col(df: pd.DataFrame, keys: list[str]) -> Optional[str]:
    normalized = {normalize_text(c): c for c in df.columns}

    for key in keys:
        nk = normalize_text(key)
        for norm, raw in normalized.items():
            if nk == norm:
                return raw

    for key in keys:
        nk = normalize_text(key)
        for norm, raw in normalized.items():
            if nk and nk in norm:
                return raw

    return None


def read_csv_flexible(path: Path, *, skiprows: int = 0) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]
    seps = [",", ";", "\t"]

    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, low_memory=False, skiprows=skiprows)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue
    return pd.DataFrame()


def read_shopify_order_csv_robust(path: Path) -> pd.DataFrame:
    """
    Shopify export'larında bazı dosyalarda satırlar tek hücreye düşebiliyor.
    Bu fonksiyon header 79 kolon olsa bile tek hücreye düşen satırı tekrar csv.reader ile parçalar.
    """
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)

            if not rows:
                continue

            header = rows[0]
            # Header yanlışlıkla tek hücre geldiyse tekrar parse et.
            if len(header) == 1 and "," in header[0]:
                header = next(csv.reader([header[0]]))

            header_len = len(header)
            fixed_rows = []

            for raw in rows[1:]:
                if not raw:
                    continue

                row = raw

                if len(row) == 1 and "," in row[0]:
                    try:
                        row = next(csv.reader([row[0]]))
                    except Exception:
                        pass

                # Bazı satırlarda ilk hücre komple satır, geri kalanlar boş gelebilir.
                if len(row) == header_len and row[0].count(",") > 10 and all(str(x).strip() == "" for x in row[1:]):
                    try:
                        row = next(csv.reader([row[0]]))
                    except Exception:
                        pass

                if len(row) < header_len:
                    row = row + [""] * (header_len - len(row))
                elif len(row) > header_len:
                    row = row[:header_len]

                if len(row) == header_len:
                    fixed_rows.append(row)

            if fixed_rows and header_len > 5:
                df = pd.DataFrame(fixed_rows, columns=header)
                df = df.loc[:, ~df.columns.duplicated()]
                return df

        except Exception:
            continue

    return pd.DataFrame()


def safe_divide(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def all_csv_files() -> list[Path]:
    return sorted(DATA_DIR.glob("*.csv"))


# =========================================================
# FILE CLASSIFICATION
# =========================================================
def is_shopify_order_file(path: Path) -> bool:
    name = normalize_text(path.name)

    if any(x in name for x in ["maliyet", "meta", "billing", "campaign", "fatura", "zamana gore", "oturum"]):
        return False

    if any(x in name for x in ["shopify002", "shopify003", "shopify004"]):
        return False

    df = read_shopify_order_csv_robust(path)
    if df.empty:
        return False

    required = {"Name", "Created at", "Lineitem name"}
    return required.issubset(set(df.columns))


def classify_files() -> dict[str, list[Path]]:
    files = all_csv_files()
    groups = {
        "orders": [],
        "costs": [],
        "funnel": [],
        "geo": [],
        "gross_monthly": [],
        "meta": [],
        "billing": [],
        "other": [],
    }

    for path in files:
        name = normalize_text(path.name)

        if "maliyet" in name:
            groups["costs"].append(path)
        elif "shopify002" in name or "oturumlar" in name:
            groups["funnel"].append(path)
        elif "shopify003" in name:
            groups["geo"].append(path)
        elif "shopify004" in name:
            groups["gross_monthly"].append(path)
        elif "meta" in name or "campaign" in name:
            groups["meta"].append(path)
        elif "billing" in name or "fatura" in name:
            groups["billing"].append(path)
        elif is_shopify_order_file(path):
            groups["orders"].append(path)
        else:
            groups["other"].append(path)

    return groups


# =========================================================
# LOADERS
# =========================================================
@st.cache_data(show_spinner=False)
def load_costs() -> pd.DataFrame:
    groups = classify_files()
    if not groups["costs"]:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "unit_ship", "vat_rate"])

    path = groups["costs"][0]
    df = read_csv_flexible(path)
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "unit_ship", "vat_rate"])

    sku_col = find_col(df, ["SKU"])
    comm_col = find_col(df, ["Komisyon oran", "Komisyon", "Commission"])
    cost_col = find_col(df, ["Maliyet", "Cost"])
    ship_col = find_col(df, ["Kargo", "Shipping"])
    vat_col = find_col(df, ["KDV", "VAT"])

    if not sku_col:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "unit_ship", "vat_rate"])

    out = pd.DataFrame({
        "sku_key": df[sku_col].apply(clean_sku),
        "commission_rate": df[comm_col].apply(to_float) if comm_col else 0.0,
        "unit_cost": df[cost_col].apply(to_float) if cost_col else 0.0,
        "unit_ship": df[ship_col].apply(to_float) if ship_col else 0.0,
        "vat_rate": df[vat_col].apply(to_float) if vat_col else 0.0,
    })

    # Komisyon 1'den büyükse yüzde gibi gelmiştir: 10 -> 0.10
    out["commission_rate"] = out["commission_rate"].apply(lambda x: x / 100 if x > 1 else x)

    out = out[out["sku_key"] != ""].drop_duplicates("sku_key", keep="last")
    return out


@st.cache_data(show_spinner=False)
def load_orders_and_lines() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    groups = classify_files()
    order_files = groups["orders"]
    debug = []

    if not order_files:
        return pd.DataFrame(), pd.DataFrame(), debug

    frames = []

    for path in order_files:
        df = read_shopify_order_csv_robust(path)
        debug.append({"file": path.name, "type": "order", "rows": len(df), "cols": len(df.columns)})

        if df.empty:
            continue

        required_cols = {"Name", "Created at", "Lineitem name"}
        if not required_cols.issubset(set(df.columns)):
            continue

        df["source_file"] = path.name
        frames.append(df)

    if not frames:
        return pd.DataFrame(), pd.DataFrame(), debug

    raw = pd.concat(frames, ignore_index=True)

    for col in [
        "Total", "Subtotal", "Shipping", "Taxes", "Discount Amount", "Refunded Amount",
        "Lineitem quantity", "Lineitem price", "Lineitem discount"
    ]:
        if col in raw.columns:
            raw[col] = raw[col].apply(to_float)
        else:
            raw[col] = 0.0

    raw["order_date"] = pd.to_datetime(raw["Created at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["paid_at"] = pd.to_datetime(raw.get("Paid at", ""), errors="coerce", utc=True).dt.tz_localize(None)
    raw["cancelled_at"] = pd.to_datetime(raw.get("Cancelled at", ""), errors="coerce", utc=True).dt.tz_localize(None)
    raw["order_name"] = raw["Name"].astype(str)
    raw["financial_status"] = raw.get("Financial Status", "").fillna("").astype(str).str.lower()
    raw["fulfillment_status"] = raw.get("Fulfillment Status", "").fillna("").astype(str).str.lower()

    # Sadece dolu order name satırları.
    raw = raw[raw["order_name"].fillna("").astype(str).str.strip() != ""].copy()

    dedupe_cols = [c for c in [
        "Name", "Created at", "Lineitem name", "Lineitem sku",
        "Lineitem quantity", "Lineitem price", "Financial Status",
        "Fulfillment Status", "Total", "Discount Amount", "source_file"
    ] if c in raw.columns]
    raw = raw.drop_duplicates(subset=dedupe_cols, keep="first")

    orders = raw.groupby("order_name", dropna=False).agg({
        "order_date": "first",
        "paid_at": "first",
        "cancelled_at": "first",
        "financial_status": "first",
        "fulfillment_status": "first",
        "Total": "first",
        "Subtotal": "first",
        "Shipping": "first",
        "Taxes": "first",
        "Discount Amount": "first",
        "Refunded Amount": "first",
        "Currency": "first",
        "Payment Method": "first",
        "Billing City": "first",
        "Source": "first",
        "source_file": "first",
    }).reset_index()

    orders["is_cancelled"] = orders["cancelled_at"].notna() | orders["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    orders["net_sales"] = orders["Total"].fillna(0) - orders["Refunded Amount"].fillna(0)
    orders.loc[orders["is_cancelled"], "net_sales"] = 0.0
    orders["order_count"] = (~orders["is_cancelled"]).astype(int)

    lines = raw.copy()
    lines["product_name"] = lines["Lineitem name"].fillna("").astype(str)
    lines["product_name_norm"] = lines["product_name"].apply(normalize_text)
    lines["sku_key"] = lines.get("Lineitem sku", "").apply(clean_sku)
    lines["qty"] = lines["Lineitem quantity"].apply(to_float)
    lines["line_price"] = lines["Lineitem price"].apply(to_float)
    lines["line_discount"] = lines["Lineitem discount"].apply(to_float)
    lines["line_revenue"] = lines["line_price"] * lines["qty"] - lines["line_discount"]
    lines["is_cancelled"] = lines["cancelled_at"].notna() | lines["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    lines.loc[lines["is_cancelled"], ["qty", "line_revenue"]] = 0.0

    keep = [
        "order_name", "order_date", "financial_status", "fulfillment_status",
        "sku_key", "product_name", "product_name_norm", "qty", "line_revenue",
        "is_cancelled", "source_file"
    ]
    return orders, lines[keep].copy(), debug


@st.cache_data(show_spinner=False)
def load_funnel() -> pd.DataFrame:
    groups = classify_files()
    files = groups["funnel"]
    if not files:
        return pd.DataFrame()

    df = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame()

    month_col = find_col(df, ["Ay", "Month"])
    sessions_col = find_col(df, ["Oturumlar", "Sessions"])
    cart_col = find_col(df, ["Sepete ekleme", "Added to cart"])
    checkout_col = find_col(df, ["Ödeme sayfasına", "Checkout"])
    purchase_col = find_col(df, ["Ödemeyi tamamlayan", "Completed checkout"])
    conv_col = find_col(df, ["Dönüşüm oranı", "Conversion rate"])

    if not month_col:
        return pd.DataFrame()

    out = pd.DataFrame({
        "month": pd.to_datetime(df[month_col], errors="coerce"),
        "sessions": df[sessions_col].apply(to_float) if sessions_col else 0.0,
        "sessions_added_to_cart": df[cart_col].apply(to_float) if cart_col else 0.0,
        "sessions_reached_checkout": df[checkout_col].apply(to_float) if checkout_col else 0.0,
        "sessions_completed_checkout": df[purchase_col].apply(to_float) if purchase_col else 0.0,
        "conversion_rate": df[conv_col].apply(to_float) if conv_col else 0.0,
    })
    return out.dropna(subset=["month"])


@st.cache_data(show_spinner=False)
def load_geo() -> pd.DataFrame:
    groups = classify_files()
    files = groups["geo"]
    if not files:
        return pd.DataFrame()

    df = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame()

    country_col = find_col(df, ["Oturum ülkesi", "Country"])
    region_col = find_col(df, ["Oturum bölgesi", "Region"])
    city_col = find_col(df, ["Oturum şehri", "City"])
    visitors_col = find_col(df, ["Online mağaza ziyaretçileri", "Visitors"])
    sessions_col = find_col(df, ["Oturumlar", "Sessions"])

    out = pd.DataFrame({
        "country": df[country_col] if country_col else "",
        "region": df[region_col] if region_col else "",
        "city": df[city_col] if city_col else "",
        "visitors": df[visitors_col].apply(to_float) if visitors_col else 0.0,
        "sessions": df[sessions_col].apply(to_float) if sessions_col else 0.0,
    })
    return out


@st.cache_data(show_spinner=False)
def load_gross_monthly() -> pd.DataFrame:
    groups = classify_files()
    files = groups["gross_monthly"]
    if not files:
        return pd.DataFrame()

    df = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame()

    month_col = find_col(df, ["Ay", "Month"])
    gross_col = find_col(df, ["Brüt satışlar", "Gross sales"])

    if not month_col or not gross_col:
        return pd.DataFrame()

    out = pd.DataFrame({
        "month": pd.to_datetime(df[month_col], errors="coerce"),
        "gross_sales": df[gross_col].apply(to_float),
    })
    return out.dropna(subset=["month"])


@st.cache_data(show_spinner=False)
def load_meta() -> pd.DataFrame:
    groups = classify_files()
    files = groups["meta"] + groups["billing"]
    rows = []

    for path in files:
        df = read_csv_flexible(path)
        if df.empty:
            continue

        date_col = find_col(df, ["Date", "Day", "Tarih", "Reporting starts", "Rapor Başlangıcı", "Rapor Baslangici"])
        campaign_col = find_col(df, ["Campaign name", "Kampanya Adı", "Kampanya"])
        spend_col = find_col(df, ["Amount spent", "Harcanan Tutar", "Spend", "Harcama", "Tutar"])
        revenue_col = find_col(df, ["Purchase conversion value", "Purchases conversion value", "Revenue", "Gelir", "Dönüşüm değeri"])
        purchase_col = find_col(df, ["Purchases", "Satın almalar", "Alışverişler", "Results"])

        if not spend_col:
            continue

        tmp = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
            "campaign_name": df[campaign_col].astype(str) if campaign_col else path.stem,
            "spend": df[spend_col].apply(to_float),
            "attributed_revenue": df[revenue_col].apply(to_float) if revenue_col else 0.0,
            "purchases": df[purchase_col].apply(to_float) if purchase_col else 0.0,
            "source_file": path.name,
        })
        rows.append(tmp)

    if not rows:
        return pd.DataFrame(columns=["date", "campaign_name", "spend", "attributed_revenue", "purchases", "source_file"])

    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    return out


# =========================================================
# BUILD MODEL
# =========================================================
@st.cache_data(show_spinner=False)
def build_model():
    costs = load_costs()
    orders, lines, order_debug = load_orders_and_lines()
    funnel = load_funnel()
    geo = load_geo()
    gross_monthly = load_gross_monthly()
    meta = load_meta()
    groups = classify_files()

    issues = []

    if orders.empty:
        issues.append("Shopify sipariş dosyası okunamadı. Shopify export dosyasında Name, Created at ve Lineitem name kolonları olmalı.")
    if costs.empty:
        issues.append("Shopify maliyet tablosu okunamadı veya SKU kolonu bulunamadı.")
    if funnel.empty:
        issues.append("shopify002.csv funnel dosyası okunamadı.")
    if geo.empty:
        issues.append("shopify003.csv şehir/bölge dosyası okunamadı.")
    if gross_monthly.empty:
        issues.append("shopify004.csv aylık brüt satış dosyası okunamadı.")
    if meta.empty:
        issues.append("Meta reklam/fatura dosyası okunamadı veya harcama kolonu bulunamadı.")

    if not lines.empty:
        lines = lines.merge(costs, on="sku_key", how="left")
        lines["unit_cost"] = lines["unit_cost"].fillna(0.0)
        lines["unit_ship"] = lines["unit_ship"].fillna(0.0)
        lines["commission_rate"] = lines["commission_rate"].fillna(0.0)
        lines["matched_cost"] = lines["unit_cost"].gt(0)
        lines["estimated_cost_total"] = (lines["unit_cost"] + lines["unit_ship"]) * lines["qty"]
        lines["estimated_commission_total"] = lines["line_revenue"] * lines["commission_rate"]
        lines["gross_profit"] = lines["line_revenue"] - lines["estimated_cost_total"] - lines["estimated_commission_total"]
    else:
        lines["gross_profit"] = []
        lines["matched_cost"] = []

    if not orders.empty and not lines.empty:
        profit = lines.groupby("order_name", as_index=False).agg(gross_profit_estimated=("gross_profit", "sum"))
        orders = orders.merge(profit, on="order_name", how="left")
        orders["gross_profit_estimated"] = orders["gross_profit_estimated"].fillna(0.0)
    elif not orders.empty:
        orders["gross_profit_estimated"] = orders["net_sales"] * 0.45

    return {
        "costs": costs,
        "orders": orders,
        "lines": lines,
        "funnel": funnel,
        "geo": geo,
        "gross_monthly": gross_monthly,
        "meta": meta,
        "groups": groups,
        "issues": issues,
        "order_debug": order_debug,
    }


model = build_model()

orders = model["orders"]
lines = model["lines"]
funnel = model["funnel"]
geo = model["geo"]
gross_monthly = model["gross_monthly"]
meta = model["meta"]
groups = model["groups"]
issues = model["issues"]
order_debug = model["order_debug"]


# =========================================================
# FILTERS
# =========================================================
date_values = []
if not orders.empty and "order_date" in orders.columns:
    date_values.append(pd.to_datetime(orders["order_date"], errors="coerce").dropna())
if not meta.empty and "date" in meta.columns:
    date_values.append(pd.to_datetime(meta["date"], errors="coerce").dropna())

if date_values and any(len(x) for x in date_values):
    all_dates = pd.concat([x for x in date_values if len(x)], ignore_index=True)
    min_date = all_dates.min().date()
    max_date = all_dates.max().date()
else:
    min_date = max_date = pd.Timestamp.today().date()

with st.sidebar:
    st.header("Filters")
    all_time = st.toggle("All Time", value=True)
    start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, disabled=all_time)
    end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, disabled=all_time)
    low_stock_threshold = st.number_input("Low stock threshold", min_value=0, value=20, step=1)
    show_debug = st.checkbox("Dosya okuma debug göster", value=True)


def filter_df_by_date(df: pd.DataFrame, date_col: str):
    if df.empty or all_time or date_col not in df.columns:
        return df.copy()
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d = pd.to_datetime(df[date_col], errors="coerce")
    return df[(d >= s) & (d <= e)].copy()


orders_f = filter_df_by_date(orders, "order_date")
lines_f = filter_df_by_date(lines, "order_date")
meta_f = filter_df_by_date(meta, "date")

# =========================================================
# KPI
# =========================================================
total_sales = float(orders_f["net_sales"].sum()) if not orders_f.empty else 0.0
total_orders = int(orders_f["order_count"].sum()) if not orders_f.empty and "order_count" in orders_f.columns else int(orders_f["order_name"].nunique()) if not orders_f.empty else 0
aov = safe_divide(total_sales, total_orders)
gross_profit = float(orders_f["gross_profit_estimated"].sum()) if not orders_f.empty and "gross_profit_estimated" in orders_f.columns else float(lines_f["gross_profit"].sum()) if not lines_f.empty else 0.0
meta_spend = float(meta_f["spend"].sum()) if not meta_f.empty else 0.0
meta_revenue = float(meta_f["attributed_revenue"].sum()) if not meta_f.empty else 0.0
meta_purchases = float(meta_f["purchases"].sum()) if not meta_f.empty else 0.0
net_profit_after_ads = gross_profit - meta_spend
roas = safe_divide(meta_revenue, meta_spend)
mer = safe_divide(total_sales, meta_spend)


# =========================================================
# UI
# =========================================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Net Sales", f"{total_sales:,.2f} TL")
c2.metric("Orders", f"{total_orders:,}")
c3.metric("AOV", f"{aov:,.2f} TL")
c4.metric("Estimated Gross Profit", f"{gross_profit:,.2f} TL")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Meta Spend", f"{meta_spend:,.2f} TL")
c6.metric("Net Profit After Ads", f"{net_profit_after_ads:,.2f} TL")
c7.metric("Meta ROAS", f"{roas:,.2f}" if roas else "N/A")
c8.metric("MER", f"{mer:,.2f}" if mer else "N/A")

if issues:
    with st.expander("Okuma uyarıları", expanded=orders.empty):
        for msg in issues:
            st.info(msg)

if show_debug:
    with st.expander("Dosya okuma debug", expanded=orders.empty):
        rows = []
        for group_name, paths in groups.items():
            for p in paths:
                rows.append({"group": group_name, "file": p.name})
        st.write("DATA_DIR:")
        st.code(str(DATA_DIR))
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if order_debug:
            st.write("Order parser debug")
            st.dataframe(pd.DataFrame(order_debug), use_container_width=True, hide_index=True)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Sales Performance",
    "Products & Inventory",
    "Traffic & Funnel",
    "Marketing",
    "Orders",
    "Data Quality",
])

with tab1:
    st.subheader("Daily Sales and Profit")
    if orders_f.empty:
        st.warning("Shopify sipariş verisi bulunamadı veya okunamadı.")
    else:
        daily = orders_f.groupby(orders_f["order_date"].dt.normalize(), as_index=False).agg({
            "net_sales": "sum",
            "order_count": "sum",
            "gross_profit_estimated": "sum",
        }).rename(columns={"order_date": "date"})
        if not meta_f.empty:
            meta_daily = meta_f.groupby(meta_f["date"].dt.normalize(), as_index=False).agg({
                "spend": "sum",
                "attributed_revenue": "sum",
                "purchases": "sum",
            }).rename(columns={"date": "date"})
            daily = daily.merge(meta_daily, on="date", how="outer").fillna(0.0)
        else:
            daily["spend"] = 0.0
            daily["attributed_revenue"] = 0.0
            daily["purchases"] = 0.0

        daily["net_profit_after_ads"] = daily["gross_profit_estimated"] - daily["spend"]
        chart_df = daily.melt(
            id_vars="date",
            value_vars=["net_sales", "gross_profit_estimated", "net_profit_after_ads"],
            var_name="metric",
            value_name="value",
        )
        fig = px.line(chart_df, x="date", y="value", color="metric", markers=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(daily.sort_values("date", ascending=False), use_container_width=True)

    if not gross_monthly.empty:
        st.subheader("Shopify Gross Sales Export")
        fig2 = px.line(gross_monthly.sort_values("month"), x="month", y="gross_sales", markers=True)
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(gross_monthly, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Product Profitability")
    if lines_f.empty:
        st.info("Ürün satır verisi bulunamadı.")
    else:
        product = lines_f.groupby("product_name", as_index=False).agg(
            qty_sold=("qty", "sum"),
            revenue=("line_revenue", "sum"),
            gross_profit=("gross_profit", "sum"),
            matched_cost_rate=("matched_cost", "mean"),
        ).sort_values(["qty_sold", "revenue"], ascending=False)

        st.dataframe(
            product.style.format({
                "qty_sold": "{:,.0f}",
                "revenue": "{:,.2f} TL",
                "gross_profit": "{:,.2f} TL",
                "matched_cost_rate": "{:.1%}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        fig = px.bar(product.head(15).sort_values("qty_sold"), x="qty_sold", y="product_name", orientation="h")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Funnel")
    if funnel.empty:
        st.info("shopify002.csv okunamadı veya bulunamadı.")
    else:
        fchart = funnel.melt(
            id_vars="month",
            value_vars=["sessions", "sessions_added_to_cart", "sessions_reached_checkout", "sessions_completed_checkout"],
            var_name="metric",
            value_name="value",
        )
        fig = px.line(fchart, x="month", y="value", color="metric", markers=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(funnel, use_container_width=True, hide_index=True)

    st.subheader("Geo Performance")
    if geo.empty:
        st.info("shopify003.csv okunamadı veya bulunamadı.")
    else:
        st.dataframe(geo.sort_values("sessions", ascending=False).head(30), use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Meta / Marketing")
    if meta_f.empty:
        st.info("Meta dosyası okunamadı veya seçili tarihte veri yok.")
    else:
        st.dataframe(meta_f.sort_values("date", ascending=False), use_container_width=True, hide_index=True)
        campaign = meta_f.groupby("campaign_name", as_index=False).agg(
            spend=("spend", "sum"),
            attributed_revenue=("attributed_revenue", "sum"),
            purchases=("purchases", "sum"),
        )
        campaign["roas"] = campaign.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
        st.subheader("Campaign Summary")
        st.dataframe(campaign.sort_values("spend", ascending=False), use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Orders")
    if orders_f.empty:
        st.warning("Sipariş tablosu boş.")
    else:
        cols = [
            "order_name", "order_date", "financial_status", "fulfillment_status",
            "net_sales", "gross_profit_estimated", "Payment Method", "Billing City", "Source", "source_file"
        ]
        cols = [c for c in cols if c in orders_f.columns]
        st.dataframe(orders_f.sort_values("order_date", ascending=False)[cols], use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Data Quality")
    quality = pd.DataFrame([
        {"Check": "Order files detected", "Value": len(groups["orders"])},
        {"Check": "Order rows loaded", "Value": len(orders)},
        {"Check": "Line rows loaded", "Value": len(lines)},
        {"Check": "Cost rows loaded", "Value": len(model["costs"])},
        {"Check": "Funnel rows loaded", "Value": len(funnel)},
        {"Check": "Geo rows loaded", "Value": len(geo)},
        {"Check": "Gross monthly rows loaded", "Value": len(gross_monthly)},
        {"Check": "Meta rows loaded", "Value": len(meta)},
    ])
    st.dataframe(quality, use_container_width=True, hide_index=True)

    if not lines.empty and "matched_cost" in lines.columns:
        missing = lines[~lines["matched_cost"]][["product_name", "sku_key", "source_file"]].drop_duplicates()
        st.write("Products without matched cost")
        st.dataframe(missing, use_container_width=True, hide_index=True)
