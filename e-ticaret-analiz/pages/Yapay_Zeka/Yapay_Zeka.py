
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
st.set_page_config(page_title="SMARTEK360 | Yapay Zeka Analiz", layout="wide")

if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()


# =========================================================
# THEME
# =========================================================
st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at 50% 8%, rgba(218,165,32,0.16), transparent 30%),
                linear-gradient(135deg, #050505 0%, #111111 48%, #050505 100%);
        }
        header { visibility: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1450px;
        }
        .ai-hero {
            background: rgba(8, 8, 8, 0.78);
            border: 1px solid rgba(212, 175, 55, 0.35);
            box-shadow: 0 24px 85px rgba(0,0,0,0.50);
            border-radius: 30px;
            padding: 28px 34px;
            backdrop-filter: blur(16px);
            margin-bottom: 22px;
        }
        .ai-title {
            color: #ffffff;
            font-size: 42px;
            font-weight: 850;
            letter-spacing: 0.4px;
            margin-bottom: 6px;
        }
        .ai-subtitle {
            color: rgba(255,255,255,0.72);
            font-size: 16px;
            line-height: 1.5;
        }
        .gold-line {
            width: 150px;
            height: 3px;
            background: linear-gradient(90deg, transparent, #d4af37, transparent);
            margin-top: 18px;
            border-radius: 99px;
        }
        .assistant-box {
            background: rgba(255,255,255,0.055);
            border: 1px solid rgba(212,175,55,0.22);
            border-radius: 24px;
            padding: 20px;
            margin-top: 10px;
            margin-bottom: 18px;
        }
        div.stButton > button {
            border-radius: 14px;
            border: 1px solid rgba(212,175,55,0.55);
            background: linear-gradient(135deg, #d4af37, #9d7417);
            color: #111111;
            font-weight: 800;
        }
        div.stButton > button:hover {
            border-color: #ffffff;
            color: #000000;
            box-shadow: 0 0 22px rgba(212,175,55,0.35);
        }
        [data-testid="stMetric"] {
            background: rgba(255,255,255,0.055);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 14px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="ai-hero">
        <div class="ai-title">🤖 SMARTEK360: Yapay Zeka Analiz Paneli</div>
        <div class="ai-subtitle">
            Bu sürümde veri kaynakları net ayrıldı:
            <b>Net Ciro / Sipariş / Kâr Shopify dosyalarından</b>,
            <b>reklam harcaması / ROAS / kreatif yorumu Kreatif_Takip yani Meta raporlarından</b> alınır.
        </div>
        <div class="gold-line"></div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# PATHS
# =========================================================
def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "ana_sayfa.py").exists():
            return parent
    return Path(__file__).resolve().parents[2]


PROJECT_DIR = find_project_root()
PAGES_DIR = PROJECT_DIR / "pages"

SHOPIFY_DIR = PAGES_DIR / "Shopify_app"
TRENDYOL_DIR = PAGES_DIR / "smartek_app"
HEPSIBURADA_DIR = PAGES_DIR / "Hepsiburada_app"
KREATIF_DIR = PAGES_DIR / "Kreatif_Takip"


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


def read_table_flexible(path: Path, skiprows: int = 0) -> tuple[pd.DataFrame, str, str]:
    """
    CSV ve XLSX dosyalarını ortak okumak için kullanılır.
    Trendyol / Hepsiburada bazı raporları xlsx geldiği için yapay zeka artık ikisini de okur.
    """
    suffix = path.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        try:
            df = pd.read_excel(path, dtype=str, skiprows=skiprows)
            if df.shape[1] > 1:
                return df, "excel", "sheet"
        except Exception:
            pass

        # Bazı marketplace dosyalarında ilk satır açıklama olabilir.
        try:
            df = pd.read_excel(path, dtype=str, skiprows=1)
            if df.shape[1] > 1:
                return df, "excel", "sheet_skip1"
        except Exception:
            pass

        return pd.DataFrame(), "", ""

    return read_csv_flexible(path, skiprows=skiprows)


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


def compact_table(df: pd.DataFrame, max_rows: int = 10) -> str:
    if df is None or df.empty:
        return "Veri yok."
    view = df.head(max_rows).copy()
    try:
        return view.to_markdown(index=False)
    except Exception:
        return view.to_string(index=False)


# =========================================================
# PANEL SUMMARY STANDARD
# =========================================================
# Her panel aynı formatta panel_summary.csv üretirse,
# Yapay Zeka paneli ham dosya okumak yerine önce bu özetleri kullanır.
#
# Beklenen dosya:
# pages/Shopify_app/panel_summary.csv
# pages/smartek_app/panel_summary.csv
# pages/Hepsiburada_app/panel_summary.csv
# pages/Kreatif_Takip/panel_summary.csv
#
# Format:
# metric,value
# total_revenue,123456.78
# order_count,100
# gross_profit_before_ads,50000
# total_ad_spend,12000
# total_ad_revenue,45000
# roas,3.75

def load_panel_summary(folder: Path, platform_name: str) -> tuple[pd.DataFrame, dict]:
    summary_path = folder / "panel_summary.csv"
    info = {
        "platform": platform_name,
        "path": str(summary_path),
        "exists": summary_path.exists(),
        "status": "NOT_FOUND",
        "metrics": 0,
        "notes": "",
    }

    if not summary_path.exists():
        return pd.DataFrame(columns=["metric", "value", "platform"]), info

    df, enc, sep = read_table_flexible(summary_path)
    if df.empty:
        info["status"] = "ERROR"
        info["notes"] = "panel_summary.csv okunamadı."
        return pd.DataFrame(columns=["metric", "value", "platform"]), info

    metric_col = find_col(df, ["metric", "metrik", "kpi", "name", "baslik", "başlık"])
    value_col = find_col(df, ["value", "deger", "değer", "amount", "tutar"])

    if not metric_col or not value_col:
        # Alternatif: kolon adları metric gibi, ilk satır value gibi olabilir.
        rows = []
        for col in df.columns:
            if len(df) > 0:
                rows.append({"metric": normalize_text(col), "value": df[col].iloc[0], "platform": platform_name})
        out = pd.DataFrame(rows)
    else:
        out = pd.DataFrame({
            "metric": df[metric_col].apply(normalize_text),
            "value": df[value_col],
            "platform": platform_name,
        })

    out["value_num"] = out["value"].apply(to_float)
    out = out[out["metric"].astype(str).str.strip() != ""].copy()

    info["status"] = "OK"
    info["metrics"] = len(out)
    info["notes"] = f"panel_summary.csv okundu. encoding={enc}, sep={sep}"
    return out, info


def summary_value(summary: pd.DataFrame, aliases: list[str], default: float = 0.0) -> float:
    if summary is None or summary.empty:
        return default
    wanted = {normalize_text(a) for a in aliases}
    for _, row in summary.iterrows():
        metric = normalize_text(row.get("metric", ""))
        if metric in wanted:
            return to_float(row.get("value_num", row.get("value", default)))
    # Partial match fallback
    for _, row in summary.iterrows():
        metric = normalize_text(row.get("metric", ""))
        if any(w in metric for w in wanted if w):
            return to_float(row.get("value_num", row.get("value", default)))
    return default


def has_summary_value(summary: pd.DataFrame, aliases: list[str]) -> bool:
    if summary is None or summary.empty:
        return False
    wanted = {normalize_text(a) for a in aliases}
    metrics = [normalize_text(m) for m in summary["metric"].tolist()]
    return any(m in wanted or any(w in m for w in wanted if w) for m in metrics)


# =========================================================
# SHOPIFY LOADERS
# =========================================================
def is_shopify_order_file(path: Path) -> bool:
    name = normalize_text(path.name)
    if any(x in name for x in ["maliyet", "meta", "billing", "fatura", "zamana gore", "oturum"]):
        return False
    df, _, _ = read_shopify_orders(path)
    return not df.empty


@st.cache_data(show_spinner=False)
def load_shopify_costs() -> pd.DataFrame:
    if not SHOPIFY_DIR.exists():
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping"])

    files = [p for p in SHOPIFY_DIR.glob("*.csv") if "maliyet" in normalize_text(p.name)]
    if not files:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping"])

    df, _, _ = read_csv_flexible(files[0])
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping"])

    sku_col = find_col(df, ["SKU"])
    cost_col = find_col(df, ["Maliyet", "Maliyet Alış", "Cost"])
    comm_col = find_col(df, ["Komisyon oran", "Komisyon", "Commission"])
    ship_col = find_col(df, ["Kargo", "Shipping"])

    if not sku_col:
        return pd.DataFrame(columns=["sku_key", "unit_cost", "commission_rate", "unit_shipping"])

    out = pd.DataFrame({
        "sku_key": df[sku_col].apply(clean_sku),
        "unit_cost": df[cost_col].apply(to_float) if cost_col else 0.0,
        "commission_rate": df[comm_col].apply(to_float) if comm_col else 0.0,
        "unit_shipping": df[ship_col].apply(to_float) if ship_col else 0.0,
    })
    out["commission_rate"] = out["commission_rate"].apply(lambda x: x / 100 if x > 1 else x)
    out = out[out["sku_key"] != ""].drop_duplicates("sku_key", keep="last")
    return out


@st.cache_data(show_spinner=False)
def load_shopify_orders() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    debug_rows = []
    frames = []

    if not SHOPIFY_DIR.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{
            "file": "",
            "status": "ERROR",
            "rows": 0,
            "notes": f"Shopify klasörü bulunamadı: {SHOPIFY_DIR}",
        }])

    for path in sorted(SHOPIFY_DIR.glob("*.csv")):
        if not is_shopify_order_file(path):
            continue

        df, enc, sep = read_shopify_orders(path)
        debug_rows.append({
            "file": path.name,
            "status": "OK" if not df.empty else "ERROR",
            "rows": len(df),
            "cols": len(df.columns),
            "encoding": enc,
            "separator": sep,
        })
        if df.empty:
            continue
        df["source_file"] = path.name
        frames.append(df)

    debug = pd.DataFrame(debug_rows)

    if not frames:
        return pd.DataFrame(), pd.DataFrame(), debug

    raw = pd.concat(frames, ignore_index=True)

    for col in [
        "Total", "Subtotal", "Shipping", "Taxes", "Discount Amount", "Refunded Amount",
        "Lineitem quantity", "Lineitem price", "Lineitem discount"
    ]:
        if col not in raw.columns:
            raw[col] = 0.0
        raw[col] = raw[col].apply(to_float)

    for col in [
        "Paid at", "Cancelled at", "Financial Status", "Fulfillment Status",
        "Currency", "Payment Method", "Billing City", "Source", "Lineitem sku"
    ]:
        if col not in raw.columns:
            raw[col] = ""

    raw["order_name"] = raw["Name"].fillna("").astype(str)
    raw["order_date"] = pd.to_datetime(raw["Created at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["cancelled_at"] = pd.to_datetime(raw["Cancelled at"], errors="coerce", utc=True).dt.tz_localize(None)
    raw["financial_status"] = raw["Financial Status"].fillna("").astype(str).str.lower()
    raw["fulfillment_status"] = raw["Fulfillment Status"].fillna("").astype(str).str.lower()
    raw = raw[raw["order_name"].str.strip() != ""].copy()

    dedupe_cols = [c for c in [
        "Name", "Created at", "Lineitem name", "Lineitem sku",
        "Lineitem quantity", "Lineitem price", "Total"
    ] if c in raw.columns]
    raw = raw.drop_duplicates(subset=dedupe_cols, keep="first")

    orders = raw.groupby("order_name", as_index=False).agg(
        platform=("source_file", lambda x: "Shopify"),
        order_date=("order_date", "first"),
        cancelled_at=("cancelled_at", "first"),
        financial_status=("financial_status", "first"),
        fulfillment_status=("fulfillment_status", "first"),
        total=("Total", "first"),
        refunded_amount=("Refunded Amount", "first"),
        source_file=("source_file", "first"),
    )
    orders["is_cancelled"] = orders["cancelled_at"].notna() | orders["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    orders["net_sales"] = orders["total"] - orders["refunded_amount"]
    orders.loc[orders["is_cancelled"], "net_sales"] = 0.0
    orders["order_count"] = (~orders["is_cancelled"]).astype(int)

    lines = raw.copy()
    lines["platform"] = "Shopify"
    lines["sku_key"] = lines["Lineitem sku"].apply(clean_sku)
    lines["product_name"] = lines["Lineitem name"].fillna("").astype(str)
    lines["qty"] = lines["Lineitem quantity"].apply(to_float)
    lines["line_revenue"] = lines["Lineitem price"].apply(to_float) * lines["qty"] - lines["Lineitem discount"].apply(to_float)
    lines["is_cancelled"] = lines["cancelled_at"].notna() | lines["financial_status"].isin(["voided", "void", "cancelled", "canceled"])
    lines.loc[lines["is_cancelled"], ["qty", "line_revenue"]] = 0.0
    lines = lines[["platform", "order_name", "order_date", "sku_key", "product_name", "qty", "line_revenue", "source_file"]].copy()

    return orders, lines, debug


# =========================================================
# TRENDYOL / HEPSIBURADA BASIC LOADERS
# =========================================================

def parse_money_like_value(value) -> float:
    """Trendyol sayfasından gelen 1,234.56 TL / 1.234,56 TL gibi değerleri sayıya çevirir."""
    return to_float(value)


@st.cache_data(show_spinner=False)
def load_trendyol_page_total_revenue() -> tuple[float, pd.DataFrame]:
    """
    Yapay Zeka'nın Trendyol net cirosunu direkt Trendyol sayfasındaki
    Total Revenue değerinden alması için ortak özet dosyasını okur.

    Trendyol sayfası şu dosyalardan birini üretirse AI önce onu kullanır:
    - trendyol_page_summary.csv
    - trend_yol_page_summary.csv
    - smartek_page_summary.csv

    Beklenen formatlardan herhangi biri olabilir:

    1) metric,value
       Total Revenue,123456.78

    2) Metric,Value
       Total Revenue,"123.456,78 TL"

    3) total_revenue
       123456.78

    4) Total Revenue
       123456.78
    """
    summary_names = [
        "trendyol_page_summary.csv",
        "trend_yol_page_summary.csv",
        "smartek_page_summary.csv",
        "trendyol_summary.csv",
    ]

    debug_rows = []

    for filename in summary_names:
        path = TRENDYOL_DIR / filename
        if not path.exists():
            debug_rows.append({
                "file": filename,
                "status": "NOT_FOUND",
                "total_revenue": 0.0,
                "notes": "Özet dosyası bulunamadı.",
            })
            continue

        df, enc, sep = read_table_flexible(path)
        if df.empty:
            debug_rows.append({
                "file": filename,
                "status": "ERROR",
                "total_revenue": 0.0,
                "notes": "Özet dosyası okunamadı.",
            })
            continue

        # Format 1/2: metric-value kolonları
        metric_col = find_col(df, ["metric", "metrik", "kpi", "name", "başlık", "baslik"])
        value_col = find_col(df, ["value", "değer", "deger", "amount", "tutar"])

        if metric_col and value_col:
            for _, row in df.iterrows():
                metric_name = normalize_text(row.get(metric_col, ""))
                if metric_name in ["total revenue", "net ciro", "toplam net ciro", "ciro", "total sales"]:
                    total = parse_money_like_value(row.get(value_col))
                    debug_rows.append({
                        "file": filename,
                        "status": "OK",
                        "total_revenue": total,
                        "notes": f"Trendyol sayfası özetinden alındı. {metric_col} / {value_col}",
                    })
                    return total, pd.DataFrame(debug_rows)

        # Format 3/4: total_revenue veya Total Revenue kolonu
        total_col = find_col(df, [
            "total_revenue", "Total Revenue", "Net Ciro", "Toplam Net Ciro",
            "total sales", "revenue", "ciro"
        ])

        if total_col and len(df) > 0:
            total = parse_money_like_value(df[total_col].iloc[0])
            debug_rows.append({
                "file": filename,
                "status": "OK",
                "total_revenue": total,
                "notes": f"Trendyol sayfası özetinden alındı. Kolon: {total_col}",
            })
            return total, pd.DataFrame(debug_rows)

        debug_rows.append({
            "file": filename,
            "status": "WARNING",
            "total_revenue": 0.0,
            "notes": "Özet dosyasında Total Revenue / Net Ciro bulunamadı.",
        })

    return 0.0, pd.DataFrame(debug_rows)



@st.cache_data(show_spinner=False)
def load_trendyol_basic() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Trendyol net ciro okuyucu.

    ÖNEMLİ:
    Total Revenue / Net Ciro için Trendyol'da sadece sipariş dosyaları kullanılır.
    Reklam raporu, mağaza raporu, kampanya raporu, meta/ad revenue dosyaları kesinlikle net ciroya katılmaz.

    Öncelikli ciro kolonları:
    1. Faturalanacak Tutar
    2. Net Satış Tutarı
    3. Satış Tutarı
    4. Ürün Tutarı
    5. Sipariş Tutarı

    Bilerek kullanılmayan kolonlar:
    - Reklam Geliri
    - Total Ad Revenue
    - ROAS
    - Atfedilen Gelir
    - Dönüşüm Değeri
    - GMV / Görüntülenme / Ziyaretçi gibi özet metrikler
    """
    rows = []
    debug = []

    if not TRENDYOL_DIR.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame([{
            "file": "",
            "status": "ERROR",
            "rows": 0,
            "net_sales": 0.0,
            "used_revenue_col": "",
            "notes": f"Trendyol klasörü bulunamadı: {TRENDYOL_DIR}",
        }])

    files = (
        list(TRENDYOL_DIR.glob("*.csv"))
        + list(TRENDYOL_DIR.glob("*.xlsx"))
        + list(TRENDYOL_DIR.glob("*.xls"))
    )

    # Sadece Trendyol sipariş/net ciro dosyalarını kabul et.
    hard_exclude_terms = [
        "reklam", "ads", "ad ", "advert", "kampanya", "campaign",
        "magaza raporu", "mağaza raporu", "store report",
        "performans", "performance", "trafik", "traffic",
        "ziyaret", "visit", "goruntulenme", "görüntülenme",
        "manual weekly", "haftalik reklam", "haftalık reklam",
        "maliyet", "cost"
    ]

    # Net ciro için güvenli kolon önceliği.
    revenue_priority = [
        "Faturalanacak Tutar",
        "Faturalanacak Tutar KDV Dahil",
        "Net Satış Tutarı",
        "Net Satis Tutari",
        "Satış Tutarı",
        "Satis Tutari",
        "Ürün Tutarı",
        "Urun Tutari",
        "Sipariş Tutarı",
        "Siparis Tutari",
        "Toplam Satış Tutarı",
        "Toplam Satis Tutari",
    ]

    # Bu kolonlar net ciro değil; bulunursa özellikle seçme.
    forbidden_revenue_terms = [
        "reklam", "ad revenue", "total ad revenue", "roas",
        "donusum", "dönüşüm", "conversion value",
        "atfedilen", "attribution", "gmv", "gelir"
    ]

    for path in sorted(files):
        name = normalize_text(path.name)

        if any(term in name for term in hard_exclude_terms):
            debug.append({
                "file": path.name,
                "status": "SKIPPED",
                "rows": 0,
                "net_sales": 0.0,
                "used_revenue_col": "",
                "notes": "Net ciro dosyası değil: reklam/mağaza/performans/maliyet dosyası hariç tutuldu.",
            })
            continue

        # Dosya adında sipariş/tedarikçi sinyali olmalı.
        name_has_order_signal = any(term in name for term in [
            "tedarikci siparisleri", "tedarikci", "siparis", "sipariş", "order"
        ])

        df, enc, sep = read_table_flexible(path)
        if df.empty:
            debug.append({
                "file": path.name,
                "status": "ERROR",
                "rows": 0,
                "net_sales": 0.0,
                "used_revenue_col": "",
                "notes": "Dosya okunamadı.",
            })
            continue

        # Bazı Trendyol raporlarında ilk satır açıklama olabilir.
        def get_cols(frame: pd.DataFrame):
            date = find_col(frame, ["Sipariş Tarihi", "Siparis Tarihi", "Tarih", "Order Date"])
            order = find_col(frame, ["Sipariş Numarası", "Siparis Numarasi", "Sipariş No", "Siparis No", "Order Number", "Order"])
            product = find_col(frame, ["Ürün Adı", "Urun Adi", "Ürün Ad", "Urun Ad", "Product Name", "Product"])
            qty = find_col(frame, ["Adet", "Miktar", "Quantity", "Ürün Adedi", "Urun Adedi"])
            sku = find_col(frame, ["Barkod", "Barcode", "SKU", "Stok Kodu", "Ürün Barkodu", "Urun Barkodu"])
            status = find_col(frame, ["Sipariş Statüsü", "Siparis Statusu", "Durum", "Status"])

            revenue = None
            for candidate in revenue_priority:
                col = find_col(frame, [candidate])
                if col:
                    ncol = normalize_text(col)
                    if not any(bad in ncol for bad in forbidden_revenue_terms):
                        revenue = col
                        break

            return date, order, product, qty, sku, status, revenue

        date_col, order_col, product_col, qty_col, sku_col, status_col, revenue_col = get_cols(df)

        if not order_col or not revenue_col:
            df2, enc2, sep2 = read_table_flexible(path, skiprows=1)
            if not df2.empty:
                d2, o2, p2, q2, s2, st2, r2 = get_cols(df2)
                if o2 and r2:
                    df, enc, sep = df2, enc2, sep2
                    date_col, order_col, product_col, qty_col, sku_col, status_col, revenue_col = d2, o2, p2, q2, s2, st2, r2

        # Dosya adı sipariş değilse ve kolonlar çok net sipariş değilse geç.
        if not name_has_order_signal:
            debug.append({
                "file": path.name,
                "status": "SKIPPED",
                "rows": len(df),
                "net_sales": 0.0,
                "used_revenue_col": revenue_col or "",
                "notes": "Dosya adı sipariş/tedarikçi sinyali taşımadığı için net ciroya dahil edilmedi.",
            })
            continue

        if not order_col or not revenue_col:
            debug.append({
                "file": path.name,
                "status": "SKIPPED",
                "rows": len(df),
                "net_sales": 0.0,
                "used_revenue_col": revenue_col or "",
                "notes": "Net ciro için gerekli kolonlar bulunamadı. Gerekli: Sipariş Numarası + Faturalanacak/Net/Satış Tutarı.",
            })
            continue

        tmp = pd.DataFrame({
            "platform": "Trendyol",
            "order_name": df[order_col].astype(str),
            "order_date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True) if date_col else pd.NaT,
            "product_name": df[product_col].astype(str) if product_col else "Trendyol Product",
            "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
            "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
            "line_revenue": df[revenue_col].apply(to_float),
            "status": df[status_col].astype(str) if status_col else "",
            "source_file": path.name,
        })

        tmp["is_cancelled_or_returned"] = tmp["status"].str.contains(
            "iptal|iade|cancel|return|red|reddedildi", case=False, na=False
        )
        tmp.loc[tmp["is_cancelled_or_returned"], ["qty", "line_revenue"]] = 0.0

        # Boş siparişler ve negatif/garip satırlar atılır.
        tmp = tmp[
            (tmp["order_name"].fillna("").astype(str).str.strip() != "")
            & (tmp["line_revenue"].fillna(0) >= 0)
        ].copy()

        net_sales = float(tmp["line_revenue"].sum()) if not tmp.empty else 0.0

        debug.append({
            "file": path.name,
            "status": "OK" if net_sales > 0 else "WARNING",
            "rows": len(tmp),
            "net_sales": net_sales,
            "used_revenue_col": revenue_col,
            "notes": f"Trendyol NET CİRO sipariş dosyasından alındı. Encoding={enc}, sep={sep}",
        })

        if not tmp.empty:
            rows.append(tmp)

    lines = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    if lines.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(debug)

    orders = lines.groupby("order_name", as_index=False).agg(
        platform=("platform", "first"),
        order_date=("order_date", "first"),
        net_sales=("line_revenue", "sum"),
        source_file=("source_file", "first"),
    )

    # Sipariş sayısı sadece net satışı pozitif olan benzersiz siparişler.
    orders["order_count"] = orders["net_sales"].gt(0).astype(int)

    return orders, lines, pd.DataFrame(debug)


@st.cache_data(show_spinner=False)
def load_hepsiburada_basic() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []

    if not HEPSIBURADA_DIR.exists():
        return pd.DataFrame(), pd.DataFrame()

    files = list(HEPSIBURADA_DIR.glob("*.csv")) + list(HEPSIBURADA_DIR.glob("*.xlsx")) + list(HEPSIBURADA_DIR.glob("*.xls"))

    for path in files:
        name = normalize_text(path.name)
        if "maliyet" in name or "iade" in name:
            continue

        df, enc, sep = read_table_flexible(path)
        if df.empty:
            continue

        # Hepsiburada dosyalarında bazen üst açıklama satırı olabilir.
        if not find_col(df, ["Ürün Adı", "Urun Adi", "SKU", "Toplam Satis Tutari", "Toplam Satış Tutarı"]):
            df2, enc2, sep2 = read_table_flexible(path, skiprows=1)
            if not df2.empty:
                df, enc, sep = df2, enc2, sep2

        product_col = find_col(df, ["Ürün Adı", "Urun Adi", "Product Name", "Product"])
        sku_col = find_col(df, ["SKU", "Stok Kodu", "Merchant SKU"])
        qty_col = find_col(df, ["Toplam Satış Adedi", "Toplam Satis Adedi", "Satış Adedi", "Satis Adedi", "Adet", "Quantity"])
        revenue_col = find_col(df, [
            "Toplam Satış Tutarı", "Toplam Satis Tutari", "Satış Tutarı", "Satis Tutari",
            "Net Satış Tutarı", "Net Satis Tutari", "Tutar", "Amount", "Revenue"
        ])

        # Bazı Hepsiburada raporları mağaza özeti olabilir; ürün kolonu yoksa dosyayı satış satırı gibi kullanma.
        if not revenue_col:
            continue

        tmp = pd.DataFrame({
            "platform": "Hepsiburada",
            "order_name": path.stem,
            "order_date": pd.NaT,
            "product_name": df[product_col].astype(str) if product_col else "Hepsiburada Product",
            "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
            "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
            "line_revenue": df[revenue_col].apply(to_float),
            "source_file": path.name,
        })

        # Tamamen boş/sıfır satırları at
        tmp = tmp[(tmp["line_revenue"] > 0) | (tmp["qty"] > 0)].copy()
        if not tmp.empty:
            rows.append(tmp)

    lines = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if lines.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Hepsiburada dosyası çoğunlukla aggregate rapor olduğu için order_count tam sipariş sayısı olmayabilir.
    # Burada net ciroyu doğru almak için toplam ciroyu kullanıyoruz.
    orders = pd.DataFrame([{
        "platform": "Hepsiburada",
        "order_name": "hepsiburada_aggregate",
        "order_date": pd.NaT,
        "net_sales": float(lines["line_revenue"].sum()),
        "order_count": 1,
        "source_file": ", ".join(lines["source_file"].dropna().unique().tolist()[:5]),
    }])
    return orders, lines


# =========================================================
# CREATIVE / META LOADER
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
        ad_revenue = df[revenue_col].apply(to_float)
    else:
        ad_revenue = spend * roas

    out = pd.DataFrame({
        "campaign_name": df[campaign_col].astype(str) if campaign_col else source_file,
        "creative_name": df[ad_col].astype(str) if ad_col else "Unknown Creative",
        "date": pd.to_datetime(df[end_col], errors="coerce") if end_col else (pd.to_datetime(df[start_col], errors="coerce") if start_col else pd.NaT),
        "spend": spend,
        "ad_revenue": ad_revenue,
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
            debug.append({"file": path.name, "status": "WARNING", "rows": len(df), "notes": "Meta/kreatif raporu olarak tanınmadı veya spend kolonu yok"})
            continue

        debug.append({"file": path.name, "status": "OK", "rows": len(norm), "notes": f"Encoding={enc}, sep={sep}"})
        rows.append(norm)

    ads = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=[
        "campaign_name", "creative_name", "date", "spend", "ad_revenue", "purchases",
        "roas", "reach", "impressions", "results", "ctr", "cpc", "cpm", "frequency", "source_file"
    ])
    return ads, pd.DataFrame(debug)


# =========================================================
# MODEL
# =========================================================
@st.cache_data(show_spinner=False)
def build_model():
    shopify_costs = load_shopify_costs()
    shopify_orders, shopify_lines, shopify_debug = load_shopify_orders()
    trendyol_page_total_revenue, trendyol_page_summary_debug = load_trendyol_page_total_revenue()
    trendyol_orders, trendyol_lines, trendyol_debug = load_trendyol_basic()
    hb_orders, hb_lines = load_hepsiburada_basic()

    # Trendyol sayfası Total Revenue özet dosyası varsa,
    # AI toplam net ciro için bunu ana kaynak olarak kullanır.
    if trendyol_page_total_revenue > 0:
        trendyol_orders = pd.DataFrame([{
            "platform": "Trendyol",
            "order_name": "trendyol_page_total_revenue",
            "order_date": pd.NaT,
            "net_sales": trendyol_page_total_revenue,
            "order_count": 1,
            "source_file": "trendyol_page_summary.csv / Trendyol page Total Revenue",
        }])
        if trendyol_lines.empty:
            trendyol_lines = pd.DataFrame([{
                "platform": "Trendyol",
                "order_name": "trendyol_page_total_revenue",
                "order_date": pd.NaT,
                "product_name": "Trendyol Total Revenue",
                "sku_key": "",
                "qty": 1,
                "line_revenue": trendyol_page_total_revenue,
                "source_file": "trendyol_page_summary.csv / Trendyol page Total Revenue",
            }])

    creative_ads, creative_debug = load_creative_ads()

    if not shopify_lines.empty:
        shopify_lines = shopify_lines.merge(shopify_costs, on="sku_key", how="left")
        for col in ["unit_cost", "unit_shipping", "commission_rate"]:
            shopify_lines[col] = shopify_lines[col].fillna(0.0)
        shopify_lines["matched_cost"] = shopify_lines["unit_cost"].gt(0)
        shopify_lines["gross_profit_before_ads"] = (
            shopify_lines["line_revenue"]
            - (shopify_lines["unit_cost"] + shopify_lines["unit_shipping"]) * shopify_lines["qty"]
            - shopify_lines["line_revenue"] * shopify_lines["commission_rate"]
        )
    else:
        shopify_lines["matched_cost"] = []
        shopify_lines["gross_profit_before_ads"] = []

    if not shopify_orders.empty and not shopify_lines.empty:
        profit = shopify_lines.groupby("order_name", as_index=False).agg(
            gross_profit_before_ads=("gross_profit_before_ads", "sum"),
            units=("qty", "sum"),
        )
        shopify_orders = shopify_orders.merge(profit, on="order_name", how="left")
        shopify_orders["gross_profit_before_ads"] = shopify_orders["gross_profit_before_ads"].fillna(0.0)
        shopify_orders["units"] = shopify_orders["units"].fillna(0.0)

    all_orders = pd.concat(
        [df for df in [shopify_orders, trendyol_orders, hb_orders] if not df.empty],
        ignore_index=True
    ) if any(not df.empty for df in [shopify_orders, trendyol_orders, hb_orders]) else pd.DataFrame()

    all_lines = pd.concat(
        [df for df in [shopify_lines, trendyol_lines, hb_lines] if not df.empty],
        ignore_index=True
    ) if any(not df.empty for df in [shopify_lines, trendyol_lines, hb_lines]) else pd.DataFrame()

    issues = []
    if shopify_orders.empty:
        issues.append("Shopify sipariş verisi okunamadı. Net ciro Shopify dosyasından alınmalıdır.")
    if shopify_costs.empty:
        issues.append("Shopify maliyet tablosu okunamadı. Kâr hesabı eksik olabilir.")
    if trendyol_orders.empty:
        issues.append("Trendyol Total Revenue okunamadı. Öncelik: pages/smartek_app/trendyol_page_summary.csv içindeki Trendyol sayfası Total Revenue. Yoksa Tedarikci_Siparisleri / sipariş dosyası gerekir.")
    if creative_ads.empty:
        issues.append("Kreatif_Takip klasöründen Meta reklam/kreatif verisi okunamadı. ROAS ve reklam harcaması eksik kalır.")

    return {
        "shopify_orders": shopify_orders,
        "shopify_lines": shopify_lines,
        "shopify_costs": shopify_costs,
        "shopify_debug": shopify_debug,
        "trendyol_orders": trendyol_orders,
        "trendyol_lines": trendyol_lines,
        "trendyol_debug": trendyol_debug,
        "trendyol_page_summary_debug": trendyol_page_summary_debug,
        "hepsiburada_orders": hb_orders,
        "orders": all_orders,
        "lines": all_lines,
        "creative_ads": creative_ads,
        "creative_debug": creative_debug,
        "issues": issues,
    }


model = build_model()

shopify_orders = model["shopify_orders"]
shopify_lines = model["shopify_lines"]
shopify_costs = model["shopify_costs"]
shopify_debug = model["shopify_debug"]
trendyol_orders = model["trendyol_orders"]
trendyol_lines = model.get("trendyol_lines", pd.DataFrame())
trendyol_debug = model.get("trendyol_debug", pd.DataFrame())
trendyol_page_summary_debug = model.get("trendyol_page_summary_debug", pd.DataFrame())
hepsiburada_orders = model["hepsiburada_orders"]
orders_all = model["orders"]
lines_all = model["lines"]
creative_ads_all = model["creative_ads"]
creative_debug = model["creative_debug"]
issues = model["issues"]

# =========================================================
# PANEL SUMMARY FILES
# =========================================================
shopify_summary, shopify_summary_info = load_panel_summary(SHOPIFY_DIR, "Shopify")
trendyol_summary, trendyol_summary_info = load_panel_summary(TRENDYOL_DIR, "Trendyol")
hepsiburada_summary, hepsiburada_summary_info = load_panel_summary(HEPSIBURADA_DIR, "Hepsiburada")
kreatif_summary, kreatif_summary_info = load_panel_summary(KREATIF_DIR, "Kreatif/Meta")

summary_info_df = pd.DataFrame([
    shopify_summary_info,
    trendyol_summary_info,
    hepsiburada_summary_info,
    kreatif_summary_info,
])


# =========================================================
# SIDEBAR
# =========================================================
date_sources = []
if not orders_all.empty and "order_date" in orders_all.columns:
    date_sources.append(pd.to_datetime(orders_all["order_date"], errors="coerce").dropna())
if not creative_ads_all.empty and "date" in creative_ads_all.columns:
    date_sources.append(pd.to_datetime(creative_ads_all["date"], errors="coerce").dropna())

if date_sources and any(len(s) for s in date_sources):
    all_dates = pd.concat([s for s in date_sources if len(s)], ignore_index=True)
    min_date = all_dates.min().date()
    max_date = all_dates.max().date()
else:
    min_date = max_date = pd.Timestamp.today().date()

with st.sidebar:
    st.header("AI Varsayımları")
    all_time = st.toggle("Tüm Zamanlar", value=True)
    start_date = st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date, disabled=all_time)
    end_date = st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date, disabled=all_time)

    monthly_revenue_target = st.number_input("Aylık Net Ciro Hedefi", min_value=0.0, value=500000.0, step=50000.0)
    fixed_costs_30d = st.number_input("30 Günlük Sabit Gider", min_value=0.0, value=0.0, step=1000.0)
    current_cash = st.number_input("Mevcut Nakit", min_value=0.0, value=0.0, step=1000.0)
    planned_stock_purchase = st.number_input("Planlanan Stok Alımı", min_value=0.0, value=0.0, step=1000.0)
    new_customer_count = st.number_input("Yeni Müşteri Sayısı", min_value=0, value=0, step=10)
    returning_customer_count = st.number_input("Geri Gelen Müşteri Sayısı", min_value=0, value=0, step=10)
    avg_purchase_per_customer = st.number_input("LTV için müşteri başı ort. satın alma", min_value=1.0, value=1.5, step=0.1)
    show_debug = st.checkbox("Veri okuma debug göster", value=True)

    selected_report = st.selectbox(
        "AI rapor başlığı seç",
        [
            "Genel Yönetici Özeti",
            "Net Ciro ve Sipariş Yorumu",
            "Anlık Net Kar",
            "Kanal Karlılık Kıyaslaması",
            "Kampanya Bazlı ROAS",
            "Kreatif Karnesi",
            "CAC ve Müşteri Edinme Yorumu",
            "Sepet Ortalaması (AOV)",
            "30 Günlük Satış Tahmini",
            "Nakit Akış Projeksiyonu",
            "Yapay Zeka Notu",
        ],
    )


def date_filter(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or all_time or col not in df.columns:
        return df.copy()
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d = pd.to_datetime(df[col], errors="coerce")
    return df[(d >= s) & (d <= e)].copy()


shopify_orders = date_filter(shopify_orders, "order_date")
shopify_lines = date_filter(shopify_lines, "order_date")
orders_all = date_filter(orders_all, "order_date")
lines_all = date_filter(lines_all, "order_date")
creative_ads = date_filter(creative_ads_all, "date")


# =========================================================
# KPI
# =========================================================
# Kritik düzeltme:
# Net ciro 3 kanaldan gelir: Shopify + Trendyol + Hepsiburada.
# Kreatif_Takip sadece Meta/reklam datasıdır; net ciro kaynağı değildir.
shopify_net_revenue = float(shopify_orders["net_sales"].sum()) if not shopify_orders.empty else 0.0
shopify_order_count = int(shopify_orders["order_count"].sum()) if not shopify_orders.empty and "order_count" in shopify_orders.columns else 0
shopify_units = float(shopify_lines["qty"].sum()) if not shopify_lines.empty else 0.0
shopify_aov = safe_divide(shopify_net_revenue, shopify_order_count)
shopify_gross_profit = float(shopify_lines["gross_profit_before_ads"].sum()) if not shopify_lines.empty and "gross_profit_before_ads" in shopify_lines.columns else 0.0

trendyol_net_revenue = float(trendyol_orders["net_sales"].sum()) if not trendyol_orders.empty and "net_sales" in trendyol_orders.columns else 0.0
trendyol_order_count = int(trendyol_orders["order_count"].sum()) if not trendyol_orders.empty and "order_count" in trendyol_orders.columns else 0

hepsiburada_net_revenue = float(hepsiburada_orders["net_sales"].sum()) if not hepsiburada_orders.empty and "net_sales" in hepsiburada_orders.columns else 0.0
hepsiburada_order_count = int(hepsiburada_orders["order_count"].sum()) if not hepsiburada_orders.empty and "order_count" in hepsiburada_orders.columns else 0

# =========================================================
# SUMMARY OVERRIDES
# =========================================================
# Aynı istatistiklerin AI'da farklı yerde toplanmaması için öncelik panel_summary.csv dosyalarıdır.
# panel_summary yoksa ham dosyalardan hesaplanan fallback değerler kullanılır.

if has_summary_value(shopify_summary, ["total_revenue", "net_ciro", "total revenue"]):
    shopify_net_revenue = summary_value(shopify_summary, ["total_revenue", "net_ciro", "total revenue"], shopify_net_revenue)
if has_summary_value(shopify_summary, ["order_count", "orders", "siparis_adedi"]):
    shopify_order_count = int(summary_value(shopify_summary, ["order_count", "orders", "siparis_adedi"], shopify_order_count))
if has_summary_value(shopify_summary, ["units_sold", "units", "adet"]):
    shopify_units = summary_value(shopify_summary, ["units_sold", "units", "adet"], shopify_units)
if has_summary_value(shopify_summary, ["aov", "average_order_value"]):
    shopify_aov = summary_value(shopify_summary, ["aov", "average_order_value"], shopify_aov)
if has_summary_value(shopify_summary, ["gross_profit_before_ads", "gross_profit", "brut_kar"]):
    shopify_gross_profit = summary_value(shopify_summary, ["gross_profit_before_ads", "gross_profit", "brut_kar"], shopify_gross_profit)

if has_summary_value(trendyol_summary, ["total_revenue", "net_ciro", "total revenue"]):
    trendyol_net_revenue = summary_value(trendyol_summary, ["total_revenue", "net_ciro", "total revenue"], trendyol_net_revenue)
if has_summary_value(trendyol_summary, ["order_count", "orders", "siparis_adedi"]):
    trendyol_order_count = int(summary_value(trendyol_summary, ["order_count", "orders", "siparis_adedi"], trendyol_order_count))

if has_summary_value(hepsiburada_summary, ["total_revenue", "net_ciro", "total revenue"]):
    hepsiburada_net_revenue = summary_value(hepsiburada_summary, ["total_revenue", "net_ciro", "total revenue"], hepsiburada_net_revenue)
if has_summary_value(hepsiburada_summary, ["order_count", "orders", "siparis_adedi"]):
    hepsiburada_order_count = int(summary_value(hepsiburada_summary, ["order_count", "orders", "siparis_adedi"], hepsiburada_order_count))

all_net_revenue = shopify_net_revenue + trendyol_net_revenue + hepsiburada_net_revenue
all_order_count = shopify_order_count + trendyol_order_count + hepsiburada_order_count
all_aov = safe_divide(all_net_revenue, all_order_count)

# Panel summary varsa kârı panellerin verdiği aynı değerden al.
shopify_gross_profit = summary_value(shopify_summary, ["gross_profit_before_ads", "gross_profit", "brut_kar"], shopify_gross_profit)
trendyol_gross_profit = summary_value(trendyol_summary, ["gross_profit_before_ads", "gross_profit", "brut_kar"], 0.0)
hepsiburada_gross_profit = summary_value(hepsiburada_summary, ["gross_profit_before_ads", "gross_profit", "brut_kar"], 0.0)
all_gross_profit = shopify_gross_profit + trendyol_gross_profit + hepsiburada_gross_profit

ad_spend = float(creative_ads["spend"].sum()) if not creative_ads.empty else 0.0
ad_revenue = float(creative_ads["ad_revenue"].sum()) if not creative_ads.empty else 0.0
ad_purchases = float(creative_ads["purchases"].sum()) if not creative_ads.empty else 0.0

# Kreatif/Meta panel summary varsa reklam KPI'ları da aynı özetten gelir.
ad_spend = summary_value(kreatif_summary, ["total_ad_spend", "ad_spend", "meta_spend"], ad_spend)
ad_revenue = summary_value(kreatif_summary, ["total_ad_revenue", "ad_revenue", "reklam_geliri"], ad_revenue)
ad_purchases = summary_value(kreatif_summary, ["ad_purchases", "purchases", "alisverisler"], ad_purchases)
overall_roas = safe_divide(ad_revenue, ad_spend)
cac = safe_divide(ad_spend, new_customer_count) if new_customer_count else safe_divide(ad_spend, ad_purchases)

# Net Profit After Ads = şimdilik Shopify kârı - Meta spend.
# Toplam ciro raporu 3 kanaldır; kâr raporu maliyet entegrasyonu olan kanaldan başlar.
net_profit_after_ads = all_gross_profit - ad_spend
mer = safe_divide(all_net_revenue, ad_spend)
target_rate = safe_divide(all_net_revenue, monthly_revenue_target) * 100 if monthly_revenue_target else 0.0
ltv = all_aov * avg_purchase_per_customer

# Channel table
platform_rows = [
    {
        "platform": "Shopify",
        "net_revenue": shopify_net_revenue,
        "orders": shopify_order_count,
        "gross_profit_before_ads": shopify_gross_profit,
        "ad_spend": ad_spend,
        "ad_revenue": ad_revenue,
        "net_profit_after_ads": shopify_gross_profit - ad_spend,
        "roas": overall_roas,
        "aov": shopify_aov,
        "data_source": "Net ciro: Shopify | Reklam: Kreatif_Takip/Meta",
    },
    {
        "platform": "Trendyol",
        "net_revenue": trendyol_net_revenue,
        "orders": trendyol_order_count,
        "gross_profit_before_ads": 0.0,
        "ad_spend": 0.0,
        "ad_revenue": 0.0,
        "net_profit_after_ads": trendyol_net_revenue,
        "roas": 0.0,
        "aov": safe_divide(trendyol_net_revenue, trendyol_order_count),
        "data_source": "Net ciro: Trendyol sipariş dosyaları",
    },
    {
        "platform": "Hepsiburada",
        "net_revenue": hepsiburada_net_revenue,
        "orders": hepsiburada_order_count,
        "gross_profit_before_ads": 0.0,
        "ad_spend": 0.0,
        "ad_revenue": 0.0,
        "net_profit_after_ads": hepsiburada_net_revenue,
        "roas": 0.0,
        "aov": safe_divide(hepsiburada_net_revenue, hepsiburada_order_count),
        "data_source": "Net ciro: Hepsiburada rapor dosyaları",
    },
]
platform_summary = pd.DataFrame(platform_rows)



if not shopify_lines.empty:
    product_summary = shopify_lines.groupby(["platform", "product_name", "sku_key"], as_index=False).agg(
        revenue=("line_revenue", "sum"),
        qty=("qty", "sum"),
        gross_profit_before_ads=("gross_profit_before_ads", "sum"),
        matched_cost=("matched_cost", "max"),
    ).sort_values(["qty", "revenue"], ascending=False)
else:
    product_summary = pd.DataFrame()

if not creative_ads.empty:
    creative_summary = creative_ads.groupby(["campaign_name", "creative_name"], as_index=False).agg(
        spend=("spend", "sum"),
        ad_revenue=("ad_revenue", "sum"),
        purchases=("purchases", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        results=("results", "sum"),
        ctr=("ctr", "mean"),
        cpc=("cpc", "mean"),
        cpm=("cpm", "mean"),
        frequency=("frequency", "mean"),
    )
    creative_summary["roas"] = creative_summary.apply(lambda r: safe_divide(r["ad_revenue"], r["spend"]), axis=1)
    creative_summary["cac"] = creative_summary.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
else:
    creative_summary = pd.DataFrame()


# =========================================================
# GEMINI / LOCAL CHAT
# =========================================================
def get_secret_value(key: str) -> str:
    try:
        return str(st.secrets.get(key, "")).strip()
    except Exception:
        return ""


def build_report_context() -> str:
    return f"""
VERİ KAYNAĞI KURALI:
- Net Ciro, Sipariş Adedi, Units Sold, AOV ve Gross Profit kaynak: Shopify orders ve Shopify maliyet tablosu.
- Kreatif_Takip sadece Meta reklam/kreatif datasıdır. Kreatif_Takip'ten NET CİRO alınmaz.
- Reklam harcaması, reklam geliri, ROAS, CAC kaynak: Kreatif_Takip Meta raporları.

GENEL ÖZET / 3 KANAL:
- Toplam Net Ciro: {money(all_net_revenue)}
- Toplam Sipariş: {all_order_count:,}
- Toplam AOV: {money(all_aov)}

SHOPIFY ÖZETİ:
- Shopify Net Ciro: {money(shopify_net_revenue)}
- Shopify Sipariş Adedi: {shopify_order_count:,}
- Shopify Units Sold: {shopify_units:,.0f}
- Shopify AOV: {money(shopify_aov)}
- Shopify Gross Profit Before Ads: {money(shopify_gross_profit)}
- Shopify Gross Profit: {money(shopify_gross_profit)}
- Toplam Net Profit After Ads: {money(net_profit_after_ads)}
- MER: {mer:.2f}

META / KREATİF ÖZETİ:
- Reklam Harcaması: {money(ad_spend)}
- Reklam Geliri: {money(ad_revenue)}
- ROAS: {overall_roas:.2f}
- Ad Purchases: {ad_purchases:,.0f}
- CAC: {money(cac)}

HEDEF / FİNANS:
- Aylık Net Ciro Hedefi: {money(monthly_revenue_target)}
- Hedef Gerçekleşme: %{target_rate:.1f}
- Sabit Gider Varsayımı: {money(fixed_costs_30d)}
- Mevcut Nakit: {money(current_cash)}
- Planlanan Stok Alımı: {money(planned_stock_purchase)}

KANAL ÖZETİ:
{compact_table(platform_summary, 10)}

TOP SHOPIFY ÜRÜNLER:
{compact_table(product_summary[["product_name", "sku_key", "qty", "revenue", "gross_profit_before_ads", "matched_cost"]] if not product_summary.empty else product_summary, 10)}

KREATİF KARNESİ:
{compact_table(creative_summary[["campaign_name", "creative_name", "spend", "ad_revenue", "purchases", "roas", "cac", "ctr"]] if not creative_summary.empty else creative_summary, 10)}
"""


def local_answer(question: str) -> str:
    q = normalize_text(question)

    if any(k in q for k in ["net ciro", "ciro", "revenue", "gelir"]):
        return (
            f"Toplam net ciro **3 kanaldan** alınıyor: **{money(all_net_revenue)}**. "
            f"Bunun içinde Shopify **{money(shopify_net_revenue)}**, Trendyol **{money(trendyol_net_revenue)}**, Hepsiburada **{money(hepsiburada_net_revenue)}**. "
            "Kreatif_Takip sadece Meta reklam verisidir; net ciro için kullanılmaz."
        )

    if any(k in q for k in ["roas", "reklam", "kreatif", "meta"]):
        return (
            f"Meta/Kreatif tarafında reklam harcaması **{money(ad_spend)}**, reklam geliri **{money(ad_revenue)}**, "
            f"ROAS **{overall_roas:.2f}**. Bu veriler **Kreatif_Takip klasöründen** geliyor."
        )

    if any(k in q for k in ["kar", "profit"]):
        return (
            f"Shopify brüt kâr **{money(shopify_gross_profit)}**. "
            f"Kreatif/Meta reklam harcaması düşüldükten sonra net kâr **{money(net_profit_after_ads)}**."
        )

    if any(k in q for k in ["urun", "stok", "top seller", "top-seller"]):
        if product_summary.empty:
            return "Shopify ürün verisi okunamadı."
        return "Shopify top ürünler:\n\n" + compact_table(product_summary[["product_name", "qty", "revenue", "gross_profit_before_ads"]], 8)

    return (
        f"Genel özet: toplam net ciro **{money(all_net_revenue)}**, toplam sipariş **{all_order_count:,}**, "
        f"genel AOV **{money(all_aov)}**, Meta reklam harcaması **{money(ad_spend)}**, ROAS **{overall_roas:.2f}**, "
        f"net kâr **{money(net_profit_after_ads)}**. Shopify: {money(shopify_net_revenue)}, Trendyol: {money(trendyol_net_revenue)}, Hepsiburada: {money(hepsiburada_net_revenue)}."
    )


def call_gemini(question: str, context: str, model_name: str) -> str:
    api_key = get_secret_value("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API anahtarı bulunamadı. Streamlit Secrets içine GEMINI_API_KEY eklenmeli."

    try:
        from google import genai
    except Exception as exc:
        return f"google-genai paketi kurulu değil. requirements.txt içine google-genai ekle. Hata: {exc}"

    prompt = f"""
Sen IQIBLA Türkiye için çalışan e-ticaret veri analizi asistanısın.
Cevabın Türkçe, net, yöneticiye uygun ve aksiyon odaklı olsun.

ÇOK ÖNEMLİ VERİ KURALI:
Net ciroyu Kreatif_Takip'ten alma.
Net ciro / sipariş Shopify + Trendyol + Hepsiburada satış/sipariş dosyalarından gelir.
Kreatif_Takip sadece Meta reklam/kreatif verisidir: reklam harcaması, reklam geliri, ROAS, CAC, kreatif performansı.

Aşağıdaki rapor özetine göre cevap ver:
{context}

Kullanıcı sorusu:
{question}
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model_name, contents=prompt)
        return response.text
    except Exception as exc:
        return f"Gemini yanıtı alınamadı: {exc}"


# =========================================================
# TOP KPI
# =========================================================
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Toplam Net Ciro", money(all_net_revenue))
k2.metric("Toplam Orders", f"{all_order_count:,}")
k3.metric("Genel AOV", money(all_aov))
k4.metric("Shopify Gross Profit", money(shopify_gross_profit))
k5.metric("Meta Spend", money(ad_spend))
k6.metric("ROAS", f"{overall_roas:.2f}" if overall_roas else "N/A")

k7, k8, k9, k10 = st.columns(4)
k7.metric("Net Profit After Ads", money(net_profit_after_ads))
k8.metric("MER", f"{mer:.2f}" if mer else "N/A")
k9.metric("CAC", money(cac))
k10.metric("Hedef Gerçekleşme", f"%{target_rate:.1f}")

c1, c2, c3 = st.columns(3)
c1.metric("Shopify Ciro", money(shopify_net_revenue))
c2.metric("Trendyol Ciro", money(trendyol_net_revenue))
c3.metric("Hepsiburada Ciro", money(hepsiburada_net_revenue))

if issues:
    with st.expander("Veri Okuma Uyarıları", expanded=True):
        for issue in issues:
            st.info(issue)

if show_debug:
    with st.expander("Veri kaynakları / debug", expanded=False):
        st.write("Shopify order debug")
        st.dataframe(shopify_debug, use_container_width=True, hide_index=True)
        st.write("Trendyol sayfası Total Revenue özet debug")
        st.dataframe(trendyol_page_summary_debug, use_container_width=True, hide_index=True)
        st.write("Trendyol sipariş fallback debug")
        st.dataframe(trendyol_debug, use_container_width=True, hide_index=True)
        st.write("Kreatif/Meta debug")
        st.dataframe(creative_debug, use_container_width=True, hide_index=True)
        st.write("Panel summary dosyaları")
        st.dataframe(summary_info_df, use_container_width=True, hide_index=True)

        st.write("Kaynak klasörleri")
        st.code(f"Shopify: {SHOPIFY_DIR}\nTrendyol: {TRENDYOL_DIR}\nHepsiburada: {HEPSIBURADA_DIR}\nKreatif/Meta: {KREATIF_DIR}")


# =========================================================
# LIVE CHAT
# =========================================================
st.markdown(
    """
    <div class="assistant-box">
        <h3 style="color:white; margin-bottom: 6px;">💬 Raporlara Göre Gemini Asistanı</h3>
        <p style="color: rgba(255,255,255,0.70); margin-bottom: 0;">
            Net ciro Shopify'dan, reklam verileri Kreatif_Takip/Meta'dan alınır. Sorularını buna göre yanıtlar.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2 = st.columns([1, 1])
with c1:
    ai_provider = st.selectbox("AI Motoru", ["Yerel Kural Bazlı", "Gemini"], index=1)
with c2:
    gemini_model = st.text_input("Gemini model", value="gemini-2.5-flash")

context = build_report_context()

quick_questions = [
    "Net ciromuz nereden geliyor ve durum nasıl?",
    "Kreatif/Meta reklam performansı nasıl?",
    "ROAS ve net kârı yorumla.",
    "Hangi kreatifleri ölçeklemeliyim?",
    "Shopify ürün ve kâr durumunu yorumla.",
    "30 günlük satış ve nakit riskini yorumla.",
]
quick = st.selectbox("Hazır soru seç", [""] + quick_questions)

if "ai_chat_history" not in st.session_state:
    st.session_state.ai_chat_history = []

if quick and st.button("Hazır soruyu sor"):
    st.session_state.ai_chat_history.append({"role": "user", "content": quick})
    with st.spinner("Yapay zeka raporları yorumluyor..."):
        answer = call_gemini(quick, context, gemini_model) if ai_provider == "Gemini" else local_answer(quick)
    st.session_state.ai_chat_history.append({"role": "assistant", "content": answer})
    st.rerun()

for msg in st.session_state.ai_chat_history[-8:]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_prompt = st.chat_input("Raporlara göre soru sor...")
if user_prompt:
    st.session_state.ai_chat_history.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.spinner("Yapay zeka raporları yorumluyor..."):
        answer = call_gemini(user_prompt, context, gemini_model) if ai_provider == "Gemini" else local_answer(user_prompt)

    st.session_state.ai_chat_history.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)

with st.expander("AI'ın kullandığı rapor özetini göster"):
    st.code(context)


# =========================================================
# SELECTED REPORT + TABS
# =========================================================
st.divider()
st.subheader(f"Seçili Rapor: {selected_report}")

if selected_report == "Net Ciro ve Sipariş Yorumu":
    st.markdown(f"""
**Durum Özeti:** Toplam net ciro 3 kanaldan geliyor: **{money(all_net_revenue)}**.  

- Shopify: **{money(shopify_net_revenue)}**
- Trendyol: **{money(trendyol_net_revenue)}** *(öncelik: Trendyol sayfası Total Revenue özet dosyası)*
- Hepsiburada: **{money(hepsiburada_net_revenue)}**

**Toplam Sipariş:** {all_order_count:,}  
**Genel AOV:** {money(all_aov)}  

**Önemli düzeltme:** Kreatif_Takip net ciro kaynağı değildir. Kreatif_Takip sadece Meta reklam verisidir.
""")

elif selected_report == "Anlık Net Kar":
    st.markdown(f"""
**Shopify Gross Profit Before Ads:** {money(shopify_gross_profit)}  
**Meta Spend / Kreatif_Takip:** {money(ad_spend)}  
**Net Profit After Ads:** {money(net_profit_after_ads)}  

Net kâr hesabı: Shopify kârı - Meta reklam harcaması.
""")

elif selected_report == "Kanal Karlılık Kıyaslaması":
    if platform_summary.empty:
        st.info("Kanal verisi yok.")
    else:
        st.dataframe(
            platform_summary.style.format({
                "net_revenue": "{:,.2f} TL",
                "gross_profit_before_ads": "{:,.2f} TL",
                "ad_spend": "{:,.2f} TL",
                "ad_revenue": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "roas": "{:.2f}",
                "aov": "{:,.2f} TL",
            }),
            use_container_width=True,
            hide_index=True,
        )

elif selected_report == "Kampanya Bazlı ROAS":
    if creative_summary.empty:
        st.info("Kreatif/Meta verisi yok.")
    else:
        campaign = creative_summary.groupby("campaign_name", as_index=False).agg(
            spend=("spend", "sum"),
            ad_revenue=("ad_revenue", "sum"),
            purchases=("purchases", "sum"),
        )
        campaign["roas"] = campaign.apply(lambda r: safe_divide(r["ad_revenue"], r["spend"]), axis=1)
        st.dataframe(campaign.sort_values("roas", ascending=False), use_container_width=True, hide_index=True)

elif selected_report == "Kreatif Karnesi":
    if creative_summary.empty:
        st.info("Kreatif verisi yok.")
    else:
        creative_summary["decision"] = creative_summary.apply(
            lambda r: "Ölçekle" if r["roas"] >= 3 and r["purchases"] >= 1 else ("Durdurmayı Değerlendir" if r["spend"] >= 500 and r["roas"] < 1.5 else "İzle"),
            axis=1,
        )
        st.dataframe(creative_summary.sort_values(["decision", "roas"], ascending=[True, False]), use_container_width=True, hide_index=True)

elif selected_report == "CAC ve Müşteri Edinme Yorumu":
    st.markdown(f"""
**CAC:** {money(cac)}  
**Ad Spend:** {money(ad_spend)}  
**Ad Purchases:** {ad_purchases:,.0f}  

Yeni müşteri sayısı manuel girilirse CAC daha doğru hesaplanır.
""")

elif selected_report == "Sepet Ortalaması (AOV)":
    st.markdown(f"Shopify AOV: **{money(shopify_aov)}**")

elif selected_report == "30 Günlük Satış Tahmini":
    if date_sources and not all_time:
        days = max((pd.Timestamp(max(start_date, end_date)) - pd.Timestamp(min(start_date, end_date))).days + 1, 1)
    else:
        valid = pd.to_datetime(shopify_orders["order_date"], errors="coerce").dropna() if not shopify_orders.empty else pd.Series(dtype="datetime64[ns]")
        days = max((valid.max() - valid.min()).days + 1, 1) if not valid.empty else 1
    forecast_revenue = safe_divide(shopify_net_revenue, days) * 30
    forecast_profit = safe_divide(shopify_gross_profit, days) * 30 - safe_divide(ad_spend, days) * 30
    st.markdown(f"""
**30 Günlük Shopify Net Ciro Tahmini:** {money(forecast_revenue)}  
**30 Günlük Net Kâr Tahmini:** {money(forecast_profit)}
""")

elif selected_report == "Nakit Akış Projeksiyonu":
    valid = pd.to_datetime(shopify_orders["order_date"], errors="coerce").dropna() if not shopify_orders.empty else pd.Series(dtype="datetime64[ns]")
    days = max((valid.max() - valid.min()).days + 1, 1) if not valid.empty else 1
    projected_gross_profit = safe_divide(shopify_gross_profit, days) * 30
    projected_ad_spend = safe_divide(ad_spend, days) * 30
    projected_cash = current_cash + projected_gross_profit - projected_ad_spend - fixed_costs_30d - planned_stock_purchase
    st.markdown(f"""
**30 Gün Sonu Tahmini Nakit:** {money(projected_cash)}  
Hesap: mevcut nakit + Shopify kâr tahmini - Meta reklam harcaması - sabit gider - stok alımı.
""")

else:
    st.markdown(local_answer("genel özet"))


tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Kanallar", "🟠 Trendyol", "🎨 Kreatif / Meta", "📦 Shopify Ürün", "🧪 Veri Durumu"])

with tab1:
    st.subheader("Kanal Bazlı Satış Özeti")
    st.dataframe(platform_summary, use_container_width=True, hide_index=True)

    st.subheader("Shopify Kaynaklı Satış Verisi")
    if shopify_orders.empty:
        st.warning("Shopify sipariş verisi yok.")
    else:
        st.dataframe(shopify_orders.sort_values("order_date", ascending=False), use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Trendyol Kaynaklı Satış Verisi")
    st.info("Trendyol net ciro burada pages/smartek_app klasöründeki sipariş / Tedarikci_Siparisleri dosyalarından alınır.")
    st.markdown("### Trendyol Sayfası Total Revenue Özet Durumu")
    if trendyol_page_summary_debug.empty:
        st.warning("Trendyol sayfası özet debug verisi yok.")
    else:
        st.dataframe(trendyol_page_summary_debug, use_container_width=True, hide_index=True)

    st.markdown("### Trendyol Sipariş Fallback Okuma Durumu")
    if trendyol_debug.empty:
        st.info("Fallback sipariş debug verisi yok.")
    else:
        st.dataframe(trendyol_debug, use_container_width=True, hide_index=True)

    if trendyol_orders.empty:
        st.warning("Trendyol sipariş verisi okunamadı.")
    else:
        st.markdown("### Trendyol Sipariş Özeti")
        st.dataframe(trendyol_orders.sort_values("net_sales", ascending=False), use_container_width=True, hide_index=True)

    if not trendyol_lines.empty:
        st.markdown("### Trendyol Ürün Satırları")
        st.dataframe(trendyol_lines.sort_values("line_revenue", ascending=False).head(100), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Kreatif_Takip Kaynaklı Meta Verisi")
    if creative_summary.empty:
        st.warning("Kreatif/Meta verisi yok.")
    else:
        st.dataframe(creative_summary.sort_values("spend", ascending=False), use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Shopify Ürün ve Kâr")
    if product_summary.empty:
        st.warning("Ürün verisi yok.")
    else:
        st.dataframe(product_summary, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Veri Kaynakları")
    status = pd.DataFrame([
        {"Alan": "Shopify Net Ciro", "Kaynak": str(SHOPIFY_DIR), "Durum": "OK" if not shopify_orders.empty else "Eksik"},
        {"Alan": "Shopify Maliyet", "Kaynak": str(SHOPIFY_DIR), "Durum": "OK" if not shopify_costs.empty else "Eksik"},
        {"Alan": "Meta / Kreatif", "Kaynak": str(KREATIF_DIR), "Durum": "OK" if not creative_ads_all.empty else "Eksik"},
        {"Alan": "Trendyol", "Kaynak": str(TRENDYOL_DIR), "Durum": "OK" if not trendyol_orders.empty else "Opsiyonel/Eksik"},
        {"Alan": "Hepsiburada", "Kaynak": str(HEPSIBURADA_DIR), "Durum": "OK" if not hepsiburada_orders.empty else "Opsiyonel/Eksik"},
    ])
    st.dataframe(status, use_container_width=True, hide_index=True)

    st.markdown("### Panel Summary Durumu")
    st.dataframe(summary_info_df, use_container_width=True, hide_index=True)

    st.markdown("### Önemli veri kuralı")
    st.info("Yapay Zeka önce her panelin panel_summary.csv dosyasını okur. Böylece panellerde görünen aynı istatistikler AI sayfasında aynı değerle toplanır. Summary yoksa ham dosyalardan fallback hesaplama yapar.")
