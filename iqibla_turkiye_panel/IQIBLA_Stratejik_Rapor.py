# -*- coding: utf-8 -*-
"""
IQIBLA Türkiye - Stratejik Performans Karargahı

Bu dosyayı Streamlit projenizde şu konuma koyun:
    pages/IQIBLA_Stratejik_Rapor.py

Gerekli paketler:
    streamlit
    pandas
    numpy
    openpyxl  # Excel export için

Mantık:
- Shopify sipariş CSV'leri
- Hepsiburada ürün/satış CSV'leri
- Shopify / Hepsiburada maliyet tabloları
- Meta kampanya raporları ve/veya Meta fatura raporu
- Opsiyonel stok dosyası ve iş birliği dosyası
tek ekranda okunur, normalize edilir ve birleşik KPI raporu çıkarılır.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="IQIBLA Stratejik Rapor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# BASIC HELPERS
# =========================================================
def tr_norm(text: object) -> str:
    """Column eşleştirmesi için Türkçe karakterlerden bağımsız normalize eder."""
    if text is None:
        return ""
    s = str(text).strip().lower()
    repl = str.maketrans({
        "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    })
    s = s.translate(repl)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Farklı panel kolon isimlerini güvenli şekilde bulur."""
    if df is None or df.empty:
        return None
    norm_map = {tr_norm(c): c for c in df.columns}
    # exact-ish
    for cand in candidates:
        key = tr_norm(cand)
        if key in norm_map:
            return norm_map[key]
    # substring
    for cand in candidates:
        key = tr_norm(cand)
        for n, real in norm_map.items():
            if key and key in n:
                return real
    return None


def smart_float(x: object, default: float = 0.0) -> float:
    """TR/US sayı formatlarını okur: 14.433,11 / 4290.00 / 0,15 / %0.024."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return default
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)

    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return default

    s = (
        s.replace("\xa0", "")
        .replace("TRY", "")
        .replace("TL", "")
        .replace("₺", "")
        .replace("%", "")
        .replace(" ", "")
        .strip()
    )
    s = s.lstrip("'")

    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")

    if "," in s and "." in s:
        # Son ayırıcı virgülse: 14.433,11 -> 14433.11
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")

    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return default


def smart_int(x: object, default: int = 0) -> int:
    return int(round(smart_float(x, default=float(default))))


def clean_sku(x: object) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none"}:
        return ""
    s = s.replace("'", "").replace(" ", "")
    # Excel/Pandas kaynaklı 6970126922170.0 gibi değerleri temizle
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def parse_date_series(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce", utc=True)
    try:
        dt = dt.dt.tz_convert("Europe/Istanbul").dt.tz_localize(None)
    except Exception:
        try:
            dt = pd.to_datetime(s, errors="coerce")
        except Exception:
            pass
    return dt


def fmt_money(x: float) -> str:
    try:
        return f"₺{float(x):,.0f}".replace(",", ".")
    except Exception:
        return "₺0"


def fmt_money_2(x: float) -> str:
    try:
        s = f"₺{float(x):,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "₺0,00"


def fmt_pct(x: float) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "0,0%"


def not_empty_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().ne("")


def first_non_empty(series: pd.Series) -> object:
    for v in series:
        if pd.notna(v) and str(v).strip() != "":
            return v
    return ""


def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe = re.sub(r"[^A-Za-z0-9_ğüşöçıİĞÜŞÖÇ -]", "", name)[:31] or "Sheet"
            df.to_excel(writer, index=False, sheet_name=safe)
    return output.getvalue()


# =========================================================
# CSV READING
# =========================================================
def decode_bytes(data: bytes) -> Tuple[str, str]:
    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    best_text, best_enc, best_score = "", "utf-8", 10**9
    for enc in encodings:
        try:
            text = data.decode(enc)
            # replacement char yok + mojibake az olsun
            score = text.count("�") * 1000 + text.count("Ã") * 5 + text.count("Ä") * 5 + text.count("Å") * 5
            if score < best_score:
                best_text, best_enc, best_score = text, enc, score
        except Exception:
            continue
    if not best_text:
        best_text = data.decode("latin1", errors="replace")
        best_enc = "latin1"
    return best_text, best_enc


def read_shopify_special(text: str) -> pd.DataFrame:
    """Bazı Shopify exportlarında satır komple tırnak içine giriyor. Bunu düzeltir."""
    lines = text.splitlines()
    if not lines:
        return pd.DataFrame()
    header = next(csv.reader([lines[0]]))
    rows: List[List[str]] = []

    for raw in lines[1:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = list(csv.reader([raw]))[0]
        except Exception:
            parsed = []
        if len(parsed) == 1 and "," in parsed[0]:
            try:
                parsed = list(csv.reader([parsed[0]]))[0]
            except Exception:
                parsed = parsed[0].split(",")
        if len(parsed) < len(header):
            parsed += [""] * (len(header) - len(parsed))
        elif len(parsed) > len(header):
            parsed = parsed[: len(header)]
        rows.append(parsed)

    return pd.DataFrame(rows, columns=header)


def read_csv_flexible(name: str, data: bytes) -> Tuple[pd.DataFrame, str, str, List[str]]:
    """CSV'yi en yüksek ihtimalle doğru ayırıcı/encoding ile okur."""
    warnings: List[str] = []
    text, enc = decode_bytes(data)
    first_line = text.splitlines()[0] if text.splitlines() else ""

    # Shopify header varsa özel parser kullan
    if "Financial Status" in first_line and "Lineitem" in first_line:
        try:
            df = read_shopify_special(text)
            return df, enc, "shopify_special", warnings
        except Exception as e:
            warnings.append(f"Shopify özel parser başarısız oldu: {e}")

    # Meta fatura gibi düz olmayan dosyalarda yine DataFrame boş dönebilir; invoice ayrıca parse edilecek.
    seps = [";", ",", "\t"]
    best_df = pd.DataFrame()
    best_sep = ","
    best_cols = 0
    for sep in seps:
        try:
            df = pd.read_csv(io.BytesIO(data), sep=sep, encoding=enc, engine="python", dtype=str, on_bad_lines="skip")
            df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
            if len(df.columns) > best_cols:
                best_df, best_sep, best_cols = df, sep, len(df.columns)
        except Exception:
            continue

    if best_df.empty and text.strip():
        # En kötü ihtimal tek kolon olarak oku
        best_df = pd.DataFrame({"raw": text.splitlines()})
        best_sep = "raw"

    return best_df, enc, best_sep, warnings


# =========================================================
# FILE CLASSIFICATION
# =========================================================
def classify_df(df: pd.DataFrame, raw_text: str, file_name: str) -> str:
    cols = [tr_norm(c) for c in df.columns]
    joined = " ".join(cols)
    raw_norm = tr_norm(raw_text[:3000])
    name_norm = tr_norm(file_name)

    if "metareklamlarodemes" in raw_norm or ("faturaraporu" in raw_norm and "meta" in raw_norm):
        return "meta_invoice"

    if all(k in joined for k in ["financialstatus", "lineitemquantity", "createdat"]):
        return "shopify_orders"

    if "maliyet" in joined and "kargo" in joined and "sku" in joined:
        return "cost_table"

    if "toplamsatisadedi" in joined and "toplamsatistutari" in joined and "sku" in joined:
        return "hb_sales"

    if "iademiktari" in joined and "iadesebebi" in joined:
        return "returns"

    if "toplamgoruntulenmesayisi" in joined and "sepeteeklenmesayisi" in joined:
        return "traffic_product"

    if "harcanantutar" in joined and ("kampanyaadi" in joined or "campaignname" in joined):
        return "meta_campaign"

    if "oturumlar" in joined and "odemeyitamamlayanoturumlar" in joined:
        return "shopify_funnel"

    if "onlinemagazaziyaretcileri" in joined or "oturumulkesi" in joined:
        return "shopify_region"

    if "brutsatislar" in joined or "grosssales" in joined:
        return "shopify_monthly_sales"

    if "stok" in joined and "sku" in joined:
        return "stock"

    if any(k in joined for k in ["influencer", "isbirligi", "utm", "coupon", "kupon", "discountcode"]):
        return "collaboration"

    if "shopify" in name_norm:
        return "shopify_other"
    if "hepsiburada" in name_norm:
        return "hb_other"
    if "meta" in name_norm or "kampanya" in name_norm:
        return "meta_other"
    return "unknown"


