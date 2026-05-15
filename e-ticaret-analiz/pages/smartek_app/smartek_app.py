from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# PAGE
# =========================================================
st.set_page_config(page_title="SMARTEK360 Trendyol", layout="wide")

# =========================================================
# LOGIN CONTROL
# =========================================================
# Bu dosya ana sayfadan giriş yapılmadan çalışmasın.
if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🟠 SMARTEK360: Trendyol Dashboard")
st.caption(
    "Runs only with Trendyol orders, Trendyol ads, store report, cost data, and optional Meta ads data. "
    "Includes date filters, daily/monthly net profit, top-selling product cards, and manual inventory support."
)

BASE_DIR = Path(__file__).resolve().parent
MANUAL_WEEKLY_ADS_FILE = BASE_DIR / "manual_weekly_trendyol_ads.csv"
MANUAL_WEEKLY_ADS_START = pd.Timestamp("2026-01-12")


# =========================================================
# HELPERS
# =========================================================
def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()



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


def clean_sku(val) -> str:
    if pd.isna(val):
        return ""

    s = str(val).strip().replace(" ", "")

    # Trendyol barkodlarında sık görülen önek: 6-970126...
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



def find_col(df: pd.DataFrame, keys: Iterable[str]) -> Optional[str]:
    lowered = {c: normalize_text(c) for c in df.columns}
    for key in keys:
        key_n = normalize_text(key)
        for col, col_n in lowered.items():
            if key_n in col_n:
                return col
    return None



def read_csv_safely(path: Path, *, sep: Optional[str] = None, skiprows: int = 0) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "iso-8859-9", "latin1"]
    seps = [sep] if sep is not None else [",", ";"]
    last_error = None
    for enc in encodings:
        for chosen_sep in seps:
            try:
                return pd.read_csv(
                    path,
                    encoding=enc,
                    sep=chosen_sep,
                    low_memory=False,
                    skiprows=skiprows,
                    dtype=str,
                    keep_default_na=False,
                )
            except Exception as exc:
                last_error = exc
    raise last_error



def read_table(path: Path, *, sep: Optional[str] = None, skiprows: int = 0) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return read_csv_safely(path, sep=sep, skiprows=skiprows)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, skiprows=skiprows)
    raise ValueError(f"Unsupported file type: {path.name}")



def exact_file(name: str) -> Optional[Path]:
    p = BASE_DIR / name
    return p if p.exists() else None



def files_matching(patterns: Iterable[str]) -> list[Path]:
    matches: list[Path] = []
    for pat in patterns:
        matches.extend(BASE_DIR.glob(pat))
    uniq = sorted({p.resolve() for p in matches})
    return [Path(p) for p in uniq]


# =========================================================
# FILE GROUPS
# =========================================================
def get_trendyol_order_files() -> list[Path]:
    return files_matching([
        "*Trendyol*(Tedarikci_Siparisleri)*.csv",
        "*Trendyol*Sipariş*.csv",
        "*Trendyol*Siparis*.csv",
    ])



def get_meta_files() -> list[Path]:
    patterns = [
        "*meta*.csv",
        "*meta*.xlsx",
        "*facebook*.csv",
        "*facebook*.xlsx",
        "*fb_ads*.csv",
        "*fb_ads*.xlsx",
        "*ads_manager*.csv",
        "*ads_manager*.xlsx",
    ]
    result = []
    for f in files_matching(patterns):
        if "template" in f.name.lower():
            continue
        result.append(f)
    return result



def get_stock_files() -> list[Path]:
    return files_matching([
        "*trendyol*stok*.csv",
        "*trendyol*stok*.xlsx",
        "*trendyol*inventory*.csv",
        "*trendyol*inventory*.xlsx",
        "*stok*trendyol*.csv",
        "*stok*trendyol*.xlsx",
    ])


# =========================================================
# LOADERS
# =========================================================
def load_trendyol_costs() -> pd.DataFrame:
    path = exact_file("Trendyol Maliyet tablosu(Sayfa1).csv")
    if not path:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "shipping_cost", "vat_rate"])

    df = read_csv_safely(path, sep=";")
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "shipping_cost", "vat_rate"])

    sku_col = find_col(df, ["SKU"])
    comm_col = find_col(df, ["Komisyon", "Commission"])
    cost_col = find_col(df, ["Maliyet", "Cost"])
    ship_col = find_col(df, ["Kargo", "Shipping"])
    vat_col = find_col(df, ["KDV", "VAT"])

    out = pd.DataFrame({
        "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
        "commission_rate": df[comm_col].apply(to_float) if comm_col else 0.0,
        "unit_cost": df[cost_col].apply(to_float) if cost_col else 0.0,
        "shipping_cost": df[ship_col].apply(to_float) if ship_col else 0.0,
        "vat_rate": df[vat_col].apply(to_float) if vat_col else 0.0,
    })

    out = out[out["sku_key"] != ""].drop_duplicates(subset=["sku_key"], keep="last")
    return out



def parse_trendyol_orders() -> pd.DataFrame:
    rows = []
    for f in get_trendyol_order_files():
        df = read_csv_safely(f, sep=";", skiprows=1)
        if df.empty:
            continue

        date_col = find_col(df, ["Sipari? Tarihi", "Sipariş Tarihi"])
        order_col = find_col(df, ["Sipari? Numaras?", "Sipariş Numarası"])
        qty_col = find_col(df, ["Adet"])
        status_col = find_col(df, ["Sipari? Statüsü", "Sipariş Statüsü"])
        sku_col = find_col(df, ["Barkod"])
        product_col = find_col(df, ["Ürün Ad", "Urun Ad"])
        revenue_col = find_col(df, ["Faturalanacak Tutar"])
        list_price_col = find_col(df, ["Sat?? Tutar?", "Satış Tutarı"])
        unit_price_col = find_col(df, ["Birim Fiyat?"])
        commission_col = find_col(df, ["Komisyon Oran?"])
        city_col = find_col(df, ["?l"])

        temp = pd.DataFrame({
            "order_id": df[order_col].astype(str) if order_col else "",
            "order_date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True) if date_col else pd.NaT,
            "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
            "product_name": df[product_col].astype(str) if product_col else "",
            "qty": df[qty_col].apply(to_float) if qty_col else 1.0,
            "revenue": df[revenue_col].apply(to_float) if revenue_col else 0.0,
            "gross_sales": df[list_price_col].apply(to_float) if list_price_col else 0.0,
            "unit_price": df[unit_price_col].apply(to_float) if unit_price_col else 0.0,
            "commission_rate_reported": (df[commission_col].apply(to_float) / 100.0) if commission_col else 0.0,
            "status": df[status_col].astype(str) if status_col else "",
            "city": df[city_col].astype(str) if city_col else "",
            "source_file": f.name,
        })
        temp["is_returned"] = temp["status"].str.contains("ade|iptal", case=False, na=False)
        rows.append(temp)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)
    out["order_day"] = pd.to_datetime(out["order_date"], errors="coerce").dt.date
    out["order_month"] = pd.to_datetime(out["order_date"], errors="coerce").dt.to_period("M").astype(str)
    return out



