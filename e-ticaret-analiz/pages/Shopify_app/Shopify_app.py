
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
st.set_page_config(page_title="SMARTEK360 Shopify Diagnostic Dashboard", layout="wide")

if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🟣 SMARTEK360: Shopify Diagnostic Dashboard")
st.caption(
    "Bu sürüm dosyaları sadece raporlamaz; önce klasördeki tüm dosyaları tanır, hata/eksik kolonları gösterir, sonra doğru okunan verilerden KPI üretir."
)

DATA_DIR = Path(__file__).resolve().parent


# =========================================================
# HELPERS
# =========================================================
def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower().strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    })
    text = text.translate(tr_map)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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

    if s.lower() in {"-", "nan", "none", "null", "sürekli", "surekli", "henüzfaturakesilmemiştir."}:
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
    normalized = {normalize_text(c): c for c in df.columns}

    for candidate in candidates:
        target = normalize_text(candidate)
        for norm_col, raw_col in normalized.items():
            if target == norm_col:
                return raw_col

    for candidate in candidates:
        target = normalize_text(candidate)
        for norm_col, raw_col in normalized.items():
            if target and target in norm_col:
                return raw_col

    return None


def safe_divide(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def read_csv_flexible(path: Path, skiprows: int = 0) -> tuple[pd.DataFrame, str, str]:
    """
    Return: df, encoding, separator
    """
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]
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


def read_shopify_order_csv_robust(path: Path) -> tuple[pd.DataFrame, str]:
    """
    Shopify CSV bazen normal gelir, bazen tek hücreye gömülmüş satırlar olur.
    Bu okuyucu iki durumu da toparlar.
    """
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace", newline="") as f:
                rows = list(csv.reader(f))

            if not rows:
                continue

            header = rows[0]
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

                if len(row) == header_len and row and str(row[0]).count(",") > 10 and all(str(x).strip() == "" for x in row[1:]):
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
                return df, enc

        except Exception:
            continue

    return pd.DataFrame(), ""


def money(value: float) -> str:
    return f"{value:,.2f} TL"


# =========================================================
# FILE DIAGNOSTIC
# =========================================================
ORDER_REQUIRED = ["Name", "Created at", "Lineitem name"]
ORDER_RECOMMENDED = ["Lineitem quantity", "Lineitem price", "Total", "Financial Status"]

COST_REQUIRED = ["SKU"]
COST_RECOMMENDED = ["Maliyet", "Komisyon", "Kargo"]

FUNNEL_HINTS = ["Oturumlar", "Sepete ekleme", "Ödeme sayfası", "Dönüşüm oranı"]
GEO_HINTS = ["Oturum ülkesi", "Oturum bölgesi", "Oturum şehri", "Online mağaza ziyaretçileri"]
GROSS_HINTS = ["Brüt satışlar", "Ay"]
META_HINTS = ["Amount spent", "Harcanan Tutar", "Campaign", "Kampanya", "Purchase ROAS", "Purchases"]
BILLING_HINTS = ["Fatura", "Billing", "Amount", "Tutar", "Payment"]


