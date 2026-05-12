import streamlit as st
import base64
from pathlib import Path
import mimetypes
import runpy

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="IQIBLA Türkiye",
    page_icon="🕋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =========================
# PATHS
# =========================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

LOGO_DARK = ASSETS_DIR / "logo_dark.png"
LOGO_LIGHT = ASSETS_DIR / "logo_light.png"

PRODUCT_IMAGES = sorted(
    list(ASSETS_DIR.glob("product*.png")) +
    list(ASSETS_DIR.glob("product*.jpg")) +
    list(ASSETS_DIR.glob("product*.jpeg"))
)

# =========================
# HELPERS
# =========================
def image_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""

    mime_type, _ = mimetypes.guess_type(path)
    if mime_type is None:
        mime_type = "image/png"

    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime_type};base64,{encoded}"


def get_secret_password():
    try:
        return st.secrets["APP_PASSWORD"]
    except Exception:
        return "1234"


logo_dark_uri = image_to_data_uri(LOGO_DARK)
logo_light_uri = image_to_data_uri(LOGO_LIGHT)
product_uri_list = [image_to_data_uri(img) for img in PRODUCT_IMAGES if img.exists()]

# =========================
# SESSION STATE
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "active_app" not in st.session_state:
    st.session_state.active_app = "home"


# =========================
# PRODUCT RAIN BACKGROUND
# =========================
def build_rain_items_html():
    rain_items_html = ""

    for i, img_uri in enumerate(product_uri_list):
        left_positions = [5, 18, 32, 47, 62, 76, 88]
        delays = [0, 4, 8, 12, 16, 20, 24]
        durations = [28, 34, 40, 46, 52]

        left = left_positions[i % len(left_positions)]
        delay = delays[i % len(delays)]
        duration = durations[i % len(durations)]

        rain_items_html += f"""
        <img class="rain-product"
             src="{img_uri}"
             style="left:{left}%; animation-delay:-{delay}s; animation-duration:{duration}s;">
        """

    return rain_items_html