def normalize_week_start(value) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    ts = pd.Timestamp(ts).normalize()
    return ts - pd.Timedelta(days=ts.weekday())


def load_manual_weekly_trendyol_ads() -> pd.DataFrame:
    columns = ["week_start", "week_end", "weekly_spend", "weekly_revenue", "note", "source_file"]
    if not MANUAL_WEEKLY_ADS_FILE.exists():
        return pd.DataFrame(columns=columns)

    try:
        df = read_csv_safely(MANUAL_WEEKLY_ADS_FILE, sep=",")
    except Exception:
        df = pd.read_csv(MANUAL_WEEKLY_ADS_FILE, dtype=str).fillna("")

    if df.empty:
        return pd.DataFrame(columns=columns)

    week_col = find_col(df, ["week_start", "week start", "Hafta Başlangıç", "Hafta Baslangic"])
    spend_col = find_col(df, ["weekly_spend", "weekly spend", "Haftalık Harcama", "Haftalik Harcama", "Spend"])
    revenue_col = find_col(df, ["weekly_revenue", "weekly revenue", "total ad revenue", "ad revenue", "Haftalık Reklam Cirosu", "Haftalik Reklam Cirosu", "Reklam Cirosu", "Revenue"])
    note_col = find_col(df, ["note", "campaign", "Açıklama", "Aciklama"])

    out = pd.DataFrame({
        "week_start": pd.to_datetime(df[week_col], errors="coerce") if week_col else pd.NaT,
        "weekly_spend": df[spend_col].apply(to_float) if spend_col else 0.0,
        "weekly_revenue": df[revenue_col].apply(to_float) if revenue_col else 0.0,
        "note": df[note_col].astype(str).str.strip() if note_col else "Manual Weekly Spend",
        "source_file": MANUAL_WEEKLY_ADS_FILE.name,
    })
    out["week_start"] = out["week_start"].apply(normalize_week_start)
    out = out.dropna(subset=["week_start"]).copy()
    out = out[out["week_start"] >= MANUAL_WEEKLY_ADS_START].copy()
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    out["note"] = out["note"].replace({"": "Manual Weekly Spend"})
    out = out.groupby(["week_start", "week_end", "note", "source_file"], as_index=False)[["weekly_spend", "weekly_revenue"]].sum()
    return out.sort_values("week_start").reset_index(drop=True)


def save_manual_weekly_trendyol_ads(df: pd.DataFrame) -> None:
    save_df = df.copy()
    if save_df.empty:
        save_df = pd.DataFrame(columns=["week_start", "weekly_spend", "weekly_revenue", "note"])
    else:
        save_df = save_df[["week_start", "weekly_spend", "weekly_revenue", "note"]].copy()
        save_df["week_start"] = pd.to_datetime(save_df["week_start"], errors="coerce").dt.strftime("%Y-%m-%d")
    save_df.to_csv(MANUAL_WEEKLY_ADS_FILE, index=False, encoding="utf-8-sig")




def parse_trendyol_ads() -> pd.DataFrame:
    weekly_ads = load_manual_weekly_trendyol_ads()
    if weekly_ads.empty:
        return pd.DataFrame()

    out = pd.DataFrame({
        "marketing_source": "Trendyol Ads",
        "target_channel": "Trendyol",
        "campaign_name": weekly_ads["note"],
        "campaign_status": "Manual Weekly Entry",
        "start_date": pd.to_datetime(weekly_ads["week_start"], errors="coerce"),
        "end_date": pd.to_datetime(weekly_ads["week_end"], errors="coerce"),
        "total_budget": weekly_ads["weekly_spend"],
        "daily_budget": weekly_ads["weekly_spend"] / 7.0,
        "remaining_budget": 0.0,
        "spend": weekly_ads["weekly_spend"],
        "impressions": 0.0,
        "clicks": 0.0,
        "conversions": 0.0,
        "attributed_revenue": weekly_ads["weekly_revenue"],
        "roas_reported": weekly_ads.apply(lambda r: (r["weekly_revenue"] / r["weekly_spend"]) if r["weekly_spend"] else 0.0, axis=1),
        "source_file": weekly_ads["source_file"],
    })

    out["date"] = pd.to_datetime(out["start_date"], errors="coerce")
    out["day"] = out["date"].dt.date
    out["month"] = out["date"].dt.to_period("M").astype(str)
    return out


def parse_meta_ads() -> pd.DataFrame:
    rows = []
    for f in get_meta_files():
        df = read_table(f)
        if df.empty:
            continue

        date_col = find_col(df, ["Day", "Date", "Reporting starts", "Tarih"])
        campaign_col = find_col(df, ["Campaign name", "Campaign", "Kampanya"])
        spend_col = find_col(df, ["Amount spent (TRY)", "Amount spent", "Harcama", "Spend"])
        impr_col = find_col(df, ["Impressions", "Gösterim", "Gosterim"])
        clicks_col = find_col(df, ["Link clicks", "Clicks", "Tıklama", "Tiklama"])
        purchase_col = find_col(df, ["Purchases", "Website purchases", "Satın alma", "Satin alma"])
        revenue_col = find_col(df, [
            "Purchases conversion value",
            "Website purchase conversion value",
            "Purchase conversion value",
            "Alışveriş değeri",
            "Satın alma dönüşüm değeri",
            "Revenue",
        ])

        if not spend_col:
            continue

        out = pd.DataFrame({
            "marketing_source": "Meta Ads",
            "target_channel": "Trendyol",
            "date": pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT,
            "campaign_name": df[campaign_col].astype(str) if campaign_col else f.stem,
            "spend": df[spend_col].apply(to_float),
            "impressions": df[impr_col].apply(to_float) if impr_col else 0.0,
            "clicks": df[clicks_col].apply(to_float) if clicks_col else 0.0,
            "conversions": df[purchase_col].apply(to_float) if purchase_col else 0.0,
            "attributed_revenue": df[revenue_col].apply(to_float) if revenue_col else 0.0,
            "source_file": f.name,
        })
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out["day"] = out["date"].dt.date
        out["month"] = out["date"].dt.to_period("M").astype(str)
        rows.append(out)

    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()



def _max_timestamp_like(value) -> pd.Timestamp:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT

    parsed = pd.to_datetime(value, errors="coerce")

    if isinstance(parsed, pd.Series):
        return parsed.max()
    if isinstance(parsed, pd.DatetimeIndex):
        return parsed.max() if len(parsed) else pd.NaT
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed)



