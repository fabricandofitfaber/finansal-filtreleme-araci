import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Gelişmiş Hisse Tarama", layout="wide")
st.title("📊 Akademik Hisse Senedi Analiz ve Tarama Aracı")
st.markdown("""
**Metodolojik Not:** Kârlılık oranları (F/K, ROE) **Son 12 Aylık (TTM)** veriye dayanırken,
bilanço oranları (Borç/Özkaynak) **Son Çeyrek (MRQ)** verisini esas alır.
""")

# --- Yan Menü Filtreleri ---
st.sidebar.header("🔍 Filtreleme Kriterleri")

# Sektör Seçimi (Genişletilmiş ve Opsiyonel)
sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical",
    "Consumer Defensive", "Energy", "Financial", "Healthcare",
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör (Opsiyonel)", sector_list, index=0)

# Finansal Rasyolar
pe_ratio = st.sidebar.selectbox("F/K Oranı (Değerleme)", ["Any", "Under 15", "Under 20", "Under 25", "Over 50"], index=0)
roe = st.sidebar.selectbox("ROE (Kârlılık)", ["Any", "Over 15%", "Over 20%", "Positive"], index=0)
debt_equity = st.sidebar.selectbox("Borç/Özkaynak (Risk)", ["Any", "Under 0.5", "Under 1", "Low (<0.1)"], index=0)

# --- Veri Çekme Motoru ---
@st.cache_data
def get_finviz_screener(pe, roe_val, de, sec):
    filters = []

    # Sektör Mapping (Eğer "Any" değilse ekle)
    if sec != "Any":
        sec_map = {
            "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
            "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
            "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
            "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
            "Technology": "sec_technology", "Utilities": "sec_utilities"
        }
        if sec in sec_map: filters.append(f"s={sec_map[sec]}")

    # Rasyo Mapping
    if pe == "Under 15": filters.append("fa_pe_u15")
    elif pe == "Under 20": filters.append("fa_pe_u20")
    elif pe == "Under 25": filters.append("fa_pe_u25")
    elif pe == "Over 50": filters.append("fa_pe_o50")

    if roe == "Over 15%": filters.append("fa_roe_o15")
    elif roe == "Over 20%": filters.append("fa_roe_o20")
    elif roe == "Positive": filters.append("fa_roe_pos")

    if de == "Under 0.5": filters.append("fa_debteq_u0.5")
    elif de == "Under 1": filters.append("fa_debteq_u1")
    elif de == "Low (<0.1)": filters.append("fa_debteq_u0.1")

    filter_string = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_string}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(base_url, headers=headers)
        # HTML Tablo Okuma (lxml engine ile)
        dfs = pd.read_html(response.text, match="Ticker")
        df = dfs[0] # Genellikle eşleşen ilk tablo doğrudur
        # Sütun Temizliği
        cols_to_keep = ['Ticker', 'Company', 'Sector', 'P/E', 'Price', 'Change', 'Volume']
        return df[cols_to_keep], base_url
    except Exception as e:
        return pd.DataFrame(), base_url

# --- Uygulama Akışı ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner('Piyasa taranıyor, lütfen bekleyin...'):
        df_results, url = get_finviz_screener(pe_ratio, roe, debt_equity, sector)

    if not df_results.empty:
        st.success(f"Toplam {len(df_results)} şirket bulundu.")
        st.dataframe(df_results, use_container_width=True)
        st.caption(f"Veri Kaynağı URL: {url}")

        st.divider()
        st.subheader("📈 Teknik Analiz Paneli")

        selected_ticker = st.selectbox("Grafik Çizilecek Hisse:", df_results['Ticker'].tolist())

        if selected_ticker:
            try:
                # Yahoo Finance Verisi
                data = yf.download(selected_ticker, period="1y", progress=False)

                # Grafik
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=data.index,
                                open=data['Open'], high=data['High'],
                                low=data['Low'], close=data['Close'],
                                name=selected_ticker))
                fig.update_layout(title=f"{selected_ticker} - Son 1 Yıl", yaxis_title="Fiyat (USD)", height=500)
                st.plotly_chart(fig, use_container_width=True)

                # Ek Bilgi Kartları
                info = yf.Ticker(selected_ticker).info
                c1, c2, c3 = st.columns(3)
                c1.metric("Endüstri", info.get('industry', '-'))
                c2.metric("Çalışan Sayısı", info.get('fullTimeEmployees', '-'))
                c3.metric("Öneri", info.get('recommendationKey', '-').upper())

            except Exception as e:
                st.error(f"Grafik verisi alınırken hata oluştu: {e}")
    else:
        st.warning("Kriterlere uygun sonuç bulunamadı. Filtreleri gevşetmeyi deneyin.")
