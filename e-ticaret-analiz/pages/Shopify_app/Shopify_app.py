
import csv
import glob
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="SMARTEK360 Shopify Dashboard", layout="wide")

# =========================================================
# LOGIN CONTROL
# =========================================================
# Bu dosya ana sayfadan giriş yapılmadan çalışmasın.
if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🟣 SMARTEK360: Shopify Dashboard")
st.caption(
    "Built for Shopify orders, Shopify traffic exports, Shopify cost table, manual inventory, Meta Ads performance exports, and Meta billing spend."
)

# Bu dosyanın bulunduğu klasör:
# e-ticaret-analiz/pages/Shopify_app/
# Tüm Shopify CSV dosyaları bu klasörden okunacak.
DATA_DIR = Path(__file__).resolve().parent


# ==============================
# Helpers
# ==============================

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

    if s in {"-", "nan", "None", "null", "Henüzfaturakesilmemiştir.", "Sürekli"}:
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
    if pd.isna(val) or val == "":
        return ""
    s = str(val).strip().replace("6-", "")
    if "E+" in s.upper():
        try:
            s = f"{float(s):.0f}"
        except Exception:
            pass
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    try:
        if re.fullmatch(r"\d+\.\d+", s):
            s = f"{float(s):.0f}"
    except Exception:
        pass
    return s


def normalize_text(text: str) -> str:
    if pd.isna(text):
        return ""
    s = str(text).lower().strip()
    tr_map = str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ç": "c", "Ç": "c", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u",
    })
    s = s.translate(tr_map)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("®", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_first_existing(patterns):
    """
    Streamlit ana sayfadan runpy ile çalıştırıldığı için çalışma klasörü farklı olabilir.
    Bu yüzden dosyaları bulunduğumuz klasörden, yani DATA_DIR içinden arıyoruz.
    """
    files = []
    for p in patterns:
        files.extend(glob.glob(str(DATA_DIR / p)))
    deduped = []
    seen = set()
    for f in files:
        full = os.path.abspath(f)
        if full not in seen and os.path.exists(full):
            seen.add(full)
            deduped.append(full)
    return deduped


def parse_any_date(series):
    if series is None:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_localize(None)


def get_all_csv_files():
    files = find_first_existing(["*.csv", "*.CSV"])
    return sorted(files)


def get_shopify_order_files():
    """
    Shopify sipariş dosyalarını sadece dosya adına göre değil, kolonlara göre de tanır.
    Böylece orders_export_1.csv gibi Shopify'ın kendi verdiği dosya adları da okunur.
    """
    files = get_all_csv_files()
    excluded_exact = {
        "shopify002.csv",
        "shopify003.csv",
        "shopify004.csv",
        "shopify maliyet tablosu(sayfa1).csv",
        "meta(formatted report).csv",
        "meta(formatted report)(1).csv",
        "meta070426.csv",
        "meta_ads_template_shopify.csv",
    }

    order_files = []
    for path in files:
        name = os.path.basename(path).lower()

        if name in excluded_exact:
            continue
        if "maliyet" in name or "cost" in name:
            continue
        if "meta" in name or "facebook" in name or "formatted report" in name:
            continue
        if "shopify002" in name or "shopify003" in name or "shopify004" in name:
            continue
        if "zamana göre" in name or "oturum" in name:
            continue
        if "fatura" in name:
            continue

        # Dosya adı Shopify içeriyorsa direkt adaydır.
        if "shopify" in name or "orders_export" in name or "order" in name:
            order_files.append(path)
            continue

        # Dosya adı farklı olsa bile kolonları Shopify sipariş export'una benziyorsa aday yap.
        try:
            sample = read_shopify_order_csv_robust(path)
            required_cols = {"Name", "Created at", "Lineitem name"}
            if not sample.empty and required_cols.issubset(set(sample.columns)):
                order_files.append(path)
        except Exception:
            pass

    return sorted(set(order_files))


def read_shopify_order_csv_robust(path: str) -> pd.DataFrame:
    """
    Handles both normal Shopify CSV exports and malformed mixed exports where
    some rows collapse into a single quoted field while others remain split.
    """
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "latin1"]
    last_error = None

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                continue

            header = rows[0]
            header_len = len(header)
            fixed_rows = []

            for raw in rows[1:]:
                if not raw:
                    continue
                row = raw

                if len(row) == 1:
                    try:
                        reparsed = next(csv.reader([row[0]]))
                        if len(reparsed) > 1:
                            row = reparsed
                    except Exception:
                        pass

                if len(row) < header_len:
                    row = row + [""] * (header_len - len(row))
                elif len(row) > header_len:
                    row = row[:header_len]

                if len(row) == header_len:
                    fixed_rows.append(row)

            if not fixed_rows:
                continue

            df = pd.DataFrame(fixed_rows, columns=header)
            df = df.loc[:, ~df.columns.duplicated()]
            return df

        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    return pd.DataFrame()


def safe_minmax(series_list):
    values = []
    for s in series_list:
        if s is None or len(s) == 0:
            continue
        s = pd.to_datetime(s, errors="coerce")
        s = s.dropna()
        if not s.empty:
            values.append((s.min(), s.max()))
    if not values:
        today = pd.Timestamp.today().normalize()
        return today, today
    return min(v[0] for v in values), max(v[1] for v in values)


def find_col_by_keywords(df: pd.DataFrame, keywords: list[str]):
    for col in df.columns:
        col_norm = normalize_text(col)
        if any(k in col_norm for k in keywords):
            return col
    return None


# ==============================
# Manual inventory seed
# ==============================

MANUAL_INVENTORY = {
    "j01t green": 102,
    "j01t camel": 102,
    "j01 blue": 60,
    "j01 grey": 47,
    "j03 pro titanium": 541,
    "black j01t": 266,
    "salat counter": 35,
    "premium black gold 22mm": 9,
    "premium rose gold 20mm": 7,
    "premium black gray 22mm": 7,
    "j01 pink": 120,
    "j01 green": 120,
    "j01 black": 160,
}

INVENTORY_ALIASES = {
    "j01t green": ["jood lite yesil", "jood lite green", "jood lite ye il"],
    "j01t camel": ["jood lite camel bej", "jood lite kum beji", "jood lite camel", "jood lite kum"],
    "j01 blue": ["jood mavi", "jood blue"],
    "j01 grey": ["jood gri", "jood grey", "jood gray"],
    "j03 pro titanium": ["jood 3 pro titanyum gri", "jood 3 pro titanium", "jood 3 pro gri", "zikr jood 3 pro gri", "zikr jood 3 pro titanium", "jood 3 pro"],
    "black j01t": ["jood lite siyah", "jood lite black"],
    "salat counter": ["rekat sayaci", "salat counter", "salavatmatik"],
    "premium black gold 22mm": ["premium altin siyah 22 mm", "premium black gold 22 mm", "premium siyah altin 22 mm"],
    "premium rose gold 20mm": ["premium rose altin 20 mm", "premium altin gul 20 mm", "premium rose gold 20 mm"],
    "premium black gray 22mm": ["premium black gray 22 mm", "premium siyah gri 22 mm", "premium altin siyah 22mm"],
    "j01 pink": ["jood pembe", "jood pink"],
    "j01 green": ["jood yesil", "jood green"],
    "j01 black": ["jood siyah", "jood black"],
}

