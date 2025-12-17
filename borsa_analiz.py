import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup # İşte cerrahımız bu

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Piyasa Analiz", layout="wide")
st.title("📊 Pro Hisse Senedi Tarama ve Analiz")
st.markdown("""
**Yöntem:** BeautifulSoup ile HTML Ayrıştırma (Sadece Veri Tablosu Hedeflenir)
**Kapsam:** Tüm ABD Piyasası (Sınırlama Yok)
""")

# --- Session State (Veri Kalıcılığı) ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- Yan Menü (Filtreler) ---
st.sidebar.header("🔍 Filtreleme Kriterleri")

# 1. Borsa
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

# 2. Sektör
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 3. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 4. F/K (P/E)
pe_ratio = st.sidebar.selectbox("F/K Oranı", ["Any", "Low (<15)", "Under 20", "Under 25", "Under 30", "High (>50)", "Under 50"], index=0)

# 5. ROE
roe = st.sidebar.selectbox("ROE (Kârlılık)", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%"], index=0)

# 6. Temettü
dividend = st.sidebar.selectbox("Temettü Verimi", ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)"], index=0)

# --- Veri Çekme Fonksiyonu (BeautifulSoup ile) ---
def get_finviz_surgical(exc, sec, mc, pe, roe_val, div):
    # URL Parametrelerini Hazırla
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": filters.append(f"s={sec_map[sec]}")

    if mc == "Mega ($200bln+)": filters.append("cap_mega")
    elif mc == "Large ($10bln+)": filters.append("cap_large")
    elif mc == "Mid ($2bln+)": filters.append("cap_mid")
    elif mc == "Small ($300mln+)": filters.append("cap_small")

    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "High (>50)": "fa_pe_o50", "Under 50": "fa_pe_u50"}
    if pe in pe_map: filters.append(pe_map[pe])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    div_map = {"Positive (>0%)": "fa_div_pos", "High (>5%)": "fa_div_o5", "Very High (>10%)": "fa_div_o10"}
    if div in div_map: filters.append(div_map[div])

    filter_str = ",".join(filters)
    url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        # --- CERRAH MÜDAHALESİ BAŞLIYOR ---
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Sayfadaki tüm tabloları bul
        tables = soup.find_all('table')
        
        target_table = None
        
        # Doğru tabloyu bulmak için içeriğine bak
        for table in tables:
            # Tablo satırlarını (tr) al
            rows = table.find_all('tr')
            if len(rows) > 1:
                # İlk satırın metnini al (Header)
                header_text = rows[0].get_text()
                # Eğer başlıkta 'No.', 'Ticker' ve 'Price' varsa, aradığımız tablo budur.
                if 'No.' in header_text and 'Ticker' in header_text and 'Price' in header_text:
                    target_table = table
                    break
        
        if target_table:
            # Bulunan HTML tablosunu Pandas ile oku
            # str(target_table) diyerek sadece o tabloyu veriyoruz, menüleri değil.
            df = pd.read_html(str(target_table), header=0)[0]
            return df, url
        else:
            return pd.DataFrame(), url

    except Exception as e:
        return pd.DataFrame(), str(e)

# --- Ana Akış ---

if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Piyasa taranıyor..."):
        df_result, info = get_finviz_surgical(exchange, sector, mcap, pe_ratio, roe, dividend)
        
        if not df_result.empty:
            st.session_state.scan_data = df_result
            st.session_state.data_url = info
        else:
            st.error("Veri tablosu ayrıştırılamadı. Filtreleri gevşetip tekrar deneyin.")

# Veri Gösterimi
if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    
    # 1. Tablo Alanı
    st.success(f"✅ {len(df)} Şirket Bulundu")
    st.caption(f"Veri Kaynağı: {st.session_state.get('data_url', '')}")
    
    # Veri temizliği (Boş sütunları at)
    st.dataframe(df, use_container_width=True)

    st.divider()
    
    # 2. Grafik Alanı
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📉 Teknik Analiz (Fiyat/Getiri)")
        
        # Ticker listesini hazırla
        ticker_list = df['Ticker'].astype(str).tolist()
        selected_ticker = st.selectbox("Grafik için hisse seçiniz:", ticker_list)
        
        if selected_ticker:
            try:
                # Yahoo Finance'den grafik verisi
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                
                if not stock_data.empty:
                    # Mum Grafiği
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'],
                                    name=selected_ticker)])
                    
                    fig.update_layout(height=500, title=f"{selected_ticker} - Günlük Fiyat Hareketi", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Grafik verisi yüklenemedi.")
            except:
                st.error("Grafik hatası.")
    
    with col2:
        if selected_ticker:
            st.subheader("ℹ️ Şirket Özeti")
            # Seçilen satırı bul
            try:
                row = df[df['Ticker'] == selected_ticker].iloc[0]
                st.metric("Fiyat", str(row['Price']))
                st.metric("F/K (P/E)", str(row['P/E']))
                st.metric("Değişim", str(row['Change']))
                st.metric("Hacim", str(row['Volume']))
                st.write(f"**Sektör:** {row['Sector']}")
                st.write(f"**Endüstri:** {row['Industry']}")
                st.write(f"**Ülke:** {row['Country']}")
            except:
                st.write("Özet bilgi okunamadı.")

elif st.session_state.scan_data.empty:
    st.info("👈 Kriterleri belirleyip 'Sonuçları Getir' butonuna basınız.")
