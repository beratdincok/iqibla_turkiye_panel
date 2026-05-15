
from __future__ import annotations

import csv
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
st.set_page_config(page_title="SMARTEK360 Shopify Reader", layout="wide")

if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🟣 SMARTEK360: Shopify Reader & Diagnostic Dashboard")
st.caption(
    "Shopify sipariş, maliyet ve oturum dosyalarını okuyup rapora aktarır. "
    "Reklam harcaması ve reklam geliri Meta/fatura dosyasından değil, Kreatif_Takip klasöründeki kreatif raporlarından alınır."
)

DATA_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DATA_DIR.parents[1] if len(DATA_DIR.parents) > 1 else DATA_DIR.parent
KREATIF_DIR = PROJECT_DIR / "pages" / "Kreatif_Takip"


# =========================================================
# HELPERS
# =========================================================
def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    s = str(value).lower().strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    })
    s = s.translate(tr_map)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def to_float(value) -> float:
    if value is None or pd.isna(value) or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    s = (
        s.replace("TL", "")
        .replace("TRY", "")
        .replace("₺", "")
        .replace("%", "")
        .replace('"', "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    if s.lower() in {"-", "nan", "none", "null"}:
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


def clean_sku(value) -> str:
    if value is None or pd.isna(value):
        return ""
    s = str(value).strip().replace(" ", "").replace("'", "")
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


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    norm_map = {normalize_text(c): c for c in df.columns}

    for cand in candidates:
        target = normalize_text(cand)
        for norm, raw in norm_map.items():
            if target == norm:
                return raw

    for cand in candidates:
        target = normalize_text(cand)
        for norm, raw in norm_map.items():
            if target and target in norm:
                return raw

    return None


def safe_divide(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def money(v: float) -> str:
    return f"{v:,.2f} TL"


def read_csv_flexible(path: Path, skiprows: int = 0) -> tuple[pd.DataFrame, str, str]:
    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    seps = [",", ";", "\t"]

    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, low_memory=False, skiprows=skiprows)
                if df.shape[1] > 1:
                    return df, enc, sep
            except Exception:
                continue
    return pd.DataFrame(), "", ""


def read_shopify_orders(path: Path) -> tuple[pd.DataFrame, str, str]:
    df, enc, sep = read_csv_flexible(path)
    if not df.empty and {"Name", "Created at", "Lineitem name"}.issubset(set(df.columns)):
        return df, enc, sep

    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace", newline="") as f:
                rows = list(csv.reader(f))
            if not rows:
                continue
            header = rows[0]
            if len(header) == 1 and "," in header[0]:
                header = next(csv.reader([header[0]]))
            hlen = len(header)
            fixed = []
            for row in rows[1:]:
                if len(row) == 1 and "," in row[0]:
                    row = next(csv.reader([row[0]]))
                if len(row) < hlen:
                    row += [""] * (hlen - len(row))
                elif len(row) > hlen:
                    row = row[:hlen]
                fixed.append(row)
            out = pd.DataFrame(fixed, columns=header)
            if {"Name", "Created at", "Lineitem name"}.issubset(set(out.columns)):
                return out, enc, "robust-csv"
        except Exception:
            continue

    return pd.DataFrame(), "", ""


def detect_file(path: Path) -> dict:
    name = normalize_text(path.name)

    order_df, enc, sep = read_shopify_orders(path)
    if not order_df.empty:
        return {
            "file": path.name,
            "type": "orders",
            "status": "OK",
            "rows": len(order_df),
            "cols": len(order_df.columns),
            "encoding": enc,
            "separator": sep,
            "notes": "Shopify order export detected.",
        }

    df, enc, sep = read_csv_flexible(path)
    if df.empty:
        return {
            "file": path.name,
            "type": "unreadable",
            "status": "ERROR",
            "rows": 0,
            "cols": 0,
            "encoding": "",
            "separator": "",
            "notes": "Cannot read as CSV.",
        }

    cols = " ".join(normalize_text(c) for c in df.columns)

    if "maliyet" in name or ("sku" in cols and ("maliyet" in cols or "cost" in cols)):
        return {
            "file": path.name,
            "type": "costs",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "notes": "Cost table detected.",
        }

    if "zamana gore" in name or "oturum" in name or ("online store visitors" in cols and "sessions" in cols):
        return {
            "file": path.name,
            "type": "sessions",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "notes": "Sessions / traffic file detected.",
        }

    if "meta" in name or "campaign" in name or "fatura" in name or "billing" in name:
        return {
            "file": path.name,
            "type": "ignored_meta",
            "status": "IGNORED",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "notes": "Shopify panelinde Meta dosyası kullanılmıyor. Reklam verisi Kreatif_Takip klasöründen alınır.",
        }

    return {
        "file": path.name,
        "type": "other",
        "status": "WARNING",
        "rows": len(df),
        "cols": len(df.columns),
        "encoding": enc,
        "separator": sep,
        "notes": "File read but type not recognized.",
    }


@st.cache_data(show_spinner=False)
def scan_files() -> pd.DataFrame:
    rows = [detect_file(p) for p in sorted(DATA_DIR.glob("*.csv"))]
    return pd.DataFrame(rows)


def paths_of_type(scan: pd.DataFrame, kind: str) -> list[Path]:
    if scan.empty:
        return []
    return [DATA_DIR / f for f in scan.loc[scan["type"].eq(kind), "file"].tolist()]


# =========================================================
# SHOPIFY LOADERS
# =========================================================
@st.cache_data(show_spinner=False)
def load_costs(scan: pd.DataFrame) -> pd.DataFrame:
    files = paths_of_type(scan, "costs")
    if not files:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping", "vat_rate"])

    df, _, _ = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping", "vat_rate"])

    sku_col = find_col(df, ["SKU"])
    cost_col = find_col(df, ["Maliyet", "Maliyet Alış", "Maliyet (Al??)", "Cost"])
    comm_col = find_col(df, ["Komisyon oran", "Komisyon", "Commission"])
    ship_col = find_col(df, ["Kargo", "Shipping"])
    vat_col = find_col(df, ["KDV Oranı", "KDV Oran", "KDV", "VAT"])

    if not sku_col:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping", "vat_rate"])

    out = pd.DataFrame({
        "sku_key": df[sku_col].apply(clean_sku),
        "unit_cost": df[cost_col].apply(to_float) if cost_col else 0.0,
        "commission_rate": df[comm_col].apply(to_float) if comm_col else 0.0,
        "unit_shipping": df[ship_col].apply(to_float) if ship_col else 0.0,
        "vat_rate": df[vat_col].apply(to_float) if vat_col else 0.0,
    })
    out["commission_rate"] = out["commission_rate"].apply(lambda x: x / 100 if x > 1 else x)
    out = out[out["sku_key"] != ""].drop_duplicates("sku_key", keep="last")
    return out


@st.cache_data(show_spinner=False)
def load_orders(scan: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = []
    debug = []
    for path in paths_of_type(scan, "orders"):
        df, enc, sep = read_shopify_orders(path)
        debug.append({"file": path.name, "rows": len(df), "cols": len(df.columns), "encoding": enc, "separator": sep})
        if df.empty:
            continue
        df["source_file"] = path.name
        frames.append(df)

    debug_df = pd.DataFrame(debug)
    if not frames:
        return pd.DataFrame(), pd.DataFrame(), debug_df

    raw = pd.concat(frames, ignore_index=True)

    for col in [
        "Total", "Subtotal", "Shipping", "Taxes", "Discount Amount", "Refunded Amount",
        "Lineitem quantity", "Lineitem price", "Lineitem discount"
    ]:
        if col not in raw.columns:
            raw[col] = 0.0
        raw[col] = raw[col].apply(to_float)

    for col in ["Paid at", "Cancelled at", "Financial Status", "Fulfillment Status", "Currency", "Payment Method", "Billing City", "Source", "Lineitem sku"]:
        if col not in raw.columns:
            raw[col] = ""

    raw["order_name"] = raw["Name"].fillna("").astype(str)
    raw["order_date"] = pd.to_datetime(raw["Created at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["cancelled_at"] = pd.to_datetime(raw["Cancelled at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["financial_status"] = raw["Financial Status"].fillna("").astype(str).str.lower()
    raw["fulfillment_status"] = raw["Fulfillment Status"].fillna("").astype(str).str.lower()
    raw = raw[raw["order_name"].str.strip() != ""].copy()

    dedupe_cols = [c for c in ["Name", "Created at", "Lineitem name", "Lineitem sku", "Lineitem quantity", "Lineitem price", "Total"] if c in raw.columns]
    raw = raw.drop_duplicates(subset=dedupe_cols, keep="first")

    orders = raw.groupby("order_name", as_index=False).agg(
        order_date=("order_date", "first"),
        cancelled_at=("cancelled_at", "first"),
        financial_status=("financial_status", "first"),
        fulfillment_status=("fulfillment_status", "first"),
        total=("Total", "first"),
        refunded_amount=("Refunded Amount", "first"),
        billing_city=("Billing City", "first"),
        source=("Source", "first"),
        source_file=("source_file", "first"),
    )
    orders["is_cancelled"] = orders["cancelled_at"].notna() | orders["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    orders["net_sales"] = orders["total"] - orders["refunded_amount"]
    orders.loc[orders["is_cancelled"], "net_sales"] = 0.0
    orders["order_count"] = (~orders["is_cancelled"]).astype(int)

    lines = raw.copy()
    lines["sku_key"] = lines["Lineitem sku"].apply(clean_sku)
    lines["product_name"] = lines["Lineitem name"].fillna("").astype(str)
    lines["qty"] = lines["Lineitem quantity"].apply(to_float)
    lines["line_revenue"] = lines["Lineitem price"].apply(to_float) * lines["qty"] - lines["Lineitem discount"].apply(to_float)
    lines["is_cancelled"] = lines["cancelled_at"].notna() | lines["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    lines.loc[lines["is_cancelled"], ["qty", "line_revenue"]] = 0.0

    lines = lines[["order_name", "order_date", "sku_key", "product_name", "qty", "line_revenue", "source_file"]].copy()
    return orders, lines, debug_df


@st.cache_data(show_spinner=False)
def load_sessions(scan: pd.DataFrame) -> pd.DataFrame:
    files = paths_of_type(scan, "sessions")
    rows = []
    for path in files:
        df, _, _ = read_csv_flexible(path)
        if df.empty:
            continue

        cols = list(df.columns)
        for i, col in enumerate(cols):
            if normalize_text(col).startswith("day"):
                day_col = col

                visitor_col = None
                session_col = None
                for j in range(i + 1, min(i + 5, len(cols))):
                    if "online store visitors" in normalize_text(cols[j]) or "ziyaretci" in normalize_text(cols[j]):
                        visitor_col = cols[j]
                    if "sessions" in normalize_text(cols[j]) or "oturum" in normalize_text(cols[j]):
                        session_col = cols[j]

                if session_col:
                    tmp = pd.DataFrame({
                        "date": pd.to_datetime(df[day_col], errors="coerce"),
                        "visitors": df[visitor_col].apply(to_float) if visitor_col else 0.0,
                        "sessions": df[session_col].apply(to_float),
                        "source_file": path.name,
                    }).dropna(subset=["date"])
                    rows.append(tmp)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "visitors", "sessions", "source_file"])


# =========================================================
# CREATIVE / ADS LOADER
# =========================================================
def normalize_creative_report(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    campaign_col = find_col(df, ["Kampanya Adı", "Campaign name", "Campaign", "Kampanya"])
    ad_col = find_col(df, ["Reklam Adı", "Reklamlar", "Ad name", "Ad"])
    reach_col = find_col(df, ["Erişim", "Reach"])
    impressions_col = find_col(df, ["Gösterim", "Impressions"])
    result_col = find_col(df, ["Sonuçlar", "Results"])
    spend_col = find_col(df, ["Harcanan Tutar (TRY)", "Amount spent", "Amount spent (TRY)", "Spend", "Harcama"])
    purchase_col = find_col(df, ["Alışverişler", "Alisverisler", "Purchases", "Website purchases", "Satın almalar", "Satin almalar"])
    roas_col = find_col(df, ["Alışveriş Reklam Harcamasının Getirisi", "Alisveris Reklam Harcamasinin Getirisi", "Purchase ROAS", "Website purchase ROAS", "ROAS"])
    revenue_col = find_col(df, ["Website purchases conversion value", "Purchase conversion value", "Purchases conversion value", "Revenue", "Gelir", "Dönüşüm değeri", "Donusum degeri"])
    ctr_col = find_col(df, ["CTR", "CTR (Tümü)", "CTR (Tumu)"])
    cpc_col = find_col(df, ["CPC"])
    cpm_col = find_col(df, ["CPM"])
    frequency_col = find_col(df, ["Sıklık", "Siklik", "Frequency"])
    start_col = find_col(df, ["Rapor Başlangıcı", "Rapor Baslangici", "Reporting starts", "Reporting start"])
    end_col = find_col(df, ["Rapor Sonu", "Reporting ends", "Reporting end"])

    if not spend_col:
        return pd.DataFrame()

    spend = df[spend_col].apply(to_float)
    purchases = df[purchase_col].apply(to_float) if purchase_col else pd.Series([0.0] * len(df))
    roas = df[roas_col].apply(to_float) if roas_col else pd.Series([0.0] * len(df))

    if revenue_col:
        revenue = df[revenue_col].apply(to_float)
    else:
        revenue = spend * roas

    out = pd.DataFrame({
        "campaign_name": df[campaign_col].astype(str) if campaign_col else source_file,
        "creative_name": df[ad_col].astype(str) if ad_col else "Unknown Creative",
        "date": pd.to_datetime(df[end_col], errors="coerce") if end_col else (pd.to_datetime(df[start_col], errors="coerce") if start_col else pd.NaT),
        "spend": spend,
        "ad_revenue": revenue,
        "purchases": purchases,
        "roas": roas,
        "reach": df[reach_col].apply(to_float) if reach_col else 0.0,
        "impressions": df[impressions_col].apply(to_float) if impressions_col else 0.0,
        "results": df[result_col].apply(to_float) if result_col else 0.0,
        "ctr": df[ctr_col].apply(to_float) if ctr_col else 0.0,
        "cpc": df[cpc_col].apply(to_float) if cpc_col else 0.0,
        "cpm": df[cpm_col].apply(to_float) if cpm_col else 0.0,
        "frequency": df[frequency_col].apply(to_float) if frequency_col else 0.0,
        "source_file": source_file,
    })

    out = out[~((out["campaign_name"].fillna("").astype(str).str.strip() == "") & (out["creative_name"].fillna("").astype(str).str.strip() == ""))]
    out = out[(out["spend"] > 0) | (out["ad_revenue"] > 0) | (out["purchases"] > 0)].copy()
    return out.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_creative_ads() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    debug = []

    if not KREATIF_DIR.exists():
        return pd.DataFrame(), pd.DataFrame([{
            "file": "",
            "status": "ERROR",
            "rows": 0,
            "notes": f"Kreatif_Takip klasörü bulunamadı: {KREATIF_DIR}",
        }])

    skip_names = {"creative_history.csv", "creative_summary.csv", "creative_scorecard.csv"}

    for path in sorted(KREATIF_DIR.glob("*.csv")):
        if path.name.lower() in skip_names:
            continue

        df, enc, sep = read_csv_flexible(path)
        if df.empty:
            debug.append({"file": path.name, "status": "ERROR", "rows": 0, "notes": "CSV okunamadı"})
            continue

        norm = normalize_creative_report(df, path.name)
        if norm.empty:
            debug.append({"file": path.name, "status": "WARNING", "rows": len(df), "notes": "Kreatif reklam verisi olarak tanınmadı veya spend kolonu yok"})
            continue

        debug.append({"file": path.name, "status": "OK", "rows": len(norm), "notes": f"Encoding={enc}, sep={sep}"})
        rows.append(norm)

    ads = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=[
        "campaign_name", "creative_name", "date", "spend", "ad_revenue", "purchases",
        "roas", "reach", "impressions", "results", "ctr", "cpc", "cpm", "frequency", "source_file"
    ])

    debug_df = pd.DataFrame(debug)
    return ads, debug_df


# =========================================================
# BUILD MODEL
# =========================================================
@st.cache_data(show_spinner=False)
def build_model():
    scan = scan_files()
    costs = load_costs(scan)
    orders, lines, order_debug = load_orders(scan)
    sessions = load_sessions(scan)
    creative_ads, creative_debug = load_creative_ads()

    if not lines.empty:
        lines = lines.merge(costs, on="sku_key", how="left")
        for col in ["unit_cost", "unit_shipping", "commission_rate"]:
            lines[col] = lines[col].fillna(0.0)
        lines["matched_cost"] = lines["unit_cost"].gt(0)
        lines["gross_profit_before_ads"] = (
            lines["line_revenue"]
            - (lines["unit_cost"] + lines["unit_shipping"]) * lines["qty"]
            - lines["line_revenue"] * lines["commission_rate"]
        )
    else:
        lines["matched_cost"] = []
        lines["gross_profit_before_ads"] = []

    if not orders.empty and not lines.empty:
        profit = lines.groupby("order_name", as_index=False).agg(
            gross_profit_before_ads=("gross_profit_before_ads", "sum"),
            units=("qty", "sum"),
        )
        orders = orders.merge(profit, on="order_name", how="left")
        orders["gross_profit_before_ads"] = orders["gross_profit_before_ads"].fillna(0.0)
        orders["units"] = orders["units"].fillna(0.0)

    issues = []
    if orders.empty:
        issues.append("Sipariş dosyası okunamadı. Orders export içinde Name, Created at, Lineitem name kolonları olmalı.")
    if costs.empty:
        issues.append("Maliyet tablosu okunamadı veya SKU kolonu bulunamadı.")
    if sessions.empty:
        issues.append("Oturum dosyası okunamadı. Day, Online store visitors, Sessions kolonları bekleniyor.")
    if creative_ads.empty:
        issues.append("Kreatif_Takip klasöründen reklam harcaması okunamadı. Kreatif raporunda Harcanan Tutar / ROAS / Alışveriş kolonları bekleniyor.")

    return {
        "scan": scan,
        "costs": costs,
        "orders": orders,
        "lines": lines,
        "sessions": sessions,
        "creative_ads": creative_ads,
        "order_debug": order_debug,
        "creative_debug": creative_debug,
        "issues": issues,
    }


model = build_model()
scan = model["scan"]
costs = model["costs"]
orders = model["orders"]
lines = model["lines"]
sessions = model["sessions"]
creative_ads = model["creative_ads"]
order_debug = model["order_debug"]
creative_debug = model["creative_debug"]
issues = model["issues"]


# =========================================================
# FILTERS
# =========================================================
date_sources = []
if not orders.empty:
    date_sources.append(pd.to_datetime(orders["order_date"], errors="coerce").dropna())
if not creative_ads.empty:
    date_sources.append(pd.to_datetime(creative_ads["date"], errors="coerce").dropna())
if not sessions.empty:
    date_sources.append(pd.to_datetime(sessions["date"], errors="coerce").dropna())

if date_sources and any(len(s) for s in date_sources):
    all_dates = pd.concat([s for s in date_sources if len(s)], ignore_index=True)
    min_date = all_dates.min().date()
    max_date = all_dates.max().date()
else:
    min_date = max_date = pd.Timestamp.today().date()

with st.sidebar:
    st.header("Filters")
    all_time = st.toggle("All Time", value=True)
    start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, disabled=all_time)
    end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, disabled=all_time)
    manual_inventory_units = st.number_input("Manual Total Inventory Units", min_value=0, value=0, step=1)
    low_stock_items_manual = st.number_input("Manual Low Stock Items", min_value=0, value=0, step=1)
    show_diagnostic = st.checkbox("Show file diagnostic", value=True)


def date_filter(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or all_time or col not in df.columns:
        return df.copy()
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d = pd.to_datetime(df[col], errors="coerce")
    return df[(d >= s) & (d <= e)].copy()


orders_f = date_filter(orders, "order_date")
lines_f = date_filter(lines, "order_date")
sessions_f = date_filter(sessions, "date")
creative_ads_f = date_filter(creative_ads, "date")


# =========================================================
# METRICS
# =========================================================
total_revenue = float(orders_f["net_sales"].sum()) if not orders_f.empty else 0.0
order_count = int(orders_f["order_count"].sum()) if not orders_f.empty and "order_count" in orders_f.columns else 0
units_sold = float(lines_f["qty"].sum()) if not lines_f.empty else 0.0
aov = safe_divide(total_revenue, order_count)

total_ad_spend = float(creative_ads_f["spend"].sum()) if not creative_ads_f.empty else 0.0
total_ad_revenue = float(creative_ads_f["ad_revenue"].sum()) if not creative_ads_f.empty else 0.0
ad_purchases = float(creative_ads_f["purchases"].sum()) if not creative_ads_f.empty else 0.0
roas = safe_divide(total_ad_revenue, total_ad_spend)

gross_profit_before_ads = float(lines_f["gross_profit_before_ads"].sum()) if not lines_f.empty else 0.0
net_profit_after_ads = gross_profit_before_ads - total_ad_spend
mer = safe_divide(total_revenue, total_ad_spend)

tracked_inventory_items = int(costs["sku_key"].nunique()) if not costs.empty else 0
total_inventory_units = manual_inventory_units
low_stock_items = low_stock_items_manual
cost_match_rate = float(lines_f["matched_cost"].mean()) if not lines_f.empty and "matched_cost" in lines_f.columns else 0.0

total_sessions = float(sessions_f["sessions"].sum()) if not sessions_f.empty else 0.0
total_visitors = float(sessions_f["visitors"].sum()) if not sessions_f.empty else 0.0
conversion_rate = safe_divide(order_count, total_sessions) * 100


# =========================================================
# MAIN REPORT
# =========================================================
if show_diagnostic:
    with st.expander("📁 File diagnostic / dosya tanıma", expanded=False):
        st.write(f"Shopify klasörü: `{DATA_DIR}`")
        st.write(f"Kreatif reklam klasörü: `{KREATIF_DIR}`")
        st.markdown("### Shopify dosyaları")
        st.dataframe(scan, use_container_width=True, hide_index=True)
        st.markdown("### Kreatif reklam dosyaları")
        st.dataframe(creative_debug, use_container_width=True, hide_index=True)
        if issues:
            st.markdown("#### Uyarılar")
            for issue in issues:
                st.info(issue)

st.subheader("Main Report")

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("Total Revenue", money(total_revenue))
r1c2.metric("Order Count", f"{order_count:,}")
r1c3.metric("Units Sold", f"{units_sold:,.0f}")
r1c4.metric("AOV", money(aov))

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("Total Ad Revenue", money(total_ad_revenue))
r2c2.metric("ROAS", f"{roas:.2f}" if roas else "N/A")
r2c3.metric("Gross Profit Before Ads", money(gross_profit_before_ads))
r2c4.metric("Total Ad Spend", money(total_ad_spend))

r3c1, r3c2, r3c3, r3c4 = st.columns(4)
r3c1.metric("Net Profit After Ads", money(net_profit_after_ads))
r3c2.metric("MER", f"{mer:.2f}" if mer else "N/A")
r3c3.metric("Total Inventory Units", f"{total_inventory_units:,.0f}")
r3c4.metric("Tracked Inventory Items", f"{tracked_inventory_items:,}")

r4c1, r4c2, r4c3, r4c4 = st.columns(4)
r4c1.metric("Low Stock Items", f"{low_stock_items:,}")
r4c2.metric("Ad Purchases", f"{ad_purchases:,.0f}")
r4c3.metric("Sessions", f"{total_sessions:,.0f}")
r4c4.metric("Conversion Rate", f"{conversion_rate:.2f}%")

st.info("Bu Shopify sürümünde Meta/fatura dosyası kullanılmaz. Total Ad Spend ve Total Ad Revenue, Kreatif_Takip klasöründeki kreatif raporlarından alınır.")


# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📁 File Diagnostic",
    "📊 Sales",
    "📦 Products & Cost",
    "🎨 Creative Ads",
    "🧭 Sessions",
    "🧪 Data Quality",
])

with tab1:
    st.subheader("File Diagnostic")
    st.write("Shopify klasöründeki dosyalar:")
    st.dataframe(scan, use_container_width=True, hide_index=True)
    st.write("Kreatif_Takip klasöründeki reklam raporları:")
    st.dataframe(creative_debug, use_container_width=True, hide_index=True)
    st.subheader("Order parser debug")
    st.dataframe(order_debug, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Sales")
    if orders_f.empty:
        st.warning("Sipariş verisi yok.")
    else:
        daily = orders_f.groupby(orders_f["order_date"].dt.normalize(), as_index=False).agg(
            revenue=("net_sales", "sum"),
            orders=("order_count", "sum"),
            gross_profit_before_ads=("gross_profit_before_ads", "sum"),
            units=("units", "sum"),
        ).rename(columns={"order_date": "date"})
        fig = px.line(daily, x="date", y=["revenue", "gross_profit_before_ads"], markers=True, title="Daily Revenue & Gross Profit")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(daily.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Products & Cost")
    if lines_f.empty:
        st.warning("Ürün satır verisi yok.")
    else:
        product = lines_f.groupby(["product_name", "sku_key"], as_index=False).agg(
            units_sold=("qty", "sum"),
            revenue=("line_revenue", "sum"),
            gross_profit_before_ads=("gross_profit_before_ads", "sum"),
            matched_cost=("matched_cost", "max"),
            source_file=("source_file", "last"),
        ).sort_values(["units_sold", "revenue"], ascending=False)
        st.dataframe(
            product.style.format({
                "units_sold": "{:,.0f}",
                "revenue": "{:,.2f} TL",
                "gross_profit_before_ads": "{:,.2f} TL",
            }),
            use_container_width=True,
            hide_index=True,
        )

        unmatched = product[~product["matched_cost"]]
        if not unmatched.empty:
            st.warning("Bazı ürünlerin SKU'su maliyet tablosuyla eşleşmedi.")
            st.dataframe(unmatched, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Creative Ads / Reklam Harcaması")
    if creative_ads_f.empty:
        st.warning("Kreatif reklam verisi yok. Kreatif_Takip klasörüne günlük kreatif CSV raporu yükle.")
    else:
        daily_ads = creative_ads_f.groupby(creative_ads_f["date"].dt.normalize(), as_index=False).agg(
            spend=("spend", "sum"),
            ad_revenue=("ad_revenue", "sum"),
            purchases=("purchases", "sum"),
            reach=("reach", "sum"),
            impressions=("impressions", "sum"),
        ).rename(columns={"date": "date"})
        daily_ads["roas"] = daily_ads.apply(lambda r: safe_divide(r["ad_revenue"], r["spend"]), axis=1)

        fig = px.line(daily_ads, x="date", y=["spend", "ad_revenue"], markers=True, title="Daily Creative Spend & Ad Revenue")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(daily_ads.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

        st.subheader("Campaign / Creative Summary")
        creative_summary = creative_ads_f.groupby(["campaign_name", "creative_name"], as_index=False).agg(
            spend=("spend", "sum"),
            ad_revenue=("ad_revenue", "sum"),
            purchases=("purchases", "sum"),
            reach=("reach", "sum"),
            impressions=("impressions", "sum"),
            ctr=("ctr", "mean"),
            cpc=("cpc", "mean"),
            cpm=("cpm", "mean"),
            frequency=("frequency", "mean"),
        )
        creative_summary["roas"] = creative_summary.apply(lambda r: safe_divide(r["ad_revenue"], r["spend"]), axis=1)
        st.dataframe(
            creative_summary.sort_values("spend", ascending=False).style.format({
                "spend": "{:,.2f} TL",
                "ad_revenue": "{:,.2f} TL",
                "purchases": "{:,.0f}",
                "reach": "{:,.0f}",
                "impressions": "{:,.0f}",
                "ctr": "{:.2f}",
                "cpc": "{:,.2f}",
                "cpm": "{:,.2f}",
                "frequency": "{:.2f}",
                "roas": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

with tab5:
    st.subheader("Sessions")
    if sessions_f.empty:
        st.warning("Oturum verisi yok.")
    else:
        daily_sessions = sessions_f.groupby("date", as_index=False).agg(
            visitors=("visitors", "sum"),
            sessions=("sessions", "sum"),
        )
        fig = px.line(daily_sessions, x="date", y=["visitors", "sessions"], markers=True, title="Visitors & Sessions")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(daily_sessions.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Data Quality")
    quality = pd.DataFrame([
        {"Check": "Shopify CSV files found", "Value": len(scan)},
        {"Check": "Order rows", "Value": len(orders)},
        {"Check": "Line rows", "Value": len(lines)},
        {"Check": "Cost rows", "Value": len(costs)},
        {"Check": "Creative ad rows", "Value": len(creative_ads)},
        {"Check": "Sessions rows", "Value": len(sessions)},
        {"Check": "Cost match rate", "Value": f"{cost_match_rate:.1%}"},
    ])
    st.dataframe(quality, use_container_width=True, hide_index=True)

    if issues:
        st.subheader("Issues")
        for issue in issues:
            st.info(issue)
    else:
        st.success("Kritik dosya okuma sorunu yok.")