def detect_file_type(path: Path) -> dict:
    name_norm = normalize_text(path.name)

    # 1. Önce robust Shopify order dene
    order_df, order_enc = read_shopify_order_csv_robust(path)
    order_cols = set(order_df.columns) if not order_df.empty else set()
    order_missing = [c for c in ORDER_REQUIRED if c not in order_cols]

    if not order_df.empty and not order_missing:
        return {
            "file": path.name,
            "detected_type": "orders",
            "status": "OK",
            "rows": len(order_df),
            "cols": len(order_df.columns),
            "encoding": order_enc,
            "separator": "robust-csv",
            "required_found": ", ".join(ORDER_REQUIRED),
            "missing_required": "",
            "notes": "Shopify sipariş dosyası olarak tanındı.",
        }

    df, enc, sep = read_csv_flexible(path)
    if df.empty:
        return {
            "file": path.name,
            "detected_type": "unreadable",
            "status": "ERROR",
            "rows": 0,
            "cols": 0,
            "encoding": "",
            "separator": "",
            "required_found": "",
            "missing_required": "",
            "notes": "CSV okunamadı veya tek kolon olarak kaldı.",
        }

    cols_norm = " ".join([normalize_text(c) for c in df.columns])

    def has_any(words: list[str]) -> bool:
        return any(normalize_text(w) in cols_norm for w in words)

    if "maliyet" in name_norm or (find_col(df, COST_REQUIRED) and has_any(COST_RECOMMENDED)):
        missing = []
        if not find_col(df, COST_REQUIRED):
            missing.append("SKU")
        return {
            "file": path.name,
            "detected_type": "costs",
            "status": "OK" if not missing else "WARNING",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "SKU" if not missing else "",
            "missing_required": ", ".join(missing),
            "notes": "Maliyet tablosu olarak tanındı.",
        }

    if "shopify002" in name_norm or has_any(FUNNEL_HINTS):
        return {
            "file": path.name,
            "detected_type": "funnel",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "funnel kolonları",
            "missing_required": "",
            "notes": "Funnel/oturum dosyası olarak tanındı.",
        }

    if "shopify003" in name_norm or has_any(GEO_HINTS):
        return {
            "file": path.name,
            "detected_type": "geo",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "geo kolonları",
            "missing_required": "",
            "notes": "Şehir/bölge trafik dosyası olarak tanındı.",
        }

    if "shopify004" in name_norm or has_any(GROSS_HINTS):
        return {
            "file": path.name,
            "detected_type": "gross_monthly",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "brüt satış kolonları",
            "missing_required": "",
            "notes": "Aylık brüt satış dosyası olarak tanındı.",
        }

    if "billing" in name_norm or "fatura" in name_norm:
        return {
            "file": path.name,
            "detected_type": "billing",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "billing/fatura",
            "missing_required": "",
            "notes": "Meta fatura/billing dosyası olarak tanındı.",
        }

    if "meta" in name_norm or "campaign" in name_norm or has_any(META_HINTS):
        return {
            "file": path.name,
            "detected_type": "meta_campaign",
            "status": "OK",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
            "required_found": "meta/kampanya kolonları",
            "missing_required": "",
            "notes": "Meta campaign/performance dosyası olarak tanındı.",
        }

    return {
        "file": path.name,
        "detected_type": "other",
        "status": "WARNING",
        "rows": len(df),
        "cols": len(df.columns),
        "encoding": enc,
        "separator": sep,
        "required_found": "",
        "missing_required": "",
        "notes": "Tanımlı dosya türlerinden biri olarak algılanmadı.",
    }


@st.cache_data(show_spinner=False)
def scan_files() -> pd.DataFrame:
    rows = []
    for path in sorted(DATA_DIR.glob("*.csv")):
        rows.append(detect_file_type(path))

    if not rows:
        return pd.DataFrame(columns=[
            "file", "detected_type", "status", "rows", "cols", "encoding", "separator",
            "required_found", "missing_required", "notes"
        ])
    return pd.DataFrame(rows)


def files_by_type(scan: pd.DataFrame, file_type: str) -> list[Path]:
    if scan.empty:
        return []
    names = scan.loc[scan["detected_type"].eq(file_type) & scan["status"].isin(["OK", "WARNING"]), "file"].tolist()
    return [DATA_DIR / name for name in names]


# =========================================================
# LOADERS
# =========================================================
@st.cache_data(show_spinner=False)
def load_costs(scan: pd.DataFrame) -> pd.DataFrame:
    files = files_by_type(scan, "costs")
    if not files:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_ship", "vat_rate"])

    df, _, _ = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_ship", "vat_rate"])

    sku_col = find_col(df, ["SKU"])
    cost_col = find_col(df, ["Maliyet", "Cost"])
    comm_col = find_col(df, ["Komisyon oran", "Komisyon", "Commission"])
    ship_col = find_col(df, ["Kargo", "Shipping"])
    vat_col = find_col(df, ["KDV", "VAT"])

    if not sku_col:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_ship", "vat_rate"])

    out = pd.DataFrame({
        "sku_key": df[sku_col].apply(clean_sku),
        "unit_cost": df[cost_col].apply(to_float) if cost_col else 0.0,
        "commission_rate": df[comm_col].apply(to_float) if comm_col else 0.0,
        "unit_ship": df[ship_col].apply(to_float) if ship_col else 0.0,
        "vat_rate": df[vat_col].apply(to_float) if vat_col else 0.0,
    })
    out["commission_rate"] = out["commission_rate"].apply(lambda x: x / 100 if x > 1 else x)
    out = out[out["sku_key"] != ""].drop_duplicates("sku_key", keep="last")
    return out


