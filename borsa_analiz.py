import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Hassas Filtreleme", layout="wide")
st.title("📊 Kantitatif Hisse Tarama ve Analiz")

# --- Veri Çekme Fonksiyonu (Geniş Kapsamlı) ---
@st.cache_data
def get_raw_data(sector):
    # Sektör Mapping
    sec_map = {
        "Technology": "sec_technology", "Financial": "sec_financial", 
        "Energy": "sec_energy", "Healthcare": "sec_healthcare",
        "Basic Materials": "sec_basicmaterials", "Industrials": "sec_industrials",
        "Consumer Cyclical": "sec_consumercyclical", "Real Estate": "sec_realestate"
    }
    
    # URL: Sadece sektörü seçiyoruz, rasyo filtrelerini bilerek boş bırakıyoruz (Ham veri almak için)
    # v=111: Genel Bakış (Overview) tablosunu getirir.
    base_url = f"https://finviz.com/screener.ashx?v=111&s={sec_map.get(sector, 'sec_technology')}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(base_url, headers=headers)
        # 'match' parametresini 'P/E' yaparak doğru tabloyu hedefliyoruz
        dfs = pd.read_html(response.text, match="P/E")
        df = dfs[0]
        
        # Veri Temizliği (Data Cleaning) - String'i Sayıya Çevirme
        # Finviz bazen verileri '-' olarak gösterir, bunları NaN yaparız.
        cols_to_numeric = ['P/E', 'Price', 'Change', 'Volume']
        
        # Sütun isimlerini akademik standarta getirelim
        df.rename(columns={'P/E': 'FK', 'Price': 'Fiyat', 'Change': 'Degisim'}, inplace=True)
        
        for col in ['FK', 'Fiyat']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df[['Ticker', 'Company', 'Sector', 'FK', 'Fiyat', 'Degisim', 'Volume']]
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()

# --- Yan Menü (Sidebar) ---
st.sidebar.header("🎛️ Parametre Kontrolü")

# 1. Adım: Sektör Seçimi (API'den bu gelecek)
selected_sector = st.sidebar.selectbox("Sektör Seçiniz", 
    ["Technology", "Financial", "Energy", "Healthcare", "Basic Materials", "Real Estate"])

# Veriyi Çek
df_raw = get_raw_data(selected_sector)

if not df_raw.empty:
    # 2. Adım: Python İçinde Hassas Filtreleme (Sürekli Değişkenler)
    st.sidebar.subheader("Hassas Filtreler")
    
    # F/K Filtresi (Slider ile ondalıklı seçim)
    max_pe_input = st.sidebar.number_input("Maksimum F/K Oranı", min_value=0.0, max_value=200.0, value=25.5, step=0.5)
    
    # Fiyat Filtresi
    min_price, max_price = st.sidebar.slider("Fiyat Aralığı ($)", 0.0, 1000.0, (10.0, 500.0))
    
    # --- Filtreleme Mantığı (Pandas filtering) ---
    # Akademik filtreleme burada gerçekleşiyor:
    filtered_df = df_raw[
        (df_raw['FK'] < max_pe_input) & 
        (df_raw['FK'] > 0) & # Negatif veya yok sayılanları eliyoruz
        (df_raw['Fiyat'] >= min_price) &
        (df_raw['Fiyat'] <= max_price)
    ]
    
    # --- Sonuç Ekranı ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader(f"Tarama Sonuçları ({len(filtered_df)} Şirket)")
        st.dataframe(filtered_df, use_container_width=True)

    with col2:
        st.markdown("### İstatistikler")
        st.write(f"**Ortalama F/K:** {filtered_df['FK'].mean():.2f}")
        st.write(f"**Medyan Fiyat:** ${filtered_df['Fiyat'].median():.2f}")

    # --- Grafik Bölümü ---
    st.divider()
    if not filtered_df.empty:
        ticker_select = st.selectbox("Teknik Analiz için Şirket Seç:", filtered_df['Ticker'].tolist())
        
        if ticker_select:
            with st.spinner(f'{ticker_select} verileri indiriliyor...'):
                stock_data = yf.download(ticker_select, period="6mo", progress=False)
                
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=stock_data.index,
                                open=stock_data['Open'], high=stock_data['High'],
                                low=stock_data['Low'], close=stock_data['Close'],
                                name=ticker_select))
                fig.update_layout(title=f"{ticker_select} Fiyat Grafiği", height=500)
                st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Veri çekilemedi veya tablo bulunamadı.")