# =========================
# CSS
# =========================
def inject_main_css():
    rain_items_html = build_rain_items_html()

    st.markdown(
        f"""
        <style>
            .stApp {{
                background:
                    radial-gradient(circle at 50% 20%, rgba(218, 165, 32, 0.18), transparent 32%),
                    linear-gradient(135deg, #050505 0%, #111111 48%, #050505 100%);
            }}

            header {{
                visibility: hidden;
            }}

            #MainMenu {{
                visibility: hidden;
            }}

            footer {{
                visibility: hidden;
            }}

            [data-testid="stSidebar"] {{
                display: none;
            }}

            .block-container {{
                padding-top: 2rem;
                padding-bottom: 2rem;
                max-width: 1450px;
            }}

            .rain-layer {{
                position: fixed;
                inset: 0;
                z-index: 0;
                overflow: hidden;
                pointer-events: none;
            }}

            .rain-product {{
                position: absolute;
                top: -280px;
                width: 170px;
                opacity: 0.14;
                filter: blur(0.2px) drop-shadow(0 0 24px rgba(212,175,55,0.25));
                animation-name: productRain;
                animation-timing-function: linear;
                animation-iteration-count: infinite;
            }}

            @keyframes productRain {{
                0% {{
                    transform: translateY(-300px) rotate(0deg) scale(0.75);
                    opacity: 0;
                }}
                12% {{
                    opacity: 0.16;
                }}
                70% {{
                    opacity: 0.13;
                }}
                100% {{
                    transform: translateY(125vh) rotate(32deg) scale(1.05);
                    opacity: 0;
                }}
            }}

            .main-card {{
                position: relative;
                z-index: 2;
                background: rgba(8, 8, 8, 0.76);
                border: 1px solid rgba(212, 175, 55, 0.35);
                box-shadow: 0 24px 85px rgba(0,0,0,0.60);
                border-radius: 34px;
                padding: 44px;
                backdrop-filter: blur(16px);
                margin-top: 38px;
            }}

            .brand-logo {{
                width: 390px;
                max-width: 100%;
                display: block;
                margin: 0 auto 18px auto;
            }}

            .brand-title {{
                text-align: center;
                color: #ffffff;
                font-size: 48px;
                font-weight: 850;
                letter-spacing: 1px;
                margin-bottom: 8px;
            }}

            .brand-subtitle {{
                text-align: center;
                color: rgba(255,255,255,0.72);
                font-size: 18px;
                margin-bottom: 32px;
            }}

            .gold-line {{
                width: 170px;
                height: 3px;
                background: linear-gradient(90deg, transparent, #d4af37, transparent);
                margin: 0 auto 32px auto;
                border-radius: 99px;
            }}

            .login-box {{
                max-width: 440px;
                margin: 0 auto;
                padding: 28px;
                border-radius: 26px;
                background: rgba(255,255,255,0.065);
                border: 1px solid rgba(255,255,255,0.12);
            }}

            .panel-title {{
                color: #ffffff;
                font-size: 25px;
                font-weight: 750;
                text-align: center;
                margin-bottom: 10px;
            }}

            .panel-desc {{
                color: rgba(255,255,255,0.65);
                text-align: center;
                font-size: 15px;
                margin-bottom: 20px;
            }}

            .platform-card {{
                background: rgba(255,255,255,0.075);
                border: 1px solid rgba(255,255,255,0.13);
                padding: 24px;
                border-radius: 28px;
                height: 190px;
                transition: all 0.25s ease;
                margin-bottom: 14px;
            }}

            .platform-card:hover {{
                transform: translateY(-5px);
                border-color: rgba(212,175,55,0.70);
                box-shadow: 0 18px 44px rgba(212,175,55,0.13);
            }}

            .platform-title {{
                color: #ffffff;
                font-size: 21px;
                font-weight: 800;
                margin-bottom: 8px;
            }}

            .platform-desc {{
                color: rgba(255,255,255,0.66);
                font-size: 14px;
                min-height: 72px;
                line-height: 1.45;
            }}

            .metric-mini {{
                color: #d4af37;
                font-size: 12px;
                letter-spacing: 0.7px;
                text-transform: uppercase;
                margin-bottom: 8px;
                font-weight: 700;
            }}

            div.stButton > button {{
                width: 100%;
                border-radius: 15px;
                border: 1px solid rgba(212,175,55,0.55);
                background: linear-gradient(135deg, #d4af37, #9d7417);
                color: #111111;
                font-weight: 850;
                padding: 0.78rem 0.7rem;
                font-size: 14px;
            }}

            div.stButton > button:hover {{
                border-color: #ffffff;
                color: #000000;
                box-shadow: 0 0 24px rgba(212,175,55,0.38);
            }}

            .footer-text {{
                position: relative;
                z-index: 2;
                text-align: center;
                color: rgba(255,255,255,0.42);
                font-size: 13px;
                margin-top: 28px;
            }}

            [data-testid="stTextInput"] input {{
                border-radius: 14px;
            }}
        </style>

        <div class="rain-layer">
            {rain_items_html}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# LOGIN PAGE
# =========================
def login_page():
    inject_main_css()

    logo_to_use = logo_dark_uri if logo_dark_uri else logo_light_uri

    st.markdown('<div class="main-card">', unsafe_allow_html=True)

    if logo_to_use:
        st.markdown(
            f'<img class="brand-logo" src="{logo_to_use}">',
            unsafe_allow_html=True
        )
    else:
        st.markdown('<div class="brand-title">IQIBLA Türkiye</div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="brand-subtitle">
            Satış, ürün, reklam, kreatif ve yapay zeka analizleri için merkezi yönetim paneli
        </div>
        <div class="gold-line"></div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="login-box">', unsafe_allow_html=True)

    st.markdown('<div class="panel-title">Yönetici Girişi</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="panel-desc">
            Panellere erişmek için şifre gir.
        </div>
        """,
        unsafe_allow_html=True
    )

    password = st.text_input("Şifre", type="password", placeholder="Şifrenizi girin")

    if st.button("Giriş Yap"):
        if password == get_secret_password():
            st.session_state.logged_in = True
            st.session_state.active_app = "home"
            st.rerun()
        else:
            st.error("Şifre hatalı. Lütfen tekrar dene.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer-text">IQIBLA Türkiye © Yönetim Paneli</div>',
        unsafe_allow_html=True
    )


# =========================
# FIND APP FILE
# =========================
def find_app_file(active_app: str):
    app_paths = {
        "shopify": [
            BASE_DIR / "pages" / "Shopify_app" / "Shopify_app.py",
            BASE_DIR / "pages" / "Shopify_app.py",
            BASE_DIR / "Shopify_app.py",
        ],
        "trendyol": [
            BASE_DIR / "pages" / "smartek_app" / "smartek_app.py",
            BASE_DIR / "pages" / "smartek_app.py",
            BASE_DIR / "smartek_app.py",
        ],
        "hepsiburada": [
            BASE_DIR / "pages" / "Hepsiburada_app" / "Hepsiburada_app.py",
            BASE_DIR / "pages" / "Hepsiburada_app.py",
            BASE_DIR / "Hepsiburada_app.py",
        ],
        "kreatif": [
            BASE_DIR / "pages" / "Kreatif_Takip" / "Kreatif_Takip.py",
            BASE_DIR / "pages" / "Kreatif_Takip.py",
            BASE_DIR / "Kreatif_Takip.py",
        ],
        "yapay_zeka": [
            BASE_DIR / "pages" / "Yapay_Zeka" / "Yapay_Zeka.py",
            BASE_DIR / "pages" / "Yapay_Zeka.py",
            BASE_DIR / "Yapay_Zeka.py",
        ],
    }

    possible_paths = app_paths.get(active_app, [])

    for path in possible_paths:
        if path.exists():
            return path, possible_paths

    return None, possible_paths