@st.cache_data(show_spinner=False)
def load_orders_and_lines(scan: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    files = files_by_type(scan, "orders")
    debug_rows = []
    frames = []

    for path in files:
        df, enc = read_shopify_order_csv_robust(path)
        debug_rows.append({
            "file": path.name,
            "encoding": enc,
            "rows_loaded": len(df),
            "columns_loaded": len(df.columns),
            "has_required_columns": set(ORDER_REQUIRED).issubset(set(df.columns)) if not df.empty else False,
        })
        if df.empty or not set(ORDER_REQUIRED).issubset(set(df.columns)):
            continue
        df["source_file"] = path.name
        frames.append(df)

    debug_df = pd.DataFrame(debug_rows)

    if not frames:
        return pd.DataFrame(), pd.DataFrame(), debug_df

    raw = pd.concat(frames, ignore_index=True)

    needed_numeric = [
        "Total", "Subtotal", "Shipping", "Taxes", "Discount Amount",
        "Refunded Amount", "Lineitem quantity", "Lineitem price", "Lineitem discount"
    ]
    for col in needed_numeric:
        if col not in raw.columns:
            raw[col] = 0.0
        raw[col] = raw[col].apply(to_float)

    if "Paid at" not in raw.columns:
        raw["Paid at"] = ""
    if "Cancelled at" not in raw.columns:
        raw["Cancelled at"] = ""
    if "Financial Status" not in raw.columns:
        raw["Financial Status"] = ""
    if "Fulfillment Status" not in raw.columns:
        raw["Fulfillment Status"] = ""
    if "Currency" not in raw.columns:
        raw["Currency"] = ""
    if "Payment Method" not in raw.columns:
        raw["Payment Method"] = ""
    if "Billing City" not in raw.columns:
        raw["Billing City"] = ""
    if "Source" not in raw.columns:
        raw["Source"] = ""
    if "Lineitem sku" not in raw.columns:
        raw["Lineitem sku"] = ""

    raw["order_date"] = pd.to_datetime(raw["Created at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["paid_at"] = pd.to_datetime(raw["Paid at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["cancelled_at"] = pd.to_datetime(raw["Cancelled at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["order_name"] = raw["Name"].fillna("").astype(str)
    raw["financial_status"] = raw["Financial Status"].fillna("").astype(str).str.lower()
    raw["fulfillment_status"] = raw["Fulfillment Status"].fillna("").astype(str).str.lower()

    raw = raw[raw["order_name"].str.strip() != ""].copy()

    dedupe_cols = [c for c in [
        "Name", "Created at", "Lineitem name", "Lineitem sku",
        "Lineitem quantity", "Lineitem price", "Financial Status",
        "Fulfillment Status", "Total", "Discount Amount"
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
    orders["net_sales"] = orders["Total"].fillna(0.0) - orders["Refunded Amount"].fillna(0.0)
    orders.loc[orders["is_cancelled"], "net_sales"] = 0.0
    orders["order_count"] = (~orders["is_cancelled"]).astype(int)

    lines = raw.copy()
    lines["product_name"] = lines["Lineitem name"].fillna("").astype(str)
    lines["sku_key"] = lines["Lineitem sku"].apply(clean_sku)
    lines["qty"] = lines["Lineitem quantity"].apply(to_float)
    lines["line_price"] = lines["Lineitem price"].apply(to_float)
    lines["line_discount"] = lines["Lineitem discount"].apply(to_float)
    lines["line_revenue"] = lines["line_price"] * lines["qty"] - lines["line_discount"]
    lines["is_cancelled"] = lines["cancelled_at"].notna() | lines["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    lines.loc[lines["is_cancelled"], ["qty", "line_revenue"]] = 0.0

    lines = lines[[
        "order_name", "order_date", "financial_status", "fulfillment_status",
        "sku_key", "product_name", "qty", "line_revenue", "is_cancelled", "source_file"
    ]].copy()

    return orders, lines, debug_df


@st.cache_data(show_spinner=False)
def load_funnel(scan: pd.DataFrame) -> pd.DataFrame:
    files = files_by_type(scan, "funnel")
    if not files:
        return pd.DataFrame()

    df, _, _ = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame()

    month_col = find_col(df, ["Ay", "Month", "Tarih"])
    sessions_col = find_col(df, ["Oturumlar", "Sessions"])
    cart_col = find_col(df, ["Sepete ekleme", "Added to cart"])
    checkout_col = find_col(df, ["Ödeme sayfasına", "Checkout"])
    completed_col = find_col(df, ["Ödemeyi tamamlayan", "Completed checkout"])
    conv_col = find_col(df, ["Dönüşüm oranı", "Conversion rate"])

    if not month_col:
        return pd.DataFrame()

    out = pd.DataFrame({
        "month": pd.to_datetime(df[month_col], errors="coerce"),
        "sessions": df[sessions_col].apply(to_float) if sessions_col else 0.0,
        "sessions_added_to_cart": df[cart_col].apply(to_float) if cart_col else 0.0,
        "sessions_reached_checkout": df[checkout_col].apply(to_float) if checkout_col else 0.0,
        "sessions_completed_checkout": df[completed_col].apply(to_float) if completed_col else 0.0,
        "conversion_rate": df[conv_col].apply(to_float) if conv_col else 0.0,
    })

    return out.dropna(subset=["month"])


@st.cache_data(show_spinner=False)
def load_geo(scan: pd.DataFrame) -> pd.DataFrame:
    files = files_by_type(scan, "geo")
    if not files:
        return pd.DataFrame()

    df, _, _ = read_csv_flexible(files[0])
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
def load_gross_monthly(scan: pd.DataFrame) -> pd.DataFrame:
    files = files_by_type(scan, "gross_monthly")
    if not files:
        return pd.DataFrame()

    df, _, _ = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame()

    month_col = find_col(df, ["Ay", "Month", "Tarih"])
    gross_col = find_col(df, ["Brüt satışlar", "Brut satislar", "Gross sales"])

    if not month_col or not gross_col:
        return pd.DataFrame()

    out = pd.DataFrame({
        "month": pd.to_datetime(df[month_col], errors="coerce"),
        "gross_sales": df[gross_col].apply(to_float),
    })
    return out.dropna(subset=["month"])


@st.cache_data(show_spinner=False)
def load_meta(scan: pd.DataFrame) -> pd.DataFrame:
    billing_files = files_by_type(scan, "billing")
    campaign_files = files_by_type(scan, "meta_campaign")

    billing_rows = []
    campaign_rows = []

    # Billing: gerçek harcama kaynağı
    for path in billing_files:
        df, _, _ = read_csv_flexible(path)
        if df.empty:
            continue

        date_col = find_col(df, ["Date", "Day", "Tarih", "Fatura Tarihi", "Billing date", "Transaction date"])
        spend_col = find_col(df, ["Amount", "Tutar", "Harcanan Tutar", "Spend", "Harcama", "Total", "Toplam", "Paid", "Payment"])
        desc_col = find_col(df, ["Description", "Açıklama", "Aciklama", "Campaign", "Kampanya", "Type"])

        if not spend_col:
            # Son çare: toplamı pozitif en büyük sayısal kolonu seç
            numeric_candidates = []
            for col in df.columns:
                total = df[col].apply(to_float).sum()
                if total > 0:
                    numeric_candidates.append((total, col))
            if numeric_candidates:
                spend_col = sorted(numeric_candidates, reverse=True)[0][1]

        if not spend_col:
            continue

        tmp = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
            "campaign_name": df[desc_col].astype(str) if desc_col else "Meta Billing",
            "spend": df[spend_col].apply(to_float),
            "attributed_revenue": 0.0,
            "purchases": 0.0,
            "source_file": path.name,
            "source_type": "billing",
            "campaign_spend_original": 0.0,
        })
        tmp = tmp[tmp["spend"] > 0].copy()
        billing_rows.append(tmp)

    billing_df = pd.concat(billing_rows, ignore_index=True) if billing_rows else pd.DataFrame()

    # Campaign: revenue/purchase/ROAS kaynağı
    for path in campaign_files:
        df, _, _ = read_csv_flexible(path)
        if df.empty:
            continue

        date_col = find_col(df, ["Date", "Day", "Tarih", "Reporting starts", "Rapor Başlangıcı", "Rapor Baslangici"])
        campaign_col = find_col(df, ["Campaign name", "Campaign", "Kampanya Adı", "Kampanya Adi", "Kampanya"])
        spend_col = find_col(df, ["Amount spent", "Harcanan Tutar", "Spend", "Harcama", "Tutar"])
        revenue_col = find_col(df, [
            "Website purchases conversion value", "Purchase conversion value", "Purchases conversion value",
            "Revenue", "Gelir", "Dönüşüm değeri", "Donusum degeri", "Alışveriş dönüşüm değeri"
        ])
        purchase_col = find_col(df, ["Purchases", "Website purchases", "Satın almalar", "Satin almalar", "Alışverişler", "Results"])
        roas_col = find_col(df, ["Purchase ROAS", "Website purchase ROAS", "ROAS", "Alışveriş Reklam Harcamasının Getirisi"])

        if not spend_col:
            continue

        spend_series = df[spend_col].apply(to_float)
        purchase_series = df[purchase_col].apply(to_float) if purchase_col else pd.Series([0.0] * len(df))

        if revenue_col:
            revenue_series = df[revenue_col].apply(to_float)
        elif roas_col:
            revenue_series = spend_series * df[roas_col].apply(to_float)
        else:
            revenue_series = pd.Series([0.0] * len(df))

        tmp = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
            "campaign_name": df[campaign_col].astype(str) if campaign_col else path.stem,
            "campaign_spend_original": spend_series,
            "attributed_revenue": revenue_series,
            "purchases": purchase_series,
            "source_file": path.name,
            "source_type": "campaign",
        })
        campaign_rows.append(tmp)

    campaign_df = pd.concat(campaign_rows, ignore_index=True) if campaign_rows else pd.DataFrame()

    # Double count önleme:
    if not billing_df.empty:
        if not campaign_df.empty:
            campaign_df["spend"] = 0.0
            campaign_df = campaign_df[[
                "date", "campaign_name", "spend", "attributed_revenue", "purchases",
                "source_file", "source_type", "campaign_spend_original"
            ]]
        final = pd.concat([billing_df, campaign_df], ignore_index=True) if not campaign_df.empty else billing_df.copy()
    else:
        if not campaign_df.empty:
            campaign_df["spend"] = campaign_df["campaign_spend_original"]
            final = campaign_df[[
                "date", "campaign_name", "spend", "attributed_revenue", "purchases",
                "source_file", "source_type", "campaign_spend_original"
            ]].copy()
        else:
            final = pd.DataFrame(columns=[
                "date", "campaign_name", "spend", "attributed_revenue", "purchases",
                "source_file", "source_type", "campaign_spend_original"
            ])

    if final.empty:
        return final

    for col in ["spend", "attributed_revenue", "purchases", "campaign_spend_original"]:
        final[col] = final[col].fillna(0.0)

    final["date"] = pd.to_datetime(final["date"], errors="coerce")
    return final


# =========================================================
# BUILD MODEL
# =========================================================
@st.cache_data(show_spinner=False)
def build_model():
    scan = scan_files()
    costs = load_costs(scan)
    orders, lines, order_debug = load_orders_and_lines(scan)
    funnel = load_funnel(scan)
    geo = load_geo(scan)
    gross_monthly = load_gross_monthly(scan)
    meta = load_meta(scan)

    issues = []

    if scan.empty:
        issues.append("Shopify_app klasöründe hiç CSV dosyası bulunamadı.")
    if orders.empty:
        issues.append("Sipariş dosyası okunamadı. Sipariş dosyasında Name, Created at ve Lineitem name kolonları olmalı.")
    if costs.empty:
        issues.append("Maliyet tablosu okunamadı. Maliyet dosyasında SKU kolonu olmalı.")
    if funnel.empty:
        issues.append("Funnel dosyası okunamadı. shopify002.csv veya oturum kolonları bekleniyor.")
    if geo.empty:
        issues.append("Geo dosyası okunamadı. shopify003.csv veya şehir/bölge kolonları bekleniyor.")
    if gross_monthly.empty:
        issues.append("Brüt satış dosyası okunamadı. shopify004.csv veya Brüt satışlar kolonu bekleniyor.")
    if meta.empty:
        issues.append("Meta/fatura dosyası okunamadı. Harcama kolonu bulunmalı.")

    if not lines.empty:
        lines = lines.merge(costs, on="sku_key", how="left")
        for col in ["unit_cost", "unit_ship", "commission_rate"]:
            lines[col] = lines[col].fillna(0.0)
        lines["matched_cost"] = lines["unit_cost"].gt(0)
        lines["estimated_cost_total"] = (lines["unit_cost"] + lines["unit_ship"]) * lines["qty"]
        lines["estimated_commission_total"] = lines["line_revenue"] * lines["commission_rate"]
        lines["gross_profit"] = lines["line_revenue"] - lines["estimated_cost_total"] - lines["estimated_commission_total"]
    else:
        lines["matched_cost"] = []
        lines["gross_profit"] = []

    if not orders.empty and not lines.empty:
        profit = lines.groupby("order_name", as_index=False).agg(gross_profit_estimated=("gross_profit", "sum"))
        units = lines.groupby("order_name", as_index=False).agg(units=("qty", "sum"))
        orders = orders.merge(profit, on="order_name", how="left").merge(units, on="order_name", how="left")
        orders["gross_profit_estimated"] = orders["gross_profit_estimated"].fillna(0.0)
        orders["units"] = orders["units"].fillna(0.0)
    elif not orders.empty:
        orders["gross_profit_estimated"] = orders["net_sales"] * 0.45
        orders["units"] = 0.0

    return {
        "scan": scan,
        "costs": costs,
        "orders": orders,
        "lines": lines,
        "funnel": funnel,
        "geo": geo,
        "gross_monthly": gross_monthly,
        "meta": meta,
        "order_debug": order_debug,
        "issues": issues,
    }


model = build_model()
scan = model["scan"]
costs = model["costs"]
orders = model["orders"]
lines = model["lines"]
funnel = model["funnel"]
geo = model["geo"]
gross_monthly = model["gross_monthly"]
meta = model["meta"]
order_debug = model["order_debug"]
issues = model["issues"]


# =========================================================
# FILTERS
# =========================================================
date_series = []
if not orders.empty and "order_date" in orders.columns:
    date_series.append(pd.to_datetime(orders["order_date"], errors="coerce").dropna())
if not meta.empty and "date" in meta.columns:
    date_series.append(pd.to_datetime(meta["date"], errors="coerce").dropna())

if date_series and any(len(s) for s in date_series):
    all_dates = pd.concat([s for s in date_series if len(s)], ignore_index=True)
    min_date = all_dates.min().date()
    max_date = all_dates.max().date()
else:
    min_date = max_date = pd.Timestamp.today().date()

with st.sidebar:
    st.header("Filters")
    all_time = st.toggle("All Time", value=True)
    start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, disabled=all_time)
    end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, disabled=all_time)
    inventory_default = st.number_input("Manual total inventory units", min_value=0, value=0, step=1)
    low_stock_threshold = st.number_input("Low stock threshold", min_value=0, value=20, step=1)
    show_diagnostic_top = st.checkbox("Dosya tanıma tablosunu üstte göster", value=True)


def filter_by_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or all_time or col not in df.columns:
        return df.copy()
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    parsed = pd.to_datetime(df[col], errors="coerce")
    return df[(parsed >= s) & (parsed <= e)].copy()


orders_f = filter_by_date(orders, "order_date")
lines_f = filter_by_date(lines, "order_date")
meta_f = filter_by_date(meta, "date")


# =========================================================
# KPI MODEL
# =========================================================
total_revenue = float(orders_f["net_sales"].sum()) if not orders_f.empty else 0.0
order_count = int(orders_f["order_count"].sum()) if not orders_f.empty and "order_count" in orders_f.columns else 0
units_sold = float(lines_f["qty"].sum()) if not lines_f.empty else float(orders_f["units"].sum()) if not orders_f.empty and "units" in orders_f.columns else 0.0
aov = safe_divide(total_revenue, order_count)

gross_profit_before_ads = (
    float(orders_f["gross_profit_estimated"].sum())
    if not orders_f.empty and "gross_profit_estimated" in orders_f.columns
    else float(lines_f["gross_profit"].sum()) if not lines_f.empty and "gross_profit" in lines_f.columns
    else 0.0
)

total_ad_spend = float(meta_f["spend"].sum()) if not meta_f.empty else 0.0
total_ad_revenue = float(meta_f["attributed_revenue"].sum()) if not meta_f.empty else 0.0
ad_purchases = float(meta_f["purchases"].sum()) if not meta_f.empty else 0.0
roas = safe_divide(total_ad_revenue, total_ad_spend)
net_profit_after_ads = gross_profit_before_ads - total_ad_spend
mer = safe_divide(total_revenue, total_ad_spend)

tracked_inventory_items = int(costs["sku_key"].nunique()) if not costs.empty else 0
total_inventory_units = inventory_default
low_stock_items = 0  # Gerçek stok dosyası yoksa manuel stok girişi olmadan hesaplanamaz.

cost_match_rate = float(lines_f["matched_cost"].mean()) if not lines_f.empty and "matched_cost" in lines_f.columns else 0.0


# =========================================================
# UI - KPI CARDS
# =========================================================
if show_diagnostic_top:
    with st.expander("📁 Dosya Tanıma Sistemi", expanded=orders.empty):
        st.write(f"Okunan klasör: `{DATA_DIR}`")
        if scan.empty:
            st.warning("Bu klasörde CSV dosyası bulunamadı.")
        else:
            st.dataframe(scan, use_container_width=True, hide_index=True)

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
r4c3.metric("Cost Match Rate", f"{cost_match_rate:.1%}")
r4c4.metric("Report Period", "All Time" if all_time else f"{start_date} → {end_date}")


# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📁 File Diagnostic",
    "📊 Sales Performance",
    "📦 Product & Profit",
    "🧭 Traffic & Funnel",
    "📣 Meta / Marketing",
    "🧾 Orders",
    "🧪 Data Quality",
])