MANUAL_PRODUCT_SKU_MAP = {
    "zikr jood 3 pro gri": "6970126922132",
    "zikr jood 3 pro siyah": "6970126922125",
    "zikr ring m02 premium altin gul 20 mm": "6970126922170",
    "zikr ring m02 premium rose altin 20 mm": "6970126921630",
    "zikr ring jood gri": "970126921944",
    "zikr ring jood mavi": "970126921920",
    "zikr ring jood pembe": "970126921951",
    "zikr ring jood siyah": "970126921913",
    "zikr ring jood yesil": "970126921937",
    "zikr ring jood lite kum beji": "970126922903",
    "zikr ring jood lite siyah": "970126922880",
    "zikr ring jood lite yesil": "970126922910",
}

ZERO_COST_PRODUCT_NAMES = {
    "kapida odeme ucreti",
    "hediye kutusu",
}


def inventory_for_product(product_name: str):
    name = normalize_text(product_name)
    for key, aliases in INVENTORY_ALIASES.items():
        for alias in aliases:
            if alias in name:
                return MANUAL_INVENTORY.get(key)
    return None


def manual_sku_for_product(product_name: str) -> str:
    name = normalize_text(product_name)
    return MANUAL_PRODUCT_SKU_MAP.get(name, "")


def is_zero_cost_product(product_name: str) -> bool:
    name = normalize_text(product_name)
    return name in ZERO_COST_PRODUCT_NAMES


# ==============================
# Shopify loaders
# ==============================

@st.cache_data(show_spinner=False)
def load_shopify_costs() -> pd.DataFrame:
    files = find_first_existing([
        "Shopify Maliyet Tablosu(Sayfa1).csv",
        "*Shopify*Maliyet*.csv",
        "*shopify*maliyet*.csv"
    ])
    if not files:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "unit_ship", "vat_rate"])

    path = files[0]
    df = pd.read_csv(path, sep=";", encoding="utf-8", header=None, dtype=str)
    if df.empty:
        return pd.DataFrame(columns=["sku_key", "commission_rate", "unit_cost", "unit_ship", "vat_rate"])

    header = df.iloc[0].tolist()
    df = df.iloc[1:].copy()
    df.columns = header

    col_sku = find_col_by_keywords(df, ["sku"])
    col_comm = find_col_by_keywords(df, ["komisyon"])
    col_cost = find_col_by_keywords(df, ["maliyet"])
    col_ship = find_col_by_keywords(df, ["kargo", "shipping"])
    col_vat = find_col_by_keywords(df, ["kdv", "vat"])

    out = pd.DataFrame()
    out["sku_key"] = df[col_sku].apply(clean_sku) if col_sku else ""
    out["commission_rate"] = df[col_comm].apply(to_float) if col_comm else 0.0
    out["unit_cost"] = df[col_cost].apply(to_float) if col_cost else 0.0
    out["unit_ship"] = df[col_ship].apply(to_float) if col_ship else 0.0
    out["vat_rate"] = df[col_vat].apply(to_float) if col_vat else 0.0
    out = out[out["sku_key"] != ""].drop_duplicates("sku_key", keep="last")
    return out