# =========================
# DEBUG IF FILE NOT FOUND
# =========================
def show_file_debug(active_app: str, possible_paths: list[Path]):
    st.error("Uygulama dosyası bulunamadı.")
    st.write("Aranan uygulama:")
    st.code(active_app)

    st.write("BASE_DIR:")
    st.code(str(BASE_DIR))

    st.write("Denenen yollar:")
    for path in possible_paths:
        st.code(str(path))

    st.write("BASE_DIR içindeki dosyalar:")
    try:
        st.write([p.name for p in BASE_DIR.iterdir()])
    except Exception as e:
        st.write(str(e))

    pages_dir = BASE_DIR / "pages"

    if pages_dir.exists():
        st.write("pages klasörü içeriği:")
        try:
            st.write([p.name for p in pages_dir.iterdir()])
        except Exception as e:
            st.write(str(e))

        try:
            for folder in pages_dir.iterdir():
                if folder.is_dir():
                    st.write(f"{folder.name} klasörü içeriği:")
                    st.write([p.name for p in folder.iterdir()])
        except Exception as e:
            st.write(str(e))
    else:
        st.warning("pages klasörü bulunamadı.")

    st.stop()


# =========================
# RUN SELECTED APP
# =========================
def run_selected_app():
    active_app = st.session_state.get("active_app", "home")

    if active_app == "home":
        dashboard_page()
        return

    target_file, possible_paths = find_app_file(active_app)

    if target_file is None:
        show_file_debug(active_app, possible_paths)

    top_left, top_right = st.columns([1, 5])
    with top_left:
        if st.button("← Ana Sayfaya Dön"):
            st.session_state.active_app = "home"
            st.rerun()

    st.caption(f"Çalıştırılan dosya: {target_file}")

    original_set_page_config = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None

    try:
        runpy.run_path(str(target_file), run_name="__main__")
    finally:
        st.set_page_config = original_set_page_config


# =========================
# DASHBOARD PAGE
# =========================
def dashboard_page():
    inject_main_css()

    logo_to_use = logo_dark_uri if logo_dark_uri else logo_light_uri

    st.markdown('<div class="main-card">', unsafe_allow_html=True)

    if logo_to_use:
        st.markdown(
            f'<img class="brand-logo" src="{logo_to_use}">',
            unsafe_allow_html=True
        )

    st.markdown(
        """
        <div class="brand-title">IQIBLA Türkiye</div>
        <div class="brand-subtitle">
            Platform seçerek ilgili satış, kreatif veya yapay zeka analiz ekranına geçiş yapabilirsin.
        </div>
        <div class="gold-line"></div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(
            """
            <div class="platform-card">
                <div class="metric-mini">E-Ticaret</div>
                <div class="platform-title">Shopify Paneli</div>
                <div class="platform-desc">
                    Shopify satış, sipariş, ürün, AOV ve kâr analizlerini görüntüle.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Shopify'a Git 🛍️"):
            st.session_state.active_app = "shopify"
            st.rerun()

    with col2:
        st.markdown(
            """
            <div class="platform-card">
                <div class="metric-mini">Marketplace</div>
                <div class="platform-title">Trendyol Paneli</div>
                <div class="platform-desc">
                    Trendyol satış, ürün performansı, maliyet ve net kâr analizlerini aç.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Trendyol'a Git 📦"):
            st.session_state.active_app = "trendyol"
            st.rerun()

    with col3:
        st.markdown(
            """
            <div class="platform-card">
                <div class="metric-mini">Marketplace</div>
                <div class="platform-title">Hepsiburada Paneli</div>
                <div class="platform-desc">
                    Hepsiburada satış raporlarını, ürünleri ve kârlılık ekranını görüntüle.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Hepsiburada'ya Git 🧾"):
            st.session_state.active_app = "hepsiburada"
            st.rerun()

    with col4:
        st.markdown(
            """
            <div class="platform-card">
                <div class="metric-mini">Creative</div>
                <div class="platform-title">Kreatif Takibi</div>
                <div class="platform-desc">
                    Günlük kreatif raporlarını, ROAS, CAC, CTR ve aksiyon önerileriyle takip et.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Kreatif Takibi 🎨"):
            st.session_state.active_app = "kreatif"
            st.rerun()

    with col5:
        st.markdown(
            """
            <div class="platform-card">
                <div class="metric-mini">AI Analysis</div>
                <div class="platform-title">Yapay Zeka Analiz</div>
                <div class="platform-desc">
                    Net ciro, ROAS, stok, AOV, CAC, LTV, tahmin ve nakit akışı yorumlarını üret.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("Yapay Zeka Analiz 🤖"):
            st.session_state.active_app = "yapay_zeka"
            st.rerun()

    st.divider()

    left, right = st.columns([3, 1])

    with left:
        st.info(
            "Bu ana sayfa merkezi giriş kapısıdır. Shopify, Trendyol, Hepsiburada, Kreatif Takibi ve Yapay Zeka Analiz panelleri buradan çalışır."
        )

    with right:
        if st.button("Çıkış Yap"):
            st.session_state.logged_in = False
            st.session_state.active_app = "home"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer-text">IQIBLA Türkiye © Merkezi Yönetim Paneli</div>',
        unsafe_allow_html=True
    )


# =========================
# ROUTER
# =========================
if st.session_state.logged_in:
    if st.session_state.active_app == "home":
        dashboard_page()
    else:
        run_selected_app()
else:
    login_page()