with tab1:
    st.subheader("Dosya Tanıma ve Hata Gösterme")
    st.write("Bu tablo, Shopify_app klasöründeki her CSV dosyasını hangi tür olarak algıladığını gösterir.")
    if scan.empty:
        st.warning("CSV dosyası yok.")
    else:
        st.dataframe(scan, use_container_width=True, hide_index=True)

    st.markdown("### Order Parser Debug")
    if order_debug.empty:
        st.info("Sipariş parser debug verisi yok.")
    else:
        st.dataframe(order_debug, use_container_width=True, hide_index=True)

    st.markdown("### Beklenen dosya türleri")
    expected = pd.DataFrame([
        {"Tür": "orders", "Gerekli kolonlar": "Name, Created at, Lineitem name", "Örnek": "orders_export_1.csv / Shopify11.05.csv"},
        {"Tür": "costs", "Gerekli kolonlar": "SKU, Maliyet, Komisyon, Kargo", "Örnek": "Shopify Maliyet Tablosu(Sayfa1).csv"},
        {"Tür": "funnel", "Gerekli kolonlar": "Oturumlar, Sepete ekleme, Ödeme sayfası", "Örnek": "shopify002.csv"},
        {"Tür": "geo", "Gerekli kolonlar": "Oturum ülkesi/bölgesi/şehri", "Örnek": "shopify003.csv"},
        {"Tür": "gross_monthly", "Gerekli kolonlar": "Ay, Brüt satışlar", "Örnek": "shopify004.csv"},
        {"Tür": "billing", "Gerekli kolonlar": "Tutar/Amount/Payment", "Örnek": "meta_billing_2026...csv"},
        {"Tür": "meta_campaign", "Gerekli kolonlar": "Campaign, Amount spent, Purchases/ROAS", "Örnek": "meta_campaigns_2026...csv"},
    ])
    st.dataframe(expected, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Sales Performance")
    if orders_f.empty:
        st.warning("Sipariş verisi boş. File Diagnostic sekmesinden dosya türünü ve eksik kolonları kontrol et.")
    else:
        daily = orders_f.groupby(orders_f["order_date"].dt.normalize(), as_index=False).agg(
            net_sales=("net_sales", "sum"),
            order_count=("order_count", "sum"),
            gross_profit_estimated=("gross_profit_estimated", "sum"),
        ).rename(columns={"order_date": "date"})

        if not meta_f.empty:
            meta_daily = meta_f.groupby(meta_f["date"].dt.normalize(), as_index=False).agg(
                spend=("spend", "sum"),
                attributed_revenue=("attributed_revenue", "sum"),
                purchases=("purchases", "sum"),
            ).rename(columns={"date": "date"})
            daily = daily.merge(meta_daily, on="date", how="outer").fillna(0.0)
        else:
            daily["spend"] = 0.0
            daily["attributed_revenue"] = 0.0
            daily["purchases"] = 0.0

        daily["net_profit_after_ads"] = daily["gross_profit_estimated"] - daily["spend"]

        chart = daily.melt(
            id_vars="date",
            value_vars=["net_sales", "gross_profit_estimated", "net_profit_after_ads"],
            var_name="metric",
            value_name="value",
        )
        fig = px.line(chart, x="date", y="value", color="metric", markers=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(daily.sort_values("date", ascending=False), use_container_width=True, hide_index=True)

    if not gross_monthly.empty:
        st.subheader("Gross Monthly Export")
        fig = px.line(gross_monthly.sort_values("month"), x="month", y="gross_sales", markers=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(gross_monthly, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Product & Profit")
    if lines_f.empty:
        st.warning("Ürün satır verisi boş.")
    else:
        product = lines_f.groupby(["product_name", "sku_key"], as_index=False).agg(
            units_sold=("qty", "sum"),
            revenue=("line_revenue", "sum"),
            gross_profit=("gross_profit", "sum"),
            matched_cost=("matched_cost", "max"),
            source_file=("source_file", "last"),
        ).sort_values(["units_sold", "revenue"], ascending=False)

        st.dataframe(
            product.style.format({
                "units_sold": "{:,.0f}",
                "revenue": "{:,.2f} TL",
                "gross_profit": "{:,.2f} TL",
            }),
            use_container_width=True,
            hide_index=True,
        )

        fig = px.bar(product.head(15).sort_values("units_sold"), x="units_sold", y="product_name", orientation="h")
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Traffic & Funnel")
    if funnel.empty:
        st.info("Funnel dosyası okunmadı.")
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

    st.subheader("Geo")
    if geo.empty:
        st.info("Geo dosyası okunmadı.")
    else:
        st.dataframe(geo.sort_values("sessions", ascending=False).head(50), use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Meta / Marketing")
    if meta_f.empty:
        st.info("Meta / billing verisi okunmadı.")
    else:
        st.markdown(
            """
            **Double-count kuralı:**  
            Billing/fatura dosyası varsa gerçek `Total Ad Spend` sadece billing dosyasından alınır.  
            Campaign dosyası varsa `campaign_spend_original` kontrol amaçlı gösterilir ama ana spend'e eklenmez.
            """
        )
        st.dataframe(meta_f.sort_values(["source_type", "date"], ascending=[True, False]), use_container_width=True, hide_index=True)

        campaign = meta_f.groupby(["source_type", "campaign_name"], as_index=False).agg(
            spend=("spend", "sum"),
            campaign_spend_original=("campaign_spend_original", "sum"),
            attributed_revenue=("attributed_revenue", "sum"),
            purchases=("purchases", "sum"),
        )
        campaign["roas"] = campaign.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]) if r["spend"] else safe_divide(r["attributed_revenue"], r["campaign_spend_original"]), axis=1)
        st.subheader("Campaign / Source Summary")
        st.dataframe(campaign.sort_values("campaign_spend_original", ascending=False), use_container_width=True, hide_index=True)

with tab6:
    st.subheader("Orders")
    if orders_f.empty:
        st.warning("Sipariş tablosu boş.")
    else:
        cols = [
            "order_name", "order_date", "financial_status", "fulfillment_status",
            "net_sales", "gross_profit_estimated", "units", "Payment Method",
            "Billing City", "Source", "source_file"
        ]
        cols = [c for c in cols if c in orders_f.columns]
        st.dataframe(orders_f.sort_values("order_date", ascending=False)[cols], use_container_width=True, hide_index=True)

with tab7:
    st.subheader("Data Quality")
    quality = pd.DataFrame([
        {"Check": "CSV files found", "Value": len(scan)},
        {"Check": "Order files detected", "Value": int(scan["detected_type"].eq("orders").sum()) if not scan.empty else 0},
        {"Check": "Order rows loaded", "Value": len(orders)},
        {"Check": "Line rows loaded", "Value": len(lines)},
        {"Check": "Cost rows loaded", "Value": len(costs)},
        {"Check": "Funnel rows loaded", "Value": len(funnel)},
        {"Check": "Geo rows loaded", "Value": len(geo)},
        {"Check": "Gross monthly rows loaded", "Value": len(gross_monthly)},
        {"Check": "Meta rows loaded", "Value": len(meta)},
        {"Check": "Cost match rate", "Value": f"{cost_match_rate:.1%}"},
    ])
    st.dataframe(quality, use_container_width=True, hide_index=True)

    if not lines.empty and "matched_cost" in lines.columns:
        missing = lines[~lines["matched_cost"]][["product_name", "sku_key", "source_file"]].drop_duplicates()
        st.markdown("### Cost eşleşmeyen ürünler")
        if missing.empty:
            st.success("Tüm ürünler maliyet tablosuyla eşleşmiş görünüyor.")
        else:
            st.dataframe(missing, use_container_width=True, hide_index=True)

    st.markdown("### Okuma uyarıları")
    if issues:
        for issue in issues:
            st.info(issue)
    else:
        st.success("Kritik okuma uyarısı yok.")
