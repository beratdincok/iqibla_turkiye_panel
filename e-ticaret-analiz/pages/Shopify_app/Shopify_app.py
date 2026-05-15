# -*- coding: utf-8 -*-
"""
Shopify Main Report System
- Shopify order export CSV okur
- Shopify maliyet tablosu CSV okur
- Meta fatura özeti CSV okur
- Shopify traffic / sessions CSV okur
- Main Report + File Diagnostic + Sales Performance + Product & Profit + Traffic & Funnel + Meta / Marketing + Orders + Data Quality raporları üretir

Çalıştırma:
    streamlit run Shopify_Main_Report_System.py
"""

from __future__ import annotations

import io
import os
import re
import csv
import glob
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.express as px
except Exception:
    px = None


# ============================================================
# PAGE CONFIG / THEME
# ============================================================
st.set_page_config(
    page_title="Shopify Main Report",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main {background-color: #f7f9fc;}
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .kpi-card {
        background: white;
        border: 1px solid #e8edf5;
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        box-shadow: 0 8px 22px rgba(18, 38, 63, 0.06);
        min-height: 108px;
    }
    .kpi-label {font-size: 0.86rem; color: #617085; margin-bottom: 6px;}
    .kpi-value {font-size: 1.55rem; font-weight: 800; color: #0b1f3a; line-height: 1.15;}
    .kpi-help {font-size: 0.76rem; color: #8793a4; margin-top: 6px;}
    .section-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #0b1f3a;
        margin-top: 0.4rem;
        margin-bottom: 0.6rem;
    }
    .ok-box {
        border-left: 5px solid #0e8f66;
        background: #ecfdf7;
        padding: 12px 14px;
        border-radius: 10px;
        color: #0b4f3b;
        margin-bottom: 10px;
    }
    .warn-box {
        border-left: 5px solid #f59e0b;
        background: #fffbeb;
        padding: 12px 14px;
        border-radius: 10px;
        color: #7c4a03;
        margin-bottom: 10px;
    }
    .bad-box {
        border-left: 5px solid #dc2626;
        background: #fef2f2;
        padding: 12px 14px;
        border-radius: 10px;
        color: #7f1d1d;
        margin-bottom: 10px;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def strip_accents(text: str) -> str:
    text = str(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def norm_text(text: Any) -> str:
    text = strip_accents(str(text).lower().strip())
    text = text.replace("ı", "i")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_encoding(raw: bytes) -> str:
    for enc in ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]:
        try:
            raw.decode(enc)
            return enc
        except Exception:
            continue
    return "latin1"


def read_raw_bytes(file_or_path: Any) -> bytes:
    if file_or_path is None:
        return b""
    if isinstance(file_or_path, (str, os.PathLike)):
        with open(file_or_path, "rb") as f:
            return f.read()
    # Streamlit UploadedFile
    try:
        pos = file_or_path.tell()
        file_or_path.seek(0)
        raw = file_or_path.read()
        file_or_path.seek(pos)
        return raw
    except Exception:
        file_or_path.seek(0)
        return file_or_path.getvalue()


def read_csv_flexible(file_or_path: Any, force_sep: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """CSV dosyasını delimiter/encoding otomatik seçerek okur. Tüm kolonları str alır; SKU kaybını engeller."""
    raw = read_raw_bytes(file_or_path)
    info = {"encoding": None, "sep": None, "rows": 0, "cols": 0, "error": None}
    if not raw:
        return pd.DataFrame(), {**info, "error": "Dosya boş veya okunamadı."}

    enc = detect_encoding(raw)
    text = raw.decode(enc, errors="replace")
    info["encoding"] = enc

    candidates = [force_sep] if force_sep else [",", ";", "\t", "|"]
    best_df = pd.DataFrame()
    best_sep = None
    best_score = -1
    best_error = None

    for sep in candidates:
        if sep is None:
            continue
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, engine="python", keep_default_na=False)
            score = df.shape[1] * 100000 + df.shape[0]
            if df.shape[1] > 1 and score > best_score:
                best_df, best_sep, best_score = df, sep, score
        except Exception as e:
            best_error = str(e)

    if best_df.empty:
        # Son deneme: pandas sep=None
        try:
            best_df = pd.read_csv(io.StringIO(text), sep=None, dtype=str, engine="python", keep_default_na=False)
            best_sep = "auto"
        except Exception as e:
            info["error"] = best_error or str(e)
            return pd.DataFrame(), info

    best_df.columns = [str(c).strip().replace("\ufeff", "") for c in best_df.columns]
    info.update({"sep": best_sep, "rows": int(best_df.shape[0]), "cols": int(best_df.shape[1])})
    return best_df, info


def parse_number_value(x: Any) -> float:
    """1,520.50 ve 1.520,50 gibi TR/EN formatlarını sayıya çevirir."""
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip()
    if not s or s.lower() in ["nan", "none", "null", "n/a"]:
        return np.nan
    s = s.replace("\xa0", " ")
    s = s.replace("TL", "").replace("TRY", "").replace("₺", "")
    s = s.replace("%", "")
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if not s or s in ["-", ".", ","]:
        return np.nan

    if "," in s and "." in s:
        # Son görünen ayırıcı decimal kabul edilir
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # 0,01 veya 14.366,91 gibi TR decimal
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return np.nan


def to_num(series: pd.Series) -> pd.Series:
    return series.map(parse_number_value).astype(float)


def clean_sku(x: Any, auto_fix_missing_6: bool = True) -> str:
    if x is None:
        return ""
    s = str(x).strip().replace("\xa0", "")
    if not s or s.lower() in ["nan", "none", "null"]:
        return ""
    # Excel/Pandas bazen SKU'yu 6.970127e+12 veya 6970126922125.0 yapar.
    try:
        if re.search(r"[eE]", s):
            s = str(int(float(s)))
        elif re.fullmatch(r"\d+\.0", s):
            s = s[:-2]
    except Exception:
        pass
    s = re.sub(r"\D", "", s)
    # Kullanıcı maliyet dosyasında bazı SKU'lar 9701269... olarak gelmiş; Shopify'da 69701269... şeklinde.
    if auto_fix_missing_6 and len(s) == 12 and s.startswith("970"):
        s = "6" + s
    return s


def find_col(df: pd.DataFrame, candidates: List[str], contains_all: Optional[List[str]] = None) -> Optional[str]:
    if df is None or df.empty:
        return None
    norm_map = {col: norm_text(col) for col in df.columns}
    cand_norm = [norm_text(c) for c in candidates]

    # Exact normalized match
    for col, ncol in norm_map.items():
        if ncol in cand_norm:
            return col

    # Candidate words included
    for cand in cand_norm:
        words = cand.split()
        for col, ncol in norm_map.items():
            if all(w in ncol for w in words):
                return col

    # Generic contains all
    if contains_all:
        words = [norm_text(w) for w in contains_all]
        for col, ncol in norm_map.items():
            if all(w in ncol for w in words):
                return col
    return None


def format_tl(value: Any) -> str:
    if value is None or pd.isna(value):
        return "0.00 TL"
    return f"{float(value):,.2f} TL"


def format_int(value: Any) -> str:
    if value is None or pd.isna(value):
        return "0"
    return f"{int(round(float(value))):,}"


def format_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def safe_div(a: float, b: float) -> float:
    if b is None or pd.isna(b) or float(b) == 0:
        return np.nan
    return float(a) / float(b)


def card(label: str, value: str, help_text: str = "") -> None:
    st.markdown(
        f"""
<div class="kpi-card">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-help">{help_text}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def msg_box(kind: str, text: str) -> None:
    css = {"ok": "ok-box", "warn": "warn-box", "bad": "bad-box"}.get(kind, "warn-box")
    st.markdown(f'<div class="{css}">{text}</div>', unsafe_allow_html=True)


def plot_line(df: pd.DataFrame, x: str, y: str, title: str):
    if df.empty or x not in df or y not in df:
        st.info("Grafik için yeterli veri yok.")
        return
    if px:
        fig = px.line(df, x=x, y=y, markers=True, title=title)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.line_chart(df.set_index(x)[y])


def plot_bar(df: pd.DataFrame, x: str, y: str, title: str):
    if df.empty or x not in df or y not in df:
        st.info("Grafik için yeterli veri yok.")
        return
    if px:
        fig = px.bar(df, x=x, y=y, title=title)
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(df.set_index(x)[y])


# ============================================================
# DATA PARSERS
# ============================================================
@dataclass
class ParsedOrders:
    raw: pd.DataFrame
    order_rows: pd.DataFrame
    valid_orders: pd.DataFrame
    line_rows: pd.DataFrame
    daily: pd.DataFrame
    info: Dict[str, Any]
    warnings: List[str]


@dataclass
class ParsedCosts:
    raw: pd.DataFrame
    clean: pd.DataFrame
    sku_cost: pd.DataFrame
    info: Dict[str, Any]
    warnings: List[str]


@dataclass
class ParsedMeta:
    payments: pd.DataFrame
    total_spend: float
    info: Dict[str, Any]
    warnings: List[str]


@dataclass
class ParsedTraffic:
    raw: pd.DataFrame
    daily: pd.DataFrame
    info: Dict[str, Any]
    warnings: List[str]


def parse_orders(file_or_path: Any, include_pending: bool = True, revenue_mode: str = "Net revenue: refunds düş") -> ParsedOrders:
    df, info = read_csv_flexible(file_or_path)
    warnings: List[str] = []
    if df.empty:
        warnings.append("Shopify Orders dosyası okunamadı veya boş.")
        return ParsedOrders(df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), info, warnings)

    # Required columns
    name_col = find_col(df, ["Name", "Order", "Order Name"])
    total_col = find_col(df, ["Total", "Order Total", "Net Sales"])
    subtotal_col = find_col(df, ["Subtotal"])
    created_col = find_col(df, ["Created at", "Created", "Date", "Paid at"])
    paid_col = find_col(df, ["Paid at"])
    cancel_col = find_col(df, ["Cancelled at", "Canceled at"])
    status_col = find_col(df, ["Financial Status", "Payment Status"])
    refund_col = find_col(df, ["Refunded Amount", "Refund", "Refunds"])
    qty_col = find_col(df, ["Lineitem quantity", "Line item quantity", "Quantity"])
    item_col = find_col(df, ["Lineitem name", "Line item name", "Product", "Title"])
    sku_col = find_col(df, ["Lineitem sku", "Line item sku", "SKU", "Variant SKU"])
    price_col = find_col(df, ["Lineitem price", "Line item price", "Price"])
    discount_col = find_col(df, ["Lineitem discount", "Line item discount", "Discount"])
    source_col = find_col(df, ["Source"])
    shipping_col = find_col(df, ["Shipping"])
    tax_col = find_col(df, ["Taxes", "Tax"])
    email_col = find_col(df, ["Email"])

    required_missing = []
    for label, col in [("Name", name_col), ("Total", total_col), ("Created at", created_col), ("Lineitem quantity", qty_col)]:
        if col is None:
            required_missing.append(label)
    if required_missing:
        warnings.append("Eksik kritik kolonlar: " + ", ".join(required_missing))

    data = df.copy()
    if name_col is None:
        data["__order_name"] = np.arange(len(data)).astype(str)
    else:
        data["__order_name"] = data[name_col].astype(str).str.strip()
    if total_col:
        data["__total"] = to_num(data[total_col])
    else:
        data["__total"] = np.nan
    if subtotal_col:
        data["__subtotal"] = to_num(data[subtotal_col])
    else:
        data["__subtotal"] = np.nan
    if refund_col:
        data["__refund"] = to_num(data[refund_col]).fillna(0)
    else:
        data["__refund"] = 0.0
    if qty_col:
        data["__qty"] = to_num(data[qty_col]).fillna(0)
    else:
        data["__qty"] = 0.0
    if price_col:
        data["__line_price"] = to_num(data[price_col]).fillna(0)
    else:
        data["__line_price"] = 0.0
    if discount_col:
        data["__line_discount"] = to_num(data[discount_col]).fillna(0)
    else:
        data["__line_discount"] = 0.0
    if shipping_col:
        data["__shipping"] = to_num(data[shipping_col]).fillna(0)
    else:
        data["__shipping"] = 0.0
    if tax_col:
        data["__taxes"] = to_num(data[tax_col]).fillna(0)
    else:
        data["__taxes"] = 0.0
    if sku_col:
        data["__sku"] = data[sku_col].map(clean_sku)
    else:
        data["__sku"] = ""
    data["__item"] = data[item_col].astype(str).str.strip() if item_col else ""
    data["__status"] = data[status_col].astype(str).str.lower().str.strip() if status_col else ""
    data["__source"] = data[source_col].astype(str).str.strip() if source_col else ""
    data["__email"] = data[email_col].astype(str).str.strip() if email_col else ""

    if cancel_col:
        data["__cancelled"] = data[cancel_col].astype(str).str.strip().ne("")
    else:
        data["__cancelled"] = False

    date_source = created_col or paid_col
    if date_source:
        data["__created_at"] = pd.to_datetime(data[date_source], errors="coerce", utc=True).dt.tz_convert(None)
    else:
        data["__created_at"] = pd.NaT

    # Shopify export: Total only appears on first row of each order.
    order_rows = data[data["__total"].notna()].copy()
    duplicate_order_names = int(order_rows["__order_name"].duplicated().sum())
    if duplicate_order_names:
        warnings.append(f"Order-level satırlarda {duplicate_order_names} tekrar eden sipariş adı bulundu.")

    if include_pending:
        excluded_statuses = {"voided"}
    else:
        excluded_statuses = {"voided", "pending"}

    valid_orders = order_rows[(~order_rows["__cancelled"]) & (~order_rows["__status"].isin(excluded_statuses))].copy()

    if revenue_mode.startswith("Net"):
        valid_orders["__revenue"] = valid_orders["__total"].fillna(0) - valid_orders["__refund"].fillna(0)
    else:
        valid_orders["__revenue"] = valid_orders["__total"].fillna(0)

    valid_order_names = set(valid_orders["__order_name"].dropna().astype(str))
    line_rows = data[data["__order_name"].isin(valid_order_names)].copy()
    line_rows["__line_gross"] = (line_rows["__line_price"].fillna(0) * line_rows["__qty"].fillna(0)) - line_rows["__line_discount"].fillna(0)
    line_rows.loc[line_rows["__line_gross"] < 0, "__line_gross"] = 0

    daily = valid_orders.copy()
    daily["Date"] = daily["__created_at"].dt.date
    daily = (
        daily.dropna(subset=["Date"])
        .groupby("Date", as_index=False)
        .agg(Revenue=("__revenue", "sum"), Orders=("__order_name", "nunique"), Refunds=("__refund", "sum"))
        .sort_values("Date")
    )

    # Friendly output columns for Orders tab
    valid_orders["Order"] = valid_orders["__order_name"]
    valid_orders["Date"] = valid_orders["__created_at"]
    valid_orders["Financial Status"] = valid_orders["__status"]
    valid_orders["Total"] = valid_orders["__total"]
    valid_orders["Refunded Amount"] = valid_orders["__refund"]
    valid_orders["Revenue"] = valid_orders["__revenue"]
    valid_orders["Email"] = valid_orders["__email"]
    valid_orders["Source"] = valid_orders["__source"]

    info.update(
        {
            "order_rows": int(order_rows.shape[0]),
            "valid_orders": int(valid_orders.shape[0]),
            "line_rows": int(line_rows.shape[0]),
            "unique_orders_raw": int(order_rows["__order_name"].nunique()),
            "cancelled_orders": int(order_rows["__cancelled"].sum()),
            "date_min": str(valid_orders["__created_at"].min()) if not valid_orders.empty else "",
            "date_max": str(valid_orders["__created_at"].max()) if not valid_orders.empty else "",
            "detected_columns": {
                "order": name_col,
                "total": total_col,
                "created": created_col,
                "status": status_col,
                "cancelled": cancel_col,
                "refund": refund_col,
                "quantity": qty_col,
                "item": item_col,
                "sku": sku_col,
                "price": price_col,
            },
        }
    )

    if line_rows["__sku"].eq("").mean() > 0.2:
        warnings.append("Lineitem SKU boş oranı yüksek. Maliyet eşleşmesi düşük görünebilir.")

    return ParsedOrders(data, order_rows, valid_orders, line_rows, daily, info, warnings)


def parse_costs(file_or_path: Any) -> ParsedCosts:
    df, info = read_csv_flexible(file_or_path, force_sep=None)
    warnings: List[str] = []
    if df.empty:
        warnings.append("Maliyet dosyası okunamadı veya boş.")
        return ParsedCosts(df, pd.DataFrame(), pd.DataFrame(), info, warnings)

    sku_col = find_col(df, ["SKU", "Variant SKU", "Stok Kodu"])
    cost_col = find_col(df, ["Maliyet", "Maliyet Alış", "Maliyet (Alış)", "Cost", "Unit Cost"], contains_all=["maliyet"])
    platform_col = find_col(df, ["Platform", "Channel"])
    commission_col = find_col(df, ["Komisyon oran", "Komisyon oranı", "Commission", "Commission Rate"], contains_all=["komisyon"])
    cargo_col = find_col(df, ["Kargo", "Kargo maliyeti", "Shipping", "Shipping Cost"], contains_all=["kargo"])
    vat_col = find_col(df, ["KDV Oranı", "KDV Oran", "VAT", "VAT Rate"], contains_all=["kdv"])
    stock_col = find_col(df, ["Stok", "Inventory", "Inventory Quantity", "Adet", "Stock"])

    if not sku_col:
        warnings.append("Maliyet dosyasında SKU kolonu bulunamadı.")
    if not cost_col:
        warnings.append("Maliyet dosyasında maliyet/alış kolonu bulunamadı.")

    clean = df.copy()
    clean["__sku"] = clean[sku_col].map(clean_sku) if sku_col else ""
    clean["__unit_cost"] = to_num(clean[cost_col]).fillna(0) if cost_col else 0.0
    clean["__platform"] = clean[platform_col].astype(str).str.strip() if platform_col else ""
    clean["__cargo"] = to_num(clean[cargo_col]).fillna(0) if cargo_col else 0.0
    clean["__commission_rate"] = to_num(clean[commission_col]).fillna(0) if commission_col else 0.0
    clean["__vat_rate"] = to_num(clean[vat_col]).fillna(0) if vat_col else 0.0
    clean["__stock_qty"] = to_num(clean[stock_col]).fillna(0) if stock_col else np.nan

    # 10 yazıldıysa %10 kabul et; 0.10 veya 0,10 yazıldıysa direkt oran kabul et.
    clean.loc[clean["__commission_rate"] > 1, "__commission_rate"] = clean.loc[clean["__commission_rate"] > 1, "__commission_rate"] / 100
    clean.loc[clean["__vat_rate"] > 1, "__vat_rate"] = clean.loc[clean["__vat_rate"] > 1, "__vat_rate"] / 100

    clean = clean[clean["__sku"].ne("")].copy()
    duplicates = int(clean["__sku"].duplicated().sum())
    if duplicates:
        warnings.append(f"Maliyet dosyasında {duplicates} tekrar eden SKU var; ilk değer kullanıldı.")

    sku_cost = clean.drop_duplicates("__sku", keep="first").set_index("__sku")
    info.update(
        {
            "valid_skus": int(sku_cost.shape[0]),
            "detected_columns": {
                "sku": sku_col,
                "cost": cost_col,
                "platform": platform_col,
                "commission": commission_col,
                "cargo": cargo_col,
                "vat": vat_col,
                "stock": stock_col,
            },
        }
    )
    return ParsedCosts(df, clean, sku_cost, info, warnings)


def parse_meta_invoice(file_or_path: Any) -> ParsedMeta:
    raw = read_raw_bytes(file_or_path)
    info = {"encoding": None, "payments": 0, "date_min": "", "date_max": ""}
    warnings: List[str] = []
    if not raw:
        warnings.append("Meta fatura dosyası okunamadı veya boş.")
        return ParsedMeta(pd.DataFrame(), 0.0, info, warnings)

    enc = detect_encoding(raw)
    text = raw.decode(enc, errors="replace")
    info["encoding"] = enc

    rows = []
    current_method = ""
    in_payment_table = False
    headers: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            in_payment_table = False
            continue
        if line.lower().startswith("ödeme yöntemi") or line.lower().startswith("odeme yontemi"):
            current_method = line.split(":", 1)[-1].strip() if ":" in line else line
        if line.startswith("Tarih,") and "Tutar" in line:
            headers = next(csv.reader([line]))
            in_payment_table = True
            continue
        if in_payment_table:
            parsed = next(csv.reader([line]))
            if len(parsed) < 3:
                continue
            joined = ",".join(parsed)
            if "Faturalandırılan Toplam Tutar" in joined or "Faturalandirilan" in joined:
                in_payment_table = False
                continue
            # İki farklı tablo tipi var:
            # Tarih,İşlem Kodu,Ödeme Yöntemi,Tutar,Para Birimi
            # Tarih,İşlem Kodu,Tutar,Para Birimi
            try:
                if len(headers) >= 5 and "Ödeme" in headers[2]:
                    date_s, trx, method, amount_s, currency = parsed[:5]
                else:
                    date_s, trx, amount_s, currency = parsed[:4]
                    method = current_method or "Meta"
                amount = parse_number_value(amount_s)
                dt = pd.to_datetime(date_s, dayfirst=True, errors="coerce")
                if pd.notna(amount):
                    rows.append({"Date": dt, "Transaction": trx, "Payment Method": method, "Spend": amount, "Currency": currency})
            except Exception:
                continue

    payments = pd.DataFrame(rows)
    if payments.empty:
        warnings.append("Meta fatura içinden ödeme tablosu bulunamadı. Dosya formatı değişmiş olabilir.")
        total_spend = 0.0
    else:
        payments = payments.sort_values("Date")
        total_spend = float(payments["Spend"].sum())
        info.update({
            "payments": int(payments.shape[0]),
            "date_min": str(payments["Date"].min().date()) if payments["Date"].notna().any() else "",
            "date_max": str(payments["Date"].max().date()) if payments["Date"].notna().any() else "",
        })
    return ParsedMeta(payments, total_spend, info, warnings)


def parse_traffic(file_or_path: Any) -> ParsedTraffic:
    df, info = read_csv_flexible(file_or_path)
    warnings: List[str] = []
    if df.empty:
        warnings.append("Traffic / sessions dosyası okunamadı veya boş.")
        return ParsedTraffic(df, pd.DataFrame(), info, warnings)

    # Shopify export bazen karşılaştırma dönemi kolonlarını da getirir. Ana kolonları seçiyoruz.
    day_col = find_col(df, ["Day", "Date", "Gün", "Tarih"])
    visitors_col = None
    sessions_col = None
    for c in df.columns:
        n = norm_text(c)
        if visitors_col is None and "online store visitors" in n and "2025" not in n and "2024" not in n:
            visitors_col = c
        if sessions_col is None and n == "sessions":
            sessions_col = c
    visitors_col = visitors_col or find_col(df, ["Online store visitors", "Visitors", "Ziyaretçi"])
    sessions_col = sessions_col or find_col(df, ["Sessions", "Oturumlar", "Oturum"])

    if not day_col:
        warnings.append("Traffic dosyasında tarih/gün kolonu bulunamadı.")
    if not sessions_col:
        warnings.append("Traffic dosyasında sessions/oturum kolonu bulunamadı.")

    daily = pd.DataFrame()
    if day_col:
        daily["Date"] = pd.to_datetime(df[day_col], errors="coerce")
    if visitors_col:
        daily["Visitors"] = to_num(df[visitors_col]).fillna(0)
    else:
        daily["Visitors"] = 0.0
    if sessions_col:
        daily["Sessions"] = to_num(df[sessions_col]).fillna(0)
    else:
        daily["Sessions"] = 0.0
    daily = daily.dropna(subset=["Date"]).sort_values("Date")
    daily["Date"] = daily["Date"].dt.date
    daily = daily.groupby("Date", as_index=False).agg(Visitors=("Visitors", "sum"), Sessions=("Sessions", "sum"))

    info.update({
        "detected_columns": {"day": day_col, "visitors": visitors_col, "sessions": sessions_col},
        "date_min": str(daily["Date"].min()) if not daily.empty else "",
        "date_max": str(daily["Date"].max()) if not daily.empty else "",
    })
    return ParsedTraffic(df, daily, info, warnings)


# ============================================================
# METRIC BUILDER
# ============================================================
def build_profit_lines(order_lines: pd.DataFrame, costs: ParsedCosts, include_cargo: bool, include_commission: bool) -> pd.DataFrame:
    if order_lines.empty:
        return pd.DataFrame()
    lines = order_lines.copy()
    if costs.sku_cost.empty:
        lines["__cost_matched"] = False
        lines["__unit_cost"] = 0.0
        lines["__cargo"] = 0.0
        lines["__commission_rate"] = 0.0
        lines["__line_cogs"] = 0.0
        lines["__line_cargo_cost"] = 0.0
        lines["__line_commission"] = 0.0
        lines["__line_total_cost"] = 0.0
        lines["__line_profit"] = lines["__line_gross"].fillna(0)
        return lines

    keep_cols = ["__unit_cost", "__cargo", "__commission_rate", "__stock_qty"]
    cost_map = costs.sku_cost[[c for c in keep_cols if c in costs.sku_cost.columns]].copy()
    lines = lines.merge(cost_map, left_on="__sku", right_index=True, how="left")
    lines["__cost_matched"] = lines["__unit_cost"].notna() & lines["__sku"].ne("")
    lines["__unit_cost"] = lines["__unit_cost"].fillna(0)
    lines["__cargo"] = lines["__cargo"].fillna(0)
    lines["__commission_rate"] = lines["__commission_rate"].fillna(0)
    lines["__line_cogs"] = lines["__unit_cost"] * lines["__qty"].fillna(0)
    lines["__line_cargo_cost"] = (lines["__cargo"] * lines["__qty"].fillna(0)) if include_cargo else 0.0
    lines["__line_commission"] = (lines["__line_gross"].fillna(0) * lines["__commission_rate"].fillna(0)) if include_commission else 0.0
    lines["__line_total_cost"] = lines["__line_cogs"] + lines["__line_cargo_cost"] + lines["__line_commission"]
    lines["__line_profit"] = lines["__line_gross"].fillna(0) - lines["__line_total_cost"].fillna(0)
    return lines


def build_product_summary(profit_lines: pd.DataFrame) -> pd.DataFrame:
    if profit_lines.empty:
        return pd.DataFrame()
    out = (
        profit_lines.groupby(["__item", "__sku"], dropna=False, as_index=False)
        .agg(
            Units=("__qty", "sum"),
            Sales=("__line_gross", "sum"),
            Product_Cost=("__line_cogs", "sum"),
            Cargo_Cost=("__line_cargo_cost", "sum"),
            Commission=("__line_commission", "sum"),
            Total_Cost=("__line_total_cost", "sum"),
            Gross_Profit=("__line_profit", "sum"),
            Cost_Matched=("__cost_matched", "max"),
        )
        .rename(columns={"__item": "Product", "__sku": "SKU"})
    )
    out["Margin"] = out.apply(lambda r: safe_div(r["Gross_Profit"], r["Sales"]), axis=1)
    out = out.sort_values("Sales", ascending=False)
    return out


def filter_by_date(parsed: ParsedOrders, traffic: ParsedTraffic, meta: ParsedMeta, start_date, end_date):
    orders = parsed.valid_orders.copy()
    lines = parsed.line_rows.copy()
    daily_orders = parsed.daily.copy()
    traffic_daily = traffic.daily.copy()
    meta_payments = meta.payments.copy()

    if start_date and end_date and not orders.empty:
        start_ts = pd.to_datetime(start_date)
        end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        valid_names = set(orders[(orders["__created_at"] >= start_ts) & (orders["__created_at"] <= end_ts)]["__order_name"])
        orders = orders[orders["__order_name"].isin(valid_names)].copy()
        lines = lines[lines["__order_name"].isin(valid_names)].copy()
        if not daily_orders.empty:
            daily_orders = daily_orders[(pd.to_datetime(daily_orders["Date"]) >= start_ts) & (pd.to_datetime(daily_orders["Date"]) <= end_ts)]
        if not traffic_daily.empty:
            traffic_daily = traffic_daily[(pd.to_datetime(traffic_daily["Date"]) >= start_ts) & (pd.to_datetime(traffic_daily["Date"]) <= end_ts)]
        if not meta_payments.empty:
            meta_payments = meta_payments[(meta_payments["Date"] >= start_ts) & (meta_payments["Date"] <= end_ts)]
    return orders, lines, daily_orders, traffic_daily, meta_payments


def find_sample_file(patterns: List[str]) -> Optional[str]:
    roots = [".", "data", "./data", "sample_data", "./sample_data"]
    for root in roots:
        for pat in patterns:
            matches = glob.glob(os.path.join(root, pat), recursive=False)
            if matches:
                return matches[0]
    return None


# ============================================================
# SIDEBAR INPUTS
# ============================================================
st.title("📊 Shopify Main Report System")
st.caption("Orders + Maliyet + Meta Fatura + Traffic dosyalarını okuyup tek panelde KPI ve hata teşhisi üretir.")

with st.sidebar:
    st.header("📥 Dosya Yükle")
    orders_file = st.file_uploader("Shopify Orders CSV", type=["csv"], key="orders")
    cost_file = st.file_uploader("Shopify Maliyet Tablosu CSV", type=["csv"], key="cost")
    meta_file = st.file_uploader("Meta Fatura Özeti CSV", type=["csv"], key="meta")
    traffic_file = st.file_uploader("Zamana Göre Oturumlar / Sessions CSV", type=["csv"], key="traffic")

    st.divider()
    st.header("⚙️ Hesap Ayarları")
    include_pending = st.checkbox("Pending siparişleri dahil et", value=True)
    revenue_mode = st.selectbox("Revenue hesabı", ["Net revenue: refunds düş", "Gross revenue: refund düşme"], index=0)
    include_cargo = st.checkbox("Kargo maliyetini kârdan düş", value=True)
    include_commission = st.checkbox("Komisyonu kârdan düş", value=True)
    low_stock_threshold = st.number_input("Low stock eşiği", min_value=0, value=5, step=1)
    manual_ad_revenue = st.number_input("Manuel Meta Attributed Revenue / Ad Purchases Revenue", min_value=0.0, value=0.0, step=100.0)

# Otomatik local dosya bulma: dosyaları aynı klasöre/data klasörüne koyarsa upload şart olmaz.
if orders_file is None:
    orders_file = find_sample_file(["*orders*.csv", "*order*.csv", "*siparis*.csv", "*sipariş*.csv"])
if cost_file is None:
    cost_file = find_sample_file(["*Maliyet*.csv", "*maliyet*.csv", "*cost*.csv"])
if meta_file is None:
    meta_file = find_sample_file(["*Fatura*.csv", "*fatura*.csv", "*Meta*.csv", "*meta*.csv"])
if traffic_file is None:
    traffic_file = find_sample_file(["*oturum*.csv", "*Oturum*.csv", "*sessions*.csv", "*Sessions*.csv", "*traffic*.csv"])

if orders_file is None:
    msg_box("warn", "Başlamak için en az Shopify Orders CSV dosyasını yükle. Diğer dosyalar opsiyonel ama raporu güçlendirir.")
    st.stop()

# ============================================================
# PARSE DATA
# ============================================================
orders = parse_orders(orders_file, include_pending=include_pending, revenue_mode=revenue_mode)
costs = parse_costs(cost_file) if cost_file is not None else ParsedCosts(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"error": "Yüklenmedi"}, ["Maliyet dosyası yüklenmedi."])
meta = parse_meta_invoice(meta_file) if meta_file is not None else ParsedMeta(pd.DataFrame(), 0.0, {"error": "Yüklenmedi"}, ["Meta fatura dosyası yüklenmedi."])
traffic = parse_traffic(traffic_file) if traffic_file is not None else ParsedTraffic(pd.DataFrame(), pd.DataFrame(), {"error": "Yüklenmedi"}, ["Traffic / sessions dosyası yüklenmedi."])

# Tarih filtresi
valid_dates = orders.valid_orders["__created_at"].dropna() if not orders.valid_orders.empty else pd.Series(dtype="datetime64[ns]")
if not valid_dates.empty:
    min_d = valid_dates.min().date()
    max_d = valid_dates.max().date()
else:
    min_d = pd.Timestamp.today().date()
    max_d = pd.Timestamp.today().date()

with st.sidebar:
    st.divider()
    st.header("🗓️ Report Period")
    all_time = st.checkbox("All Time", value=True)
    if all_time:
        start_date, end_date = min_d, max_d
    else:
        start_date, end_date = st.date_input("Tarih aralığı", value=(min_d, max_d), min_value=min_d, max_value=max_d)

filtered_orders, filtered_lines, daily_orders, traffic_daily, meta_payments = filter_by_date(orders, traffic, meta, start_date, end_date)
profit_lines = build_profit_lines(filtered_lines, costs, include_cargo=include_cargo, include_commission=include_commission)
product_summary = build_product_summary(profit_lines)

# ============================================================
# MAIN KPI CALCULATION
# ============================================================
total_revenue = float(filtered_orders["__revenue"].sum()) if not filtered_orders.empty else 0.0
order_count = int(filtered_orders["__order_name"].nunique()) if not filtered_orders.empty else 0
units_sold = float(filtered_lines["__qty"].sum()) if not filtered_lines.empty else 0
ad_spend = float(meta_payments["Spend"].sum()) if not meta_payments.empty else 0.0
ad_revenue = float(manual_ad_revenue)
ad_purchases = int(safe_div(ad_revenue, safe_div(total_revenue, order_count)) if ad_revenue > 0 and order_count > 0 else 0)

total_line_cost = float(profit_lines["__line_total_cost"].sum()) if not profit_lines.empty else 0.0
gross_profit_before_ads = total_revenue - total_line_cost
net_profit_after_ads = gross_profit_before_ads - ad_spend

aov = safe_div(total_revenue, order_count)
roas = safe_div(ad_revenue, ad_spend)
mer = safe_div(total_revenue, ad_spend)

if not profit_lines.empty and units_sold > 0:
    matched_units = float(profit_lines.loc[profit_lines["__cost_matched"], "__qty"].sum())
    cost_match_rate = safe_div(matched_units, units_sold)
else:
    matched_units = 0.0
    cost_match_rate = np.nan

tracked_inventory_items = int(costs.sku_cost.shape[0]) if not costs.sku_cost.empty else 0
if not costs.sku_cost.empty and "__stock_qty" in costs.sku_cost.columns and costs.sku_cost["__stock_qty"].notna().any():
    total_inventory_units = int(costs.sku_cost["__stock_qty"].fillna(0).sum())
    low_stock_items = int((costs.sku_cost["__stock_qty"].fillna(0) <= low_stock_threshold).sum())
else:
    total_inventory_units = 0
    low_stock_items = 0

report_period_label = "All Time" if all_time else f"{start_date} - {end_date}"

# ============================================================
# TABS
# ============================================================
tabs = st.tabs([
    "Main Report",
    "📁 File Diagnostic",
    "📊 Sales Performance",
    "📦 Product & Profit",
    "🧭 Traffic & Funnel",
    "📣 Meta / Marketing",
    "🧾 Orders",
    "🧪 Data Quality",
])

# ------------------------- Main Report -------------------------
with tabs[0]:
    st.markdown('<div class="section-title">Main Report</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: card("Total Revenue", format_tl(total_revenue), revenue_mode)
    with c2: card("Order Count", format_int(order_count), "Unique non-cancelled orders")
    with c3: card("Units Sold", format_int(units_sold), "Lineitem quantity sum")
    with c4: card("AOV", format_tl(aov), "Total Revenue / Order Count")

    c1, c2, c3, c4 = st.columns(4)
    with c1: card("Total Ad Revenue", format_tl(ad_revenue), "Manual Meta attributed revenue")
    with c2: card("ROAS", "N/A" if pd.isna(roas) else f"{roas:.2f}x", "Ad Revenue / Ad Spend")
    with c3: card("Gross Profit Before Ads", format_tl(gross_profit_before_ads), "Revenue - COGS - selected costs")
    with c4: card("Total Ad Spend", format_tl(ad_spend), "Meta invoice payments")

    c1, c2, c3, c4 = st.columns(4)
    with c1: card("Net Profit After Ads", format_tl(net_profit_after_ads), "Gross Profit - Ad Spend")
    with c2: card("MER", "N/A" if pd.isna(mer) else f"{mer:.2f}x", "Total Revenue / Ad Spend")
    with c3: card("Total Inventory Units", format_int(total_inventory_units), "Inventory column varsa")
    with c4: card("Tracked Inventory Items", format_int(tracked_inventory_items), "Cost table SKU count")

    c1, c2, c3, c4 = st.columns(4)
    with c1: card("Low Stock Items", format_int(low_stock_items), f"Threshold ≤ {low_stock_threshold}")
    with c2: card("Ad Purchases", format_int(ad_purchases), "Manual ad revenue based estimate")
    with c3: card("Cost Match Rate", format_pct(cost_match_rate), f"Matched units: {matched_units:,.0f}/{units_sold:,.0f}")
    with c4: card("Report Period", report_period_label, "Date filter")

    if not orders.warnings and not costs.warnings:
        msg_box("ok", "Ana dosyalar okundu. KPI hesapları üretildi.")
    else:
        msg_box("warn", "Rapor üretildi; ancak Data Quality sekmesindeki uyarıları kontrol et.")

# ------------------------- File Diagnostic -------------------------
with tabs[1]:
    st.markdown('<div class="section-title">📁 File Diagnostic</div>', unsafe_allow_html=True)
    diag_rows = [
        {"File": "Shopify Orders", **orders.info},
        {"File": "Shopify Maliyet", **costs.info},
        {"File": "Meta Fatura", **meta.info},
        {"File": "Traffic / Sessions", **traffic.info},
    ]
    # nested dictleri string yapalım
    clean_diag = []
    for row in diag_rows:
        new = {}
        for k, v in row.items():
            if isinstance(v, dict):
                new[k] = "; ".join([f"{kk}: {vv}" for kk, vv in v.items()])
            else:
                new[k] = v
        clean_diag.append(new)
    st.dataframe(pd.DataFrame(clean_diag), use_container_width=True)

    st.subheader("Detected Columns")
    st.json({
        "orders": orders.info.get("detected_columns", {}),
        "costs": costs.info.get("detected_columns", {}),
        "traffic": traffic.info.get("detected_columns", {}),
    })

    with st.expander("Raw previews"):
        st.write("Orders preview")
        st.dataframe(orders.raw.head(20), use_container_width=True)
        st.write("Cost preview")
        st.dataframe(costs.raw.head(20), use_container_width=True)
        st.write("Meta payments preview")
        st.dataframe(meta.payments.head(20), use_container_width=True)
        st.write("Traffic preview")
        st.dataframe(traffic.raw.head(20), use_container_width=True)

# ------------------------- Sales Performance -------------------------
with tabs[2]:
    st.markdown('<div class="section-title">📊 Sales Performance</div>', unsafe_allow_html=True)
    if daily_orders.empty:
        st.info("Sales performance için tarihli order verisi bulunamadı.")
    else:
        k1, k2, k3 = st.columns(3)
        with k1: card("Best Day Revenue", format_tl(daily_orders["Revenue"].max()), "Highest daily revenue")
        with k2: card("Average Daily Revenue", format_tl(daily_orders["Revenue"].mean()), "Selected period")
        with k3: card("Daily Order Avg", format_int(daily_orders["Orders"].mean()), "Selected period")
        plot_line(daily_orders, "Date", "Revenue", "Daily Revenue")
        plot_bar(daily_orders, "Date", "Orders", "Daily Orders")
        st.dataframe(daily_orders.sort_values("Date", ascending=False), use_container_width=True)

# ------------------------- Product & Profit -------------------------
with tabs[3]:
    st.markdown('<div class="section-title">📦 Product & Profit</div>', unsafe_allow_html=True)
    if product_summary.empty:
        st.info("Product & Profit için lineitem veya maliyet verisi yok.")
    else:
        p1, p2, p3, p4 = st.columns(4)
        with p1: card("Matched Units", format_int(matched_units), "SKU cost matched")
        with p2: card("Unmatched Units", format_int(units_sold - matched_units), "Need cost/SKU fix")
        with p3: card("Total Product Cost", format_tl(profit_lines["__line_cogs"].sum()), "COGS only")
        with p4: card("Total Selected Cost", format_tl(total_line_cost), "COGS + selected cargo/commission")

        top_products = product_summary.head(20).copy()
        plot_bar(top_products.sort_values("Sales", ascending=True), "Product", "Sales", "Top Products by Sales")

        display = product_summary.copy()
        for c in ["Sales", "Product_Cost", "Cargo_Cost", "Commission", "Total_Cost", "Gross_Profit"]:
            if c in display.columns:
                display[c] = display[c].map(lambda v: f"{v:,.2f}")
        if "Margin" in display.columns:
            display["Margin"] = display["Margin"].map(lambda v: "N/A" if pd.isna(v) else f"{v*100:.1f}%")
        st.dataframe(display, use_container_width=True)

        st.subheader("Unmatched Cost List")
        unmatched = product_summary[~product_summary["Cost_Matched"]].copy()
        if unmatched.empty:
            msg_box("ok", "Tüm SKU'lar maliyet tablosu ile eşleşiyor.")
        else:
            msg_box("warn", "Aşağıdaki ürünlerde SKU/maliyet eşleşmesi yok. Bunlar profit hesabını olduğundan yüksek gösterebilir.")
            st.dataframe(unmatched[["Product", "SKU", "Units", "Sales"]], use_container_width=True)

# ------------------------- Traffic & Funnel -------------------------
with tabs[4]:
    st.markdown('<div class="section-title">🧭 Traffic & Funnel</div>', unsafe_allow_html=True)
    total_sessions = float(traffic_daily["Sessions"].sum()) if not traffic_daily.empty else 0.0
    total_visitors = float(traffic_daily["Visitors"].sum()) if not traffic_daily.empty else 0.0
    conversion_rate = safe_div(order_count, total_sessions)
    visitor_to_order = safe_div(order_count, total_visitors)

    f1, f2, f3, f4 = st.columns(4)
    with f1: card("Visitors", format_int(total_visitors), "Online store visitors")
    with f2: card("Sessions", format_int(total_sessions), "Online store sessions")
    with f3: card("Session Conversion", format_pct(conversion_rate), "Orders / Sessions")
    with f4: card("Visitor Conversion", format_pct(visitor_to_order), "Orders / Visitors")

    if traffic_daily.empty:
        st.info("Traffic dosyası yok veya okunamadı.")
    else:
        plot_line(traffic_daily, "Date", "Sessions", "Daily Sessions")
        plot_line(traffic_daily, "Date", "Visitors", "Daily Visitors")
        st.dataframe(traffic_daily.sort_values("Date", ascending=False), use_container_width=True)

# ------------------------- Meta / Marketing -------------------------
with tabs[5]:
    st.markdown('<div class="section-title">📣 Meta / Marketing</div>', unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    with m1: card("Total Ad Spend", format_tl(ad_spend), "Meta invoice")
    with m2: card("Total Ad Revenue", format_tl(ad_revenue), "Manual input")
    with m3: card("ROAS", "N/A" if pd.isna(roas) else f"{roas:.2f}x", "Ad Revenue / Spend")
    with m4: card("MER", "N/A" if pd.isna(mer) else f"{mer:.2f}x", "Revenue / Spend")

    if meta_payments.empty:
        st.info("Meta payment data bulunamadı.")
    else:
        meta_daily = meta_payments.copy()
        meta_daily["Date"] = pd.to_datetime(meta_daily["Date"]).dt.date
        meta_daily = meta_daily.groupby("Date", as_index=False).agg(Spend=("Spend", "sum"))
        plot_bar(meta_daily, "Date", "Spend", "Daily Meta Spend")
        st.dataframe(meta_payments.sort_values("Date", ascending=False), use_container_width=True)

# ------------------------- Orders -------------------------
with tabs[6]:
    st.markdown('<div class="section-title">🧾 Orders</div>', unsafe_allow_html=True)
    if filtered_orders.empty:
        st.info("Order verisi bulunamadı.")
    else:
        status_summary = filtered_orders.groupby("Financial Status", as_index=False).agg(Orders=("Order", "nunique"), Revenue=("Revenue", "sum"), Refunds=("Refunded Amount", "sum"))
        st.subheader("Status Summary")
        st.dataframe(status_summary, use_container_width=True)

        st.subheader("Order List")
        order_cols = ["Order", "Date", "Email", "Financial Status", "Total", "Refunded Amount", "Revenue", "Source"]
        available = [c for c in order_cols if c in filtered_orders.columns]
        show_orders = filtered_orders[available].sort_values("Date", ascending=False).copy()
        st.dataframe(show_orders, use_container_width=True)

        csv_data = show_orders.to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download filtered orders CSV", csv_data, "filtered_orders_report.csv", "text/csv")

# ------------------------- Data Quality -------------------------
with tabs[7]:
    st.markdown('<div class="section-title">🧪 Data Quality</div>', unsafe_allow_html=True)
    all_warnings = []
    all_warnings += [f"Orders: {w}" for w in orders.warnings]
    all_warnings += [f"Costs: {w}" for w in costs.warnings]
    all_warnings += [f"Meta: {w}" for w in meta.warnings]
    all_warnings += [f"Traffic: {w}" for w in traffic.warnings]

    # Automatic checks
    if not filtered_lines.empty:
        empty_sku_units = float(filtered_lines.loc[filtered_lines["__sku"].eq(""), "__qty"].sum())
        if empty_sku_units > 0:
            all_warnings.append(f"{empty_sku_units:,.0f} unit için SKU boş. Bunlar maliyetle eşleşemez.")
    if not pd.isna(cost_match_rate) and cost_match_rate < 0.85:
        all_warnings.append(f"Cost Match Rate düşük: {cost_match_rate*100:.1f}%. Profit raporu eksik maliyet yüzünden yüksek görünebilir.")
    if ad_spend > 0 and ad_revenue == 0:
        all_warnings.append("Meta harcaması var fakat Meta attributed revenue girilmemiş. ROAS N/A kalır; MER yine hesaplanır.")
    if total_inventory_units == 0:
        all_warnings.append("Inventory/stok kolonu bulunmadığı için Total Inventory Units ve Low Stock Items 0 görünüyor.")

    if all_warnings:
        for w in all_warnings:
            msg_box("warn", w)
    else:
        msg_box("ok", "Kritik veri kalite uyarısı bulunmadı.")

    st.subheader("Quality Numbers")
    qrows = [
        {"Metric": "Raw order-level rows", "Value": orders.info.get("order_rows", 0)},
        {"Metric": "Valid orders", "Value": order_count},
        {"Metric": "Line rows used", "Value": int(filtered_lines.shape[0]) if not filtered_lines.empty else 0},
        {"Metric": "Units sold", "Value": units_sold},
        {"Metric": "Matched units", "Value": matched_units},
        {"Metric": "Cost match rate", "Value": None if pd.isna(cost_match_rate) else f"{cost_match_rate*100:.1f}%"},
        {"Metric": "Meta payments", "Value": int(meta_payments.shape[0]) if not meta_payments.empty else 0},
        {"Metric": "Traffic days", "Value": int(traffic_daily.shape[0]) if not traffic_daily.empty else 0},
    ]
    st.dataframe(pd.DataFrame(qrows), use_container_width=True)