def get_marketing_cutoff_date(orders: pd.DataFrame, ads_raw: pd.DataFrame) -> pd.Timestamp:
    order_cutoff = _max_timestamp_like(orders["order_date"]) if (not orders.empty and "order_date" in orders.columns) else pd.NaT
    today_cutoff = pd.Timestamp.today().normalize()

    ad_candidates = []
    if not ads_raw.empty:
        if "end_date" in ads_raw.columns:
            ad_candidates.append(_max_timestamp_like(ads_raw["end_date"]))
        if "start_date" in ads_raw.columns:
            ad_candidates.append(_max_timestamp_like(ads_raw["start_date"]))

        has_open_campaign = False
        if "end_date" in ads_raw.columns and "spend" in ads_raw.columns:
            end_na = pd.to_datetime(ads_raw["end_date"], errors="coerce").isna()
            spend_pos = pd.to_numeric(ads_raw["spend"], errors="coerce").fillna(0).gt(0)
            has_open_campaign = bool((end_na & spend_pos).any())

        if has_open_campaign:
            ad_candidates.append(today_cutoff)

    ad_cutoff = max([c for c in ad_candidates if pd.notna(c)], default=pd.NaT)
    candidates = [c for c in [order_cutoff, ad_cutoff, today_cutoff] if pd.notna(c)]
    return max(candidates) if candidates else today_cutoff


def allocate_trendyol_ads_daily(ads_raw: pd.DataFrame, cutoff_date: pd.Timestamp) -> pd.DataFrame:
    if ads_raw.empty:
        return pd.DataFrame(columns=[
            "marketing_source", "target_channel", "date", "day", "month", "campaign_name",
            "campaign_status", "spend", "impressions", "clicks", "conversions", "attributed_revenue",
            "roas_reported", "total_budget", "daily_budget", "remaining_budget", "allocation_method", "source_file"
        ])

    rows = []
    cutoff_date = pd.to_datetime(cutoff_date).normalize()

    for _, r in ads_raw.iterrows():
        start = pd.to_datetime(r.get("start_date"), errors="coerce")
        end = pd.to_datetime(r.get("end_date"), errors="coerce")
        spend = float(r.get("spend", 0.0) or 0.0)
        daily_budget = float(r.get("daily_budget", 0.0) or 0.0)
        status_text = str(r.get("campaign_status", "")).lower()
        allocation_method = "reported_range"

        if pd.isna(start):
            continue

        start = start.normalize()
        if pd.notna(end):
            end = min(end.normalize(), cutoff_date)
        elif daily_budget > 0 and spend > 0:
            estimated_days = max(int((spend / daily_budget) + 0.9999), 1)
            end = min(start + pd.Timedelta(days=estimated_days - 1), cutoff_date)
            allocation_method = "estimated_from_daily_budget"
        elif "sonland" in status_text or "paused" in status_text:
            end = start
            allocation_method = "single_day_fallback"
        else:
            end = cutoff_date
            allocation_method = "open_ended_to_cutoff"

        if end < start:
            end = start

        days = pd.date_range(start, end, freq="D")
        n_days = max(len(days), 1)

        for d in days:
            rows.append({
                "marketing_source": "Trendyol Ads",
                "target_channel": "Trendyol",
                "date": d,
                "day": d.date(),
                "month": str(d.to_period("M")),
                "campaign_name": r.get("campaign_name", ""),
                "campaign_status": r.get("campaign_status", ""),
                "spend": spend / n_days,
                "impressions": float(r.get("impressions", 0.0) or 0.0) / n_days,
                "clicks": float(r.get("clicks", 0.0) or 0.0) / n_days,
                "conversions": float(r.get("conversions", 0.0) or 0.0) / n_days,
                "attributed_revenue": float(r.get("attributed_revenue", 0.0) or 0.0) / n_days,
                "roas_reported": float(r.get("roas_reported", 0.0) or 0.0),
                "total_budget": float(r.get("total_budget", 0.0) or 0.0),
                "daily_budget": daily_budget,
                "remaining_budget": float(r.get("remaining_budget", 0.0) or 0.0),
                "allocation_method": allocation_method,
                "source_file": r.get("source_file", ""),
            })

    return pd.DataFrame(rows)



def load_marketing(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    trendyol_ads_raw = parse_trendyol_ads()
    cutoff_date = get_marketing_cutoff_date(orders, trendyol_ads_raw)
    trendyol_ads = allocate_trendyol_ads_daily(trendyol_ads_raw, cutoff_date)

    meta_ads = parse_meta_ads()
    if not meta_ads.empty:
        meta_ads = meta_ads.copy()
        meta_ads["allocation_method"] = "as_reported"
        for missing_col in ["campaign_status", "roas_reported", "total_budget", "daily_budget", "remaining_budget"]:
            if missing_col not in meta_ads.columns:
                meta_ads[missing_col] = None

    frames = [f for f in [trendyol_ads, meta_ads] if not f.empty]
    if not frames:
        marketing = pd.DataFrame(columns=[
            "marketing_source", "target_channel", "date", "day", "month", "campaign_name",
            "campaign_status", "spend", "impressions", "clicks", "conversions", "attributed_revenue",
            "roas_reported", "total_budget", "daily_budget", "remaining_budget", "allocation_method", "source_file"
        ])
    else:
        marketing = pd.concat(frames, ignore_index=True)

    return marketing, trendyol_ads_raw



def load_trendyol_store_report() -> pd.DataFrame:
    f = exact_file("trendyol002(magaza-raporu).csv")
    if not f:
        return pd.DataFrame()

    df = read_csv_safely(f, sep=";")
    if df.empty:
        return pd.DataFrame()

    date_col = find_col(df, ["Tarih"])
    gross_col = find_col(df, ["Ma?azan?n Brüt Cirosu", "Mağazanın Brüt Cirosu"])
    visitors_col = find_col(df, ["Tekil Ziyaretçi Say?s?", "Tekil Ziyaretçi Sayısı"])
    orders_col = find_col(df, ["Ma?azan?n Brüt Sipari? Adedi", "Mağazanın Brüt Sipariş Adedi"])
    conv_col = find_col(df, ["Ma?azan?n Sat??a Dönü? Oran?", "Mağazanın Satışa Dönüş Oranı"])

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce", dayfirst=True) if date_col else pd.NaT,
        "store_gross_revenue": df[gross_col].apply(to_float) if gross_col else 0.0,
        "visitors": df[visitors_col].apply(to_float) if visitors_col else 0.0,
        "orders": df[orders_col].apply(to_float) if orders_col else 0.0,
        "conversion_rate": df[conv_col].apply(to_float) if conv_col else 0.0,
        "source_file": f.name,
    })
    out["month"] = out["date"].dt.to_period("M").astype(str)
    return out.sort_values("date")