@st.cache_data(show_spinner=False)
def load_shopify_orders() -> tuple[pd.DataFrame, pd.DataFrame]:
    files = get_shopify_order_files()
    if not files:
        return pd.DataFrame(), pd.DataFrame()

    frames = []
    for path in files:
        try:
            df = read_shopify_order_csv_robust(path)
        except Exception:
            continue
        if df.empty:
            continue

        # Keep only files that look like Shopify order exports
        required_cols = {"Name", "Created at", "Lineitem name"}
        if not required_cols.issubset(set(df.columns)):
            continue

        df["source_file"] = os.path.basename(path)
        frames.append(df)

    if not frames:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Drop exact duplicate order-line rows across repeated weekly exports / duplicate uploads
    dedupe_cols = [c for c in [
        "Name", "Created at", "Lineitem name", "Lineitem sku",
        "Lineitem quantity", "Lineitem price", "Financial Status",
        "Fulfillment Status", "Total", "Discount Amount"
    ] if c in df.columns]
    if dedupe_cols:
        df = df.drop_duplicates(subset=dedupe_cols, keep="first").copy()

    numeric_cols = [
        "Total", "Subtotal", "Shipping", "Taxes", "Discount Amount", "Refunded Amount",
        "Lineitem quantity", "Lineitem price", "Lineitem discount"
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = df[c].apply(to_float)

    df["order_date"] = parse_any_date(df.get("Created at"))
    df["paid_at"] = parse_any_date(df.get("Paid at"))
    df["cancelled_at"] = parse_any_date(df.get("Cancelled at"))
    df["order_name"] = df.get("Name", "").fillna("").astype(str)
    df["financial_status"] = df.get("Financial Status", "").fillna("").astype(str).str.lower()
    df["fulfillment_status"] = df.get("Fulfillment Status", "").fillna("").astype(str).str.lower()

    orders = df.groupby("order_name", dropna=False).agg({
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
    }).reset_index()

    orders["is_cancelled"] = orders["cancelled_at"].notna() | orders["financial_status"].isin(["voided", "void"])
    orders["net_sales"] = orders["Total"].fillna(0) - orders["Refunded Amount"].fillna(0)
    orders.loc[orders["is_cancelled"], "net_sales"] = 0.0
    orders["order_count"] = (~orders["is_cancelled"]).astype(int)

    lines = df.copy()
    lines["product_name"] = df.get("Lineitem name", "").fillna("")
    lines["product_name_norm"] = lines["product_name"].apply(normalize_text)
    lines["sku_key_original"] = lines.get("Lineitem sku", "").apply(clean_sku)
    lines["sku_key_manual"] = lines["product_name"].apply(manual_sku_for_product)
    lines["sku_key"] = lines["sku_key_manual"].where(lines["sku_key_manual"] != "", lines["sku_key_original"])
    lines["sku_source"] = "order_line_sku"
    lines.loc[lines["sku_key_manual"] != "", "sku_source"] = "manual_product_map"
    lines.loc[lines["sku_key"] == "", "sku_source"] = "missing"
    lines["is_zero_cost_item"] = lines["product_name"].apply(is_zero_cost_product)
    lines["qty"] = df.get("Lineitem quantity", 0).apply(to_float)
    lines["line_discount"] = df.get("Lineitem discount", 0).apply(to_float)
    lines["line_price"] = df.get("Lineitem price", 0).apply(to_float)
    lines["line_revenue"] = lines["line_price"] * lines["qty"] - lines["line_discount"]
    lines["is_cancelled"] = lines["cancelled_at"].notna() | lines["financial_status"].isin(["voided", "void"])
    lines["is_refunded"] = lines["financial_status"].str.contains("refund", case=False, na=False)
    lines.loc[lines["is_cancelled"], "line_revenue"] = 0.0
    lines.loc[lines["is_cancelled"], "qty"] = 0.0
    lines["inventory_units"] = lines["product_name"].apply(inventory_for_product)

    keep_cols = [
        "order_name", "order_date", "financial_status", "fulfillment_status", "sku_key", "sku_key_original",
        "sku_key_manual", "sku_source", "product_name", "product_name_norm", "qty", "line_revenue",
        "is_cancelled", "is_refunded", "is_zero_cost_item", "inventory_units", "source_file"
    ]
    keep_cols = [c for c in keep_cols if c in lines.columns]
    return orders, lines[keep_cols].copy()


@st.cache_data(show_spinner=False)
def load_shopify_funnel() -> pd.DataFrame:
    files = find_first_existing(["shopify002.csv", "*shopify002*.csv"])
    if not files:
        return pd.DataFrame()

    df = pd.read_csv(files[0], low_memory=False, dtype=str)
    if df.empty:
        return pd.DataFrame()

    col_map = {
        "Ay": "month",
        "Oturumlar": "sessions",
        "Sepete ekleme yapılan oturumlar": "sessions_added_to_cart",
        "Ödeme sayfasına ulaşan oturumlar": "sessions_reached_checkout",
        "Ödemeyi tamamlayan oturumlar": "sessions_completed_checkout",
        "Dönüşüm oranı": "conversion_rate",
    }
    out = pd.DataFrame()
    for src, dst in col_map.items():
        if src in df.columns:
            out[dst] = df[src]
    if out.empty:
        return pd.DataFrame()

    out["month"] = pd.to_datetime(out["month"], errors="coerce")
    for c in ["sessions", "sessions_added_to_cart", "sessions_reached_checkout", "sessions_completed_checkout", "conversion_rate"]:
        if c in out.columns:
            out[c] = out[c].apply(to_float)
    return out.dropna(subset=["month"])


@st.cache_data(show_spinner=False)
def load_shopify_geo() -> pd.DataFrame:
    files = find_first_existing(["shopify003.csv", "*shopify003*.csv"])
    if not files:
        return pd.DataFrame()

    df = pd.read_csv(files[0], low_memory=False, dtype=str)
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    if "Oturum ülkesi" in df.columns:
        out["country"] = df["Oturum ülkesi"]
    if "Oturum bölgesi" in df.columns:
        out["region"] = df["Oturum bölgesi"]
    if "Oturum şehri" in df.columns:
        out["city"] = df["Oturum şehri"]
    if "Online mağaza ziyaretçileri" in df.columns:
        out["visitors"] = df["Online mağaza ziyaretçileri"].apply(to_float)
    if "Oturumlar" in df.columns:
        out["sessions"] = df["Oturumlar"].apply(to_float)
    return out


@st.cache_data(show_spinner=False)
def load_shopify_gross_sales_monthly() -> pd.DataFrame:
    files = find_first_existing(["shopify004.csv", "*shopify004*.csv"])
    if not files:
        return pd.DataFrame()

    df = pd.read_csv(files[0], low_memory=False, dtype=str)
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame()
    if "Ay" in df.columns:
        out["month"] = pd.to_datetime(df["Ay"], errors="coerce")
    if "Brüt satışlar" in df.columns:
        out["gross_sales"] = df["Brüt satışlar"].apply(to_float)
    return out.dropna(subset=["month"]) if not out.empty else pd.DataFrame()


# ==============================
# Meta loaders
# ==============================

def read_csv_flexible(path: str) -> pd.DataFrame:
    attempts = [
        {"sep": ",", "encoding": "utf-8-sig"},
        {"sep": ",", "encoding": "utf-8"},
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": ";", "encoding": "utf-8"},
        {"sep": ",", "encoding": "iso-8859-9"},
        {"sep": ";", "encoding": "iso-8859-9"},
    ]
    for opts in attempts:
        try:
            df = pd.read_csv(path, low_memory=False, dtype=str, **opts)
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def find_meta_col(df: pd.DataFrame, options: list[str]):
    cols_norm = {c: normalize_text(c) for c in df.columns}
    normalized_options = [normalize_text(o) for o in options]
    compact_options = [o.replace(" ", "") for o in normalized_options if o]

    for c, n in cols_norm.items():
        compact_n = n.replace(" ", "")
        if n in normalized_options or compact_n in compact_options:
            return c

    for c, n in cols_norm.items():
        compact_n = n.replace(" ", "")
        if any((opt and opt in n) or (opt.replace(" ", "") and opt.replace(" ", "") in compact_n) for opt in normalized_options):
            return c

    for c, n in cols_norm.items():
        n_tokens = {t for t in n.split() if len(t) >= 2}
        for opt in normalized_options:
            opt_tokens = [t for t in opt.split() if len(t) >= 2]
            if not opt_tokens:
                continue
            hits = sum(t in n_tokens for t in opt_tokens)
            if hits >= max(1, min(2, len(opt_tokens))):
                return c
    return None


def normalize_meta_formatted_report_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    current_cols = [normalize_text(c) for c in df.columns]
    if any(("harcanan tutar" in c) or ("amount spent" in c) or (c == "spend") for c in current_cols):
        return df

    header_idx = None
    for i in range(min(len(df), 6)):
        row_vals = [normalize_text(v) for v in df.iloc[i].tolist()]
        joined = " | ".join(row_vals)
        if (("kampanya" in joined) or ("campaign" in joined)) and (("harcanan tutar" in joined) or ("amount spent" in joined) or ("tutar" in joined)) and (("rapor" in joined) or ("report" in joined) or ("gun" in joined) or ("date" in joined)):
            header_idx = i
            break

    if header_idx is None:
        return df

    raw_header = df.iloc[header_idx].tolist()
    header = []
    seen = {}
    for j, val in enumerate(raw_header):
        name = str(val).strip() if pd.notna(val) and str(val).strip() else f"unnamed_{j}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name}_{seen[name]-1}"
        header.append(name)

    out = df.iloc[header_idx + 1:].copy()
    out.columns = header
    out = out.dropna(how="all").reset_index(drop=True)
    return out


def looks_like_meta_performance_export(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    df = normalize_meta_formatted_report_df(df)
    cols = [normalize_text(c) for c in df.columns]
    has_spend = any(("harcanan tutar" in c) or ("amount spent" in c) or (c == "spend") for c in cols)
    has_campaign = any(("kampanya" in c) or ("campaign" in c) for c in cols)
    has_period = any(("rapor" in c) or ("reporting starts" in c) or (c == "date") or (c == "day") or (c == "tarih") or (c == "gun") for c in cols)
    return bool(has_spend and (has_campaign or has_period))


def parse_meta_billing_report(path: str):
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9"]
    raw_text = ""
    for enc in encodings:
        try:
            raw_text = Path(path).read_text(encoding=enc)
            if raw_text:
                break
        except Exception:
            continue
    if not raw_text:
        return pd.DataFrame(), None

    marker_candidates = ["Meta Reklamları Ödemesi", "Meta Ads Payments", "Meta Advertising Payments"]
    start_idx = -1
    marker_used = None
    for marker in marker_candidates:
        start_idx = raw_text.find(marker)
        if start_idx != -1:
            marker_used = marker
            break
    if start_idx == -1:
        return pd.DataFrame(), None

    section_lines = raw_text[start_idx:].splitlines()
    if len(section_lines) < 3:
        return pd.DataFrame(), None

    data_lines = []
    for line in section_lines[1:]:
        if not line.strip():
            if data_lines:
                break
            continue
        if line.startswith("VAT Rate") or line.startswith('"VAT Amount'):
            break
        data_lines.append(line)

    rows = []
    reader = csv.reader(data_lines)
    for row in reader:
        if not row:
            continue
        if len(row) >= 5 and re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", str(row[0]).strip()):
            rows.append({
                "date": pd.to_datetime(str(row[0]).strip(), format="%d.%m.%Y", errors="coerce"),
                "source": "Meta Billing",
                "campaign_name": "Billing Charges",
                "adset_name": "",
                "ad_name": "",
                "spend": to_float(row[3]),
                "attributed_revenue": 0.0,
                "purchases": 0.0,
                "file_name": os.path.basename(path),
            })

    if not rows:
        return pd.DataFrame(), {
            "file_name": os.path.basename(path),
            "file_type": "Meta Billing",
            "status": "marker_found_but_no_rows",
            "rows_loaded": 0,
            "spend_total": 0.0,
            "date_min": pd.NaT,
            "date_max": pd.NaT,
            "note": f"Marker found: {marker_used}",
        }

    tmp = pd.DataFrame(rows).dropna(subset=["date"])
    if tmp.empty:
        return pd.DataFrame(), {
            "file_name": os.path.basename(path),
            "file_type": "Meta Billing",
            "status": "rows_without_valid_dates",
            "rows_loaded": 0,
            "spend_total": 0.0,
            "date_min": pd.NaT,
            "date_max": pd.NaT,
            "note": f"Marker found: {marker_used}",
        }

    tmp["date"] = pd.to_datetime(tmp["date"]).dt.normalize()
    tmp = tmp.groupby(
        ["date", "source", "campaign_name", "adset_name", "ad_name", "file_name"],
        as_index=False,
    ).agg({"spend": "sum", "attributed_revenue": "sum", "purchases": "sum"})

    debug = {
        "file_name": os.path.basename(path),
        "file_type": "Meta Billing",
        "status": "loaded",
        "rows_loaded": len(tmp),
        "spend_total": float(tmp["spend"].sum()),
        "date_min": tmp["date"].min(),
        "date_max": tmp["date"].max(),
        "note": "Spend from payment ledger; no attributed revenue in billing files.",
    }
    return tmp, debug


def parse_meta_performance_export(path: str):
    df = read_csv_flexible(path)
    df = normalize_meta_formatted_report_df(df)
    if df.empty:
        return pd.DataFrame(), {
            "file_name": os.path.basename(path),
            "file_type": "Unknown",
            "status": "empty_or_unreadable",
            "rows_loaded": 0,
            "spend_total": 0.0,
            "date_min": pd.NaT,
            "date_max": pd.NaT,
            "note": "CSV could not be read with the tested delimiters/encodings.",
        }

    if not looks_like_meta_performance_export(df):
        return pd.DataFrame(), {
            "file_name": os.path.basename(path),
            "file_type": "Unknown",
            "status": "not_meta_performance",
            "rows_loaded": 0,
            "spend_total": 0.0,
            "date_min": pd.NaT,
            "date_max": pd.NaT,
            "note": "File did not match Meta performance columns.",
        }

    date_col = find_meta_col(df, [
        "Date", "Day", "Gün", "Gun", "Tarih", "Reporting starts", "Reporting start"
    ])
    report_start_col = find_meta_col(df, [
        "Rapor Başlangıcı", "Rapor Ba", "Report start", "Reporting starts", "Reporting start"
    ])
    report_end_col = find_meta_col(df, [
        "Rapor Sonu", "Rapor So", "Report end", "Reporting ends", "Reporting end"
    ])
    spend_col = find_meta_col(df, [
        "Amount spent", "Spend", "Harcanan Tutar", "Harcama", "Tutar", "Harcanan Tutar (TRY)"
    ])
    revenue_col = find_meta_col(df, [
        "Website purchases conversion value",
        "Purchase conversion value",
        "Website purchase conversion value",
        "Purchases conversion value",
        "Purchase value",
        "Attributed revenue",
        "Revenue",
        "Gelir",
        "Alışveriş dönüşüm değeri",
        "Web sitesi satın alma dönüşüm değeri",
    ])
    roas_col = find_meta_col(df, [
        "Purchase ROAS",
        "Website purchase ROAS",
        "Alışveriş reklam harcamasının getirisi",
        "Satın alma ROAS",
        "ROAS",
        "Getirisi",
    ])
    purchase_col = find_meta_col(df, [
        "Purchases",
        "Website purchases",
        "Results",
        "Sonuçlar",
        "Satın almalar",
        "Satın alma",
        "Purchase",
        "Alışverişler",
        "Al veri ler",
        "Alışveriş"
    ])
    campaign_col = find_meta_col(df, [
        "Campaign name",
        "Campaign",
        "Kampanya Adı",
        "Kampanya",
    ])
    adset_col = find_meta_col(df, [
        "Ad set name",
        "Adset name",
        "Reklam seti adı",
        "Reklam seti",
    ])
    ad_col = find_meta_col(df, [
        "Ad name",
        "Reklam adı",
    ])

    if not spend_col:
        return pd.DataFrame(), {
            "file_name": os.path.basename(path),
            "file_type": "Meta Performance",
            "status": "missing_spend_column",
            "rows_loaded": 0,
            "spend_total": 0.0,
            "date_min": pd.NaT,
            "date_max": pd.NaT,
            "note": "Meta performance file detected, but no spend column was mapped.",
        }

    campaign_series = (
        df[campaign_col].replace("", pd.NA).ffill().fillna("Unknown Campaign")
        if campaign_col else pd.Series(["Unknown Campaign"] * len(df))
    )
    adset_series = (
        df[adset_col].replace("", pd.NA).ffill().fillna("")
        if adset_col else pd.Series([""] * len(df))
    )
    ad_series = (
        df[ad_col].replace("", pd.NA).ffill().fillna("")
        if ad_col else pd.Series([""] * len(df))
    )
    spend_series = df[spend_col].apply(to_float)
    purchases_series = df[purchase_col].apply(to_float) if purchase_col else pd.Series([0.0] * len(df))
    if revenue_col:
        revenue_series = df[revenue_col].apply(to_float)
    elif roas_col:
        revenue_series = spend_series * df[roas_col].apply(to_float)
    else:
        revenue_series = pd.Series([0.0] * len(df))

    if date_col:
        tmp = pd.DataFrame({
            "date": pd.to_datetime(df[date_col], errors="coerce"),
            "source": "Meta Performance",
            "campaign_name": campaign_series,
            "adset_name": adset_series,
            "ad_name": ad_series,
            "spend": spend_series,
            "attributed_revenue": revenue_series,
            "purchases": purchases_series,
            "file_name": os.path.basename(path),
        }).dropna(subset=["date"])
        if tmp.empty:
            return pd.DataFrame(), {
                "file_name": os.path.basename(path),
                "file_type": "Meta Performance",
                "status": "date_column_found_but_empty",
                "rows_loaded": 0,
                "spend_total": 0.0,
                "date_min": pd.NaT,
                "date_max": pd.NaT,
                "note": f"Mapped date column: {date_col}",
            }
        tmp["date"] = pd.to_datetime(tmp["date"]).dt.normalize()
        tmp = tmp.groupby(
            ["date", "source", "campaign_name", "adset_name", "ad_name", "file_name"],
            as_index=False
        ).agg({"spend": "sum", "attributed_revenue": "sum", "purchases": "sum"})
        debug = {
            "file_name": os.path.basename(path),
            "file_type": "Meta Performance",
            "status": "loaded_daily",
            "rows_loaded": len(tmp),
            "spend_total": float(tmp["spend"].sum()),
            "date_min": tmp["date"].min(),
            "date_max": tmp["date"].max(),
            "note": f"Mapped daily date column: {date_col}",
        }
        return tmp, debug

    if report_start_col and report_end_col:
        starts = pd.to_datetime(df[report_start_col], errors="coerce")
        ends = pd.to_datetime(df[report_end_col], errors="coerce")
        rows = []
        for i in range(len(df)):
            start_d = starts.iloc[i]
            end_d = ends.iloc[i]
            if pd.isna(start_d) and pd.isna(end_d):
                continue
            if pd.isna(start_d):
                start_d = end_d
            if pd.isna(end_d):
                end_d = start_d
            start_d = pd.Timestamp(start_d).normalize()
            end_d = pd.Timestamp(end_d).normalize()
            if end_d < start_d:
                start_d, end_d = end_d, start_d
            days = pd.date_range(start_d, end_d, freq="D")
            divisor = max(len(days), 1)
            daily_spend = float(spend_series.iloc[i]) / divisor
            daily_revenue = float(revenue_series.iloc[i]) / divisor
            daily_purchases = float(purchases_series.iloc[i]) / divisor
            for day in days:
                rows.append({
                    "date": day,
                    "source": "Meta Performance (Allocated)",
                    "campaign_name": campaign_series.iloc[i],
                    "adset_name": adset_series.iloc[i],
                    "ad_name": ad_series.iloc[i],
                    "spend": daily_spend,
                    "attributed_revenue": daily_revenue,
                    "purchases": daily_purchases,
                    "file_name": os.path.basename(path),
                })
        if rows:
            tmp = pd.DataFrame(rows)
            tmp = tmp.groupby(
                ["date", "source", "campaign_name", "adset_name", "ad_name", "file_name"],
                as_index=False
            ).agg({"spend": "sum", "attributed_revenue": "sum", "purchases": "sum"})
            debug = {
                "file_name": os.path.basename(path),
                "file_type": "Meta Performance",
                "status": "loaded_period_allocated",
                "rows_loaded": len(tmp),
                "spend_total": float(tmp["spend"].sum()),
                "date_min": tmp["date"].min(),
                "date_max": tmp["date"].max(),
                "note": f"Allocated evenly from {report_start_col} to {report_end_col}",
            }
            return tmp, debug

    return pd.DataFrame(), {
        "file_name": os.path.basename(path),
        "file_type": "Meta Performance",
        "status": "no_date_mapping",
        "rows_loaded": 0,
        "spend_total": float(spend_series.sum()),
        "date_min": pd.NaT,
        "date_max": pd.NaT,
        "note": "Spend was found, but no usable date/report period columns were mapped.",
    }


@st.cache_data(show_spinner=False)
def load_meta_sources():
    all_csvs = get_all_csv_files()

    excluded_names = {
        "shopify001.csv",
        "shopify002.csv",
        "shopify003.csv",
        "shopify004.csv",
        "trendyolreklam(reklam raporu).csv",
        "trendyol maliyet tablosu(sayfa1).csv",
        "hepsiburada maliyet tablosu(sayfa1).csv",
        "shopify maliyet tablosu(sayfa1).csv",
    }

    billing_frames = []
    perf_frames = []
    debug_rows = []

    for path in all_csvs:
        name = os.path.basename(path).lower()
        if name in excluded_names:
            continue

        billing_df, billing_debug = parse_meta_billing_report(path)
        if billing_debug:
            debug_rows.append(billing_debug)
        if not billing_df.empty:
            billing_frames.append(billing_df)
            continue

        perf_df, perf_debug = parse_meta_performance_export(path)
        if perf_debug:
            debug_rows.append(perf_debug)
        if not perf_df.empty:
            perf_frames.append(perf_df)

    billing = pd.concat(billing_frames, ignore_index=True) if billing_frames else pd.DataFrame(
        columns=["date", "source", "campaign_name", "adset_name", "ad_name", "spend", "attributed_revenue", "purchases", "file_name"]
    )
    perf = pd.concat(perf_frames, ignore_index=True) if perf_frames else pd.DataFrame(
        columns=["date", "source", "campaign_name", "adset_name", "ad_name", "spend", "attributed_revenue", "purchases", "file_name"]
    )

    if not billing.empty:
        billing = billing.drop_duplicates(
            subset=["date", "campaign_name", "adset_name", "ad_name", "spend", "attributed_revenue", "purchases"],
            keep="first",
        ).reset_index(drop=True)

    if not perf.empty:
        perf = perf.drop_duplicates(
            subset=["date", "campaign_name", "adset_name", "ad_name", "spend", "attributed_revenue", "purchases"],
            keep="first",
        ).reset_index(drop=True)
    debug = pd.DataFrame(debug_rows) if debug_rows else pd.DataFrame(
        columns=["file_name", "file_type", "status", "rows_loaded", "spend_total", "date_min", "date_max", "note"]
    )

    if not billing.empty:
        billing["date"] = pd.to_datetime(billing["date"]).dt.normalize()
    if not perf.empty:
        perf["date"] = pd.to_datetime(perf["date"]).dt.normalize()
    if not debug.empty:
        debug["date_min"] = pd.to_datetime(debug["date_min"], errors="coerce")
        debug["date_max"] = pd.to_datetime(debug["date_max"], errors="coerce")

    return billing, perf, debug


def build_meta_daily(billing: pd.DataFrame, perf: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    billing_daily = billing.groupby("date", as_index=False).agg({"spend": "sum"}) if not billing.empty else pd.DataFrame(columns=["date", "spend"])
    billing_daily = billing_daily.rename(columns={"spend": "billing_spend"})

    perf_daily = perf.groupby("date", as_index=False).agg({
        "spend": "sum",
        "attributed_revenue": "sum",
        "purchases": "sum",
    }) if not perf.empty else pd.DataFrame(columns=["date", "spend", "attributed_revenue", "purchases"])
    perf_daily = perf_daily.rename(columns={"spend": "performance_spend"})

    daily = pd.merge(billing_daily, perf_daily, on="date", how="outer")
    if daily.empty:
        return pd.DataFrame(columns=["date", "spend", "billing_spend", "performance_spend", "attributed_revenue", "purchases", "spend_source"]), "None"

    for c in ["billing_spend", "performance_spend", "attributed_revenue", "purchases"]:
        if c not in daily.columns:
            daily[c] = 0.0
        daily[c] = daily[c].fillna(0.0)

    has_billing = not billing.empty
    daily["spend"] = daily["billing_spend"] if has_billing else daily["performance_spend"]
    daily["spend_source"] = "Billing" if has_billing else "Performance Export"
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    daily = daily.sort_values("date")

    source_label = "Billing (used for spend) + Performance Export (used for attributed revenue)" if (has_billing and not perf.empty) else ("Billing" if has_billing else ("Performance Export" if not perf.empty else "None"))
    return daily, source_label


# ==============================
# Build model
# ==============================

@st.cache_data(show_spinner=False)
def build_model():
    issues = []

    costs = load_shopify_costs()
    orders, lines = load_shopify_orders()
    funnel = load_shopify_funnel()
    geo = load_shopify_geo()
    gross_monthly_export = load_shopify_gross_sales_monthly()
    meta_billing, meta_perf, meta_debug = load_meta_sources()
    meta_daily, meta_spend_source_label = build_meta_daily(meta_billing, meta_perf)

    if orders.empty:
        issues.append("No Shopify order export was found.")
    if costs.empty:
        issues.append("No Shopify cost table was found.")
    if funnel.empty:
        issues.append("No Shopify funnel export was found.")
    if geo.empty:
        issues.append("No Shopify geo export was found.")
    if gross_monthly_export.empty:
        issues.append("No Shopify gross sales monthly export was found.")
    if meta_billing.empty and meta_perf.empty:
        issues.append("No Meta file was detected. Marketing metrics will stay empty until you upload a Meta billing report or Meta Ads performance export.")

    if not lines.empty:
        lines = lines.merge(costs, on="sku_key", how="left")
        lines["matched_cost"] = lines["unit_cost"].notna() | lines["is_zero_cost_item"].fillna(False)
        lines["commission_rate"] = lines["commission_rate"].fillna(0.0)
        lines["unit_cost"] = lines["unit_cost"].fillna(0.0)
        lines["unit_ship"] = lines["unit_ship"].fillna(0.0)
        lines.loc[lines["is_zero_cost_item"].fillna(False), ["unit_cost", "unit_ship", "commission_rate"]] = 0.0
        lines["estimated_cost_total"] = (lines["unit_cost"] + lines["unit_ship"]) * lines["qty"]
        lines["estimated_commission_total"] = lines["line_revenue"] * lines["commission_rate"]
        lines["gross_profit"] = lines["line_revenue"] - lines["estimated_cost_total"] - lines["estimated_commission_total"]
        lines.loc[lines["is_cancelled"], "gross_profit"] = 0.0
    else:
        for c in ["commission_rate", "unit_cost", "unit_ship", "matched_cost", "estimated_cost_total", "estimated_commission_total", "gross_profit"]:
            lines[c] = []

    if not orders.empty:
        order_profit = lines.groupby("order_name", as_index=False).agg(gross_profit_estimated=("gross_profit", "sum"))
        orders = orders.merge(order_profit, on="order_name", how="left")
        orders["gross_profit_estimated"] = orders["gross_profit_estimated"].fillna(0.0)
    else:
        orders["gross_profit_estimated"] = []

    sales_daily = orders.groupby(orders["order_date"].dt.normalize(), as_index=False).agg({
        "net_sales": "sum",
        "order_count": "sum",
        "gross_profit_estimated": "sum",
    }) if not orders.empty else pd.DataFrame(columns=["date", "net_sales", "order_count", "gross_profit_estimated"])

    if not sales_daily.empty and "order_date" in sales_daily.columns:
        sales_daily = sales_daily.rename(columns={"order_date": "date"})

    daily_pnl = pd.merge(sales_daily, meta_daily, on="date", how="outer")
    if daily_pnl.empty:
        daily_pnl = pd.DataFrame(columns=[
            "date", "net_sales", "order_count", "gross_profit_estimated",
            "billing_spend", "performance_spend", "spend", "attributed_revenue",
            "purchases", "spend_source", "net_profit_after_ads"
        ])
    else:
        for c in ["net_sales", "order_count", "gross_profit_estimated", "billing_spend", "performance_spend", "spend", "attributed_revenue", "purchases"]:
            if c not in daily_pnl.columns:
                daily_pnl[c] = 0.0
            daily_pnl[c] = daily_pnl[c].fillna(0.0)
        if "spend_source" not in daily_pnl.columns:
            daily_pnl["spend_source"] = meta_spend_source_label
        daily_pnl["net_profit_after_ads"] = daily_pnl["gross_profit_estimated"] - daily_pnl["spend"]
        daily_pnl["date"] = pd.to_datetime(daily_pnl["date"]).dt.normalize()
        daily_pnl = daily_pnl.sort_values("date")

    return {
        "orders": orders,
        "lines": lines,
        "costs": costs,
        "funnel": funnel,
        "geo": geo,
        "gross_monthly_export": gross_monthly_export,
        "meta_billing": meta_billing,
        "meta_perf": meta_perf,
        "meta_debug": meta_debug,
        "meta_daily": meta_daily,
        "meta_spend_source_label": meta_spend_source_label,
        "daily_pnl": daily_pnl,
        "issues": issues,
    }


model = build_model()
orders = model["orders"]
lines = model["lines"]
funnel = model["funnel"]
geo = model["geo"]
gross_monthly_export = model["gross_monthly_export"]
meta_billing = model["meta_billing"]
meta_perf = model["meta_perf"]
meta_debug = model["meta_debug"]
meta_daily = model["meta_daily"]
daily_pnl = model["daily_pnl"]
issues = model["issues"]
meta_spend_source_label = model["meta_spend_source_label"]


# ==============================
# Top date controls + sidebar
# ==============================

date_min, date_max = safe_minmax([
    orders["order_date"] if "order_date" in orders.columns else pd.Series(dtype="datetime64[ns]"),
    meta_daily["date"] if "date" in meta_daily.columns else pd.Series(dtype="datetime64[ns]"),
    funnel["month"] if "month" in funnel.columns else pd.Series(dtype="datetime64[ns]"),
    gross_monthly_export["month"] if "month" in gross_monthly_export.columns else pd.Series(dtype="datetime64[ns]"),
])

with st.sidebar:
    st.header("Filters")
    low_stock_threshold = st.number_input("Low stock threshold", min_value=0, value=20, step=1)
    show_meta_debug = st.checkbox("Show Meta debug", value=False)

if "overview_start_date" not in st.session_state:
    st.session_state.overview_start_date = date_min.date()
if "overview_end_date" not in st.session_state:
    st.session_state.overview_end_date = date_max.date()
if "overview_all_time" not in st.session_state:
    st.session_state.overview_all_time = True

header_left, header_right = st.columns([3, 2])
with header_right:
    control_col1, control_col2, control_col3 = st.columns([1, 1, 0.8])
    with control_col1:
        selected_start = st.date_input(
            "Start date",
            value=st.session_state.overview_start_date,
            min_value=date_min.date(),
            max_value=date_max.date(),
            key="overview_start_date",
        )
    with control_col2:
        selected_end = st.date_input(
            "End date",
            value=st.session_state.overview_end_date,
            min_value=date_min.date(),
            max_value=date_max.date(),
            key="overview_end_date",
        )
    with control_col3:
        all_time_mode = st.toggle("All Time", value=st.session_state.overview_all_time, key="overview_all_time")

if selected_start > selected_end:
    selected_start, selected_end = selected_end, selected_start
    st.session_state.overview_start_date = selected_start
    st.session_state.overview_end_date = selected_end

use_custom_range = not all_time_mode
reporting_label = "All Time" if all_time_mode else f"Custom Range: {selected_start} → {selected_end}"


def filter_by_date(df, date_col):
    if df.empty or all_time_mode or date_col not in df.columns:
        return df.copy()
    out = df.copy()
    s = pd.Timestamp(selected_start)
    e = pd.Timestamp(selected_end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return out[(out[date_col] >= s) & (out[date_col] <= e)]


orders_f = filter_by_date(orders, "order_date")
lines_f = filter_by_date(lines, "order_date")
daily_pnl_f = filter_by_date(daily_pnl, "date")
meta_daily_f = filter_by_date(meta_daily, "date")
meta_perf_f = filter_by_date(meta_perf, "date")
meta_billing_f = filter_by_date(meta_billing, "date")

if not funnel.empty and use_custom_range:
    funnel_f = funnel[
        (funnel["month"] >= pd.Timestamp(selected_start).replace(day=1))
        & (funnel["month"] <= pd.Timestamp(selected_end))
    ].copy()
else:
    funnel_f = funnel.copy()

if not gross_monthly_export.empty and use_custom_range:
    gross_monthly_export_f = gross_monthly_export[
        (gross_monthly_export["month"] >= pd.Timestamp(selected_start).replace(day=1))
        & (gross_monthly_export["month"] <= pd.Timestamp(selected_end))
    ].copy()
else:
    gross_monthly_export_f = gross_monthly_export.copy()


# ==============================
# Metrics
# ==============================

total_sales = float(orders_f["net_sales"].sum()) if not orders_f.empty else 0.0
total_orders = int(orders_f["order_count"].sum()) if not orders_f.empty else 0
aov = total_sales / total_orders if total_orders else 0.0
gross_profit = float(orders_f["gross_profit_estimated"].sum()) if not orders_f.empty else 0.0

meta_spend = float(meta_daily_f["spend"].sum()) if not meta_daily_f.empty else 0.0
meta_billing_spend = float(meta_daily_f["billing_spend"].sum()) if ("billing_spend" in meta_daily_f.columns and not meta_daily_f.empty) else 0.0
meta_perf_spend = float(meta_daily_f["performance_spend"].sum()) if ("performance_spend" in meta_daily_f.columns and not meta_daily_f.empty) else 0.0
meta_attributed_revenue = float(meta_daily_f["attributed_revenue"].sum()) if not meta_daily_f.empty else 0.0
meta_purchases = float(meta_daily_f["purchases"].sum()) if not meta_daily_f.empty else 0.0

net_profit_after_ads = gross_profit - meta_spend
meta_roas = (meta_attributed_revenue / meta_spend) if (meta_spend and meta_attributed_revenue) else 0.0
mer = (total_sales / meta_spend) if meta_spend else 0.0

matched_rows = int(lines_f["matched_cost"].sum()) if (not lines_f.empty and "matched_cost" in lines_f.columns) else 0
unmatched_rows = int((~lines_f["matched_cost"]).sum()) if (not lines_f.empty and "matched_cost" in lines_f.columns) else 0

inventory_known = lines_f["inventory_units"].dropna() if (not lines_f.empty and "inventory_units" in lines_f.columns) else pd.Series(dtype=float)
low_stock_count = int((inventory_known <= low_stock_threshold).sum()) if not inventory_known.empty else 0
total_inventory_units = int(inventory_known.drop_duplicates().sum()) if not inventory_known.empty else 0


# ==============================
# Overview
# ==============================

c1, c2, c3, c4 = st.columns(4)
c1.metric("Net Sales", f"{total_sales:,.2f} TL")
c2.metric("Orders", f"{total_orders:,}")
c3.metric("AOV", f"{aov:,.2f} TL")
c4.metric("Estimated Gross Profit", f"{gross_profit:,.2f} TL")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Meta Spend", f"{meta_spend:,.2f} TL")
c6.metric("Net Profit After Ads", f"{net_profit_after_ads:,.2f} TL")
c7.metric("Meta ROAS", "N/A" if (meta_spend > 0 and meta_attributed_revenue == 0) else f"{meta_roas:,.2f}")
c8.metric("MER", f"{mer:,.2f}")

st.caption(f"Reporting period: {reporting_label}")
st.caption(f"Meta spend source: {meta_spend_source_label}")

if meta_spend == 0 and (not meta_billing.empty or not meta_perf.empty) and use_custom_range:
    st.info("Meta files were detected, but the selected custom date range excludes their dates. Switch to All Time or widen the date range.")


# ==============================
# Top product cards
# ==============================

if not lines_f.empty:
    product_rollup = lines_f.groupby("product_name", as_index=False).agg(
        qty_sold=("qty", "sum"),
        revenue=("line_revenue", "sum"),
        gross_profit=("gross_profit", "sum"),
        inventory_units=("inventory_units", "max"),
        sku_count=("sku_key", "nunique"),
    )
    product_rollup = product_rollup.sort_values(["gross_profit", "revenue"], ascending=[False, False])

    leader_qty = product_rollup.sort_values("qty_sold", ascending=False).head(1)
    leader_rev = product_rollup.sort_values("revenue", ascending=False).head(1)
    leader_profit = product_rollup.sort_values("gross_profit", ascending=False).head(1)

    st.subheader("Top Product Cards")
    a, b, c = st.columns(3)
    if not leader_qty.empty:
        r = leader_qty.iloc[0]
        a.metric("Best Seller by Units", r["product_name"], delta=f"{r['qty_sold']:.0f} units")
    if not leader_rev.empty:
        r = leader_rev.iloc[0]
        b.metric("Top Product by Revenue", r["product_name"], delta=f"{r['revenue']:,.2f} TL")
    if not leader_profit.empty:
        r = leader_profit.iloc[0]
        c.metric("Top Product by Profit", r["product_name"], delta=f"{r['gross_profit']:,.2f} TL")
else:
    product_rollup = pd.DataFrame()


# ==============================
# Tabs
# ==============================

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
    if not daily_pnl_f.empty:
        daily_chart = daily_pnl_f.sort_values("date").melt(
            id_vars="date",
            value_vars=["net_sales", "gross_profit_estimated", "net_profit_after_ads"],
            var_name="metric",
            value_name="value",
        )
        fig = px.line(daily_chart, x="date", y="value", color="metric", markers=True)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No dated Shopify orders or Meta data were found for the selected period.")

    st.subheader("Monthly Sales and Profit")
    if not daily_pnl_f.empty:
        monthly = daily_pnl_f.copy()
        monthly["month"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
        monthly = monthly.groupby("month", as_index=False).agg({
            "net_sales": "sum",
            "gross_profit_estimated": "sum",
            "spend": "sum",
            "attributed_revenue": "sum",
            "purchases": "sum",
            "net_profit_after_ads": "sum",
            "order_count": "sum",
        })
        fig = px.bar(monthly, x="month", y=["net_sales", "gross_profit_estimated", "net_profit_after_ads"], barmode="group")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(monthly, width="stretch")
    else:
        st.info("Monthly sales trend is not available for the selected period.")

    if not gross_monthly_export_f.empty:
        st.subheader("Shopify Gross Sales Export")
        fig = px.line(gross_monthly_export_f.sort_values("month"), x="month", y="gross_sales", markers=True)
        st.plotly_chart(fig, width="stretch")

with tab2:
    st.subheader("Top Products")
    if not product_rollup.empty:
        top10 = product_rollup.sort_values("qty_sold", ascending=False).head(10)
        fig = px.bar(top10.sort_values("qty_sold"), x="qty_sold", y="product_name", orientation="h")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(product_rollup.sort_values(["gross_profit", "qty_sold"], ascending=[False, False]), width="stretch")
    else:
        st.info("No product-level Shopify data was found.")

    st.subheader("Low Stock List")
    if not product_rollup.empty and "inventory_units" in product_rollup.columns:
        low_stock = product_rollup.dropna(subset=["inventory_units"]).copy()
        low_stock = low_stock[low_stock["inventory_units"] <= low_stock_threshold].sort_values("inventory_units")
        if not low_stock.empty:
            st.dataframe(low_stock[["product_name", "inventory_units", "qty_sold", "revenue", "gross_profit"]], width="stretch")
        else:
            st.success("No low-stock products under the selected threshold.")
    else:
        st.info("Manual inventory has not been matched to any Shopify products yet.")

    st.subheader("Inventory Snapshot")
    st.write(f"Total inventory units currently mapped: **{total_inventory_units:,}**")
    st.write(f"Products at or below low-stock threshold: **{low_stock_count:,}**")

with tab3:
    st.subheader("Funnel")
    if not funnel_f.empty:
        fchart = funnel_f.melt(
            id_vars="month",
            value_vars=["sessions", "sessions_added_to_cart", "sessions_reached_checkout", "sessions_completed_checkout"],
            var_name="metric",
            value_name="value",
        )
        fig = px.line(fchart, x="month", y="value", color="metric", markers=True)
        st.plotly_chart(fig, width="stretch")
        if "conversion_rate" in funnel_f.columns:
            fig2 = px.line(funnel_f.sort_values("month"), x="month", y="conversion_rate", markers=True)
            st.plotly_chart(fig2, width="stretch")
        st.dataframe(funnel_f.sort_values("month"), width="stretch")
    else:
        st.info("No Shopify funnel file was found.")

    st.subheader("Geo Performance")
    if not geo.empty:
        geo_top = geo.sort_values("sessions", ascending=False).head(20)
        st.dataframe(geo_top, width="stretch")
    else:
        st.info("No Shopify geo file was found.")

with tab4:
    st.subheader("Meta Ads Performance")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Meta Spend", f"{meta_spend:,.2f} TL")
    m2.metric("Meta Attributed Revenue", f"{meta_attributed_revenue:,.2f} TL")
    m3.metric("Meta Purchases", f"{meta_purchases:,.0f}")
    m4.metric("MER", f"{mer:,.2f}")

    note_chunks = []
    if not meta_billing.empty:
        note_chunks.append(f"Billing spend loaded: {meta_billing_spend:,.2f} TL")
    if not meta_perf.empty:
        note_chunks.append(f"Performance export spend loaded: {meta_perf_spend:,.2f} TL")
    if note_chunks:
        st.caption(" | ".join(note_chunks))

    if not meta_billing.empty and not meta_perf.empty:
        st.info("Both Meta billing and Meta performance files were found. To avoid double counting, the app uses billing as the spend source and uses performance exports for attributed revenue/purchases.")
    elif not meta_billing.empty and meta_perf.empty:
        st.info("Only Meta billing files were found. Spend is available, but attributed revenue and purchases will stay at 0 until you also upload a Meta Ads performance export.")
    elif meta_billing.empty and not meta_perf.empty:
        st.info("Only Meta performance exports were found. Spend comes from the export itself.")
    else:
        st.info("No Meta files are loaded for the current folder.")

    if not meta_daily_f.empty:
        fig_spend = px.line(meta_daily_f.sort_values("date"), x="date", y=["spend", "attributed_revenue"], markers=True)
        st.plotly_chart(fig_spend, width="stretch")

        if not orders_f.empty:
            order_daily = orders_f.groupby(orders_f["order_date"].dt.normalize(), as_index=False).agg({"net_sales": "sum"})
            order_daily = order_daily.rename(columns={"order_date": "date"})
            blended = (
                order_daily
                .merge(meta_daily_f[["date", "spend", "attributed_revenue"]], on="date", how="outer")
                .fillna(0.0)
                .sort_values("date")
            )
            st.subheader("Shopify Sales vs Meta")
            fig_blended = px.line(blended, x="date", y=["net_sales", "spend", "attributed_revenue"], markers=True)
            st.plotly_chart(fig_blended, width="stretch")

        st.subheader("Meta Monthly Summary")
        meta_monthly = meta_daily_f.copy()
        meta_monthly["month"] = meta_monthly["date"].dt.to_period("M").dt.to_timestamp()
        meta_monthly = meta_monthly.groupby("month", as_index=False).agg({
            "spend": "sum",
            "billing_spend": "sum",
            "performance_spend": "sum",
            "attributed_revenue": "sum",
            "purchases": "sum",
        })
        meta_monthly["roas"] = meta_monthly.apply(
            lambda r: (r["attributed_revenue"] / r["spend"]) if (r["spend"] and r["attributed_revenue"]) else 0.0, axis=1
        )
        st.dataframe(meta_monthly.sort_values("month"), width="stretch")

        st.subheader("Campaign Summary (Performance Exports)")
        if not meta_perf_f.empty:
            campaign_summary = meta_perf_f.groupby("campaign_name", as_index=False).agg({
                "spend": "sum",
                "attributed_revenue": "sum",
                "purchases": "sum",
            })
            campaign_summary["roas"] = campaign_summary.apply(
                lambda r: (r["attributed_revenue"] / r["spend"]) if (r["spend"] and r["attributed_revenue"]) else 0.0, axis=1
            )
            campaign_summary = campaign_summary.sort_values(["spend", "attributed_revenue"], ascending=[False, False])
            st.dataframe(campaign_summary, width="stretch")
        else:
            st.info("No Meta performance export is available yet, so campaign-level revenue/ROAS cannot be shown.")
    else:
        st.info("No dated Meta rows are available for the current filter.")

    if show_meta_debug:
        with st.expander("Meta Debug", expanded=True):
            st.write("Parser results by file")
            if not meta_debug.empty:
                debug_view = meta_debug.copy()
                debug_view["date_min"] = debug_view["date_min"].dt.date
                debug_view["date_max"] = debug_view["date_max"].dt.date
                st.dataframe(debug_view.sort_values(["status", "file_name"]), width="stretch")
            else:
                st.info("No Meta-related CSV files were scanned.")

            st.write("Loaded Meta file names")
            loaded_names = pd.concat([
                meta_billing[["file_name"]].drop_duplicates() if not meta_billing.empty else pd.DataFrame(columns=["file_name"]),
                meta_perf[["file_name"]].drop_duplicates() if not meta_perf.empty else pd.DataFrame(columns=["file_name"]),
            ], ignore_index=True).drop_duplicates()
            if not loaded_names.empty:
                st.dataframe(loaded_names.sort_values("file_name"), width="stretch")
            else:
                st.info("No Meta files were loaded.")

with tab5:
    st.subheader("Order Table")
    if not orders_f.empty:
        display_cols = [
            "order_name", "order_date", "financial_status", "fulfillment_status", "net_sales",
            "gross_profit_estimated", "Payment Method", "Billing City", "Source"
        ]
        display_cols = [c for c in display_cols if c in orders_f.columns]
        st.dataframe(orders_f.sort_values("order_date", ascending=False)[display_cols], width="stretch")
    else:
        st.info("No Shopify orders were found.")

with tab6:
    st.subheader("Data Quality")
    if issues:
        for msg in issues:
            st.info(msg)
    else:
        st.success("No data-quality issues were detected.")

    qa1, qa2, qa3 = st.columns(3)
    qa1.metric("Matched Cost Rows", f"{matched_rows:,}")
    qa2.metric("Unmatched Cost Rows", f"{unmatched_rows:,}")
    qa3.metric("Known Inventory Matches", f"{len(inventory_known):,}")

    if not lines_f.empty and unmatched_rows > 0:
        missing_cols = [c for c in ["product_name", "sku_key", "sku_key_original", "sku_key_manual", "sku_source"] if c in lines_f.columns]
        missing = (
            lines_f.loc[~lines_f["matched_cost"], missing_cols]
            .drop_duplicates()
            .sort_values([c for c in ["product_name", "sku_key"] if c in missing_cols])
        )
        st.write("Products without a cost match")
        st.dataframe(missing, width="stretch")

    st.write("Loaded Meta files")
    loaded_meta_files = pd.concat([
        meta_billing[["file_name"]].drop_duplicates() if not meta_billing.empty else pd.DataFrame(columns=["file_name"]),
        meta_perf[["file_name"]].drop_duplicates() if not meta_perf.empty else pd.DataFrame(columns=["file_name"]),
    ], ignore_index=True).drop_duplicates()
    if not loaded_meta_files.empty:
        st.dataframe(loaded_meta_files.sort_values("file_name"), width="stretch")
    else:
        st.info("No Meta files are currently loaded.")

    if show_meta_debug and not meta_debug.empty:
        st.write("Meta parser debug")
        debug_view = meta_debug.copy()
        debug_view["date_min"] = debug_view["date_min"].dt.date
        debug_view["date_max"] = debug_view["date_max"].dt.date
        st.dataframe(debug_view.sort_values(["status", "file_name"]), width="stretch")
