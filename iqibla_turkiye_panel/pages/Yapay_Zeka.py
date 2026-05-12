
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# PAGE
# =========================================================
st.set_page_config(page_title="SMARTEK360 | Yapay Zeka Analiz", layout="wide")

# Ana sayfadan giriş yapılmadan açılmasın.
if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🤖 SMARTEK360: Yapay Zeka Analiz Paneli")
st.caption(
    "Shopify, Trendyol, Hepsiburada ve Kreatif Takibi verilerini okuyarak net ciro, sipariş, kâr, ROAS, CAC, stok, tahmin ve aksiyon yorumları üretir."
)


# =========================================================
# PATHS
# =========================================================
def find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "ana_sayfa.py").exists():
            return parent
    # Normal yapı: e-ticaret-analiz/pages/Yapay_Zeka/Yapay_Zeka.py
    return Path(__file__).resolve().parents[2]


PROJECT_DIR = find_project_root()
PAGES_DIR = PROJECT_DIR / "pages"

SHOPIFY_DIR = PAGES_DIR / "Shopify_app"
TRENDYOL_DIR = PAGES_DIR / "smartek_app"
HEPSIBURADA_DIR = PAGES_DIR / "Hepsiburada_app"
KREATIF_DIR = PAGES_DIR / "Kreatif_Takip"
AI_DIR = Path(__file__).resolve().parent


# =========================================================
# HELPERS
# =========================================================
def normalize_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).lower().strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
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
    s = str(value).strip().replace(" ", "")
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


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    normalized_cols = {normalize_text(c): c for c in df.columns}
    normalized_candidates = [normalize_text(c) for c in candidates]

    for target in normalized_candidates:
        for norm_col, raw_col in normalized_cols.items():
            if target == norm_col:
                return raw_col

    for target in normalized_candidates:
        for norm_col, raw_col in normalized_cols.items():
            if target and target in norm_col:
                return raw_col

    return None


def read_csv_flexible(path: Path | str) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]
    seps = [",", ";", "\t"]

    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception:
                continue

    return pd.DataFrame()