def manual_stock_entries() -> pd.DataFrame:
    manual_rows = [
        {"sku_key": "", "stock_qty": 102.0, "product_name": "J01T green", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 102.0, "product_name": "J01T camel", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 60.0, "product_name": "J01 blue", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 47.0, "product_name": "J01 grey", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 541.0, "product_name": "J03 pro titanium", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 266.0, "product_name": "black J01T", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 35.0, "product_name": "salat counter", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 9.0, "product_name": "premium black gold 22mm", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 7.0, "product_name": "premium rose gold 20mm", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 7.0, "product_name": "premium black gray 22mm", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 120.0, "product_name": "J01 pink", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 120.0, "product_name": "J01 green", "source_file": "Manual stock entry"},
        {"sku_key": "", "stock_qty": 160.0, "product_name": "J01 black", "source_file": "Manual stock entry"},
    ]
    out = pd.DataFrame(manual_rows)
    out["product_key"] = out["product_name"].apply(normalize_text)
    return out


def load_stock() -> pd.DataFrame:
    rows = []
    for f in get_stock_files():
        df = read_table(f)
        if df.empty:
            continue
        sku_col = find_col(df, ["SKU", "Barkod", "Stok Kodu"])
        stock_col = find_col(df, ["Stok", "Inventory", "Quantity available", "Available"])
        name_col = find_col(df, ["Ürün Ad", "Urun Ad", "Product"])
        if not sku_col and not name_col:
            continue
        if not stock_col:
            continue

        out = pd.DataFrame({
            "sku_key": df[sku_col].apply(clean_sku) if sku_col else "",
            "stock_qty": df[stock_col].apply(to_float),
            "product_name": df[name_col].astype(str) if name_col else "",
            "source_file": f.name,
        })
        out["product_key"] = out["product_name"].apply(normalize_text)
        rows.append(out)

    file_stock = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["sku_key", "stock_qty", "product_name", "source_file", "product_key"]
    )

    manual_stock = manual_stock_entries()

    combined = pd.concat([file_stock, manual_stock], ignore_index=True)
    combined["sku_key"] = combined["sku_key"].fillna("")
    combined["product_name"] = combined["product_name"].fillna("")
    combined["product_key"] = combined["product_key"].fillna(combined["product_name"].apply(normalize_text))

    # Prefer manual entries when the same product name appears in both sources.
    combined = combined.sort_values(["product_key", "source_file"]).drop_duplicates(
        subset=["product_key"], keep="last"
    )

    return combined.reset_index(drop=True)


