import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Global Piyasa Tarama", layout="wide")
st.title("📊 Global Hisse Senedi Tarama ve Analiz")
st.markdown("**Veri Kaynağı:** Finviz (Tüm ABD Borsaları) | **Kapsam:** Sınırsız")

# --- Session State (Grafik seçince tablonun kaybolmaması için şart) ---
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = pd.DataFrame()

# --- Yan Menü Filtreleri (Finviz URL Mantığı) ---
st.sidebar.header("🔍 Filtreleme Kriterleri")

# 1. Borsa
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

# 2. Sektör
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 3. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 4. F/K (P/E) - Finviz'in izin verdiği aralıklar
pe_ratio = st.sidebar.selectbox("F/K Oranı", ["Any", "Low (<15)", "Under 20", "Under 25", "Under 30", "High (>50)", "Under 50"], index=0)

# 5. ROE
roe = st.sidebar.selectbox("ROE (Kârlılık)", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%"], index=0)

# 6. Temettü
dividend = st.sidebar.selectbox("Temettü Verimi", ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)"], index=0)

# --- Veri Çekme Fonksiyonu ---
def run_finviz_screener(exc, sec, mc, pe, roe_val, div):
    # URL Parametrelerini oluştur
    filters = []
    
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    
    # Sektör Haritası
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": filters.append(f"s={sec_map[sec]}")

    # Market Cap
    if mc == "Mega ($200bln+)": filters.append("cap_mega")
    elif mc == "Large ($10bln+)": filters.append("cap_large")
    elif mc == "Mid ($2bln+)": filters.append("cap_mid")
    elif mc == "Small ($300mln+)": filters.append("cap_small")

    # F/K
    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "High (>50)": "fa_pe_o50", "Under 50": "fa_pe_u50"}
    if pe in pe_map: filters.append(pe_map[pe])

    # ROE
    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    # Temettü
    div_map = {"Positive (>0%)": "fa_div_pos", "High (>5%)": "fa_div_o5", "Very High (>10%)": "fa_div_o10"}
    if div in div_map: filters.append(div_map[div])

    filter_str = ",".join(filters)
    url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}"
    
    # Header (Tarayıcı Taklidi - Bot Koruması İçin Şart)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Match 'Ticker' diyerek menü yazılarını değil, sadece ticker içeren tabloyu alıyoruz.
        dfs = pd.read_html(response.text, match="Ticker", header=0)
        df = dfs[0]
        return df, url
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame(), url

# --- Ana Akış ---

# Butona basınca veriyi çekip session_state'e atıyoruz.
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Finviz veritabanı taranıyor..."):
        df_result, link = run_finviz_screener(exchange, sector, mcap, pe_ratio, roe, dividend)
        st.session_state.scan_results = df_result
        st.session_state.data_url = link

# Veri varsa göster (Grafik seçimi yapsan bile burası çalışır)
if not st.session_state.scan_results.empty:
    df = st.session_state.scan_results
    
    st.success(f"Bulunan Şirket Sayısı: {len(df)}")
    st.caption(f"Veri Kaynağı: {st.session_state.get('data_url', '')}")
    
    # Ana Tablo
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    # --- TEKNİK ANALİZ KISMI (Burada senin istediğin o grafik var) ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📈 Fiyat Grafiği")
        # Listeyi string'e çevirip NaN'ları temizliyoruz
        ticker_options = df['Ticker'].astype(str).tolist()
        
        selected_ticker = st.selectbox("Grafik Çizmek İçin Hisse Seç:", ticker_options)
        
        if selected_ticker:
            try:
                # Yahoo Finance'den grafik verisi çek
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                
                if not stock_data.empty:
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'],
                                    name=selected_ticker)])
                    fig.update_layout(height=500, title=f"{selected_ticker} - Günlük Grafik", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Grafik verisi yüklenemedi.")
            except Exception as e:
                st.error(f"Grafik hatası: {e}")

    with col2:
        if selected_ticker:
            st.subheader("📋 Şirket Kartı")
            try:
                # Temel verileri tablodan alıyoruz (Hızlı olsun diye)
                row = df[df['Ticker'] == selected_ticker].iloc[0]
                
                st.metric("Fiyat", str(row.get('Price', '-')))
                st.metric("F/K (P/E)", str(row.get('P/E', '-')))
                st.metric("Değişim", str(row.get('Change', '-')))
                st.metric("Hacim", str(row.get('Volume', '-')))
                st.write(f"**Sektör:** {row.get('Sector', '-')}")
                st.write(f"**Endüstri:** {row.get('Industry', '-')}")
            except:
                st.write("Bilgi alınamadı.")

elif st.session_state.scan_results.empty:
    st.info("👈 Lütfen kriterleri seçip 'Sonuçları Getir' butonuna basın.")
