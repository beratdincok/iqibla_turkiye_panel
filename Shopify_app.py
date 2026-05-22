
from pathlib import Path
import runpy
import sys

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="SMARTEK360 E-Ticaret Panel", layout="wide")

st.markdown("""
<style>
.stApp { background: linear-gradient(135deg, #050505 0%, #151515 100%); }
.block-container { max-width: 1400px; padding-top: 2rem; }
[data-testid="stMetric"] { background: rgba(255,255,255,0.06); border: 1px solid rgba(212,175,55,0.25); border-radius: 16px; padding: 14px; }
div.stButton > button { width: 100%; border-radius: 14px; font-weight: 800; background: linear-gradient(135deg,#d4af37,#9d7417); color: #111; border: 0; }
</style>
""", unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = True
if "active_app" not in st.session_state:
    st.session_state.active_app = "home"

def go(app):
    st.session_state.active_app = app
    st.rerun()

def run_app(path: Path):
    if not path.exists():
        st.error(f"Uygulama dosyası bulunamadı: {path}")
        st.stop()
    runpy.run_path(str(path), run_name="__main__")

if st.session_state.active_app == "home":
    st.title("SMARTEK360 E-Ticaret Analiz Paneli")
    st.caption("Shopify + Trendyol + Hepsiburada + Kreatif/Meta + Yapay Zeka. Her panel kendi panel_summary.csv dosyasını üretir; Yapay Zeka aynı KPI değerlerini toplar.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Shopify")
        st.write("Sipariş, maliyet, Meta harcaması, manuel giriş.")
        if st.button("Shopify Paneli"):
            go("shopify")
    with c2:
        st.subheader("Trendyol")
        st.write("Tedarikçi siparişleri, maliyet, reklam, manuel giriş.")
        if st.button("Trendyol Paneli"):
            go("trendyol")
    with c3:
        st.subheader("Hepsiburada")
        st.write("Ürün/mağaza raporları, maliyet, manuel giriş.")
        if st.button("Hepsiburada Paneli"):
            go("hepsiburada")

    c4, c5 = st.columns(2)
    with c4:
        st.subheader("Kreatif / Meta")
        st.write("Kreatif raporları ve reklam performansı.")
        if st.button("Kreatif Takibi"):
            go("kreatif")
    with c5:
        st.subheader("Yapay Zeka")
        st.write("Panellerden gelen KPI değerlerini tek raporda toplar.")
        if st.button("Yapay Zeka Analiz"):
            go("ai")

    st.divider()
    st.info("Günlük manuel giriş: her panelde tarih, mağaza, ürün adedi, sipariş adedi, ciro ve reklam harcaması girebilirsin. Bu değerler otomatik hesaplamalara dahil edilir.")

else:
    if st.button("← Ana Sayfa"):
        go("home")

    mapping = {
        "shopify": BASE_DIR / "pages" / "Shopify_app" / "Shopify_app.py",
        "trendyol": BASE_DIR / "pages" / "smartek_app" / "smartek_app.py",
        "hepsiburada": BASE_DIR / "pages" / "Hepsiburada_app" / "Hepsiburada_app.py",
        "kreatif": BASE_DIR / "pages" / "Kreatif_Takip" / "Kreatif_Takip.py",
        "ai": BASE_DIR / "pages" / "Yapay_Zeka" / "Yapay_Zeka.py",
    }
    run_app(mapping[st.session_state.active_app])
