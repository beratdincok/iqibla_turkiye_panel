
from __future__ import annotations

import os
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
st.set_page_config(page_title="SMARTEK360 | Kreatif Takip", layout="wide")

# Ana sayfadan giriş yapılmadan açılmasın.
if "logged_in" not in st.session_state or st.session_state.logged_in is not True:
    st.warning("Bu sayfaya erişmek için önce ana sayfadan giriş yapmalısın.")
    st.stop()

st.title("🎨 SMARTEK360: Kreatif Takip Paneli")
st.caption(
    "Günlük Meta / reklam kreatif raporlarını okur; ROAS, CAC, CTR, CPM, CPC, erişim, dönüşüm ve kreatif karar önerilerini raporlar."
)

DATA_DIR = Path(__file__).resolve().parent
HISTORY_FILE = DATA_DIR / "creative_history.csv"


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

    if s in {"-", "nan", "none", "null", "sürekli", "surekli"}:
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


def read_csv_flexible(file_or_path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "iso-8859-9", "cp1254", "latin1"]
    seps = [",", ";", "\t"]

    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(file_or_path, encoding=enc, sep=sep, dtype=str, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception:
                try:
                    if hasattr(file_or_path, "seek"):
                        file_or_path.seek(0)
                except Exception:
                    pass
                continue

    return pd.DataFrame()


def safe_divide(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def clean_status(value: str) -> str:
    s = normalize_text(value)
    if "active" in s or "aktif" in s:
        return "Aktif"
    if "inactive" in s or "pasif" in s:
        return "Pasif"
    return str(value).strip() if str(value).strip() else "Bilinmiyor"


# =========================================================
# NORMALIZE CREATIVE REPORT
# =========================================================
def normalize_creative_report(df: pd.DataFrame, source_file: str = "") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    campaign_col = find_col(df, ["Kampanya Adı", "Campaign name", "Campaign"])
    ad_name_col = find_col(df, ["Reklam Adı", "Ad name"])
    ad_col = find_col(df, ["Reklamlar", "Ad"])
    status_col = find_col(df, ["Yayın Durumu", "Delivery", "Status"])
    level_col = find_col(df, ["Yayın Düzeyi", "Level"])
    reach_col = find_col(df, ["Erişim", "Reach"])
    impressions_col = find_col(df, ["Gösterim", "Impressions"])
    frequency_col = find_col(df, ["Sıklık", "Frequency"])
    result_type_col = find_col(df, ["Sonuç Türü", "Result type"])
    results_col = find_col(df, ["Sonuçlar", "Results"])
    spend_col = find_col(df, ["Harcanan Tutar (TRY)", "Amount spent", "Spend", "Harcama"])
    cost_per_result_col = find_col(df, ["Sonuç başına ücret", "Cost per result"])
    start_col = find_col(df, ["Başlangıç", "Start"])
    end_col = find_col(df, ["Bitiş", "End"])
    ctr_col = find_col(df, ["CTR (Tümü)", "CTR", "Click-through rate"])
    cpm_col = find_col(df, ["CPM", "CPM (1000 Gösterim Başına Ücret)"])
    cpc_col = find_col(df, ["CPC", "CPC (Bağlantı Tıklaması Başına Ücret)"])
    conv_rate_col = find_col(df, ["Dönüşüm Oranı", "Conversion rate"])
    avg_basket_col = find_col(df, ["Ortalama Sepet", "Average basket", "AOV"])
    views_col = find_col(df, ["Görüntülemeler", "Views", "Landing page views"])
    purchases_col = find_col(df, ["Alışverişler", "Purchases", "Satın almalar"])
    avg_purchase_value_col = find_col(df, ["Ortalama alışveriş dönüşüm değeri", "Average purchase conversion value"])
    roas_col = find_col(df, ["Alışveriş Reklam Harcamasının Getirisi", "Purchase ROAS", "ROAS"])
    report_start_col = find_col(df, ["Rapor Başlangıcı", "Reporting starts", "Report start"])
    report_end_col = find_col(df, ["Rapor Sonu", "Reporting ends", "Report end"])

    out = pd.DataFrame()
    out["campaign_name"] = df[campaign_col].astype(str).replace("nan", "") if campaign_col else ""
    out["ad_name"] = df[ad_name_col].astype(str).replace("nan", "") if ad_name_col else ""
    out["creative_name"] = df[ad_col].astype(str).replace("nan", "") if ad_col else out["ad_name"]
    out["delivery_status"] = df[status_col].apply(clean_status) if status_col else "Bilinmiyor"
    out["level"] = df[level_col].astype(str).replace("nan", "") if level_col else ""
    out["reach"] = df[reach_col].apply(to_float) if reach_col else 0.0
    out["impressions"] = df[impressions_col].apply(to_float) if impressions_col else 0.0
    out["frequency"] = df[frequency_col].apply(to_float) if frequency_col else 0.0
    out["result_type"] = df[result_type_col].astype(str).replace("nan", "") if result_type_col else ""
    out["results"] = df[results_col].apply(to_float) if results_col else 0.0
    out["spend"] = df[spend_col].apply(to_float) if spend_col else 0.0
    out["cost_per_result"] = df[cost_per_result_col].apply(to_float) if cost_per_result_col else 0.0
    out["start_date"] = pd.to_datetime(df[start_col], errors="coerce") if start_col else pd.NaT
    out["end_date"] = pd.to_datetime(df[end_col], errors="coerce") if end_col else pd.NaT
    out["ctr"] = df[ctr_col].apply(to_float) if ctr_col else 0.0
    out["cpm"] = df[cpm_col].apply(to_float) if cpm_col else 0.0
    out["cpc"] = df[cpc_col].apply(to_float) if cpc_col else 0.0
    out["conversion_rate"] = df[conv_rate_col].apply(to_float) if conv_rate_col else 0.0
    out["aov"] = df[avg_basket_col].apply(to_float) if avg_basket_col else 0.0
    out["views"] = df[views_col].apply(to_float) if views_col else 0.0
    out["purchases"] = df[purchases_col].apply(to_float) if purchases_col else 0.0
    out["avg_purchase_value"] = df[avg_purchase_value_col].apply(to_float) if avg_purchase_value_col else 0.0
    out["roas"] = df[roas_col].apply(to_float) if roas_col else 0.0
    out["report_start"] = pd.to_datetime(df[report_start_col], errors="coerce") if report_start_col else pd.NaT
    out["report_end"] = pd.to_datetime(df[report_end_col], errors="coerce") if report_end_col else pd.NaT
    out["source_file"] = source_file

    # İlk satır çoğu Meta export'ta genel toplam satırı oluyor. Kampanya ve reklam boşsa çıkarıyoruz.
    out["campaign_name"] = out["campaign_name"].fillna("").astype(str)
    out["ad_name"] = out["ad_name"].fillna("").astype(str)
    out["creative_name"] = out["creative_name"].fillna("").astype(str)
    out = out[~((out["campaign_name"].str.strip() == "") & (out["ad_name"].str.strip() == "") & (out["creative_name"].str.strip() == ""))].copy()

    # Reklam adı boşsa kreatif adını kullan.
    out["creative_name"] = out["creative_name"].where(out["creative_name"].str.strip() != "", out["ad_name"])
    out["creative_name"] = out["creative_name"].where(out["creative_name"].str.strip() != "", "Bilinmeyen Kreatif")
    out["campaign_name"] = out["campaign_name"].where(out["campaign_name"].str.strip() != "", "Bilinmeyen Kampanya")

    # Gelir hesaplama: Meta ROAS varsa spend * roas; yoksa purchase * avg_purchase_value.
    out["attributed_revenue_from_roas"] = out["spend"] * out["roas"]
    out["attributed_revenue_from_purchase_value"] = out["purchases"] * out["avg_purchase_value"]
    out["attributed_revenue"] = out["attributed_revenue_from_roas"]
    out.loc[out["attributed_revenue"].eq(0), "attributed_revenue"] = out.loc[out["attributed_revenue"].eq(0), "attributed_revenue_from_purchase_value"]

    out["cac"] = out.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
    out["calculated_ctr"] = out.apply(lambda r: safe_divide(r["results"], r["impressions"]) * 100 if r["ctr"] == 0 else r["ctr"], axis=1)
    out["calculated_roas"] = out.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
    out["report_day"] = out["report_end"].fillna(out["report_start"]).dt.date
    out["report_month"] = out["report_end"].fillna(out["report_start"]).dt.to_period("M").astype(str)

    return out.reset_index(drop=True)


def classify_creative(row, min_spend: float, scale_roas: float, stop_roas: float) -> str:
    spend = float(row.get("spend", 0))
    roas = float(row.get("calculated_roas", 0))
    purchases = float(row.get("purchases", 0))
    ctr = float(row.get("ctr", 0))
    cpc = float(row.get("cpc", 0))
    frequency = float(row.get("frequency", 0))

    if spend >= min_spend and purchases == 0:
        return "Durdurmayı Değerlendir"
    if spend >= min_spend and roas < stop_roas:
        return "Durdurmayı Değerlendir"
    if roas >= scale_roas and purchases >= 3:
        return "Ölçekle"
    if ctr < 1 and spend >= min_spend:
        return "Kreatif Değiştir"
    if frequency >= 4 and roas < scale_roas:
        return "Yorgunluk Riski"
    if cpc > 10 and purchases < 2 and spend >= min_spend:
        return "Hedefleme/Kreatif Kontrol"
    return "İzle"


def action_note(row) -> str:
    status = row.get("decision", "")
    roas = float(row.get("calculated_roas", 0))
    ctr = float(row.get("ctr", 0))
    purchases = float(row.get("purchases", 0))
    spend = float(row.get("spend", 0))
    frequency = float(row.get("frequency", 0))

    if status == "Ölçekle":
        return "ROAS ve satın alma güçlü. Bütçe kademeli artırılabilir, benzer varyasyon kreatif üretilebilir."
    if status == "Durdurmayı Değerlendir":
        return "Harcama oluşmuş ama dönüşüm/verim düşük. Kreatifi durdur, teklif/hedefleme veya ürün sayfasını kontrol et."
    if status == "Kreatif Değiştir":
        return "CTR düşük. İlk 3 saniye hook, görsel/video açılışı ve metin yenilenmeli."
    if status == "Yorgunluk Riski":
        return "Frekans yükselmiş. Aynı kreatif kitleye fazla gösteriliyor olabilir; yeni varyasyon çıkar."
    if status == "Hedefleme/Kreatif Kontrol":
        return "Tıklama maliyeti yüksek ve satın alma düşük. Kitle, placement veya kreatif mesajı kontrol edilmeli."
    if purchases == 0 and spend > 0:
        return "Henüz satın alma yok. Düşük harcamadaysa izlenebilir; harcama büyürse durdur."
    if roas > 0 and roas < 2:
        return "Satış var ama kâr baskısı olabilir. Maliyet ve sepet ortalamasıyla birlikte değerlendir."
    if ctr >= 2 and purchases == 0:
        return "İlgi var ama dönüşüm yok. Landing page, fiyat, ödeme veya ürün güven unsurları kontrol edilmeli."
    return "Performans orta seviyede. Veri birikene kadar izlemeye devam et."


@st.cache_data(show_spinner=False)
def load_folder_reports() -> pd.DataFrame:
    rows = []
    skip_names = {
        "creative_history.csv",
        "creative_summary.csv",
        "creative_export.csv",
    }

    for path in sorted(DATA_DIR.glob("*.csv")):
        if path.name.lower() in skip_names:
            continue
        df = read_csv_flexible(path)
        if df.empty:
            continue
        normalized = normalize_creative_report(df, source_file=path.name)
        if not normalized.empty:
            rows.append(normalized)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def load_uploaded_reports(uploaded_files) -> pd.DataFrame:
    rows = []
    for uploaded in uploaded_files or []:
        df = read_csv_flexible(uploaded)
        if df.empty:
            continue
        normalized = normalize_creative_report(df, source_file=uploaded.name)
        if not normalized.empty:
            rows.append(normalized)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def dedupe_reports(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    dedupe_cols = [
        "campaign_name", "creative_name", "spend", "impressions", "reach",
        "purchases", "report_start", "report_end", "source_file"
    ]
    existing_cols = [c for c in dedupe_cols if c in df.columns]
    if existing_cols:
        return df.drop_duplicates(subset=existing_cols, keep="last").reset_index(drop=True)
    return df.drop_duplicates().reset_index(drop=True)


def build_rollups(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    creative = df.groupby(["campaign_name", "creative_name"], as_index=False).agg(
        delivery_status=("delivery_status", "last"),
        spend=("spend", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        results=("results", "sum"),
        purchases=("purchases", "sum"),
        attributed_revenue=("attributed_revenue", "sum"),
        views=("views", "sum"),
        frequency=("frequency", "mean"),
        ctr=("ctr", "mean"),
        cpm=("cpm", "mean"),
        cpc=("cpc", "mean"),
        conversion_rate=("conversion_rate", "mean"),
        aov=("aov", "mean"),
        first_report=("report_start", "min"),
        last_report=("report_end", "max"),
        source_file=("source_file", "last"),
    )
    creative["calculated_roas"] = creative.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
    creative["cac"] = creative.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
    creative["ctr_calc"] = creative.apply(lambda r: safe_divide(r["results"], r["impressions"]) * 100, axis=1)

    campaign = df.groupby("campaign_name", as_index=False).agg(
        spend=("spend", "sum"),
        reach=("reach", "sum"),
        impressions=("impressions", "sum"),
        results=("results", "sum"),
        purchases=("purchases", "sum"),
        attributed_revenue=("attributed_revenue", "sum"),
        creative_count=("creative_name", "nunique"),
    )
    campaign["roas"] = campaign.apply(lambda r: safe_divide(r["attributed_revenue"], r["spend"]), axis=1)
    campaign["cac"] = campaign.apply(lambda r: safe_divide(r["spend"], r["purchases"]), axis=1)
    campaign["ctr"] = campaign.apply(lambda r: safe_divide(r["results"], r["impressions"]) * 100, axis=1)

    return creative.sort_values("spend", ascending=False), campaign.sort_values("spend", ascending=False)


def ai_commentary(summary: dict, best: pd.DataFrame, weak: pd.DataFrame) -> str:
    lines = []

    lines.append("### Yapay Zeka Notu")
    if summary["spend"] == 0:
        lines.append("Henüz anlamlı reklam harcaması görünmüyor. Önce günlük kreatif raporlarını bu klasöre ekle veya panelden yükle.")
        return "\n\n".join(lines)

    if summary["roas"] >= 3:
        lines.append("Genel ROAS güçlü. Kazanan kreatiflerin varyasyonlarını üretip bütçeyi kademeli artırmak mantıklı.")
    elif summary["roas"] >= 1.5:
        lines.append("Genel ROAS orta seviyede. Kârlılık baskısı oluşmaması için düşük ROAS kreatifler ayrıştırılmalı.")
    else:
        lines.append("Genel ROAS düşük. Harcama satışa yeterince dönmüyor; kreatif, hedefleme ve teklif stratejisi kontrol edilmeli.")

    if summary["ctr"] < 1:
        lines.append("CTR düşük görünüyor. Kreatiflerin ilk saniyesi, başlık ve görsel/video hook kısmı yenilenmeli.")
    elif summary["ctr"] >= 2:
        lines.append("CTR iyi seviyede. İlgi var; dönüşüm düşükse sorun ürün sayfası, fiyat veya güven unsurlarında olabilir.")

    if summary["frequency"] >= 4:
        lines.append("Frekans yüksek. Kreatif yorgunluğu riski var; yeni kreatif varyasyonları eklenmeli.")

    if not best.empty:
        names = ", ".join(best["creative_name"].head(3).astype(str).tolist())
        lines.append(f"Ölçekleme adayı kreatifler: {names}.")

    if not weak.empty:
        names = ", ".join(weak["creative_name"].head(3).astype(str).tolist())
        lines.append(f"Kontrol/durdurma adayı kreatifler: {names}.")

    lines.append("Öncelik: ROAS yüksek kreatifleri ölçekle, harcama alıp satın alma getirmeyen kreatifleri durdur veya yenile.")
    return "\n\n".join(lines)


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("Kreatif Rapor Ayarları")

    uploaded_files = st.file_uploader(
        "Günlük kreatif raporunu yükle",
        type=["csv"],
        accept_multiple_files=True,
        help="Meta Ads / kreatif raporu CSV dosyalarını buradan yükleyebilirsin."
    )

    st.markdown("---")
    min_spend = st.number_input("Karar için minimum harcama (TL)", min_value=0.0, value=500.0, step=100.0)
    scale_roas = st.number_input("Ölçekle ROAS eşiği", min_value=0.0, value=3.0, step=0.1)
    stop_roas = st.number_input("Durdur ROAS eşiği", min_value=0.0, value=1.5, step=0.1)
    low_ctr = st.number_input("Düşük CTR eşiği (%)", min_value=0.0, value=1.0, step=0.1)
    high_frequency = st.number_input("Yüksek frekans eşiği", min_value=0.0, value=4.0, step=0.1)

    st.markdown("---")
    save_history = st.checkbox("Yüklenen raporu creative_history.csv dosyasına ekle", value=False)
    show_raw = st.checkbox("Ham veriyi göster", value=False)


# =========================================================
# LOAD DATA
# =========================================================
folder_df = load_folder_reports()
uploaded_df = load_uploaded_reports(uploaded_files)

all_df = pd.concat([folder_df, uploaded_df], ignore_index=True) if not uploaded_df.empty else folder_df.copy()
all_df = dedupe_reports(all_df)

if save_history and not uploaded_df.empty:
    try:
        if HISTORY_FILE.exists():
            old_history = read_csv_flexible(HISTORY_FILE)
            old_history_norm = normalize_creative_report(old_history, source_file=HISTORY_FILE.name) if "campaign_name" not in old_history.columns else old_history
            history = pd.concat([old_history_norm, uploaded_df], ignore_index=True)
        else:
            history = uploaded_df.copy()
        history = dedupe_reports(history)
        history.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
        st.success("Yüklenen rapor creative_history.csv dosyasına eklendi.")
    except Exception as exc:
        st.warning(f"Rapor geçmişe kaydedilemedi: {exc}")

if all_df.empty:
    st.warning("Henüz okunabilir kreatif raporu bulunamadı. CSV dosyanı yükle veya bu klasöre rapor dosyalarını ekle.")
    st.stop()

# Karar alanlarını ekle
all_df["decision"] = all_df.apply(lambda r: classify_creative(r, min_spend, scale_roas, stop_roas), axis=1)
all_df["action_note"] = all_df.apply(action_note, axis=1)

creative_rollup, campaign_rollup = build_rollups(all_df)
if not creative_rollup.empty:
    creative_rollup["decision"] = creative_rollup.apply(lambda r: classify_creative(r, min_spend, scale_roas, stop_roas), axis=1)
    creative_rollup["action_note"] = creative_rollup.apply(action_note, axis=1)

# Tarih filtresi
valid_dates = pd.to_datetime(all_df["report_end"].fillna(all_df["report_start"]), errors="coerce").dropna()
if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
else:
    min_date = pd.Timestamp.today().date()
    max_date = pd.Timestamp.today().date()

top_left, top_right = st.columns([3, 2])
with top_right:
    c1, c2, c3 = st.columns([1, 1, 0.8])
    with c1:
        start_date = st.date_input("Başlangıç", value=min_date, min_value=min_date, max_value=max_date)
    with c2:
        end_date = st.date_input("Bitiş", value=max_date, min_value=min_date, max_value=max_date)
    with c3:
        all_time = st.toggle("Tüm Zamanlar", value=True)

if not all_time:
    s = pd.Timestamp(min(start_date, end_date))
    e = pd.Timestamp(max(start_date, end_date)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    date_series = pd.to_datetime(all_df["report_end"].fillna(all_df["report_start"]), errors="coerce")
    filtered_df = all_df[(date_series >= s) & (date_series <= e)].copy()
else:
    filtered_df = all_df.copy()

creative_view, campaign_view = build_rollups(filtered_df)
if not creative_view.empty:
    creative_view["decision"] = creative_view.apply(lambda r: classify_creative(r, min_spend, scale_roas, stop_roas), axis=1)
    creative_view["action_note"] = creative_view.apply(action_note, axis=1)

# Genel özet
total_spend = float(filtered_df["spend"].sum())
total_reach = float(filtered_df["reach"].sum())
total_impressions = float(filtered_df["impressions"].sum())
total_results = float(filtered_df["results"].sum())
total_purchases = float(filtered_df["purchases"].sum())
total_revenue = float(filtered_df["attributed_revenue"].sum())
overall_roas = safe_divide(total_revenue, total_spend)
overall_cac = safe_divide(total_spend, total_purchases)
overall_ctr = safe_divide(total_results, total_impressions) * 100
avg_cpm = safe_divide(total_spend, total_impressions) * 1000
avg_cpc = safe_divide(total_spend, total_results)
avg_frequency = safe_divide(total_impressions, total_reach)

summary = {
    "spend": total_spend,
    "reach": total_reach,
    "impressions": total_impressions,
    "results": total_results,
    "purchases": total_purchases,
    "revenue": total_revenue,
    "roas": overall_roas,
    "cac": overall_cac,
    "ctr": overall_ctr,
    "cpm": avg_cpm,
    "cpc": avg_cpc,
    "frequency": avg_frequency,
}


# =========================================================
# OVERVIEW
# =========================================================
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Toplam Harcama", f"{total_spend:,.2f} TL")
m2.metric("Erişim", f"{total_reach:,.0f}")
m3.metric("Gösterim", f"{total_impressions:,.0f}")
m4.metric("Alışveriş", f"{total_purchases:,.0f}")
m5.metric("ROAS", f"{overall_roas:,.2f}")
m6.metric("CAC", f"{overall_cac:,.2f} TL")

m7, m8, m9, m10 = st.columns(4)
m7.metric("CTR", f"%{overall_ctr:,.2f}")
m8.metric("CPM", f"{avg_cpm:,.2f} TL")
m9.metric("CPC", f"{avg_cpc:,.2f} TL")
m10.metric("Reklam Geliri", f"{total_revenue:,.2f} TL")

scale_df = creative_view[creative_view["decision"].eq("Ölçekle")].sort_values(["calculated_roas", "purchases"], ascending=False) if not creative_view.empty else pd.DataFrame()
weak_df = creative_view[creative_view["decision"].isin(["Durdurmayı Değerlendir", "Kreatif Değiştir", "Yorgunluk Riski", "Hedefleme/Kreatif Kontrol"])].sort_values("spend", ascending=False) if not creative_view.empty else pd.DataFrame()

st.markdown(ai_commentary(summary, scale_df, weak_df))

# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🎯 Genel Bakış",
    "🏆 Kreatif Karnesi",
    "📣 Kampanya ROAS",
    "⚠️ Alarm ve Aksiyon",
    "📈 Erişim vs Dönüşüm",
    "🧪 Veri Kalitesi",
])

with tab1:
    st.subheader("Genel Performans")
    if not campaign_view.empty:
        fig = px.bar(
            campaign_view.sort_values("spend", ascending=False).head(15),
            x="campaign_name",
            y="spend",
            title="Kampanya Bazlı Harcama",
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            campaign_view.sort_values("roas", ascending=False).head(15),
            x="campaign_name",
            y="roas",
            title="Kampanya Bazlı ROAS",
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(
        campaign_view.style.format({
            "spend": "{:,.2f} TL",
            "reach": "{:,.0f}",
            "impressions": "{:,.0f}",
            "results": "{:,.0f}",
            "purchases": "{:,.0f}",
            "attributed_revenue": "{:,.2f} TL",
            "roas": "{:.2f}",
            "cac": "{:,.2f} TL",
            "ctr": "{:.2f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.subheader("Kreatif Karnesi")
    if creative_view.empty:
        st.info("Kreatif kırılımı bulunamadı.")
    else:
        view = creative_view.sort_values(["decision", "calculated_roas", "purchases"], ascending=[True, False, False])
        cols = [
            "campaign_name", "creative_name", "delivery_status", "spend", "reach", "impressions",
            "results", "purchases", "attributed_revenue", "calculated_roas", "cac", "ctr",
            "cpm", "cpc", "frequency", "decision", "action_note"
        ]
        st.dataframe(
            view[cols].style.format({
                "spend": "{:,.2f} TL",
                "reach": "{:,.0f}",
                "impressions": "{:,.0f}",
                "results": "{:,.0f}",
                "purchases": "{:,.0f}",
                "attributed_revenue": "{:,.2f} TL",
                "calculated_roas": "{:.2f}",
                "cac": "{:,.2f} TL",
                "ctr": "{:.2f}%",
                "cpm": "{:,.2f} TL",
                "cpc": "{:,.2f} TL",
                "frequency": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
            height=520,
        )

        st.download_button(
            "Kreatif Karnesi Excel için CSV indir",
            data=view[cols].to_csv(index=False, encoding="utf-8-sig"),
            file_name="creative_scorecard.csv",
            mime="text/csv",
        )

with tab3:
    st.subheader("Kampanya Bazlı ROAS")
    if campaign_view.empty:
        st.info("Kampanya verisi bulunamadı.")
    else:
        c = campaign_view.copy()
        c["profit_signal"] = c["attributed_revenue"] - c["spend"]
        fig = px.scatter(
            c,
            x="spend",
            y="roas",
            size="purchases",
            color="campaign_name",
            hover_data=["attributed_revenue", "cac", "ctr"],
            title="Harcama vs ROAS / Satın Alma",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            c.sort_values("roas", ascending=False).style.format({
                "spend": "{:,.2f} TL",
                "attributed_revenue": "{:,.2f} TL",
                "roas": "{:.2f}",
                "cac": "{:,.2f} TL",
                "ctr": "{:.2f}%",
                "profit_signal": "{:,.2f} TL",
            }),
            use_container_width=True,
            hide_index=True,
        )

with tab4:
    st.subheader("Alarm ve Aksiyon Listesi")
    if creative_view.empty:
        st.info("Kreatif verisi bulunamadı.")
    else:
        alarm = creative_view[creative_view["decision"].ne("İzle")].sort_values(["decision", "spend"], ascending=[True, False])
        if alarm.empty:
            st.success("Şu an kritik alarm görünmüyor. Kreatifler izleme seviyesinde.")
        else:
            st.dataframe(
                alarm[[
                    "campaign_name", "creative_name", "spend", "purchases", "calculated_roas",
                    "cac", "ctr", "frequency", "decision", "action_note"
                ]].style.format({
                    "spend": "{:,.2f} TL",
                    "purchases": "{:,.0f}",
                    "calculated_roas": "{:.2f}",
                    "cac": "{:,.2f} TL",
                    "ctr": "{:.2f}%",
                    "frequency": "{:.2f}",
                }),
                use_container_width=True,
                hide_index=True,
                height=420,
            )

        st.markdown("### Ölçekleme Adayları")
        if scale_df.empty:
            st.info("ROAS eşiğine göre net ölçekleme adayı yok.")
        else:
            st.dataframe(
                scale_df[["campaign_name", "creative_name", "spend", "purchases", "calculated_roas", "cac", "action_note"]].style.format({
                    "spend": "{:,.2f} TL",
                    "purchases": "{:,.0f}",
                    "calculated_roas": "{:.2f}",
                    "cac": "{:,.2f} TL",
                }),
                use_container_width=True,
                hide_index=True,
            )

with tab5:
    st.subheader("Erişim vs Dönüşüm")
    if creative_view.empty:
        st.info("Kreatif verisi bulunamadı.")
    else:
        fig = px.scatter(
            creative_view,
            x="reach",
            y="purchases",
            size="spend",
            color="decision",
            hover_data=["campaign_name", "creative_name", "calculated_roas", "ctr", "frequency"],
            title="Erişim vs Alışveriş",
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.scatter(
            creative_view,
            x="ctr",
            y="calculated_roas",
            size="spend",
            color="decision",
            hover_data=["campaign_name", "creative_name", "purchases", "cac"],
            title="CTR vs ROAS",
        )
        st.plotly_chart(fig2, use_container_width=True)

        high_reach_low_conversion = creative_view[
            (creative_view["reach"] >= creative_view["reach"].quantile(0.70)) &
            (creative_view["purchases"] <= creative_view["purchases"].median())
        ].sort_values("reach", ascending=False)

        st.markdown("### Yüksek Erişim / Düşük Dönüşüm")
        if high_reach_low_conversion.empty:
            st.success("Yüksek erişim alıp çok düşük dönüşümde kalan belirgin kreatif yok.")
        else:
            st.dataframe(
                high_reach_low_conversion[[
                    "campaign_name", "creative_name", "reach", "impressions", "spend",
                    "purchases", "calculated_roas", "ctr", "action_note"
                ]].style.format({
                    "reach": "{:,.0f}",
                    "impressions": "{:,.0f}",
                    "spend": "{:,.2f} TL",
                    "purchases": "{:,.0f}",
                    "calculated_roas": "{:.2f}",
                    "ctr": "{:.2f}%",
                }),
                use_container_width=True,
                hide_index=True,
            )

with tab6:
    st.subheader("Veri Kalitesi")
    st.write("Okunan dosyalar:")
    file_list = pd.DataFrame({"source_file": sorted(filtered_df["source_file"].dropna().unique().tolist())})
    st.dataframe(file_list, use_container_width=True, hide_index=True)

    quality_rows = [
        {"Kontrol": "Kampanya adı", "Durum": "Var" if filtered_df["campaign_name"].notna().any() else "Eksik"},
        {"Kontrol": "Kreatif/Reklam adı", "Durum": "Var" if filtered_df["creative_name"].notna().any() else "Eksik"},
        {"Kontrol": "Harcama", "Durum": "Var" if filtered_df["spend"].sum() > 0 else "Eksik"},
        {"Kontrol": "ROAS", "Durum": "Var" if filtered_df["roas"].sum() > 0 else "Eksik"},
        {"Kontrol": "Alışveriş", "Durum": "Var" if filtered_df["purchases"].sum() > 0 else "Eksik"},
        {"Kontrol": "Rapor tarihi", "Durum": "Var" if not valid_dates.empty else "Eksik"},
    ]
    st.dataframe(pd.DataFrame(quality_rows), use_container_width=True, hide_index=True)

    if show_raw:
        st.markdown("### Ham normalize veri")
        st.dataframe(filtered_df, use_container_width=True, height=500)

    st.markdown(
        """
        **Bu panelin beklediği ana kolonlar:**
        - Kampanya Adı
        - Reklam Adı / Reklamlar
        - Yayın Durumu
        - Erişim
        - Gösterim
        - Sonuçlar
        - Harcanan Tutar (TRY)
        - CTR, CPM, CPC
        - Alışverişler
        - Ortalama alışveriş dönüşüm değeri
        - Alışveriş Reklam Harcamasının Getirisi
        - Rapor Başlangıcı / Rapor Sonu
        """
    )