@dataclass
class ParsedFile:
    name: str
    kind: str
    df: pd.DataFrame
    text: str
    encoding: str
    sep: str
    warnings: List[str]


# =========================================================
# NORMALIZERS
# =========================================================
def normalize_cost_table(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    sku_c = find_col(df, "SKU", "SaticiSKU", "Satıcı SKU")
    platform_c = find_col(df, "Platform", "Kanal")
    commission_c = find_col(df, "Komisyon oran", "Komisyon oran?", "Commission")
    cost_c = find_col(df, "Maliyet", "Maliyet (Alış)", "Alış")
    cargo_c = find_col(df, "Kargo", "Shipping")
    vat_c = find_col(df, "KDV Oran", "KDV", "VAT")

    out = pd.DataFrame()
    out["sku"] = df[sku_c].map(clean_sku) if sku_c else ""
    out["platform"] = df[platform_c].fillna("").astype(str).str.strip() if platform_c else ""
    out["commission_rate"] = df[commission_c].map(smart_float) if commission_c else 0.0
    # 15 yazılırsa 0.15'e çevir
    out.loc[out["commission_rate"] > 1, "commission_rate"] = out.loc[out["commission_rate"] > 1, "commission_rate"] / 100
    out["unit_cost"] = df[cost_c].map(smart_float) if cost_c else 0.0
    out["shipping_cost"] = df[cargo_c].map(smart_float) if cargo_c else 0.0
    out["vat_rate"] = df[vat_c].map(smart_float) if vat_c else 0.20
    out.loc[out["vat_rate"] > 1, "vat_rate"] = out.loc[out["vat_rate"] > 1, "vat_rate"] / 100
    out["source_file"] = source_name
    out = out[out["sku"].ne("")].drop_duplicates(subset=["platform", "sku"], keep="last")
    return out


def normalize_shopify_orders(df: pd.DataFrame, source_name: str, include_pending: bool) -> Tuple[pd.DataFrame, pd.DataFrame]:
    name_c = find_col(df, "Name")
    email_c = find_col(df, "Email")
    status_c = find_col(df, "Financial Status")
    created_c = find_col(df, "Created at", "Paid at")
    qty_c = find_col(df, "Lineitem quantity")
    product_c = find_col(df, "Lineitem name")
    sku_c = find_col(df, "Lineitem sku")
    line_price_c = find_col(df, "Lineitem price")
    line_discount_c = find_col(df, "Lineitem discount")
    total_c = find_col(df, "Total")
    tax_c = find_col(df, "Taxes", "Tax 1 Value")
    shipping_c = find_col(df, "Shipping")
    discount_code_c = find_col(df, "Discount Code")
    refunded_c = find_col(df, "Refunded Amount")
    cancelled_c = find_col(df, "Cancelled at")

    if not name_c or not qty_c:
        return pd.DataFrame(), pd.DataFrame()

    d = df.copy()
    d["order_id"] = d[name_c].fillna("").astype(str).str.strip()
    for col in [email_c, status_c, created_c, total_c, tax_c, shipping_c, discount_code_c, refunded_c, cancelled_c]:
        if col and col in d.columns:
            d[col] = d.groupby("order_id")[col].transform(first_non_empty)

    d["order_date"] = parse_date_series(d[created_c]) if created_c else pd.NaT
    d["customer_key"] = d[email_c].fillna("").astype(str).str.strip().str.lower() if email_c else ""
    d["payment_status"] = d[status_c].fillna("").astype(str).str.strip().str.lower() if status_c else ""
    d["cancelled_at"] = d[cancelled_c].fillna("").astype(str).str.strip() if cancelled_c else ""

    valid_status = ["paid", "partially_refunded"]
    if include_pending:
        valid_status.append("pending")
    d = d[d["payment_status"].isin(valid_status)]
    d = d[d["cancelled_at"].eq("")]

    d["quantity"] = d[qty_c].map(smart_float) if qty_c else 0.0
    d["product_name"] = d[product_c].fillna("").astype(str).str.strip() if product_c else ""
    d["sku"] = d[sku_c].map(clean_sku) if sku_c else ""
    d["line_price"] = d[line_price_c].map(smart_float) if line_price_c else 0.0
    d["line_discount"] = d[line_discount_c].map(smart_float) if line_discount_c else 0.0
    d["line_revenue_incl_vat"] = (d["line_price"] * d["quantity"] - d["line_discount"]).clip(lower=0)
    d["discount_code"] = d[discount_code_c].fillna("").astype(str).str.strip() if discount_code_c else ""
    d["source_file"] = source_name
    d["platform"] = "Shopify"

    # Order level: Total sadece bir kez sayılmalı
    order_base = d[["order_id", "order_date", "customer_key", "payment_status", "discount_code", "source_file"]].drop_duplicates("order_id")
    total_map = d.drop_duplicates("order_id").set_index("order_id")
    order_base["order_revenue_incl_vat"] = order_base["order_id"].map(total_map[total_c].map(smart_float) if total_c else pd.Series(dtype=float)).fillna(0)
    order_base["tax_amount"] = order_base["order_id"].map(total_map[tax_c].map(smart_float) if tax_c else pd.Series(dtype=float)).fillna(0)
    order_base["shipping_revenue"] = order_base["order_id"].map(total_map[shipping_c].map(smart_float) if shipping_c else pd.Series(dtype=float)).fillna(0)
    order_base["refunded_amount"] = order_base["order_id"].map(total_map[refunded_c].map(smart_float) if refunded_c else pd.Series(dtype=float)).fillna(0)
    order_base["order_revenue_incl_vat"] = (order_base["order_revenue_incl_vat"] - order_base["refunded_amount"]).clip(lower=0)
    order_base["platform"] = "Shopify"

    line_cols = [
        "platform", "source_file", "order_id", "order_date", "customer_key", "payment_status", "discount_code",
        "sku", "product_name", "quantity", "line_revenue_incl_vat",
    ]
    lines = d[d["quantity"] > 0][line_cols].copy()
    lines["is_service_fee"] = lines["product_name"].str.lower().str.contains("kapıda ödeme|cash on delivery|cod fee", regex=True, na=False)
    return lines, order_base


def normalize_hb_sales(df: pd.DataFrame, source_name: str, report_day: date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    sku_c = find_col(df, "SKU")
    seller_sku_c = find_col(df, "SaticiSKU", "SatıcıSKU", "Satıcı SKU")
    product_c = find_col(df, "Urun Adi", "Ürün Adı")
    qty_c = find_col(df, "Toplam Satis Adedi", "Toplam Satış Adedi")
    rev_c = find_col(df, "Toplam Satis Tutari", "Toplam Satış Tutarı")
    comm_c = find_col(df, "Komisyon(%)", "Komisyon")

    if not sku_c or not qty_c or not rev_c:
        return pd.DataFrame(), pd.DataFrame()

    out = pd.DataFrame()
    out["platform"] = "Hepsiburada"
    out["source_file"] = source_name
    out["order_id"] = "HB-" + source_name + "-" + df.index.astype(str)
    out["order_date"] = pd.to_datetime(report_day)
    out["customer_key"] = ""
    out["payment_status"] = "aggregated"
    out["discount_code"] = ""
    out["sku"] = df[sku_c].map(clean_sku)
    out["seller_sku"] = df[seller_sku_c].map(clean_sku) if seller_sku_c else ""
    out["product_name"] = df[product_c].fillna("").astype(str).str.strip() if product_c else out["sku"]
    out["quantity"] = df[qty_c].map(smart_float)
    out["line_revenue_incl_vat"] = df[rev_c].map(smart_float)
    out["commission_rate_from_report"] = df[comm_c].map(smart_float) if comm_c else 0.0
    out.loc[out["commission_rate_from_report"] > 1, "commission_rate_from_report"] /= 100
    out["is_service_fee"] = False
    out = out[(out["sku"].ne("")) & (out["quantity"] > 0)]

    orders = out[["platform", "source_file", "order_id", "order_date", "customer_key", "payment_status", "discount_code"]].copy()
    orders["order_revenue_incl_vat"] = out["line_revenue_incl_vat"]
    orders["tax_amount"] = 0.0
    orders["shipping_revenue"] = 0.0
    orders["refunded_amount"] = 0.0
    return out, orders


def normalize_meta_campaign(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    campaign_c = find_col(df, "Kampanya Adı", "Campaign name", "Campaign")
    adset_c = find_col(df, "Reklam Seti Adı", "Ad set name")
    ad_c = find_col(df, "Reklam Adı", "Ad name", "Kreatif", "Creative")
    spend_c = find_col(df, "Harcanan Tutar", "Amount spent", "Spend")
    reach_c = find_col(df, "Erişim", "Reach")
    imp_c = find_col(df, "Gösterim", "Impressions")
    click_c = find_col(df, "Tıklamalar", "Clicks")
    purchase_c = find_col(df, "Alışverişler", "Purchases")
    roas_c = find_col(df, "Alışveriş Reklam Harcamasının Getirisi", "ROAS")
    start_c = find_col(df, "Rapor Başlangıcı", "Reporting starts", "Start")
    end_c = find_col(df, "Rapor Sonu", "Reporting ends", "End")
    ctr_c = find_col(df, "CTR")
    cpm_c = find_col(df, "CPM")

    out = pd.DataFrame()
    out["source_file"] = source_name
    out["campaign_name"] = df[campaign_c].fillna("").astype(str).str.strip() if campaign_c else "Bilinmeyen Kampanya"
    out["adset_name"] = df[adset_c].fillna("").astype(str).str.strip() if adset_c else ""
    out["creative_name"] = df[ad_c].fillna("").astype(str).str.strip() if ad_c else out["campaign_name"]
    out["spend"] = df[spend_c].map(smart_float) if spend_c else 0.0
    out["reach"] = df[reach_c].map(smart_float) if reach_c else 0.0
    out["impressions"] = df[imp_c].map(smart_float) if imp_c else 0.0
    out["clicks"] = df[click_c].map(smart_float) if click_c else 0.0
    out["purchases"] = df[purchase_c].map(smart_float) if purchase_c else 0.0
    out["reported_roas"] = df[roas_c].map(smart_float) if roas_c else np.nan
    out["ctr"] = df[ctr_c].map(smart_float) / 100 if ctr_c else np.nan
    out["cpm"] = df[cpm_c].map(smart_float) if cpm_c else np.nan
    out["start_date"] = pd.to_datetime(df[start_c], errors="coerce") if start_c else pd.NaT
    out["end_date"] = pd.to_datetime(df[end_c], errors="coerce") if end_c else pd.NaT
    out = out[out["spend"] > 0]
    return out


def normalize_meta_invoice(text: str, source_name: str) -> pd.DataFrame:
    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if tr_norm(line).startswith("tarihislemkodu") or ("Tarih" in line and "Tutar" in line and "Para" in line):
            start_idx = i
            break
    if start_idx is None:
        return pd.DataFrame()

    rows = []
    for raw in lines[start_idx + 1:]:
        if not raw.strip():
            # Meta invoice devamında boşluk sonrası başka bölümler olabilir; çok erken kırma yapmayalım
            continue
        if raw.lower().startswith("toplam") or "ödenmesi gereken" in raw.lower():
            continue
        try:
            parsed = list(csv.reader([raw]))[0]
            if len(parsed) == 1 and "," in parsed[0]:
                parsed = list(csv.reader([parsed[0]]))[0]
        except Exception:
            parsed = raw.split(",")
        if len(parsed) < 4:
            continue
        date_raw = parsed[0]
        amount_raw = parsed[3] if len(parsed) >= 4 else "0"
        dt = pd.to_datetime(date_raw, format="%d.%m.%Y", errors="coerce")
        amount = smart_float(amount_raw)
        if pd.notna(dt) and amount > 0:
            rows.append({"source_file": source_name, "date": dt, "spend": amount, "currency": parsed[-1] if parsed else "TRY"})
    return pd.DataFrame(rows)


def normalize_traffic_product(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    sku_c = find_col(df, "SKU")
    view_c = find_col(df, "Toplam Goruntulenme Sayisi", "Görüntülenme")
    visitor_c = find_col(df, "Goruntuleyen Musteri Sayisi", "Görüntüleyen")
    cart_c = find_col(df, "Sepete Eklenme Sayisi", "Sepete")
    sales_c = find_col(df, "Satis Miktari", "Satış Miktarı")
    conv_c = find_col(df, "Satisa Donme Orani", "Dönme Oranı")
    out = pd.DataFrame()
    out["source_file"] = source_name
    out["sku"] = df[sku_c].map(clean_sku) if sku_c else ""
    out["views"] = df[view_c].map(smart_float) if view_c else 0.0
    out["visitors"] = df[visitor_c].map(smart_float) if visitor_c else 0.0
    out["cart_adds"] = df[cart_c].map(smart_float) if cart_c else 0.0
    out["sales_qty"] = df[sales_c].map(smart_float) if sales_c else 0.0
    if conv_c:
        raw = df[conv_c].fillna("").astype(str)
        out["conversion_rate"] = raw.map(lambda x: smart_float(x) / 100 if "%" in x else smart_float(x))
    else:
        out["conversion_rate"] = np.where(out["views"] > 0, out["sales_qty"] / out["views"], 0)
    return out[out["sku"].ne("")]


def normalize_returns(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    sku_c = find_col(df, "SKU")
    seller_sku_c = find_col(df, "SaticiSKU", "SatıcıSKU")
    product_c = find_col(df, "Urun Adi", "Ürün Adı")
    reason_c = find_col(df, "Iade Sebebi", "İade Sebebi")
    qty_c = find_col(df, "Iade Miktari", "İade Miktarı")
    loss_c = find_col(df, "Tahmini satis kaybi", "Tahmini satış kaybı")
    out = pd.DataFrame()
    out["source_file"] = source_name
    out["sku"] = df[sku_c].map(clean_sku) if sku_c else ""
    out["seller_sku"] = df[seller_sku_c].map(clean_sku) if seller_sku_c else ""
    out["product_name"] = df[product_c].fillna("").astype(str).str.strip() if product_c else out["sku"]
    out["return_reason"] = df[reason_c].fillna("").astype(str).str.strip() if reason_c else ""
    out["return_qty"] = df[qty_c].map(smart_float) if qty_c else 0.0
    out["estimated_sales_loss"] = df[loss_c].map(smart_float) if loss_c else 0.0
    return out[out["return_qty"] > 0]


def normalize_funnel(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    month_c = find_col(df, "Ay", "Month")
    sessions_c = find_col(df, "Oturumlar", "Sessions")
    cart_c = find_col(df, "Sepete ekleme yapılan oturumlar", "cart additions")
    checkout_c = find_col(df, "Ödeme sayfasına ulaşan oturumlar", "checkout")
    completed_c = find_col(df, "Ödemeyi tamamlayan oturumlar", "completed checkout")
    conv_c = find_col(df, "Dönüşüm oranı", "Conversion rate")
    out = pd.DataFrame()
    out["source_file"] = source_name
    out["period"] = pd.to_datetime(df[month_c], errors="coerce") if month_c else pd.NaT
    out["sessions"] = df[sessions_c].map(smart_float) if sessions_c else 0.0
    out["cart_sessions"] = df[cart_c].map(smart_float) if cart_c else 0.0
    out["checkout_sessions"] = df[checkout_c].map(smart_float) if checkout_c else 0.0
    out["completed_sessions"] = df[completed_c].map(smart_float) if completed_c else 0.0
    out["conversion_rate"] = df[conv_c].map(smart_float) if conv_c else np.where(out["sessions"] > 0, out["completed_sessions"] / out["sessions"], 0)
    return out


def normalize_stock(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    sku_c = find_col(df, "SKU", "Barkod", "Barcode")
    stock_c = find_col(df, "Stok", "Stock", "Available")
    product_c = find_col(df, "Ürün", "Urun", "Product", "Title", "Name")
    out = pd.DataFrame()
    out["source_file"] = source_name
    out["sku"] = df[sku_c].map(clean_sku) if sku_c else ""
    out["product_name"] = df[product_c].fillna("").astype(str).str.strip() if product_c else ""
    out["stock_qty"] = df[stock_c].map(smart_float) if stock_c else 0.0
    return out[out["sku"].ne("")]


def normalize_collaboration(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    name_c = find_col(df, "İş Birliği", "Isbirligi", "Influencer", "Creator", "Partner", "Kanal")
    code_c = find_col(df, "Kupon", "Coupon", "Discount Code", "Kod")
    spend_c = find_col(df, "Maliyet", "Cost", "Ücret", "Fee")
    revenue_c = find_col(df, "Ciro", "Revenue", "Sales")
    order_c = find_col(df, "Sipariş", "Orders")
    out = pd.DataFrame()
    out["source_file"] = source_name
    out["partner_name"] = df[name_c].fillna("").astype(str).str.strip() if name_c else "Bilinmeyen"
    out["discount_code"] = df[code_c].fillna("").astype(str).str.strip() if code_c else ""
    out["cost"] = df[spend_c].map(smart_float) if spend_c else 0.0
    out["revenue"] = df[revenue_c].map(smart_float) if revenue_c else 0.0
    out["orders"] = df[order_c].map(smart_float) if order_c else 0.0
    return out


# =========================================================
# ENRICHMENT AND KPI
# =========================================================
def enrich_sales_with_costs(lines: pd.DataFrame, costs: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if lines.empty:
        return lines, pd.DataFrame()
    d = lines.copy()
    d["sku"] = d["sku"].map(clean_sku)

    if costs.empty:
        d["commission_rate"] = np.where(d["platform"].eq("Shopify"), 0.01, 0.15)
        d["unit_cost"] = 0.0
        d["shipping_cost"] = 0.0
        d["vat_rate"] = 0.20
    else:
        c = costs.copy()
        c["sku"] = c["sku"].map(clean_sku)
        c["platform_norm"] = c["platform"].fillna("").astype(str).str.lower().str.strip()
        d["platform_norm"] = d["platform"].fillna("").astype(str).str.lower().str.strip()
        d = d.merge(
            c[["platform_norm", "sku", "commission_rate", "unit_cost", "shipping_cost", "vat_rate"]],
            on=["platform_norm", "sku"],
            how="left",
        )
        # Platform yoksa SKU üzerinden ikinci şans
        missing = d["unit_cost"].isna() & d["sku"].ne("")
        if missing.any():
            c2 = c.drop_duplicates("sku").set_index("sku")
            for col in ["commission_rate", "unit_cost", "shipping_cost", "vat_rate"]:
                d.loc[missing, col] = d.loc[missing, "sku"].map(c2[col])
        d.drop(columns=["platform_norm"], inplace=True, errors="ignore")
        d["commission_rate"] = d["commission_rate"].fillna(np.where(d["platform"].eq("Shopify"), 0.01, 0.15))
        d["unit_cost"] = d["unit_cost"].fillna(0.0)
        d["shipping_cost"] = d["shipping_cost"].fillna(0.0)
        d["vat_rate"] = d["vat_rate"].fillna(0.20)

    d["kdv_amount"] = d["line_revenue_incl_vat"] * d["vat_rate"] / (1 + d["vat_rate"])
    d["net_revenue_ex_vat"] = d["line_revenue_incl_vat"] - d["kdv_amount"]
    d["product_cost_total"] = d["unit_cost"] * d["quantity"]
    d["shipping_cost_total"] = d["shipping_cost"] * d["quantity"]
    d["commission_amount"] = d["line_revenue_incl_vat"] * d["commission_rate"]
    d["profit_before_ads"] = (
        d["net_revenue_ex_vat"]
        - d["product_cost_total"]
        - d["shipping_cost_total"]
        - d["commission_amount"]
    )

    missing_costs = d[(d["sku"].ne("")) & (d["unit_cost"].eq(0))][["platform", "sku", "product_name", "quantity"]].drop_duplicates()
    return d, missing_costs


def build_daily_forecast(orders: pd.DataFrame, window: int, days: int = 30) -> Tuple[pd.DataFrame, float, float]:
    if orders.empty or "order_date" not in orders:
        return pd.DataFrame(), 0.0, 0.0
    o = orders.dropna(subset=["order_date"]).copy()
    if o.empty:
        return pd.DataFrame(), 0.0, 0.0
    o["date"] = pd.to_datetime(o["order_date"]).dt.date
    daily = o.groupby("date", as_index=False).agg(
        revenue=("order_revenue_incl_vat", "sum"),
        orders=("order_id", "nunique"),
    )
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date")
    tail = daily.tail(max(1, min(window, len(daily))))
    avg_rev = tail["revenue"].mean() if not tail.empty else 0.0
    avg_orders = tail["orders"].mean() if not tail.empty else 0.0
    last_day = daily["date"].max() if not daily.empty else pd.Timestamp.today()
    future = pd.DataFrame({"date": pd.date_range(last_day + pd.Timedelta(days=1), periods=days, freq="D")})
    future["forecast_revenue"] = avg_rev
    future["forecast_orders"] = avg_orders
    return future, avg_rev * days, avg_orders * days


def make_ai_note(kpi: Dict[str, float], channel_profit: pd.DataFrame, dead_stock: pd.DataFrame, forecast_rev_30: float) -> str:
    notes = []
    if kpi.get("profit_before_ads", 0) < 0:
        notes.append("Ürün/maliyet tarafında reklam hariç kâr negatife düşüyor; öncelik maliyet, komisyon ve satış fiyatı kontrolü olmalı.")
    if kpi.get("ad_spend", 0) > 0 and kpi.get("mer", 0) > 0.35:
        notes.append("Reklam harcaması ciroya göre yüksek görünüyor; kampanya ROAS ve CAC kırılımı kontrol edilmeli.")
    if not channel_profit.empty:
        best = channel_profit.sort_values("profit_before_ads", ascending=False).iloc[0]
        worst = channel_profit.sort_values("profit_before_ads", ascending=True).iloc[0]
        notes.append(f"En güçlü kanal şu an {best['platform']}; en zayıf kanal {worst['platform']} görünüyor.")
    if not dead_stock.empty:
        notes.append(f"Ölü stok / düşük dönüşüm alarmında {len(dead_stock)} ürün var; bu ürünlerde kampanya, fiyat veya listeleme revizyonu gerekir.")
    if forecast_rev_30 > 0:
        notes.append(f"Mevcut tempoya göre 30 günlük ciro tahmini yaklaşık {fmt_money(forecast_rev_30)}.")
    if not notes:
        notes.append("Yüklenen dosyalara göre kritik alarm görünmüyor; daha sağlıklı yorum için stok, Meta kampanya ve maliyet dosyaları birlikte yüklenmeli.")
    return " ".join(notes)


# =========================================================
# UI
# =========================================================
st.markdown(
    """
    <style>
        .main .block-container {padding-top: 1.4rem;}
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(212,175,55,0.22);
            padding: 14px 16px;
            border-radius: 18px;
        }
        .small-muted {color: rgba(255,255,255,.63); font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📊 IQIBLA Stratejik Performans Karargâhı")
st.caption("Günlük CSV dosyalarını yükle, sistem platform bazlı ve toplu raporları otomatik oluştursun.")

with st.sidebar:
    st.header("1) CSV Yükleme")
    uploads = st.file_uploader(
        "Shopify, Hepsiburada, Meta, maliyet, stok ve iade CSV dosyalarını yükle",
        type=["csv"],
        accept_multiple_files=True,
    )

    st.divider()
    st.header("2) Rapor Ayarları")
    default_report_date = st.date_input("Tarih içermeyen dosyalara atanacak tarih", value=date.today())
    include_pending = st.checkbox("Shopify pending / COD siparişleri dahil et", value=True)
    exclude_service_from_top = st.checkbox("Top-seller listesinde kapıda ödeme ücretlerini gizle", value=True)

    target_revenue = st.number_input("Ciro hedefi (₺)", min_value=0.0, value=0.0, step=1000.0)
    target_orders = st.number_input("Sipariş hedefi", min_value=0, value=0, step=1)

    manual_ad_revenue = st.number_input(
        "Reklam kaynaklı gelir / attribution geliri (opsiyonel)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Meta dosyasında ROAS geliri yoksa kampanya ROAS hesaplamak için kullanılır.",
    )

    forecast_window = st.slider("Tahmin için son kaç gün ortalaması?", min_value=3, max_value=30, value=7)
    lead_time_days = st.number_input("Stok besleme lead time günü", min_value=1, value=14, step=1)
    safety_stock_days = st.number_input("Güvenlik stoğu günü", min_value=0, value=7, step=1)

    st.divider()
    st.header("3) Dosya klasörü")
    read_local_data = st.checkbox(
        "Projede data/raw klasörü varsa onu da oku",
        value=True,
        help="GitHub repo içine data/raw klasörü açıp CSV koyarsan, panel onları otomatik okur.",
    )


# Load uploaded + optional local files
raw_sources: List[Tuple[str, bytes]] = []
if uploads:
    for u in uploads:
        raw_sources.append((u.name, u.getvalue()))

if read_local_data:
    raw_dir = Path("data/raw")
    if raw_dir.exists():
        for p in sorted(raw_dir.glob("*.csv")):
            try:
                raw_sources.append((f"data/raw/{p.name}", p.read_bytes()))
            except Exception:
                pass

if not raw_sources:
    st.info(
        "Henüz CSV yüklenmedi. Başlamak için sol taraftan Shopify sipariş, Hepsiburada satış, maliyet ve Meta kampanya/fatura dosyalarını yükle."
    )
    st.markdown(
        """
        **Bu panelin doğrudan hesaplayabildiği raporlar:** Net Ciro, Sipariş Adedi, Hedef Gerçekleşme, Anlık Net Kâr, Top-Seller, Kanal Karlılığı, ROAS, CAC, Yeni/Geri Gelen Müşteri, AOV, LTV, KDV, Erişim vs. Dönüşüm, 30 Günlük Tahmin, Nakit Akış ve AI Notu.

        **Ek veri gerekebilecek alanlar:** Ölü Stok Alarmı ve Stok Besleme için stok CSV; Kreatif Karnesi için reklam/ad/creative kırılımı; İş Birliği Performansı için influencer/kupon/UTM dosyası gerekir.
        """
    )
    st.stop()

parsed: List[ParsedFile] = []
for name, data in raw_sources:
    df, enc, sep, warnings = read_csv_flexible(name, data)
    text, _ = decode_bytes(data)
    kind = classify_df(df, text, name)
    parsed.append(ParsedFile(name=name, kind=kind, df=df, text=text, encoding=enc, sep=sep, warnings=warnings))

# Report date mapping for aggregate files
needs_date = [p for p in parsed if p.kind in {"hb_sales"}]
file_dates: Dict[str, date] = {}
if needs_date:
    with st.sidebar.expander("Hepsiburada gibi tarih içermeyen dosyalar", expanded=False):
        for p in needs_date:
            file_dates[p.name] = st.date_input(f"{p.name} tarihi", value=default_report_date, key=f"date_{p.name}")

with st.expander("Okunan dosya özeti", expanded=False):
    summary_df = pd.DataFrame([
        {
            "Dosya": p.name,
            "Tür": p.kind,
            "Satır": len(p.df),
            "Kolon": len(p.df.columns),
            "Encoding": p.encoding,
            "Ayırıcı/Parser": p.sep,
        }
        for p in parsed
    ])
    st.dataframe(summary_df, use_container_width=True)

# Normalize all files
shop_lines, shop_orders = [], []
hb_lines, hb_orders = [], []
costs, campaigns, invoices, traffic, returns, funnels, stocks, collaborations = [], [], [], [], [], [], [], []
unknowns = []

for p in parsed:
    try:
        if p.kind == "shopify_orders":
            lines, orders = normalize_shopify_orders(p.df, p.name, include_pending=include_pending)
            shop_lines.append(lines)
            shop_orders.append(orders)
        elif p.kind == "hb_sales":
            lines, orders = normalize_hb_sales(p.df, p.name, file_dates.get(p.name, default_report_date))
            hb_lines.append(lines)
            hb_orders.append(orders)
        elif p.kind == "cost_table":
            costs.append(normalize_cost_table(p.df, p.name))
        elif p.kind == "meta_campaign":
            campaigns.append(normalize_meta_campaign(p.df, p.name))
        elif p.kind == "meta_invoice":
            invoices.append(normalize_meta_invoice(p.text, p.name))
        elif p.kind == "traffic_product":
            traffic.append(normalize_traffic_product(p.df, p.name))
        elif p.kind == "returns":
            returns.append(normalize_returns(p.df, p.name))
        elif p.kind == "shopify_funnel":
            funnels.append(normalize_funnel(p.df, p.name))
        elif p.kind == "stock":
            stocks.append(normalize_stock(p.df, p.name))
        elif p.kind == "collaboration":
            collaborations.append(normalize_collaboration(p.df, p.name))
        else:
            unknowns.append(p.name)
    except Exception as e:
        st.warning(f"{p.name} dosyası işlenirken hata oluştu: {e}")

sales_lines = pd.concat(shop_lines + hb_lines, ignore_index=True) if (shop_lines or hb_lines) else pd.DataFrame()
orders = pd.concat(shop_orders + hb_orders, ignore_index=True) if (shop_orders or hb_orders) else pd.DataFrame()
cost_df = pd.concat(costs, ignore_index=True).drop_duplicates(subset=["platform", "sku"], keep="last") if costs else pd.DataFrame()
campaign_df = pd.concat(campaigns, ignore_index=True) if campaigns else pd.DataFrame()
invoice_df = pd.concat(invoices, ignore_index=True) if invoices else pd.DataFrame()
traffic_df = pd.concat(traffic, ignore_index=True) if traffic else pd.DataFrame()
returns_df = pd.concat(returns, ignore_index=True) if returns else pd.DataFrame()
funnel_df = pd.concat(funnels, ignore_index=True) if funnels else pd.DataFrame()
stock_df = pd.concat(stocks, ignore_index=True) if stocks else pd.DataFrame()
collab_df = pd.concat(collaborations, ignore_index=True) if collaborations else pd.DataFrame()

if sales_lines.empty and orders.empty:
    st.error("Satış/sipariş dosyası bulunamadı veya kolonlar tanınamadı. Shopify sipariş CSV veya Hepsiburada satış CSV yüklemelisin.")
    if unknowns:
        st.write("Tanınmayan dosyalar:", ", ".join(unknowns))
    st.stop()

sales_enriched, missing_costs = enrich_sales_with_costs(sales_lines, cost_df)

# Date filter after data is ready
min_dt = pd.to_datetime(orders["order_date"], errors="coerce").min() if not orders.empty else pd.NaT
max_dt = pd.to_datetime(orders["order_date"], errors="coerce").max() if not orders.empty else pd.NaT
if pd.isna(min_dt):
    min_date, max_date = default_report_date, default_report_date
else:
    min_date, max_date = min_dt.date(), max_dt.date()

with st.sidebar:
    st.divider()
    st.header("4) Tarih Filtresi")
    all_time = st.checkbox("Tüm zamanlar", value=True)
    if not all_time:
        dr = st.date_input("Rapor aralığı", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        if isinstance(dr, tuple) and len(dr) == 2:
            start_date, end_date = dr
        else:
            start_date, end_date = min_date, max_date
    else:
        start_date, end_date = min_date, max_date

# Apply date filter
if not all_time and not orders.empty:
    order_dates = pd.to_datetime(orders["order_date"], errors="coerce").dt.date
    valid_orders = orders[(order_dates >= start_date) & (order_dates <= end_date)].copy()
    valid_order_ids = set(valid_orders["order_id"])
    sales_enriched = sales_enriched[sales_enriched["order_id"].isin(valid_order_ids)].copy()
    orders_filtered = valid_orders
else:
    orders_filtered = orders.copy()

# Ad spend source
campaign_spend = float(campaign_df["spend"].sum()) if not campaign_df.empty else 0.0
invoice_spend = float(invoice_df["spend"].sum()) if not invoice_df.empty else 0.0
if campaign_spend > 0 and invoice_spend > 0:
    ad_source = st.sidebar.radio("Meta harcama kaynağı", ["Kampanya raporu", "Fatura raporu"], index=0)
    ad_spend = campaign_spend if ad_source == "Kampanya raporu" else invoice_spend
else:
    ad_spend = campaign_spend or invoice_spend

# KPI calculations
revenue_incl = float(orders_filtered["order_revenue_incl_vat"].sum()) if not orders_filtered.empty else 0.0
order_count = int(orders_filtered["order_id"].nunique()) if not orders_filtered.empty else 0
customers = int(orders_filtered["customer_key"].replace("", np.nan).nunique()) if not orders_filtered.empty else 0
vat_amount_order = float(orders_filtered["tax_amount"].sum()) if not orders_filtered.empty and "tax_amount" in orders_filtered else 0.0
vat_amount_line = float(sales_enriched["kdv_amount"].sum()) if not sales_enriched.empty else 0.0
vat_amount = vat_amount_order if vat_amount_order > 0 else vat_amount_line
profit_before_ads = float(sales_enriched["profit_before_ads"].sum()) if not sales_enriched.empty else 0.0
profit_after_ads = profit_before_ads - ad_spend
aov = revenue_incl / order_count if order_count else 0.0
ltv = revenue_incl / customers if customers else 0.0
mer = ad_spend / revenue_incl if revenue_incl else 0.0
roas_total = (manual_ad_revenue if manual_ad_revenue > 0 else revenue_incl) / ad_spend if ad_spend else 0.0

# New vs returning customers
new_customers = returning_customers = 0
if not orders_filtered.empty and "customer_key" in orders_filtered:
    o = orders_filtered[orders_filtered["customer_key"].ne("")].copy()
    if not o.empty:
        o = o.sort_values("order_date")
        order_rank = o.groupby("customer_key").cumcount() + 1
        new_customers = int((order_rank == 1).sum())
        returning_customers = int((order_rank > 1).sum())

cac = ad_spend / new_customers if new_customers and ad_spend else 0.0
revenue_target_rate = revenue_incl / target_revenue if target_revenue else 0.0
order_target_rate = order_count / target_orders if target_orders else 0.0

future_df, forecast_rev_30, forecast_orders_30 = build_daily_forecast(orders_filtered, forecast_window, days=30)

# =========================================================
# TOP KPI CARDS
# =========================================================
st.subheader("Genel Performans")
cols = st.columns(5)
cols[0].metric("Net Ciro (KDV dahil)", fmt_money(revenue_incl), help="Shopify'da sipariş Total, Hepsiburada'da toplam satış tutarı baz alınır.")
cols[1].metric("Sipariş Adedi", f"{order_count:,}".replace(",", "."))
cols[2].metric("AOV", fmt_money_2(aov))
cols[3].metric("Anlık Net Kâr", fmt_money(profit_after_ads), help="KDV hariç gelir - ürün maliyeti - kargo - komisyon - reklam harcaması")
cols[4].metric("KDV Tutarı", fmt_money(vat_amount))

cols2 = st.columns(5)
cols2[0].metric("Hedef Gerçekleşme", fmt_pct(revenue_target_rate) if target_revenue else "Hedef yok")
cols2[1].metric("Sipariş Hedefi", fmt_pct(order_target_rate) if target_orders else "Hedef yok")
cols2[2].metric("Meta Harcama", fmt_money(ad_spend))
cols2[3].metric("ROAS", f"{roas_total:.2f}x" if ad_spend else "Veri yok")
cols2[4].metric("CAC", fmt_money_2(cac) if cac else "Veri yok")

st.divider()

# =========================================================
# TABS
# =========================================================
tabs = st.tabs([
    "Platform Kıyaslama",
    "Ürün & Top Seller",
    "Reklam / ROAS / Kreatif",
    "Müşteri Analizi",
    "Stok & Tahmin",
    "Nakit Akışı",
    "Ham Veri / Export",
])

# ---------------------------------------------------------
# Platform tab
# ---------------------------------------------------------
with tabs[0]:
    st.subheader("Kanal Karlılık Kıyaslaması")
    if sales_enriched.empty:
        st.warning("Satış satırı bulunamadı.")
    else:
        channel = sales_enriched.groupby("platform", as_index=False).agg(
            revenue_incl_vat=("line_revenue_incl_vat", "sum"),
            quantity=("quantity", "sum"),
            net_revenue_ex_vat=("net_revenue_ex_vat", "sum"),
            product_cost=("product_cost_total", "sum"),
            shipping_cost=("shipping_cost_total", "sum"),
            commission=("commission_amount", "sum"),
            kdv=("kdv_amount", "sum"),
            profit_before_ads=("profit_before_ads", "sum"),
        )
        if ad_spend > 0 and channel["revenue_incl_vat"].sum() > 0:
            channel["allocated_ad_spend"] = channel["revenue_incl_vat"] / channel["revenue_incl_vat"].sum() * ad_spend
        else:
            channel["allocated_ad_spend"] = 0.0
        channel["profit_after_ads"] = channel["profit_before_ads"] - channel["allocated_ad_spend"]
        channel["profit_margin_after_ads"] = np.where(channel["revenue_incl_vat"] > 0, channel["profit_after_ads"] / channel["revenue_incl_vat"], 0)
        st.dataframe(
            channel.style.format({
                "revenue_incl_vat": "₺{:,.0f}", "net_revenue_ex_vat": "₺{:,.0f}", "product_cost": "₺{:,.0f}",
                "shipping_cost": "₺{:,.0f}", "commission": "₺{:,.0f}", "kdv": "₺{:,.0f}",
                "profit_before_ads": "₺{:,.0f}", "allocated_ad_spend": "₺{:,.0f}", "profit_after_ads": "₺{:,.0f}",
                "profit_margin_after_ads": "{:.1%}",
            }),
            use_container_width=True,
        )
        st.bar_chart(channel.set_index("platform")[["revenue_incl_vat", "profit_after_ads"]])

# ---------------------------------------------------------
# Product tab
# ---------------------------------------------------------
with tabs[1]:
    st.subheader("Top-Seller Listesi ve Ürün Karlılığı")
    prod = sales_enriched.copy()
    if exclude_service_from_top:
        prod = prod[~prod["is_service_fee"]]
    if prod.empty:
        st.warning("Ürün satırı bulunamadı.")
    else:
        product_perf = prod.groupby(["platform", "sku", "product_name"], as_index=False).agg(
            quantity=("quantity", "sum"),
            revenue=("line_revenue_incl_vat", "sum"),
            profit=("profit_before_ads", "sum"),
            unit_cost=("unit_cost", "max"),
        )
        product_perf["margin"] = np.where(product_perf["revenue"] > 0, product_perf["profit"] / product_perf["revenue"], 0)
        product_perf = product_perf.sort_values(["quantity", "revenue"], ascending=False)
        st.dataframe(
            product_perf.head(30).style.format({"revenue": "₺{:,.0f}", "profit": "₺{:,.0f}", "unit_cost": "₺{:,.2f}", "margin": "{:.1%}"}),
            use_container_width=True,
        )
        st.bar_chart(product_perf.head(15).set_index("product_name")[["quantity"]])

    if not missing_costs.empty:
        st.warning("Maliyet tablosunda eşleşmeyen SKU'lar var. Bunlar kârı düşük/yanlış gösterebilir.")
        st.dataframe(missing_costs, use_container_width=True)

    if not returns_df.empty:
        st.subheader("İade Analizi")
        ret = returns_df.groupby(["sku", "product_name", "return_reason"], as_index=False).agg(
            return_qty=("return_qty", "sum"),
            estimated_sales_loss=("estimated_sales_loss", "sum"),
        ).sort_values("return_qty", ascending=False)
        st.dataframe(ret.style.format({"estimated_sales_loss": "₺{:,.0f}"}), use_container_width=True)

# ---------------------------------------------------------
# Ads tab
# ---------------------------------------------------------
with tabs[2]:
    st.subheader("Kampanya Bazlı ROAS ve Kreatif Karnesi")
    if campaign_df.empty and invoice_df.empty:
        st.info("Meta kampanya veya fatura dosyası yüklenmedi.")
    else:
        ad_cols = st.columns(4)
        ad_cols[0].metric("Kampanya Harcaması", fmt_money(campaign_spend) if campaign_spend else "Yok")
        ad_cols[1].metric("Fatura Harcaması", fmt_money(invoice_spend) if invoice_spend else "Yok")
        ad_cols[2].metric("ROAS", f"{roas_total:.2f}x" if ad_spend else "Veri yok")
        ad_cols[3].metric("MER", fmt_pct(mer) if revenue_incl else "Veri yok")

    if not campaign_df.empty:
        camp = campaign_df.groupby("campaign_name", as_index=False).agg(
            spend=("spend", "sum"),
            reach=("reach", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            purchases=("purchases", "sum"),
            reported_roas=("reported_roas", "mean"),
        )
        if manual_ad_revenue > 0 and camp["spend"].sum() > 0:
            camp["allocated_revenue"] = camp["spend"] / camp["spend"].sum() * manual_ad_revenue
            camp["calculated_roas"] = camp["allocated_revenue"] / camp["spend"]
        else:
            camp["allocated_revenue"] = np.nan
            camp["calculated_roas"] = camp["reported_roas"]
        camp["cpc"] = np.where(camp["clicks"] > 0, camp["spend"] / camp["clicks"], np.nan)
        camp["cpa"] = np.where(camp["purchases"] > 0, camp["spend"] / camp["purchases"], np.nan)
        st.dataframe(
            camp.sort_values("spend", ascending=False).style.format({
                "spend": "₺{:,.0f}", "allocated_revenue": "₺{:,.0f}", "calculated_roas": "{:.2f}x",
                "reported_roas": "{:.2f}x", "cpc": "₺{:,.2f}", "cpa": "₺{:,.2f}",
            }),
            use_container_width=True,
        )

        creative = campaign_df.groupby("creative_name", as_index=False).agg(
            spend=("spend", "sum"),
            reach=("reach", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            purchases=("purchases", "sum"),
        )
        creative["ctr"] = np.where(creative["impressions"] > 0, creative["clicks"] / creative["impressions"], np.nan)
        creative["cpc"] = np.where(creative["clicks"] > 0, creative["spend"] / creative["clicks"], np.nan)
        creative["cpa"] = np.where(creative["purchases"] > 0, creative["spend"] / creative["purchases"], np.nan)
        st.markdown("**Kreatif Karnesi**")
        st.dataframe(
            creative.sort_values("spend", ascending=False).style.format({"spend": "₺{:,.0f}", "ctr": "{:.2%}", "cpc": "₺{:,.2f}", "cpa": "₺{:,.2f}"}),
            use_container_width=True,
        )

    if not traffic_df.empty:
        st.subheader("Erişim / Görüntülenme vs Dönüşüm")
        trf = traffic_df.groupby("sku", as_index=False).agg(
            views=("views", "sum"), visitors=("visitors", "sum"), cart_adds=("cart_adds", "sum"), sales_qty=("sales_qty", "sum")
        )
        trf["view_to_sale"] = np.where(trf["views"] > 0, trf["sales_qty"] / trf["views"], 0)
        trf["cart_to_sale"] = np.where(trf["cart_adds"] > 0, trf["sales_qty"] / trf["cart_adds"], 0)
        st.dataframe(trf.sort_values("views", ascending=False).style.format({"view_to_sale": "{:.2%}", "cart_to_sale": "{:.2%}"}), use_container_width=True)

# ---------------------------------------------------------
# Customer tab
# ---------------------------------------------------------
with tabs[3]:
    st.subheader("Yeni vs. Geri Gelen Müşteri, CAC ve LTV")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Yeni müşteri siparişi", new_customers)
    c2.metric("Geri gelen müşteri siparişi", returning_customers)
    c3.metric("LTV", fmt_money_2(ltv))
    c4.metric("CAC", fmt_money_2(cac) if cac else "Veri yok")

    if not orders_filtered.empty and "customer_key" in orders_filtered:
        cust = orders_filtered[orders_filtered["customer_key"].ne("")].groupby("customer_key", as_index=False).agg(
            orders=("order_id", "nunique"),
            revenue=("order_revenue_incl_vat", "sum"),
            first_order=("order_date", "min"),
            last_order=("order_date", "max"),
        )
        cust["customer_type"] = np.where(cust["orders"] > 1, "Geri Gelen", "Yeni/Tek Sipariş")
        st.dataframe(cust.sort_values("revenue", ascending=False).head(100).style.format({"revenue": "₺{:,.0f}"}), use_container_width=True)

    if not collab_df.empty:
        st.subheader("İş Birliği Performansı")
        coll = collab_df.groupby(["partner_name", "discount_code"], as_index=False).agg(
            cost=("cost", "sum"), revenue=("revenue", "sum"), orders=("orders", "sum")
        )
        # Shopify discount code eşleşmesiyle gelir/sipariş tamamla
        if not orders_filtered.empty and "discount_code" in orders_filtered:
            disc = orders_filtered[orders_filtered["discount_code"].ne("")].groupby("discount_code", as_index=False).agg(
                matched_revenue=("order_revenue_incl_vat", "sum"), matched_orders=("order_id", "nunique")
            )
            coll = coll.merge(disc, on="discount_code", how="left")
            coll["revenue"] = np.where(coll["revenue"] > 0, coll["revenue"], coll["matched_revenue"].fillna(0))
            coll["orders"] = np.where(coll["orders"] > 0, coll["orders"], coll["matched_orders"].fillna(0))
        coll["roi"] = np.where(coll["cost"] > 0, coll["revenue"] / coll["cost"], np.nan)
        st.dataframe(coll.style.format({"cost": "₺{:,.0f}", "revenue": "₺{:,.0f}", "roi": "{:.2f}x"}), use_container_width=True)
    else:
        st.info("İş birliği performansı için kupon/UTM/influencer maliyeti içeren ayrı CSV yüklenirse bu bölüm otomatik dolar.")

# ---------------------------------------------------------
# Stock / forecast tab
# ---------------------------------------------------------
with tabs[4]:
    st.subheader("30 Günlük Satış Tahmini")
    f1, f2 = st.columns(2)
    f1.metric("30 günlük ciro tahmini", fmt_money(forecast_rev_30))
    f2.metric("30 günlük sipariş tahmini", f"{forecast_orders_30:,.0f}".replace(",", "."))
    if not future_df.empty:
        st.line_chart(future_df.set_index("date")[["forecast_revenue"]])

    st.subheader("Ölü Stok Alarmı ve Stok Besleme Planı")
    # Base sales by SKU
    sku_sales = sales_enriched.groupby("sku", as_index=False).agg(
        sold_qty=("quantity", "sum"),
        revenue=("line_revenue_incl_vat", "sum"),
        last_sale=("order_date", "max"),
        product_name=("product_name", "last"),
    ) if not sales_enriched.empty else pd.DataFrame()

    dead_stock = pd.DataFrame()
    reorder = pd.DataFrame()

    if not stock_df.empty and not sku_sales.empty:
        stock_latest = stock_df.groupby("sku", as_index=False).agg(stock_qty=("stock_qty", "last"), stock_name=("product_name", "last"))
        stock_plan = stock_latest.merge(sku_sales, on="sku", how="left")
        stock_plan["sold_qty"] = stock_plan["sold_qty"].fillna(0)
        stock_plan["product_name"] = np.where(stock_plan["product_name"].fillna("").eq(""), stock_plan["stock_name"], stock_plan["product_name"])
        days_span = max(1, (pd.to_datetime(orders_filtered["order_date"]).max() - pd.to_datetime(orders_filtered["order_date"]).min()).days + 1) if not orders_filtered.empty else 30
        stock_plan["avg_daily_sales"] = stock_plan["sold_qty"] / days_span
        stock_plan["required_stock"] = stock_plan["avg_daily_sales"] * (lead_time_days + safety_stock_days)
        stock_plan["recommended_purchase_qty"] = (stock_plan["required_stock"] - stock_plan["stock_qty"]).clip(lower=0).round(0)
        stock_plan["days_of_stock_left"] = np.where(stock_plan["avg_daily_sales"] > 0, stock_plan["stock_qty"] / stock_plan["avg_daily_sales"], np.inf)
        dead_stock = stock_plan[(stock_plan["stock_qty"] > 0) & (stock_plan["sold_qty"] == 0)].copy()
        reorder = stock_plan[stock_plan["recommended_purchase_qty"] > 0].copy()
        st.markdown("**Stok Besleme Planı**")
        st.dataframe(
            reorder.sort_values("recommended_purchase_qty", ascending=False).style.format({
                "stock_qty": "{:,.0f}", "sold_qty": "{:,.0f}", "avg_daily_sales": "{:,.2f}",
                "required_stock": "{:,.0f}", "recommended_purchase_qty": "{:,.0f}", "days_of_stock_left": "{:,.1f}",
            }),
            use_container_width=True,
        )
    elif stock_df.empty:
        st.info("Stok alarmı ve besleme planı için SKU + Stok kolonu olan stok CSV yüklenmeli.")

    # Traffic-based dead listing alarm even without stock
    if not traffic_df.empty:
        traffic_alarm = traffic_df.groupby("sku", as_index=False).agg(
            views=("views", "sum"), cart_adds=("cart_adds", "sum"), sales_qty=("sales_qty", "sum")
        )
        traffic_alarm["view_to_sale"] = np.where(traffic_alarm["views"] > 0, traffic_alarm["sales_qty"] / traffic_alarm["views"], 0)
        traffic_alarm = traffic_alarm[(traffic_alarm["views"] >= 500) & (traffic_alarm["view_to_sale"] < 0.001)]
        if not traffic_alarm.empty:
            st.markdown("**Düşük Dönüşüm / Ölü Listeleme Alarmı**")
            st.dataframe(traffic_alarm.sort_values("views", ascending=False).style.format({"view_to_sale": "{:.2%}"}), use_container_width=True)
            dead_stock = pd.concat([dead_stock, traffic_alarm], ignore_index=True, sort=False)

# ---------------------------------------------------------
# Cash flow tab
# ---------------------------------------------------------
with tabs[5]:
    st.subheader("Nakit Akış Projeksiyonu")
    total_costs = float(sales_enriched["product_cost_total"].sum() + sales_enriched["shipping_cost_total"].sum() + sales_enriched["commission_amount"].sum()) if not sales_enriched.empty else 0.0
    net_cash_now = revenue_incl - total_costs - ad_spend
    forecast_cost_rate = total_costs / revenue_incl if revenue_incl else 0.0
    forecast_ad_rate = ad_spend / revenue_incl if revenue_incl else 0.0
    forecast_outflow_30 = forecast_rev_30 * (forecast_cost_rate + forecast_ad_rate)
    forecast_net_cash_30 = forecast_rev_30 - forecast_outflow_30

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mevcut nakit girişi", fmt_money(revenue_incl))
    c2.metric("Maliyet + komisyon + kargo", fmt_money(total_costs))
    c3.metric("Reklam çıkışı", fmt_money(ad_spend))
    c4.metric("Net nakit", fmt_money(net_cash_now))

    c5, c6 = st.columns(2)
    c5.metric("30 gün tahmini çıkış", fmt_money(forecast_outflow_30))
    c6.metric("30 gün tahmini net nakit", fmt_money(forecast_net_cash_30))

    cash_df = pd.DataFrame({
        "Kalem": ["Satış Geliri", "Ürün+Kargo+Komisyon", "Reklam", "Net Nakit"],
        "Mevcut": [revenue_incl, -total_costs, -ad_spend, net_cash_now],
        "30 Gün Tahmini": [forecast_rev_30, -forecast_rev_30 * forecast_cost_rate, -forecast_rev_30 * forecast_ad_rate, forecast_net_cash_30],
    })
    st.dataframe(cash_df.style.format({"Mevcut": "₺{:,.0f}", "30 Gün Tahmini": "₺{:,.0f}"}), use_container_width=True)

    kpi = {
        "profit_before_ads": profit_before_ads,
        "ad_spend": ad_spend,
        "mer": mer,
    }
    channel_for_note = sales_enriched.groupby("platform", as_index=False).agg(profit_before_ads=("profit_before_ads", "sum")) if not sales_enriched.empty else pd.DataFrame()
    st.markdown("### Yapay Zeka Notu")
    st.info(make_ai_note(kpi, channel_for_note, dead_stock if "dead_stock" in locals() else pd.DataFrame(), forecast_rev_30))

# ---------------------------------------------------------
# Raw/export tab
# ---------------------------------------------------------
with tabs[6]:
    st.subheader("Ham Veri ve Rapor İndirme")
    st.markdown("**Birleşik satış satırları**")
    st.dataframe(sales_enriched.head(1000), use_container_width=True)

    sheets = {
        "KPI_Ozet": pd.DataFrame([
            {
                "Net Ciro KDV Dahil": revenue_incl,
                "Sipariş": order_count,
                "AOV": aov,
                "KDV": vat_amount,
                "Kar Reklam Once": profit_before_ads,
                "Reklam Harcaması": ad_spend,
                "Kar Reklam Sonra": profit_after_ads,
                "ROAS": roas_total,
                "MER": mer,
                "CAC": cac,
                "LTV": ltv,
                "30 Gun Ciro Tahmini": forecast_rev_30,
            }
        ]),
        "Satis_Satirlari": sales_enriched,
        "Siparisler": orders_filtered,
        "Maliyetler": cost_df,
        "Kampanyalar": campaign_df,
        "Meta_Fatura": invoice_df,
        "Trafik": traffic_df,
        "Iadeler": returns_df,
    }
    try:
        xlsx = to_excel_bytes({k: v for k, v in sheets.items() if isinstance(v, pd.DataFrame) and not v.empty})
        st.download_button(
            "📥 Excel Raporu İndir",
            data=xlsx,
            file_name=f"IQIBLA_Stratejik_Rapor_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.warning(f"Excel export oluşturulamadı: {e}")
        st.download_button(
            "CSV satış satırlarını indir",
            data=sales_enriched.to_csv(index=False).encode("utf-8-sig"),
            file_name="IQIBLA_satis_satirlari.csv",
            mime="text/csv",
        )

    if unknowns:
        st.warning("Tanınmayan dosyalar: " + ", ".join(unknowns))

    if not missing_costs.empty:
        st.markdown("**Maliyet eşleşmeyen SKU listesi**")
        st.dataframe(missing_costs, use_container_width=True)