def safe_divide(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def money(value: float) -> str:
    return f"{value:,.2f} TL"


def pct(value: float) -> str:
    return f"%{value:,.1f}"


def list_csvs(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.csv"))


def date_minmax(series: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp]:
    parsed = pd.to_datetime(series, errors="coerce").dropna()
    if parsed.empty:
        today = pd.Timestamp.today().normalize()
        return today, today
    return parsed.min(), parsed.max()


# =========================================================
# MANUAL STOCK MAP
# =========================================================
MANUAL_INVENTORY = {
    "j01t green": 102,
    "j01t camel": 102,
    "j01 blue": 60,
    "j01 grey": 47,
    "j03 pro titanium": 541,
    "black j01t": 266,
    "j01t black": 266,
    "salat counter": 35,
    "premium black gold 22mm": 9,
    "premium rose gold 20mm": 7,
    "premium black gray 22mm": 7,
    "j01 pink": 120,
    "j01 green": 120,
    "j01 black": 160,
}


def infer_inventory_key(product_name: str) -> str:
    text = normalize_text(product_name)

    if "jood lite" in text or "j01t" in text:
        if "yesil" in text or "green" in text:
            return "j01t green"
        if "camel" in text or "kum" in text or "bej" in text:
            return "j01t camel"
        if "siyah" in text or "black" in text:
            return "j01t black"

    if "jood 3 pro" in text or "j03 pro" in text:
        if "titanyum" in text or "titanium" in text or "gri" in text:
            return "j03 pro titanium"

    if "rekat" in text or "salat" in text or "salavatmatik" in text:
        return "salat counter"

    if "premium" in text:
        if "rose" in text and "20" in text:
            return "premium rose gold 20mm"
        if "black" in text and "gold" in text and "22" in text:
            return "premium black gold 22mm"
        if ("gray" in text or "grey" in text or "gri" in text) and "22" in text:
            return "premium black gray 22mm"

    if "jood" in text or "j01" in text:
        if "pembe" in text or "pink" in text:
            return "j01 pink"
        if "yesil" in text or "green" in text:
            return "j01 green"
        if "siyah" in text or "black" in text:
            return "j01 black"
        if "mavi" in text or "blue" in text:
            return "j01 blue"
        if "gri" in text or "grey" in text or "gray" in text:
            return "j01 grey"

    return ""


# =========================================================
# LOAD SHOPIFY
# =========================================================
@st.cache_data(show_spinner=False)
def load_shopify_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders_rows = []
    line_rows = []

    for path in list_csvs(SHOPIFY_DIR):
        name = path.name.lower()
        if "maliyet" in name or "meta" in name or "formatted report" in name:
            continue
        if "shopify002" in name or "shopify003" in name or "shopify004" in name:
            continue
        if "shopify" not in name:
            continue

        df = read_csv_flexible(path)
        if df.empty:
            continue

        name_col = find_col(df, ["Name"])
        created_col = find_col(df, ["Created at"])
        total_col = find_col(df, ["Total"])
        refund_col = find_col(df, ["Refunded Amount"])
        cancelled_col = find_col(df, ["Cancelled at"])
        financial_col = find_col(df, ["Financial Status"])
        product_col = find_col(df, ["Lineitem name"])
        qty_col = find_col(df, ["Lineitem quantity"])
        sku_col = find_col(df, ["Lineitem sku"])
        price_col = find_col(df, ["Lineitem price"])

        if not name_col or not created_col or not total_col:
            continue

        tmp = pd.DataFrame({
            "platform": "Shopify",
            "order_id": df[name_col].astype(str),
            "order_date": pd.to_datetime(df[created_col], errors="coerce", utc=True).dt.tz_localize(None),
            "net_sales": df[total_col].apply(to_float),
            "refund": df[refund_col].apply(to_float) if refund_col else 0.0,
            "cancelled_at": pd.to_datetime(df[cancelled_col], errors="coerce", utc=True).dt.tz_localize(None) if cancelled_col else pd.NaT,
            "financial_status": df[financial_col].astype(str) if financial_col else "",
            "source_file": path.name,
        })
        tmp["is_cancelled"] = tmp["cancelled_at"].notna() | tmp["financial_status"].str.lower().isin(["voided", "void"])
        tmp.loc[tmp["is_cancelled"], "net_sales"] = 0.0
        tmp["net_sales"] = tmp["net_sales"] - tmp["refund"].fillna(0.0)

        if product_col:
            lines = pd.DataFrame({
                "platform": "Shopify",
                "order_id": df[name_col].astype(str),
                "order_date": tmp["order_date"],
                "product_name": df[product_col].astype(str),
                "sku": df[sku_col].apply(clean_sku) if sku_col else "",
                "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
                "line_revenue": df[price_col].apply(to_float) * (df[qty_col].apply(to_float) if qty_col else 1.0) if price_col else 0.0,
                "source_file": path.name,
            })
            lines.loc[tmp["is_cancelled"], ["qty", "line_revenue"]] = 0.0
            line_rows.append(lines)

        orders_rows.append(tmp)

    if orders_rows:
        orders = pd.concat(orders_rows, ignore_index=True)
        orders = orders.drop_duplicates(subset=["order_id", "order_date", "net_sales"], keep="first")
        order_summary = orders.groupby("order_id", as_index=False).agg(
            platform=("platform", "first"),
            order_date=("order_date", "first"),
            net_sales=("net_sales", "first"),
            source_file=("source_file", "first"),
        )
    else:
        order_summary = pd.DataFrame(columns=["platform", "order_id", "order_date", "net_sales", "source_file"])

    lines_df = pd.concat(line_rows, ignore_index=True) if line_rows else pd.DataFrame(
        columns=["platform", "order_id", "order_date", "product_name", "sku", "qty", "line_revenue", "source_file"]
    )

    # Cost table
    cost_files = [p for p in list_csvs(SHOPIFY_DIR) if "maliyet" in p.name.lower()]
    costs = pd.DataFrame(columns=["sku", "unit_cost", "commission_rate", "shipping_cost"])
    if cost_files:
        cdf = read_csv_flexible(cost_files[0])
        if not cdf.empty:
            sku_col = find_col(cdf, ["SKU"])
            cost_col = find_col(cdf, ["Maliyet", "Cost"])
            comm_col = find_col(cdf, ["Komisyon"])
            ship_col = find_col(cdf, ["Kargo", "Shipping"])
            if sku_col:
                costs = pd.DataFrame({
                    "sku": cdf[sku_col].apply(clean_sku),
                    "unit_cost": cdf[cost_col].apply(to_float) if cost_col else 0.0,
                    "commission_rate": cdf[comm_col].apply(to_float) if comm_col else 0.0,
                    "shipping_cost": cdf[ship_col].apply(to_float) if ship_col else 0.0,
                }).drop_duplicates("sku", keep="last")

    if not lines_df.empty and not costs.empty:
        lines_df = lines_df.merge(costs, on="sku", how="left")
        lines_df["unit_cost"] = lines_df["unit_cost"].fillna(0.0)
        lines_df["commission_rate"] = lines_df["commission_rate"].fillna(0.0)
        lines_df["shipping_cost"] = lines_df["shipping_cost"].fillna(0.0)
        lines_df["gross_profit"] = (
            lines_df["line_revenue"]
            - (lines_df["unit_cost"] + lines_df["shipping_cost"]) * lines_df["qty"]
            - lines_df["line_revenue"] * lines_df["commission_rate"]
        )
    elif not lines_df.empty:
        lines_df["gross_profit"] = lines_df["line_revenue"] * 0.45
    else:
        lines_df["gross_profit"] = []

    return order_summary, lines_df, costs


# =========================================================
# LOAD TRENDYOL
# =========================================================
@st.cache_data(show_spinner=False)
def load_trendyol_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    order_rows = []

    for path in list_csvs(TRENDYOL_DIR):
        lname = path.name.lower()
        if "tedarikci_siparisleri" not in normalize_text(lname) and "siparis" not in normalize_text(lname):
            continue

        df = read_csv_flexible(path)
        if df.empty:
            continue

        # Bazı Trendyol raporlarında ilk satır açıklama oluyor; tekrar skiprows dene.
        if not find_col(df, ["Sipariş Tarihi", "Siparis Tarihi"]):
            try:
                df2 = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str, skiprows=1, low_memory=False)
                if df2.shape[1] > 1:
                    df = df2
            except Exception:
                pass

        date_col = find_col(df, ["Sipariş Tarihi", "Siparis Tarihi"])
        order_col = find_col(df, ["Sipariş Numarası", "Siparis Numarasi"])
        qty_col = find_col(df, ["Adet"])
        status_col = find_col(df, ["Sipariş Statüsü", "Siparis Statusu"])
        sku_col = find_col(df, ["Barkod", "SKU"])
        product_col = find_col(df, ["Ürün Ad", "Urun Ad", "Product"])
        revenue_col = find_col(df, ["Faturalanacak Tutar", "Satış Tutarı", "Satis Tutari"])

        if not order_col or not revenue_col:
            continue

        tmp = pd.DataFrame({
            "platform": "Trendyol",
            "order_id": df[order_col].astype(str),
            "order_date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True) if date_col else pd.NaT,
            "product_name": df[product_col].astype(str) if product_col else "",
            "sku": df[sku_col].apply(clean_sku) if sku_col else "",
            "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
            "line_revenue": df[revenue_col].apply(to_float),
            "status": df[status_col].astype(str) if status_col else "",
            "source_file": path.name,
        })
        tmp["is_returned"] = tmp["status"].str.contains("ade|iptal|cancel|return", case=False, na=False)
        tmp.loc[tmp["is_returned"], ["qty", "line_revenue"]] = 0.0
        order_rows.append(tmp)

    lines = pd.concat(order_rows, ignore_index=True) if order_rows else pd.DataFrame(
        columns=["platform", "order_id", "order_date", "product_name", "sku", "qty", "line_revenue", "source_file"]
    )

    # Cost table
    cost_files = [p for p in list_csvs(TRENDYOL_DIR) if "maliyet" in normalize_text(p.name)]
    costs = pd.DataFrame(columns=["sku", "unit_cost", "commission_rate", "shipping_cost"])
    if cost_files:
        cdf = read_csv_flexible(cost_files[0])
        if not cdf.empty:
            sku_col = find_col(cdf, ["SKU"])
            cost_col = find_col(cdf, ["Maliyet", "Cost"])
            comm_col = find_col(cdf, ["Komisyon"])
            ship_col = find_col(cdf, ["Kargo", "Shipping"])
            if sku_col:
                costs = pd.DataFrame({
                    "sku": cdf[sku_col].apply(clean_sku),
                    "unit_cost": cdf[cost_col].apply(to_float) if cost_col else 0.0,
                    "commission_rate": cdf[comm_col].apply(to_float) if comm_col else 0.0,
                    "shipping_cost": cdf[ship_col].apply(to_float) if ship_col else 0.0,
                }).drop_duplicates("sku", keep="last")

    if not lines.empty and not costs.empty:
        lines = lines.merge(costs, on="sku", how="left")
        lines["unit_cost"] = lines["unit_cost"].fillna(0.0)
        lines["commission_rate"] = lines["commission_rate"].fillna(0.0)
        lines["shipping_cost"] = lines["shipping_cost"].fillna(0.0)
        lines["gross_profit"] = (
            lines["line_revenue"]
            - (lines["unit_cost"] + lines["shipping_cost"]) * lines["qty"]
            - lines["line_revenue"] * lines["commission_rate"]
        )
    elif not lines.empty:
        lines["gross_profit"] = lines["line_revenue"] * 0.45
    else:
        lines["gross_profit"] = []

    if not lines.empty:
        orders = lines.groupby("order_id", as_index=False).agg(
            platform=("platform", "first"),
            order_date=("order_date", "first"),
            net_sales=("line_revenue", "sum"),
            source_file=("source_file", "first"),
        )
    else:
        orders = pd.DataFrame(columns=["platform", "order_id", "order_date", "net_sales", "source_file"])

    # Manual weekly ads
    ads = pd.DataFrame(columns=["platform", "date", "spend", "attributed_revenue", "campaign_name"])
    weekly_file = TRENDYOL_DIR / "manual_weekly_trendyol_ads.csv"
    if weekly_file.exists():
        wdf = read_csv_flexible(weekly_file)
        if not wdf.empty:
            week_col = find_col(wdf, ["week_start", "Hafta Başlangıç", "Hafta Baslangic"])
            spend_col = find_col(wdf, ["weekly_spend", "Spend", "Harcama"])
            revenue_col = find_col(wdf, ["weekly_revenue", "Revenue", "Reklam Cirosu", "Total Ad Revenue"])
            note_col = find_col(wdf, ["note", "campaign", "Açıklama", "Aciklama"])
            rows = []
            if week_col and spend_col:
                for _, r in wdf.iterrows():
                    start = pd.to_datetime(r.get(week_col), errors="coerce")
                    if pd.isna(start):
                        continue
                    spend = to_float(r.get(spend_col))
                    revenue = to_float(r.get(revenue_col)) if revenue_col else 0.0
                    note = str(r.get(note_col, "Manual Weekly Spend")) if note_col else "Manual Weekly Spend"
                    for day in pd.date_range(start, start + pd.Timedelta(days=6), freq="D"):
                        rows.append({
                            "platform": "Trendyol",
                            "date": day,
                            "spend": spend / 7,
                            "attributed_revenue": revenue / 7,
                            "campaign_name": note,
                        })
            ads = pd.DataFrame(rows) if rows else ads

    return orders, lines, ads


# =========================================================
# LOAD HEPSIBURADA
# =========================================================
@st.cache_data(show_spinner=False)
def load_hepsiburada_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sales_candidates = []

    for path in list_csvs(HEPSIBURADA_DIR):
        lname = normalize_text(path.name)
        if not lname.startswith("hepsiburada"):
            continue
        df = read_csv_flexible(path)
        if df.empty:
            continue

        sku_col = find_col(df, ["SKU"])
        product_col = find_col(df, ["Urun Adi", "Ürün Adı", "Product Name"])
        qty_col = find_col(df, ["Toplam Satis Adedi", "Total Sales Qty", "Satis Miktari"])
        rev_col = find_col(df, ["Toplam Satis Tutari", "Total Sales Amount"])
        comm_col = find_col(df, ["Komisyon Tutar", "Commission Amount"])

        if sku_col and product_col and qty_col and rev_col:
            tmp = pd.DataFrame({
                "platform": "Hepsiburada",
                "order_id": path.stem,
                "order_date": pd.NaT,
                "product_name": df[product_col].astype(str),
                "sku": df[sku_col].apply(clean_sku),
                "qty": df[qty_col].apply(to_float),
                "line_revenue": df[rev_col].apply(to_float),
                "commission_amount": df[comm_col].apply(to_float) if comm_col else 0.0,
                "source_file": path.name,
            })
            sales_candidates.append(tmp)

    if sales_candidates:
        # Aggregate snapshot: en yüksek ciro dosyasını seç, çift sayımı önle.
        selected = max(sales_candidates, key=lambda x: x["line_revenue"].sum()).copy()
    else:
        selected = pd.DataFrame(columns=["platform", "order_id", "order_date", "product_name", "sku", "qty", "line_revenue", "source_file"])

    cost_files = [p for p in list_csvs(HEPSIBURADA_DIR) if "maliyet" in normalize_text(p.name)]
    costs = pd.DataFrame(columns=["sku", "unit_cost", "commission_rate", "shipping_cost"])
    if cost_files:
        cdf = read_csv_flexible(cost_files[0])
        if not cdf.empty:
            sku_col = find_col(cdf, ["SKU"])
            cost_col = find_col(cdf, ["Maliyet", "Cost"])
            comm_col = find_col(cdf, ["Komisyon oran", "Commission Rate"])
            ship_col = find_col(cdf, ["Kargo", "Shipping"])
            if sku_col:
                costs = pd.DataFrame({
                    "sku": cdf[sku_col].apply(clean_sku),
                    "unit_cost": cdf[cost_col].apply(to_float) if cost_col else 0.0,
                    "commission_rate": cdf[comm_col].apply(to_float) if comm_col else 0.0,
                    "shipping_cost": cdf[ship_col].apply(to_float) if ship_col else 0.0,
                }).drop_duplicates("sku", keep="last")

    if not selected.empty and not costs.empty:
        selected = selected.merge(costs, on="sku", how="left")
        selected["unit_cost"] = selected["unit_cost"].fillna(0.0)
        selected["commission_rate"] = selected["commission_rate"].fillna(0.0)
        selected["shipping_cost"] = selected["shipping_cost"].fillna(0.0)
        selected["gross_profit"] = (
            selected["line_revenue"]
            - (selected["unit_cost"] + selected["shipping_cost"]) * selected["qty"]
            - selected["line_revenue"] * selected["commission_rate"]
        )
    elif not selected.empty:
        selected["gross_profit"] = selected["line_revenue"] * 0.45
    else:
        selected["gross_profit"] = []

    if not selected.empty:
        orders = pd.DataFrame([{
            "platform": "Hepsiburada",
            "order_id": "aggregate_snapshot",
            "order_date": pd.NaT,
            "net_sales": float(selected["line_revenue"].sum()),
            "source_file": selected["source_file"].iloc[0] if "source_file" in selected.columns else "",
        }])
    else:
        orders = pd.DataFrame(columns=["platform", "order_id", "order_date", "net_sales", "source_file"])

    ads = pd.DataFrame(columns=["platform", "date", "spend", "attributed_revenue", "campaign_name"])
    return orders, selected, ads


# =========================================================
# LOAD KREATIF
# =========================================================
@st.cache_data(show_spinner=False)
def load_creative_data() -> pd.DataFrame:
    rows = []

    for path in list_csvs(KREATIF_DIR):
        if path.name.lower() in {"creative_history.csv", "creative_summary.csv", "creative_scorecard.csv"}:
            continue
        df = read_csv_flexible(path)
        if df.empty:
            continue

        campaign_col = find_col(df, ["Kampanya Adı", "Campaign name", "Campaign"])
        ad_col = find_col(df, ["Reklam Adı", "Reklamlar", "Ad name", "Ad"])
        reach_col = find_col(df, ["Erişim", "Reach"])
        imp_col = find_col(df, ["Gösterim", "Impressions"])
        result_col = find_col(df, ["Sonuçlar", "Results"])
        spend_col = find_col(df, ["Harcanan Tutar (TRY)", "Amount spent", "Spend", "Harcama"])
        purchase_col = find_col(df, ["Alışverişler", "Purchases", "Satın almalar"])
        roas_col = find_col(df, ["Alışveriş Reklam Harcamasının Getirisi", "Purchase ROAS", "ROAS"])
        ctr_col = find_col(df, ["CTR", "CTR (Tümü)"])
        cpc_col = find_col(df, ["CPC"])
        cpm_col = find_col(df, ["CPM"])
        freq_col = find_col(df, ["Sıklık", "Frequency"])
        start_col = find_col(df, ["Rapor Başlangıcı", "Reporting starts"])
        end_col = find_col(df, ["Rapor Sonu", "Reporting ends"])
        avg_purchase_value_col = find_col(df, ["Ortalama alışveriş dönüşüm değeri", "Average purchase conversion value"])

        if not spend_col:
            continue

        tmp = pd.DataFrame({
            "campaign_name": df[campaign_col].astype(str) if campaign_col else "Bilinmeyen Kampanya",
            "creative_name": df[ad_col].astype(str) if ad_col else "Bilinmeyen Kreatif",
            "reach": df[reach_col].apply(to_float) if reach_col else 0.0,
            "impressions": df[imp_col].apply(to_float) if imp_col else 0.0,
            "results": df[result_col].apply(to_float) if result_col else 0.0,
            "spend": df[spend_col].apply(to_float),
            "purchases": df[purchase_col].apply(to_float) if purchase_col else 0.0,
            "roas": df[roas_col].apply(to_float) if roas_col else 0.0,
            "ctr": df[ctr_col].apply(to_float) if ctr_col else 0.0,
            "cpc": df[cpc_col].apply(to_float) if cpc_col else 0.0,
            "cpm": df[cpm_col].apply(to_float) if cpm_col else 0.0,
            "frequency": df[freq_col].apply(to_float) if freq_col else 0.0,
            "report_start": pd.to_datetime(df[start_col], errors="coerce") if start_col else pd.NaT,
            "report_end": pd.to_datetime(df[end_col], errors="coerce") if end_col else pd.NaT,
            "avg_purchase_value": df[avg_purchase_value_col].apply(to_float) if avg_purchase_value_col else 0.0,
            "source_file": path.name,
        })
        tmp["attributed_revenue"] = tmp["spend"] * tmp["roas"]
        tmp.loc[tmp["attributed_revenue"].eq(0), "attributed_revenue"] = tmp["purchases"] * tmp["avg_purchase_value"]
        tmp["cac"] = tmp.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
        tmp["calculated_roas"] = tmp.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
        tmp["report_date"] = tmp["report_end"].fillna(tmp["report_start"])
        rows.append(tmp)

    if not rows:
        return pd.DataFrame(columns=[
            "campaign_name", "creative_name", "reach", "impressions", "results",
            "spend", "purchases", "roas", "ctr", "cpc", "cpm", "frequency",
            "attributed_revenue", "cac", "calculated_roas", "report_date", "source_file"
        ])

    out = pd.concat(rows, ignore_index=True)
    out = out[~((out["campaign_name"].fillna("").str.strip() == "") & (out["creative_name"].fillna("").str.strip() == ""))]
    return out.reset_index(drop=True)


# =========================================================
# BUILD MODEL
# =========================================================
@st.cache_data(show_spinner=False)
def build_model():
    shopify_orders, shopify_lines, _ = load_shopify_data()
    trendyol_orders, trendyol_lines, trendyol_ads = load_trendyol_data()
    hb_orders, hb_lines, hb_ads = load_hepsiburada_data()
    creative = load_creative_data()

    orders = pd.concat([shopify_orders, trendyol_orders, hb_orders], ignore_index=True)
    lines = pd.concat([shopify_lines, trendyol_lines, hb_lines], ignore_index=True)
    ads = pd.concat([trendyol_ads, hb_ads], ignore_index=True)

    # Kreatif raporunda reklam harcaması varsa genel reklam performansına dahil et.
    if not creative.empty:
        creative_ads = pd.DataFrame({
            "platform": "Kreatif/Meta",
            "date": creative["report_date"],
            "spend": creative["spend"],
            "attributed_revenue": creative["attributed_revenue"],
            "campaign_name": creative["campaign_name"],
        })
        ads = pd.concat([ads, creative_ads], ignore_index=True)

    # product stock
    if not lines.empty:
        lines["inventory_key"] = lines["product_name"].apply(infer_inventory_key)
        lines["stock_units"] = lines["inventory_key"].map(MANUAL_INVENTORY)
    else:
        lines["inventory_key"] = []
        lines["stock_units"] = []

    return {
        "orders": orders,
        "lines": lines,
        "ads": ads,
        "creative": creative,
    }


model = build_model()
orders_all = model["orders"]
lines_all = model["lines"]
ads_all = model["ads"]
creative_all = model["creative"]


# =========================================================
# SIDEBAR INPUTS
# =========================================================
with st.sidebar:
    st.header("AI Varsayımları")

    monthly_revenue_target = st.number_input(
        "Aylık Net Ciro Hedefi (TL)",
        min_value=0.0,
        value=500000.0,
        step=50000.0,
        format="%.2f",
    )
    fixed_costs_30d = st.number_input(
        "30 Günlük Sabit Gider (TL)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        format="%.2f",
    )
    current_cash = st.number_input(
        "Mevcut Nakit (TL)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        format="%.2f",
    )
    planned_stock_purchase = st.number_input(
        "Planlanan Stok Alımı (TL)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        format="%.2f",
    )
    new_customer_count = st.number_input(
        "Yeni Müşteri Sayısı (veri yoksa manuel)",
        min_value=0,
        value=0,
        step=10,
    )
    returning_customer_count = st.number_input(
        "Geri Gelen Müşteri Sayısı (veri yoksa manuel)",
        min_value=0,
        value=0,
        step=10,
    )
    avg_purchase_per_customer = st.number_input(
        "LTV için müşteri başı ort. satın alma adedi",
        min_value=1.0,
        value=1.5,
        step=0.1,
    )
    stock_lead_days = st.number_input(
        "Stok besleme için tedarik süresi (gün)",
        min_value=1,
        value=30,
        step=1,
    )
    low_stock_threshold = st.number_input(
        "Ölü / düşük stok eşiği",
        min_value=0,
        value=10,
        step=1,
    )
    selected_report = st.selectbox(
        "AI rapor başlığı seç",
        [
            "Genel Yönetici Özeti",
            "Net Ciro ve Sipariş Yorumu",
            "Hedef Gerçekleşme Oranı",
            "Anlık Net Kar",
            "Top-Seller Listesi",
            "Ölü Stok Alarmı",
            "Kanal Karlılık Kıyaslaması",
            "Kampanya Bazlı ROAS",
            "Kreatif Karnesi",
            "CAC ve Müşteri Edinme Yorumu",
            "Yeni vs. Geri Gelen Müşteri",
            "Sepet Ortalaması (AOV)",
            "LTV Yorumu",
            "İş Birliği Performansı",
            "Erişim vs. Dönüşüm",
            "30 Günlük Satış Tahmini",
            "Stok Besleme Planı",
            "Nakit Akış Projeksiyonu",
            "Yapay Zeka Notu",
        ],
    )

    st.markdown("---")
    st.caption(f"Project root: {PROJECT_DIR}")


# =========================================================
# DATE FILTER
# =========================================================
date_candidates = []
if not orders_all.empty and "order_date" in orders_all.columns:
    date_candidates.append(pd.to_datetime(orders_all["order_date"], errors="coerce"))
if not ads_all.empty and "date" in ads_all.columns:
    date_candidates.append(pd.to_datetime(ads_all["date"], errors="coerce"))
if not creative_all.empty and "report_date" in creative_all.columns:
    date_candidates.append(pd.to_datetime(creative_all["report_date"], errors="coerce"))

if date_candidates:
    all_dates = pd.concat([s.dropna() for s in date_candidates if not s.dropna().empty], ignore_index=True)
else:
    all_dates = pd.Series(dtype="datetime64[ns]")

if all_dates.empty:
    min_date = max_date = pd.Timestamp.today().normalize()
else:
    min_date = all_dates.min()
    max_date = all_dates.max()

top_spacer, start_col, end_col, all_time_col = st.columns([4.5, 1.4, 1.4, 1.0])
with start_col:
    start_date = st.date_input("Başlangıç", value=min_date.date(), min_value=min_date.date(), max_value=max_date.date())
with end_col:
    end_date = st.date_input("Bitiş", value=max_date.date(), min_value=min_date.date(), max_value=max_date.date())
with all_time_col:
    all_time = st.toggle("Tüm Zamanlar", value=True)

def filter_date(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns or all_time:
        return df.copy()
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    d = pd.to_datetime(df[col], errors="coerce")
    return df[(d >= s) & (d <= e)].copy()


orders = filter_date(orders_all, "order_date")
lines = filter_date(lines_all, "order_date")
ads = filter_date(ads_all, "date")
creative = filter_date(creative_all, "report_date")

period_label = "Tüm Zamanlar" if all_time else f"{min(start_date, end_date)} → {max(start_date, end_date)}"


# =========================================================
# METRICS
# =========================================================
total_revenue = float(orders["net_sales"].sum()) if not orders.empty else float(lines["line_revenue"].sum()) if not lines.empty else 0.0
order_count = int(orders["order_id"].nunique()) if not orders.empty else 0
aov = safe_divide(total_revenue, order_count)

gross_profit = float(lines["gross_profit"].sum()) if not lines.empty and "gross_profit" in lines.columns else total_revenue * 0.45
ad_spend = float(ads["spend"].sum()) if not ads.empty else 0.0
ad_revenue = float(ads["attributed_revenue"].sum()) if not ads.empty else 0.0
net_profit_now = gross_profit - ad_spend - fixed_costs_30d
overall_roas = safe_divide(ad_revenue, ad_spend)
cac = safe_divide(ad_spend, new_customer_count) if new_customer_count else safe_divide(ad_spend, float(creative["purchases"].sum()) if not creative.empty and "purchases" in creative.columns else 0)
target_rate = safe_divide(total_revenue, monthly_revenue_target) * 100 if monthly_revenue_target else 0.0
ltv = aov * avg_purchase_per_customer

platform_summary = pd.DataFrame()
if not orders.empty:
    platform_summary = orders.groupby("platform", as_index=False).agg(
        net_revenue=("net_sales", "sum"),
        orders=("order_id", "nunique"),
    )
else:
    platform_summary = pd.DataFrame(columns=["platform", "net_revenue", "orders"])

if not lines.empty:
    profit_by_platform = lines.groupby("platform", as_index=False).agg(
        gross_profit=("gross_profit", "sum"),
        units=("qty", "sum"),
    )
    platform_summary = platform_summary.merge(profit_by_platform, on="platform", how="outer").fillna(0.0)
else:
    platform_summary["gross_profit"] = 0.0
    platform_summary["units"] = 0.0

if not ads.empty:
    ads_by_platform = ads.groupby("platform", as_index=False).agg(
        ad_spend=("spend", "sum"),
        ad_revenue=("attributed_revenue", "sum"),
    )
    platform_summary = platform_summary.merge(ads_by_platform, on="platform", how="outer").fillna(0.0)
else:
    platform_summary["ad_spend"] = 0.0
    platform_summary["ad_revenue"] = 0.0

if not platform_summary.empty:
    platform_summary["net_profit_after_ads"] = platform_summary["gross_profit"] - platform_summary["ad_spend"]
    platform_summary["aov"] = platform_summary.apply(lambda r: safe_divide(r["net_revenue"], r["orders"]), axis=1)
    platform_summary["roas"] = platform_summary.apply(lambda r: safe_divide(r["ad_revenue"], r["ad_spend"]), axis=1)

if not lines.empty:
    product_summary = lines.groupby(["platform", "product_name"], as_index=False).agg(
        revenue=("line_revenue", "sum"),
        qty=("qty", "sum"),
        gross_profit=("gross_profit", "sum"),
        stock_units=("stock_units", "max"),
    ).sort_values(["qty", "revenue"], ascending=False)
else:
    product_summary = pd.DataFrame(columns=["platform", "product_name", "revenue", "qty", "gross_profit", "stock_units"])

if not creative.empty:
    creative_summary = creative.groupby(["campaign_name", "creative_name"], as_index=False).agg(
        spend=("spend", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        results=("results", "sum"),
        purchases=("purchases", "sum"),
        attributed_revenue=("attributed_revenue", "sum"),
        ctr=("ctr", "mean"),
        cpc=("cpc", "mean"),
        cpm=("cpm", "mean"),
        frequency=("frequency", "mean"),
    )
    creative_summary["roas"] = creative_summary.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
    creative_summary["cac"] = creative_summary.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
else:
    creative_summary = pd.DataFrame(columns=["campaign_name", "creative_name", "spend", "reach", "impressions", "results", "purchases", "attributed_revenue", "ctr", "cpc", "cpm", "frequency", "roas", "cac"])


# =========================================================
# AI TEXT GENERATORS
# =========================================================
def priority_label(value: str) -> str:
    return f"**Öncelik Seviyesi:** {value}"


def ai_box(title: str, durum: str, guclu: str, risk: str, aksiyon: str, oncelik: str = "Orta"):
    st.markdown(f"### {title}")
    st.markdown(f"**Durum Özeti:** {durum}")
    st.markdown(f"**Güçlü Noktalar:** {guclu}")
    st.markdown(f"**Riskler:** {risk}")
    st.markdown(f"**Aksiyon Önerisi:** {aksiyon}")
    st.markdown(priority_label(oncelik))


def create_general_note() -> str:
    notes = []

    if target_rate >= 100:
        notes.append("Ciro hedefi yakalanmış veya aşılmış görünüyor; artık odak kâr marjı ve stok sürekliliği olmalı.")
    elif target_rate >= 70:
        notes.append("Ciro hedefinin büyük kısmı tamamlanmış; kampanya ve top-seller ürünlerde ölçekleme denenebilir.")
    else:
        notes.append("Ciro hedefinin altında kalınmış; reklam verimi, ürün görünürlüğü ve kampanya teklifleri güçlendirilmeli.")

    if overall_roas >= 3:
        notes.append("Reklam ROAS seviyesi güçlü; kazanan kampanya/kreatiflerde bütçe kademeli artırılabilir.")
    elif overall_roas >= 1.5:
        notes.append("ROAS orta seviyede; düşük performanslı kreatifler ayrıştırılmazsa net kâr baskılanabilir.")
    elif ad_spend > 0:
        notes.append("ROAS düşük; harcama satışa yeterince dönmüyor, kreatif ve hedefleme kontrol edilmeli.")

    if net_profit_now < 0:
        notes.append("Anlık net kâr negatif; gider ve reklam harcaması kısa vadede kontrol edilmeli.")
    else:
        notes.append("Anlık net kâr pozitif; ölçekleme yapılırken stok ve nakit akışı birlikte izlenmeli.")

    if not product_summary.empty:
        top = product_summary.iloc[0]
        notes.append(f"Top-seller ürün: {top['product_name']} ({top['qty']:.0f} adet). Bu ürün için stok besleme önceliği verilmeli.")

    if not creative_summary.empty:
        best = creative_summary.sort_values(["roas", "purchases"], ascending=False).head(1)
        if not best.empty:
            row = best.iloc[0]
            notes.append(f"En güçlü kreatif/kampanya sinyali: {row['creative_name']} | ROAS {row['roas']:.2f}.")

    return "\n\n".join([f"- {n}" for n in notes])


# =========================================================
# TOP METRICS
# =========================================================
st.caption(f"Rapor dönemi: {period_label}")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Net Ciro", money(total_revenue))
k2.metric("Sipariş Adedi", f"{order_count:,}")
k3.metric("Hedef Gerçekleşme", pct(target_rate))
k4.metric("Anlık Net Kar", money(net_profit_now))
k5.metric("AOV", money(aov))
k6.metric("ROAS", f"{overall_roas:.2f}")

k7, k8, k9, k10 = st.columns(4)
k7.metric("Reklam Harcaması", money(ad_spend))
k8.metric("CAC", money(cac))
k9.metric("LTV Tahmini", money(ltv))
k10.metric("30 Gün Tahmini Ciro", money((total_revenue / max((max_date - min_date).days + 1, 1)) * 30 if total_revenue else 0.0))


# =========================================================
# SELECTED AI REPORT
# =========================================================
st.divider()
st.subheader(f"Seçili AI Yorumu: {selected_report}")

if selected_report == "Net Ciro ve Sipariş Yorumu":
    durum = f"Toplam net ciro {money(total_revenue)}, sipariş adedi {order_count:,}, AOV {money(aov)}."
    guclu = "Ciro ve sipariş aynı anda artıyorsa kanal talebi güçlüdür. AOV yüksekse sepet kalitesi iyi demektir."
    risk = "Sipariş artıp kâr artmıyorsa komisyon, ürün maliyeti, kargo veya reklam harcaması kârlılığı eritiyor olabilir."
    aksiyon = "Ciroyu platform bazında takip et; düşük AOV olan kanalda bundle, hediye kutusu veya minimum sepet kampanyası dene."
    ai_box("Net Ciro ve Sipariş Yorumu", durum, guclu, risk, aksiyon)

elif selected_report == "Hedef Gerçekleşme Oranı":
    durum = f"Aylık hedef {money(monthly_revenue_target)}, gerçekleşen net ciro {money(total_revenue)}, gerçekleşme oranı {pct(target_rate)}."
    guclu = "Hedefe yaklaşan kanallarda mevcut trafik ve ürün uyumu güçlüdür."
    risk = "Hedef düşük kalırsa ay sonuna doğru agresif reklam harcaması kârı bozabilir."
    aksiyon = "Hedefin altındaysa top-seller ürünleri öne çıkar, düşük ROAS kreatifleri durdur, yüksek dönüşümlü kanala bütçe kaydır."
    ai_box("Hedef Gerçekleşme Oranı", durum, guclu, risk, aksiyon, "Yüksek" if target_rate < 70 else "Orta")

elif selected_report == "Anlık Net Kar":
    durum = f"Tahmini brüt kâr {money(gross_profit)}, reklam harcaması {money(ad_spend)}, sabit gider {money(fixed_costs_30d)}, anlık net kâr {money(net_profit_now)}."
    guclu = "Net kâr pozitifse operasyon ölçeklemeye daha uygundur."
    risk = "Net kâr negatifse ciro büyüse bile nakit çıkışı artabilir."
    aksiyon = "Kârı düşüren kanalı tespit et; maliyeti yüksek SKU'ları ve düşük ROAS kampanyaları ayrı incele."
    ai_box("Anlık Net Kar", durum, guclu, risk, aksiyon, "Yüksek" if net_profit_now < 0 else "Orta")

elif selected_report == "Top-Seller Listesi":
    st.markdown("### Top-Seller Listesi")
    if product_summary.empty:
        st.info("Top-seller için ürün satış verisi bulunamadı.")
    else:
        st.dataframe(
            product_summary.head(20).style.format({
                "revenue": "{:,.2f} TL",
                "qty": "{:,.0f}",
                "gross_profit": "{:,.2f} TL",
                "stock_units": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        top = product_summary.iloc[0]
        ai_box(
            "Top-Seller Yorumu",
            f"En çok satan ürün {top['product_name']} ve satış adedi {top['qty']:.0f}.",
            "Top-seller ürünler reklam ve stok tarafında önceliklendirilebilir.",
            "Top-seller ürünün stoğu zayıfsa satış kaçırma riski oluşur.",
            "Bu ürün için stok, reklam ve kreatif varyasyonlarını ayrı takip et.",
            "Yüksek",
        )

elif selected_report == "Ölü Stok Alarmı":
    st.markdown("### Ölü / Düşük Stok Alarmı")
    if product_summary.empty:
        st.info("Stok alarmı için ürün verisi bulunamadı.")
    else:
        low_stock = product_summary[product_summary["stock_units"].fillna(999999) <= low_stock_threshold].sort_values("stock_units")
        no_sales_stock = product_summary[(product_summary["qty"].fillna(0) <= 0) & (product_summary["stock_units"].fillna(0) > low_stock_threshold)]
        c1, c2 = st.columns(2)
        with c1:
            st.write("Düşük stok ürünleri")
            st.dataframe(low_stock, use_container_width=True, hide_index=True)
        with c2:
            st.write("Satışı zayıf / ölü stok adayları")
            st.dataframe(no_sales_stock, use_container_width=True, hide_index=True)
        ai_box(
            "Ölü Stok Alarmı",
            f"Düşük stok ürün sayısı {len(low_stock)}, satışı zayıf stok adayı {len(no_sales_stock)}.",
            "Stok görünürlüğü olan ürünlerde besleme kararı daha sağlıklı yapılabilir.",
            "Top-seller ürünlerde stok azalırsa reklam bütçesi boşa gidebilir; ölü stokta ise nakit bağlanır.",
            "Düşük stok top-seller ürünleri önceliklendir; satışı zayıf ürünler için indirim veya bundle planı yap.",
            "Yüksek",
        )

elif selected_report == "Kanal Karlılık Kıyaslaması":
    st.markdown("### Kanal Karlılık Kıyaslaması")
    if platform_summary.empty:
        st.info("Kanal kıyaslaması için veri bulunamadı.")
    else:
        st.dataframe(
            platform_summary.sort_values("net_profit_after_ads", ascending=False).style.format({
                "net_revenue": "{:,.2f} TL",
                "gross_profit": "{:,.2f} TL",
                "ad_spend": "{:,.2f} TL",
                "ad_revenue": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "aov": "{:,.2f} TL",
                "roas": "{:.2f}",
                "units": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        best = platform_summary.sort_values("net_profit_after_ads", ascending=False).iloc[0]
        ai_box(
            "Kanal Karlılık Yorumu",
            f"En kârlı kanal şu an {best['platform']} görünüyor.",
            "Kanal bazlı ayrım bütçe ve stok kararını netleştirir.",
            "Sadece ciroya göre karar verilirse kârsız kanal büyütülebilir.",
            "Net kârı yüksek kanala ürün ve reklam önceliği ver; düşük kârlı kanalda maliyetleri kontrol et.",
            "Yüksek",
        )

elif selected_report == "Kampanya Bazlı ROAS":
    st.markdown("### Kampanya Bazlı ROAS")
    if creative_summary.empty and ads.empty:
        st.info("Kampanya bazlı ROAS için kreatif veya reklam verisi bulunamadı.")
    elif not creative_summary.empty:
        campaign = creative_summary.groupby("campaign_name", as_index=False).agg(
            spend=("spend", "sum"),
            revenue=("attributed_revenue", "sum"),
            purchases=("purchases", "sum"),
            reach=("reach", "sum"),
        )
        campaign["roas"] = campaign.apply(lambda r: safe_divide(r["revenue"], r["spend"]), axis=1)
        st.dataframe(campaign.sort_values("roas", ascending=False), use_container_width=True, hide_index=True)
        fig = px.bar(campaign.sort_values("roas", ascending=False).head(15), x="campaign_name", y="roas", title="Kampanya Bazlı ROAS")
        st.plotly_chart(fig, use_container_width=True)
    ai_box(
        "Kampanya Bazlı ROAS Yorumu",
        f"Genel ROAS {overall_roas:.2f}.",
        "ROAS yüksek kampanyalar ölçekleme için adaydır.",
        "Düşük ROAS kampanyalar kârı hızlı şekilde eritebilir.",
        "ROAS 3+ kampanyaları ölçekle, 1.5 altı kampanyalarda kreatif/hedefleme yenile.",
        "Yüksek",
    )

elif selected_report == "Kreatif Karnesi":
    st.markdown("### Kreatif Karnesi")
    if creative_summary.empty:
        st.info("Kreatif karnesi için kreatif raporu bulunamadı.")
    else:
        creative_summary["decision"] = creative_summary.apply(
            lambda r: "Ölçekle" if r["roas"] >= 3 and r["purchases"] >= 1 else ("Durdurmayı Değerlendir" if r["spend"] >= 500 and r["roas"] < 1.5 else "İzle"),
            axis=1,
        )
        st.dataframe(
            creative_summary.sort_values(["decision", "roas"], ascending=[True, False]).style.format({
                "spend": "{:,.2f} TL",
                "reach": "{:,.0f}",
                "impressions": "{:,.0f}",
                "results": "{:,.0f}",
                "purchases": "{:,.0f}",
                "attributed_revenue": "{:,.2f} TL",
                "roas": "{:.2f}",
                "cac": "{:,.2f} TL",
                "ctr": "{:.2f}",
                "cpc": "{:,.2f}",
                "cpm": "{:,.2f}",
                "frequency": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        scale_count = int((creative_summary["decision"] == "Ölçekle").sum())
        stop_count = int((creative_summary["decision"] == "Durdurmayı Değerlendir").sum())
        ai_box(
            "Kreatif Karnesi Yorumu",
            f"Ölçekleme adayı {scale_count}, durdurma/değiştirme adayı {stop_count} kreatif var.",
            "Kreatif bazlı karar ile reklam bütçesi daha kontrollü yönetilir.",
            "Aynı kreatif uzun süre dönerse frekans ve yorgunluk riski artar.",
            "Kazanan kreatiflerin varyasyonlarını üret; düşük ROAS kreatifleri yenile veya durdur.",
            "Yüksek",
        )

elif selected_report == "CAC ve Müşteri Edinme Yorumu":
    durum = f"CAC yaklaşık {money(cac)}. Reklam harcaması {money(ad_spend)}, yeni müşteri girişi {new_customer_count:,}."
    guclu = "CAC, LTV'nin altında kaldığında müşteri edinimi sağlıklı kabul edilir."
    risk = "Yeni müşteri verisi yoksa CAC tahmini eksik kalır. Reklam harcamasını alışveriş sayısına bölmek tam müşteri CAC'i vermez."
    aksiyon = "Shopify müşteri tipini veya müşteri ID/e-posta bazlı raporu ekleyerek gerçek CAC hesaplamasını güçlendir."
    ai_box("CAC ve Müşteri Edinme Yorumu", durum, guclu, risk, aksiyon, "Orta")

elif selected_report == "Yeni vs. Geri Gelen Müşteri":
    total_customers = new_customer_count + returning_customer_count
    new_rate = safe_divide(new_customer_count, total_customers) * 100
    returning_rate = safe_divide(returning_customer_count, total_customers) * 100
    durum = f"Manuel veriye göre yeni müşteri oranı {pct(new_rate)}, geri gelen müşteri oranı {pct(returning_rate)}."
    guclu = "Geri gelen müşteri oranı yükselirse reklam maliyeti baskısı azalır."
    risk = "Bu veri manuel girilmediyse veya müşteri bazlı dosya yoksa analiz sınırlıdır."
    aksiyon = "Tekrar satın alma için WhatsApp/e-posta akışı, sadakat indirimi ve aksesuar bundle kampanyası kurulabilir."
    ai_box("Yeni vs. Geri Gelen Müşteri", durum, guclu, risk, aksiyon)

elif selected_report == "Sepet Ortalaması (AOV)":
    durum = f"AOV şu an {money(aov)}."
    guclu = "AOV yüksekse reklam maliyetini taşıma kapasitesi artar."
    risk = "AOV düşükse aynı reklam harcamasıyla daha düşük kâr oluşur."
    aksiyon = "Bundle, 2. ürün indirimi, ücretsiz kargo eşiği ve hediye kutusu upsell testleri yap."
    ai_box("Sepet Ortalaması (AOV)", durum, guclu, risk, aksiyon)

elif selected_report == "LTV Yorumu":
    durum = f"Tahmini LTV {money(ltv)}. Hesap: AOV x müşteri başı ortalama satın alma adedi."
    guclu = "LTV yüksekse daha yüksek CAC tolere edilebilir."
    risk = "Gerçek müşteri tekrar satın alma verisi olmadan LTV tahmini sınırlıdır."
    aksiyon = "Müşteri bazlı satış geçmişi eklenirse gerçek LTV ve tekrar satın alma oranı hesaplanabilir."
    ai_box("LTV Yorumu", durum, guclu, risk, aksiyon)

elif selected_report == "İş Birliği Performansı":
    ai_box(
        "İş Birliği Performansı",
        "Bu bölüm için influencer/iş birliği bazlı harcama, kupon kodu, link tıklaması ve satış dosyası gerekir.",
        "Kupon/link bazlı veri gelirse hangi iş birliğinin satışa döndüğü net ölçülür.",
        "Sadece erişim/veri ile karar verilirse satış getirmeyen iş birlikleri iyi görünebilir.",
        "İş birliği raporu için partner adı, harcama/ücret, erişim, tıklama, satış, ciro ve ROAS kolonlarını içeren CSV ekle.",
        "Orta",
    )

elif selected_report == "Erişim vs. Dönüşüm":
    st.markdown("### Erişim vs. Dönüşüm")
    if creative_summary.empty:
        st.info("Erişim vs dönüşüm için kreatif raporu bulunamadı.")
    else:
        fig = px.scatter(
            creative_summary,
            x="reach",
            y="purchases",
            size="spend",
            color="roas",
            hover_data=["campaign_name", "creative_name", "ctr", "frequency"],
            title="Erişim vs Satın Alma",
        )
        st.plotly_chart(fig, use_container_width=True)
        weak = creative_summary[(creative_summary["reach"] >= creative_summary["reach"].quantile(0.7)) & (creative_summary["purchases"] <= creative_summary["purchases"].median())]
        st.write("Yüksek erişim / düşük dönüşüm adayları")
        st.dataframe(weak, use_container_width=True, hide_index=True)
        ai_box(
            "Erişim vs. Dönüşüm Yorumu",
            f"Yüksek erişim-düşük dönüşüm adayı {len(weak)} kreatif var.",
            "Erişim güçlüyse kreatif dikkat çekiyor olabilir.",
            "Dönüşüm düşükse teklif, ürün sayfası, fiyat veya güven sorunu olabilir.",
            "Yüksek erişim ama düşük satın alma getiren kreatiflerde ürün sayfası ve mesaj uyumunu kontrol et.",
            "Yüksek",
        )

elif selected_report == "30 Günlük Satış Tahmini":
    days = max((max_date - min_date).days + 1, 1)
    forecast_revenue = safe_divide(total_revenue, days) * 30
    forecast_orders = safe_divide(order_count, days) * 30
    forecast_profit = safe_divide(gross_profit, days) * 30 - fixed_costs_30d
    durum = f"Son veri hızına göre 30 günlük ciro tahmini {money(forecast_revenue)}, sipariş tahmini {forecast_orders:,.0f}, kâr tahmini {money(forecast_profit)}."
    guclu = "Mevcut satış hızı korunursa planlama için temel tahmin oluşur."
    risk = "Kampanya, stok ve sezon etkisi tahmini değiştirebilir."
    aksiyon = "Tahmini top-seller ürünlerin stoklarıyla karşılaştır ve reklam bütçesini kâr hedefiyle sınırla."
    ai_box("30 Günlük Satış Tahmini", durum, guclu, risk, aksiyon, "Yüksek")

elif selected_report == "Stok Besleme Planı":
    st.markdown("### Stok Besleme Planı")
    if product_summary.empty:
        st.info("Stok besleme planı için ürün verisi yok.")
    else:
        days = max((max_date - min_date).days + 1, 1)
        plan = product_summary.copy()
        plan["daily_qty"] = plan["qty"] / days
        plan["needed_for_lead_days"] = plan["daily_qty"] * stock_lead_days
        plan["recommended_restock"] = (plan["needed_for_lead_days"] - plan["stock_units"].fillna(0)).clip(lower=0)
        plan = plan.sort_values("recommended_restock", ascending=False)
        st.dataframe(
            plan[["platform", "product_name", "qty", "stock_units", "daily_qty", "needed_for_lead_days", "recommended_restock"]].style.format({
                "qty": "{:,.0f}",
                "stock_units": "{:,.0f}",
                "daily_qty": "{:,.2f}",
                "needed_for_lead_days": "{:,.0f}",
                "recommended_restock": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        ai_box(
            "Stok Besleme Planı",
            f"Tedarik süresi {stock_lead_days} gün kabul edildi. En yüksek restock ihtiyacı olan ürünler listelendi.",
            "Satış hızına göre stok besleme, satış kaçırma riskini azaltır.",
            "Stok verisi eksik ürünlerde öneri hatalı olabilir.",
            "Top-seller + düşük stok ürünlerini öncele; ölü stok ürünlere yeni alım yapma.",
            "Yüksek",
        )

elif selected_report == "Nakit Akış Projeksiyonu":
    days = max((max_date - min_date).days + 1, 1)
    projected_gross_profit = safe_divide(gross_profit, days) * 30
    projected_ad_spend = safe_divide(ad_spend, days) * 30
    projected_cash = current_cash + projected_gross_profit - projected_ad_spend - fixed_costs_30d - planned_stock_purchase
    durum = f"30 gün sonunda tahmini nakit: {money(projected_cash)}. Mevcut nakit {money(current_cash)}, tahmini brüt kâr {money(projected_gross_profit)}, tahmini reklam harcaması {money(projected_ad_spend)}."
    guclu = "Nakit projeksiyonu reklam ve stok kararlarını birlikte görmeyi sağlar."
    risk = "Tahsilat gecikmesi, iade ve ek stok alımı projeksiyonu bozabilir."
    aksiyon = "Nakit negatife düşüyorsa reklam ölçeklemeyi sınırlı tut, stok alımını top-seller ürünlerle sınırla."
    ai_box("Nakit Akış Projeksiyonu", durum, guclu, risk, aksiyon, "Yüksek" if projected_cash < 0 else "Orta")

elif selected_report == "Yapay Zeka Notu" or selected_report == "Genel Yönetici Özeti":
    st.markdown("### Yapay Zeka Notu")
    st.markdown(create_general_note())

else:
    st.info("Bu başlık için yorum hazırlanıyor.")


# =========================================================
# FULL DASHBOARD TABS
# =========================================================
st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Genel Veri",
    "🏪 Kanal Kıyaslama",
    "📦 Ürün & Stok",
    "📣 Reklam & Kreatif",
    "🧪 Veri Durumu",
])

with tab1:
    st.subheader("Genel Özet")
    summary_df = pd.DataFrame([
        {"Metrik": "Net Ciro", "Değer": money(total_revenue)},
        {"Metrik": "Sipariş Adedi", "Değer": f"{order_count:,}"},
        {"Metrik": "Hedef Gerçekleşme", "Değer": pct(target_rate)},
        {"Metrik": "Anlık Net Kar", "Değer": money(net_profit_now)},
        {"Metrik": "AOV", "Değer": money(aov)},
        {"Metrik": "ROAS", "Değer": f"{overall_roas:.2f}"},
        {"Metrik": "CAC", "Değer": money(cac)},
        {"Metrik": "LTV Tahmini", "Değer": money(ltv)},
    ])
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Kanal Karlılık Kıyaslaması")
    if platform_summary.empty:
        st.info("Kanal verisi bulunamadı.")
    else:
        st.dataframe(
            platform_summary.sort_values("net_profit_after_ads", ascending=False).style.format({
                "net_revenue": "{:,.2f} TL",
                "orders": "{:,.0f}",
                "gross_profit": "{:,.2f} TL",
                "units": "{:,.0f}",
                "ad_spend": "{:,.2f} TL",
                "ad_revenue": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "aov": "{:,.2f} TL",
                "roas": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
        )
        fig = px.bar(platform_summary, x="platform", y="net_profit_after_ads", title="Kanal Bazlı Net Kâr")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Ürün ve Stok")
    if product_summary.empty:
        st.info("Ürün verisi bulunamadı.")
    else:
        st.dataframe(
            product_summary.head(50).style.format({
                "revenue": "{:,.2f} TL",
                "qty": "{:,.0f}",
                "gross_profit": "{:,.2f} TL",
                "stock_units": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    st.subheader("Reklam ve Kreatif")
    if creative_summary.empty:
        st.info("Kreatif verisi bulunamadı.")
    else:
        st.dataframe(
            creative_summary.sort_values("roas", ascending=False).style.format({
                "spend": "{:,.2f} TL",
                "reach": "{:,.0f}",
                "impressions": "{:,.0f}",
                "results": "{:,.0f}",
                "purchases": "{:,.0f}",
                "attributed_revenue": "{:,.2f} TL",
                "ctr": "{:.2f}",
                "cpc": "{:,.2f}",
                "cpm": "{:,.2f}",
                "frequency": "{:.2f}",
                "roas": "{:.2f}",
                "cac": "{:,.2f} TL",
            }),
            use_container_width=True,
            hide_index=True,
        )

with tab5:
    st.subheader("Veri Durumu")
    data_status = pd.DataFrame([
        {"Alan": "Shopify klasörü", "Durum": "Var" if SHOPIFY_DIR.exists() else "Yok", "Yol": str(SHOPIFY_DIR)},
        {"Alan": "Trendyol klasörü", "Durum": "Var" if TRENDYOL_DIR.exists() else "Yok", "Yol": str(TRENDYOL_DIR)},
        {"Alan": "Hepsiburada klasörü", "Durum": "Var" if HEPSIBURADA_DIR.exists() else "Yok", "Yol": str(HEPSIBURADA_DIR)},
        {"Alan": "Kreatif klasörü", "Durum": "Var" if KREATIF_DIR.exists() else "Yok", "Yol": str(KREATIF_DIR)},
        {"Alan": "Sipariş verisi", "Durum": "Var" if not orders_all.empty else "Eksik", "Yol": "-"},
        {"Alan": "Ürün verisi", "Durum": "Var" if not lines_all.empty else "Eksik", "Yol": "-"},
        {"Alan": "Reklam verisi", "Durum": "Var" if not ads_all.empty else "Eksik", "Yol": "-"},
        {"Alan": "Kreatif verisi", "Durum": "Var" if not creative_all.empty else "Eksik", "Yol": "-"},
    ])
    st.dataframe(data_status, use_container_width=True, hide_index=True)

    st.markdown(
        """
        **Not:** Bu panel ilk sürümde kural bazlı yapay zeka mantığıyla çalışır. Yani API gerektirmez.  
        Daha sonra istersen OpenAI API ekleyerek bu yorumları gerçek LLM çıktısına çevirebiliriz.
        """
    )
