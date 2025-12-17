import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Global Piyasa Tarama", layout="wide")
st.title("📊 Global Hisse Senedi Tarama (Akıllı Ayıklayıcı)")
st.markdown("**Veri Kaynağı:** Finviz (Tüm ABD Piyasası) | **Kapsam:** Sınırsız")

# --- Session State (Veri Kalıcılığı) ---
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = pd.DataFrame()

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

# --- Veri Çekme Fonksiyonu (Düzeltilmiş) ---
def run_finviz_screener(exc, sec, mc, pe, roe_val, div):
    # URL Parametreleri
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
        
        # --- KRİTİK DÜZELTME ---
        # Sayfadaki TÜM tabloları çekiyoruz
        all_tables = pd.read_html(response.text)
        
        target_df = pd.DataFrame()
        
        # Tablolar arasında geziniyoruz ve doğru olanı arıyoruz
        for t in all_tables:
            # Finviz'in gerçek veri tablosunda mutlaka 'No.', 'Ticker' ve 'Company' sütunları olur.
            # Menü tablosunda bunlar olmaz.
            if 'No.' in t.columns and 'Ticker' in t.columns and 'Company' in t.columns:
                target_df = t
                break
        
        if not target_df.empty:
            return target_df, url
        else:
            return pd.DataFrame(), url

    except Exception as e:
        return pd.DataFrame(), url

# --- Ana Akış ---

if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Finviz taranıyor ve menüler temizleniyor..."):
        df_result, link = run_finviz_screener(exchange, sector, mcap, pe_ratio, roe, dividend)
        st.session_state.scan_results = df_result
        st.session_state.data_url = link

# Veri Gösterimi
if not st.session_state.scan_results.empty:
    df = st.session_state.scan_results
    
    st.success(f"✅ {len(df)} Şirket Bulundu")
    st.caption(f"Kaynak URL: {st.session_state.get('data_url', '')}")
    
    # Tabloyu Temizle ve Göster
    # Finviz bazen ilk satırı tekrar başlık olarak alabilir, temizliyoruz
    if 'Ticker' in df.columns:
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        
        # --- TEKNİK ANALİZ (Grafik) ---
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("📉 Fiyat Grafiği")
            # Ticker listesini al
            ticker_list = df['Ticker'].astype(str).tolist()
            
            selected_ticker = st.selectbox("Grafik için Hisse Seç:", ticker_list)
            
            if selected_ticker:
                try:
                    # Grafik verisi Yahoo'dan gelir
                    stock_data = yf.download(selected_ticker, period="1y", progress=False)
                    
                    if not stock_data.empty:
                        fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                        open=stock_data['Open'], high=stock_data['High'],
                                        low=stock_data['Low'], close=stock_data['Close'],
                                        name=selected_ticker)])
                        fig.update_layout(height=500, title=f"{selected_ticker} - Günlük", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi yüklenemedi.")
                except:
                    st.error("Grafik oluşturulurken hata oluştu.")
        
        with col2:
            if selected_ticker:
                st.subheader("ℹ️ Özet")
                # Seçilen satırı bul
                row = df[df['Ticker'] == selected_ticker].iloc[0]
                try:
                    st.metric("Fiyat", str(row['Price']))
                    st.metric("F/K", str(row['P/E']))
                    st.metric("Sektör", str(row['Sector']))
                    st.metric("Hacim", str(row['Volume']))
                except:
                    st.write("Veri okunamadı.")
    else:
        st.error("Veri formatı bozuk. Lütfen tekrar deneyin.")

elif st.session_state.scan_results.empty:
    st.info("Sol menüden kriterleri seçip 'Sonuçları Getir' butonuna basınız.")