# =========================================================
# MODEL
# =========================================================
def enrich_orders(orders: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return orders

    merged = orders.merge(costs, on="sku_key", how="left")
    merged["qty"] = merged["qty"].fillna(1.0)
    merged["commission_rate"] = merged["commission_rate"].fillna(merged.get("commission_rate_reported", 0.0)).fillna(0.0)
    merged["unit_cost"] = merged["unit_cost"].fillna(0.0)
    merged["shipping_cost"] = merged["shipping_cost"].fillna(0.0)

    merged["commission_amount"] = merged["revenue"] * merged["commission_rate"]
    merged["product_cost_amount"] = merged["qty"] * merged["unit_cost"]
    merged["shipping_amount"] = merged["qty"] * merged["shipping_cost"]
    merged["gross_profit_before_ads"] = (
        merged["revenue"]
        - merged["commission_amount"]
        - merged["product_cost_amount"]
        - merged["shipping_amount"]
    )
    merged.loc[merged["is_returned"], "gross_profit_before_ads"] = 0.0
    merged["cost_matched"] = merged["unit_cost"].gt(0)
    return merged



def monthly_order_summary(order_model: pd.DataFrame) -> pd.DataFrame:
    if order_model.empty:
        return pd.DataFrame(columns=["month", "revenue", "orders", "qty", "gross_profit_before_ads"])

    valid = order_model[~order_model["is_returned"]].copy()
    month_base = valid.groupby("order_month", as_index=False).agg(
        revenue=("revenue", "sum"),
        qty=("qty", "sum"),
        gross_profit_before_ads=("gross_profit_before_ads", "sum"),
    ).rename(columns={"order_month": "month"})

    order_counts = (
        valid[["order_month", "order_id"]]
        .drop_duplicates()
        .groupby("order_month", as_index=False)
        .size()
        .rename(columns={"order_month": "month", "size": "orders"})
    )
    return month_base.merge(order_counts, on="month", how="left").sort_values("month")



def daily_sales_summary(order_model: pd.DataFrame) -> pd.DataFrame:
    if order_model.empty:
        return pd.DataFrame(columns=["order_day", "revenue", "orders", "qty", "gross_profit_before_ads"])

    valid = order_model[~order_model["is_returned"]].copy()
    day_base = valid.groupby("order_day", as_index=False).agg(
        revenue=("revenue", "sum"),
        qty=("qty", "sum"),
        gross_profit_before_ads=("gross_profit_before_ads", "sum"),
    )
    order_counts = (
        valid[["order_day", "order_id"]]
        .drop_duplicates()
        .groupby("order_day", as_index=False)
        .size()
        .rename(columns={"size": "orders"})
    )
    return day_base.merge(order_counts, on="order_day", how="left").sort_values("order_day")



def marketing_summary(marketing: pd.DataFrame) -> pd.DataFrame:
    if marketing.empty:
        return pd.DataFrame(columns=["marketing_source", "spend", "impressions", "clicks", "conversions", "attributed_revenue", "roas_calc"])

    out = marketing.groupby("marketing_source", as_index=False).agg(
        spend=("spend", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        conversions=("conversions", "sum"),
        attributed_revenue=("attributed_revenue", "sum"),
    )
    out["roas_calc"] = out.apply(lambda r: (r["attributed_revenue"] / r["spend"]) if r["spend"] else 0.0, axis=1)
    return out.sort_values("spend", ascending=False)



def product_summary(order_model: pd.DataFrame) -> pd.DataFrame:
    if order_model.empty:
        return pd.DataFrame()
    valid = order_model[~order_model["is_returned"]].copy()
    out = valid.groupby(["sku_key", "product_name"], as_index=False).agg(
        revenue=("revenue", "sum"),
        qty=("qty", "sum"),
        gross_profit_before_ads=("gross_profit_before_ads", "sum"),
        commission_amount=("commission_amount", "sum"),
        product_cost_amount=("product_cost_amount", "sum"),
        shipping_amount=("shipping_amount", "sum"),
    )
    out["margin_pct"] = out.apply(lambda r: (r["gross_profit_before_ads"] / r["revenue"] * 100) if r["revenue"] else 0.0, axis=1)
    return out.sort_values(["qty", "revenue"], ascending=[False, False])



def attach_stock_to_products(product_df: pd.DataFrame, stock_df: pd.DataFrame) -> pd.DataFrame:
    if product_df.empty:
        return product_df

    out = product_df.copy()
    out["product_key"] = out["product_name"].apply(normalize_text)

    if stock_df.empty:
        out["stock_qty"] = pd.NA
        out["stock_source"] = ""
        return out

    stock_view = stock_df.copy()
    if "product_key" not in stock_view.columns:
        stock_view["product_key"] = stock_view["product_name"].apply(normalize_text)

    by_name = stock_view[["product_key", "stock_qty", "source_file"]].drop_duplicates(subset=["product_key"], keep="last")
    out = out.merge(by_name, on="product_key", how="left")
    out = out.rename(columns={"source_file": "stock_source"})
    return out


def inventory_summary(stock_df: pd.DataFrame) -> dict:
    if stock_df.empty:
        return {"total_stock_units": 0.0, "tracked_products": 0, "low_stock_products": 0}

    total_units = stock_df["stock_qty"].fillna(0).sum()
    tracked_products = stock_df["product_key"].fillna("").nunique() if "product_key" in stock_df.columns else len(stock_df)
    return {
        "total_stock_units": float(total_units),
        "tracked_products": int(tracked_products),
        "low_stock_products": 0,
    }


def daily_net_profit_summary(order_model: pd.DataFrame, marketing: pd.DataFrame) -> pd.DataFrame:
    sales = daily_sales_summary(order_model)
    if sales.empty:
        return pd.DataFrame(columns=["day", "revenue", "orders", "qty", "gross_profit_before_ads", "ad_spend", "net_profit_after_ads"])

    sales = sales.rename(columns={"order_day": "day"})
    if marketing.empty:
        sales["ad_spend"] = 0.0
        sales["net_profit_after_ads"] = sales["gross_profit_before_ads"]
        return sales.sort_values("day")

    ad_day = marketing.groupby("day", as_index=False).agg(ad_spend=("spend", "sum"))
    out = sales.merge(ad_day, on="day", how="left")
    out["ad_spend"] = out["ad_spend"].fillna(0.0)
    out["net_profit_after_ads"] = out["gross_profit_before_ads"] - out["ad_spend"]
    return out.sort_values("day")



def monthly_net_profit_summary(order_model: pd.DataFrame, marketing: pd.DataFrame) -> pd.DataFrame:
    sales = monthly_order_summary(order_model)
    if sales.empty:
        return pd.DataFrame(columns=["month", "revenue", "orders", "qty", "gross_profit_before_ads", "ad_spend", "net_profit_after_ads"])

    if marketing.empty:
        sales["ad_spend"] = 0.0
        sales["net_profit_after_ads"] = sales["gross_profit_before_ads"]
        return sales.sort_values("month")

    ad_month = marketing.groupby("month", as_index=False).agg(ad_spend=("spend", "sum"))
    out = sales.merge(ad_month, on="month", how="left")
    out["ad_spend"] = out["ad_spend"].fillna(0.0)
    out["net_profit_after_ads"] = out["gross_profit_before_ads"] - out["ad_spend"]
    return out.sort_values("month")



def top_product_cards(product_df: pd.DataFrame) -> dict:
    empty_card = {"name": "-", "sku": "-", "qty": 0, "revenue": 0.0, "profit": 0.0}
    if product_df.empty:
        return {
            "best_seller_qty": empty_card,
            "best_seller_revenue": empty_card,
            "best_seller_profit": empty_card,
        }

    by_qty = product_df.sort_values(["qty", "revenue"], ascending=[False, False]).iloc[0]
    by_revenue = product_df.sort_values(["revenue", "qty"], ascending=[False, False]).iloc[0]
    by_profit = product_df.sort_values(["gross_profit_before_ads", "revenue"], ascending=[False, False]).iloc[0]

    def to_card(row):
        return {
            "name": row.get("product_name", "-"),
            "sku": row.get("sku_key", "-"),
            "qty": float(row.get("qty", 0)),
            "revenue": float(row.get("revenue", 0.0)),
            "profit": float(row.get("gross_profit_before_ads", 0.0)),
        }

    return {
        "best_seller_qty": to_card(by_qty),
        "best_seller_revenue": to_card(by_revenue),
        "best_seller_profit": to_card(by_profit),
    }



def data_quality(order_model: pd.DataFrame, marketing: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not order_model.empty:
        rows.append({
            "Check": "Cost Match Rate",
            "Value": f"%{order_model['cost_matched'].mean() * 100:.1f}",
            "Comment": "Share of order rows matched to the Trendyol cost table.",
        })
        rows.append({
            "Check": "Returned Rows",
            "Value": int(order_model["is_returned"].sum()),
            "Comment": "Number of return/cancel rows excluded from profit.",
        })
    rows.append({
        "Check": "Trendyol Weekly Ad Spend",
        "Value": "Available" if not marketing[marketing["marketing_source"].eq("Trendyol Ads")].empty else "Missing",
        "Comment": "Spend is calculated from your manual weekly Trendyol ad spend entries. Each saved week is distributed across 7 days.",
    })
    rows.append({
        "Check": "Meta Ads File",
        "Value": "Available" if not marketing[marketing["marketing_source"].eq("Meta Ads")].empty else "Missing",
        "Comment": "If available, it is included as an additional marketing source supporting Trendyol sales.",
    })
    rows.append({
        "Check": "Trendyol Stock File",
        "Value": "Available" if not stock.empty else "Missing",
        "Comment": "A separate inventory/stock export is required for the stock tab.",
    })
    return pd.DataFrame(rows)



def north_star(order_model: pd.DataFrame, marketing: pd.DataFrame) -> dict:
    if order_model.empty:
        return {
            "revenue": 0.0,
            "orders": 0,
            "qty": 0.0,
            "aov": 0.0,
            "gross_profit_before_ads": 0.0,
            "ad_spend": 0.0,
            "net_profit_after_ads": 0.0,
            "ad_revenue": 0.0,
            "roas": 0.0,
            "mer": 0.0,
        }

    valid = order_model[~order_model["is_returned"]].copy()
    total_revenue = valid["revenue"].sum()
    order_count = valid["order_id"].nunique()
    qty = valid["qty"].sum()
    profit_before_ads = valid["gross_profit_before_ads"].sum()
    ad_spend = marketing["spend"].sum() if not marketing.empty else 0.0
    ad_revenue = marketing["attributed_revenue"].sum() if not marketing.empty else 0.0

    return {
        "revenue": total_revenue,
        "orders": int(order_count),
        "qty": qty,
        "aov": (valid.groupby("order_id")["revenue"].sum().mean() if order_count else 0.0),
        "gross_profit_before_ads": profit_before_ads,
        "ad_spend": ad_spend,
        "net_profit_after_ads": profit_before_ads - ad_spend,
        "ad_revenue": ad_revenue,
        "roas": (ad_revenue / ad_spend) if ad_spend else 0.0,
        "mer": (total_revenue / ad_spend) if ad_spend else 0.0,
    }



@st.cache_data
def build_model() -> dict[str, pd.DataFrame | dict]:
    costs = load_trendyol_costs()
    orders = parse_trendyol_orders()
    marketing, trendyol_ads_raw = load_marketing(orders)
    store_report = load_trendyol_store_report()
    stock = load_stock()

    order_model = enrich_orders(orders, costs)
    month_summary = monthly_order_summary(order_model)
    day_summary = daily_sales_summary(order_model)
    day_profit = daily_net_profit_summary(order_model, marketing)
    month_profit = monthly_net_profit_summary(order_model, marketing)
    mkt_summary = marketing_summary(marketing)
    prod_summary = attach_stock_to_products(product_summary(order_model), stock)
    top_cards = top_product_cards(prod_summary)
    checks = data_quality(order_model, marketing, stock)
    ns = north_star(order_model, marketing)
    inventory_stats = inventory_summary(stock)

    return {
        "costs": costs,
        "orders": orders,
        "order_model": order_model,
        "marketing": marketing,
        "trendyol_ads_raw": trendyol_ads_raw,
        "store_report": store_report,
        "stock": stock,
        "month_summary": month_summary,
        "day_summary": day_summary,
        "day_profit": day_profit,
        "month_profit": month_profit,
        "marketing_summary": mkt_summary,
        "product_summary": prod_summary,
        "top_cards": top_cards,
        "data_quality": checks,
        "north_star": ns,
        "inventory_stats": inventory_stats,
    }


# =========================================================
# UI
# =========================================================
model = build_model()
orders = model["orders"]
order_model = model["order_model"]
marketing = model["marketing"]
trendyol_ads_raw = model["trendyol_ads_raw"]
store_report = model["store_report"]
stock = model["stock"]
day_summary = model["day_summary"]
month_summary = model["month_summary"]
day_profit = model["day_profit"]
month_profit = model["month_profit"]
marketing_sum = model["marketing_summary"]
product_sum = model["product_summary"]
top_cards = model["top_cards"]
data_checks = model["data_quality"]
ns = model["north_star"]
inventory_stats = model["inventory_stats"]

if orders.empty:
    st.error("Trendyol order file could not be found or read.")
    st.stop()

min_date = pd.to_datetime(order_model["order_date"], errors="coerce").min()
max_date = pd.to_datetime(order_model["order_date"], errors="coerce").max()

if pd.notna(min_date) and pd.notna(max_date):
    top_spacer, top_start_col, top_end_col, top_all_time_col = st.columns([4.6, 1.4, 1.4, 1.0])
    with top_spacer:
        st.markdown("")
    with top_start_col:
        top_start_date = st.date_input(
            "Start date",
            value=min_date.date(),
            min_value=min_date.date(),
            max_value=max_date.date(),
            key="top_start_date",
            disabled=st.session_state.get("top_all_time_mode", True),
        )
    with top_end_col:
        top_end_date = st.date_input(
            "End date",
            value=max_date.date(),
            min_value=min_date.date(),
            max_value=max_date.date(),
            key="top_end_date",
            disabled=st.session_state.get("top_all_time_mode", True),
        )
    with top_all_time_col:
        all_time_mode = st.toggle("All Time", value=True, key="top_all_time_mode")

    if all_time_mode:
        start_date = end_date = None
    else:
        start_date = min(top_start_date, top_end_date)
        end_date = max(top_start_date, top_end_date)
else:
    start_date = end_date = None

with st.sidebar:
    st.header("Filters")
    if pd.notna(min_date) and pd.notna(max_date):
        st.caption(f"All available data: {min_date.date()} → {max_date.date()}")
    low_stock_threshold = st.number_input("Low stock threshold", min_value=1, max_value=500, value=10, step=1)

    st.markdown("---")
    st.subheader("Weekly Ad Spend Input")
    st.caption("Enter Trendyol ad spend by week starting from 12.01.2026. Reporting will use these weekly entries.")

    existing_weekly_ads = load_manual_weekly_trendyol_ads()
    if existing_weekly_ads.empty:
        default_week_start = MANUAL_WEEKLY_ADS_START.date()
    else:
        default_week_start = (existing_weekly_ads["week_start"].max() + pd.Timedelta(days=7)).date()

    with st.form("weekly_trendyol_ad_spend_form", clear_on_submit=False):
        entered_week_start = st.date_input(
            "Week start",
            value=default_week_start,
            min_value=MANUAL_WEEKLY_ADS_START.date(),
        )
        weekly_spend_value = st.number_input("Weekly ad spend (TL)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        weekly_revenue_value = st.number_input("Total Ad Revenue (TL)", min_value=0.0, value=0.0, step=100.0, format="%.2f")
        weekly_note = st.text_input("Note", value="Manual Weekly Spend")
        save_weekly_ad = st.form_submit_button("Save weekly ad spend")

    if save_weekly_ad:
        normalized_week_start = normalize_week_start(entered_week_start)
        if pd.isna(normalized_week_start) or normalized_week_start < MANUAL_WEEKLY_ADS_START:
            st.error("Week start must be on or after 12.01.2026.")
        else:
            updated_weekly_ads = existing_weekly_ads.copy()
            updated_weekly_ads = updated_weekly_ads[updated_weekly_ads["week_start"] != normalized_week_start]
            new_row = pd.DataFrame([{
                "week_start": normalized_week_start,
                "week_end": normalized_week_start + pd.Timedelta(days=6),
                "weekly_spend": weekly_spend_value,
                "weekly_revenue": weekly_revenue_value,
                "note": weekly_note.strip() or "Manual Weekly Spend",
                "source_file": MANUAL_WEEKLY_ADS_FILE.name,
            }])
            updated_weekly_ads = pd.concat([updated_weekly_ads, new_row], ignore_index=True)
            save_manual_weekly_trendyol_ads(updated_weekly_ads)
            st.cache_data.clear()
            st.rerun()

    if not existing_weekly_ads.empty:
        with st.expander("Manage saved weekly ad spend", expanded=False):
            manage_view = existing_weekly_ads[["week_start", "week_end", "weekly_spend", "weekly_revenue", "note"]].copy()
            st.dataframe(
                manage_view.sort_values("week_start", ascending=False).style.format({"weekly_spend": "{:,.2f} TL", "weekly_revenue": "{:,.2f} TL"}),
                use_container_width=True,
                height=220,
            )
            delete_week = st.selectbox(
                "Delete a saved week",
                options=manage_view.sort_values("week_start", ascending=False)["week_start"].dt.strftime("%Y-%m-%d").tolist(),
                index=None,
                placeholder="Select week start to delete",
            )
            if st.button("Delete selected week", use_container_width=True, disabled=delete_week is None):
                delete_ts = normalize_week_start(delete_week)
                updated_weekly_ads = existing_weekly_ads[existing_weekly_ads["week_start"] != delete_ts].copy()
                save_manual_weekly_trendyol_ads(updated_weekly_ads)
                st.cache_data.clear()
                st.rerun()

filtered = order_model.copy()
if start_date and end_date:
    mask = filtered["order_date"].dt.date.between(start_date, end_date)
    filtered = filtered[mask].copy()

filtered_marketing = marketing.copy()
if start_date and end_date and not filtered_marketing.empty and filtered_marketing["date"].notna().any():
    filtered_marketing = filtered_marketing[
        filtered_marketing["date"].dt.date.between(start_date, end_date)
    ].copy()

filtered_store_report = store_report.copy()
if start_date and end_date and not filtered_store_report.empty and filtered_store_report["date"].notna().any():
    filtered_store_report = filtered_store_report[
        filtered_store_report["date"].dt.date.between(start_date, end_date)
    ].copy()

filtered_ns = north_star(filtered, filtered_marketing)
filtered_products = attach_stock_to_products(product_summary(filtered), stock)
filtered_days = daily_sales_summary(filtered)
filtered_months = monthly_order_summary(filtered)
filtered_day_profit = daily_net_profit_summary(filtered, filtered_marketing)
filtered_month_profit = monthly_net_profit_summary(filtered, filtered_marketing)
filtered_marketing_sum = marketing_summary(filtered_marketing)
filtered_top_cards = top_product_cards(filtered_products)

if start_date and end_date:
    active_period_label = f"Custom Range: {start_date} → {end_date}"
else:
    active_period_label = "All Time"

if filtered_marketing.empty:
    st.info("The dashboard still works without a Meta ads file. Trendyol ad spend now comes from your manual weekly entries, and Meta remains optional.")

if stock.empty:
    st.info("No stock export was uploaded. Manual stock entries are being used where available.")


t1, t2, t3, t4, t5, t6 = st.tabs([
    "🎯 Overview",
    "📈 Order Trends",
    "📣 Marketing",
    "📦 Product Profitability",
    "🏬 Store Traffic",
    "🧪 Data Quality",
])

with t1:
    st.caption(f"Reporting period: {active_period_label}")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Revenue", f"{filtered_ns['revenue']:,.2f} TL")
    c2.metric("Order Count", f"{filtered_ns['orders']:,}")
    c3.metric("Units Sold", f"{filtered_ns['qty']:,.0f}")
    c4.metric("AOV", f"{filtered_ns['aov']:,.2f} TL")
    c5.metric("Total Ad Revenue", f"{filtered_ns['ad_revenue']:,.2f} TL")
    c6.metric("ROAS", f"{filtered_ns['roas']:.2f}")

    c7, c8, c9, c10 = st.columns(4)
    c7.metric("Gross Profit Before Ads", f"{filtered_ns['gross_profit_before_ads']:,.2f} TL")
    c8.metric("Total Ad Spend", f"{filtered_ns['ad_spend']:,.2f} TL")
    c9.metric("Net Profit After Ads", f"{filtered_ns['net_profit_after_ads']:,.2f} TL")
    c10.metric("MER", f"{filtered_ns['mer']:.2f}")

    if not stock.empty:
        c9, c10, c11 = st.columns(3)
        c9.metric("Total Inventory Units", f"{stock['stock_qty'].fillna(0).sum():,.0f}")
        c10.metric("Tracked Inventory Items", f"{stock['product_key'].nunique():,}")
        c11.metric(
            "Low Stock Items",
            f"{int((stock['stock_qty'].fillna(0) <= low_stock_threshold).sum()):,}"
        )

    st.markdown("### Top-selling product cards")
    top1, top2, top3 = st.columns(3)
    card_qty = filtered_top_cards["best_seller_qty"]
    card_rev = filtered_top_cards["best_seller_revenue"]
    card_profit = filtered_top_cards["best_seller_profit"]

    top1.info(
        f"**Units Leader**\n\n{card_qty['name']}\n\nSKU: `{card_qty['sku']}`\n\nUnits: **{card_qty['qty']:,.0f}**\n\nCiro: **{card_qty['revenue']:,.2f} TL**"
    )
    top2.info(
        f"**Revenue Leader**\n\n{card_rev['name']}\n\nSKU: `{card_rev['sku']}`\n\nCiro: **{card_rev['revenue']:,.2f} TL**\n\nUnits: **{card_rev['qty']:,.0f}**"
    )
    top3.info(
        f"**Profit Leader**\n\n{card_profit['name']}\n\nSKU: `{card_profit['sku']}`\n\nGross Profit: **{card_profit['profit']:,.2f} TL**\n\nCiro: **{card_profit['revenue']:,.2f} TL**"
    )

    if not filtered_month_profit.empty:
        st.markdown("### Monthly net profit after ads")
        fig = px.bar(filtered_month_profit, x="month", y="net_profit_after_ads", title="Monthly Net Profit (After Ads)")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            filtered_month_profit.style.format({
                "revenue": "{:,.2f} TL",
                "gross_profit_before_ads": "{:,.2f} TL",
                "ad_spend": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "qty": "{:,.0f}",
                "orders": "{:,.0f}",
            }),
            use_container_width=True,
        )

with t2:
    st.caption(f"Reporting period: {active_period_label}")
    st.subheader("Daily and Monthly Profit Trends")
    if filtered_day_profit.empty:
        st.warning("No daily order data in the selected range.")
    else:
        fig1 = px.line(filtered_day_profit, x="day", y="revenue", markers=True, title="Daily Revenue")
        st.plotly_chart(fig1, use_container_width=True)

        fig2 = px.line(filtered_day_profit, x="day", y="gross_profit_before_ads", markers=True, title="Daily Gross Profit (Before Ads)")
        st.plotly_chart(fig2, use_container_width=True)

        fig3 = px.line(filtered_day_profit, x="day", y="net_profit_after_ads", markers=True, title="Daily Net Profit (After Ads)")
        st.plotly_chart(fig3, use_container_width=True)

        fig4 = px.bar(filtered_day_profit, x="day", y="orders", title="Daily Order Count")
        st.plotly_chart(fig4, use_container_width=True)

        st.dataframe(
            filtered_day_profit.sort_values("day", ascending=False).style.format({
                "revenue": "{:,.2f} TL",
                "gross_profit_before_ads": "{:,.2f} TL",
                "ad_spend": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "orders": "{:,.0f}",
                "qty": "{:,.0f}",
            }),
            use_container_width=True,
            height=430,
        )

    if not filtered_month_profit.empty:
        st.markdown("### Monthly summary")
        st.dataframe(
            filtered_month_profit.sort_values("month", ascending=False).style.format({
                "revenue": "{:,.2f} TL",
                "gross_profit_before_ads": "{:,.2f} TL",
                "ad_spend": "{:,.2f} TL",
                "net_profit_after_ads": "{:,.2f} TL",
                "orders": "{:,.0f}",
                "qty": "{:,.0f}",
            }),
            use_container_width=True,
            height=300,
        )

with t3:
    st.caption(f"Reporting period: {active_period_label}")
    st.subheader("Marketing Efficiency")
    st.caption("Note: Trendyol ad spend is now driven by your manual weekly entries. Each saved week is allocated across its 7 calendar days for daily and monthly reporting.")
    if filtered_marketing.empty:
        st.warning("No manual weekly Trendyol ad spend or Meta Ads data was found.")
    else:
        st.dataframe(
            filtered_marketing_sum.style.format({
                "spend": "{:,.2f} TL",
                "impressions": "{:,.0f}",
                "clicks": "{:,.0f}",
                "conversions": "{:,.0f}",
                "attributed_revenue": "{:,.2f} TL",
                "roas_calc": "{:.2f}",
            }),
            use_container_width=True,
        )

        fig = px.bar(filtered_marketing_sum, x="marketing_source", y="spend", title="Ad Spend by Source")
        st.plotly_chart(fig, use_container_width=True)

        if not trendyol_ads_raw.empty:
            st.markdown("### Trendyol weekly ad spend entries")
            raw_ads_view = trendyol_ads_raw.copy()
            raw_ads_view["roas_calc"] = raw_ads_view.apply(lambda r: (r["attributed_revenue"] / r["spend"]) if r["spend"] else 0.0, axis=1)
            st.dataframe(
                raw_ads_view[[
                    "campaign_name", "campaign_status", "start_date", "end_date", "daily_budget", "total_budget", "remaining_budget", "spend", "attributed_revenue", "roas_reported", "roas_calc"
                ]].sort_values("spend", ascending=False).style.format({
                    "daily_budget": "{:,.2f} TL",
                    "total_budget": "{:,.2f} TL",
                    "remaining_budget": "{:,.2f} TL",
                    "spend": "{:,.2f} TL",
                    "attributed_revenue": "{:,.2f} TL",
                    "roas_reported": "{:.2f}",
                    "roas_calc": "{:.2f}",
                }),
                use_container_width=True,
                height=260,
            )


with t4:
    st.caption(f"Reporting period: {active_period_label}")
    st.subheader("Product Profitability")
    if filtered_products.empty:
        st.warning("No product summary in the selected range.")
    else:
        st.markdown("### Top 10 best-selling products")
        best_sellers = filtered_products.sort_values(["qty", "revenue"], ascending=[False, False]).head(10)
        st.dataframe(
            best_sellers.style.format({
                "revenue": "{:,.2f} TL",
                "qty": "{:,.0f}",
                "gross_profit_before_ads": "{:,.2f} TL",
                "margin_pct": "%{:.2f}",
                "stock_qty": "{:,.0f}",
            }),
            use_container_width=True,
        )

        fig = px.bar(
            best_sellers,
            x="product_name",
            y="qty",
            title="Top 10 Best-Selling Products (Units)",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### Full product profitability table")
        st.dataframe(
            filtered_products.style.format({
                "revenue": "{:,.2f} TL",
                "qty": "{:,.0f}",
                "gross_profit_before_ads": "{:,.2f} TL",
                "commission_amount": "{:,.2f} TL",
                "product_cost_amount": "{:,.2f} TL",
                "shipping_amount": "{:,.2f} TL",
                "margin_pct": "%{:.2f}",
                "stock_qty": "{:,.0f}",
            }),
            use_container_width=True,
            height=520,
        )

        unmatched = filtered[~filtered["cost_matched"]][["sku_key", "product_name", "source_file"]].drop_duplicates()
        if not unmatched.empty:
            st.markdown("**SKUs with no matched cost**")
            st.dataframe(unmatched, use_container_width=True)

with t5:
    st.caption(f"Reporting period: {active_period_label}")
    st.subheader("Trendyol Store Traffic and Inventory")
    if not filtered_store_report.empty:
        c1, c2, c3 = st.columns(3)
        latest = filtered_store_report.sort_values("date").iloc[-1]
        c1.metric("Latest Day Unique Visitors", f"{latest['visitors']:,.0f}")
        c2.metric("Latest Day Store Orders", f"{latest['orders']:,.0f}")
        c3.metric("Latest Day Store Revenue", f"{latest['store_gross_revenue']:,.2f} TL")

        fig = px.line(filtered_store_report, x="date", y="visitors", markers=True, title="Unique Visitors Trend")
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.line(filtered_store_report, x="date", y="store_gross_revenue", markers=True, title="Store Gross Revenue Trend")
        st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(
            filtered_store_report.sort_values("date", ascending=False).head(20).style.format({
                "store_gross_revenue": "{:,.2f} TL",
                "visitors": "{:,.0f}",
                "orders": "{:,.0f}",
                "conversion_rate": "%{:.2f}",
            }),
            use_container_width=True,
        )
    else:
        st.warning("Trendyol store report was not found.")

    if not stock.empty:
        st.markdown("**Trendyol inventory view**")
        st.dataframe(stock.sort_values("stock_qty").style.format({"stock_qty": "{:,.0f}"}), use_container_width=True)
        low_stock = stock[stock["stock_qty"] <= low_stock_threshold]
        if not low_stock.empty:
            st.markdown(f"**Low stock items (<= {low_stock_threshold})**")
            st.dataframe(low_stock.sort_values("stock_qty"), use_container_width=True)
    else:
        st.info("When you upload a stock export, Trendyol inventory and low-stock items will appear here. Manual stock entries are also shown below.")

with t6:
    st.caption(f"Reporting period: {active_period_label}")
    st.subheader("Data Quality")
    st.dataframe(data_checks, use_container_width=True)
    st.markdown(
        """
        **Minimum expected columns in a Meta export:**
        - Date / Day / Reporting starts
        - Campaign name
        - Amount spent
        - Impressions
        - Link clicks
        - Purchases veya Purchase conversion value

        **Minimum expected columns in a Trendyol stock export:**
        - SKU / Barcode / Stock Code
        - Stock / Inventory / Available
        - Product name
        """
    )