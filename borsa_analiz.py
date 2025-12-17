import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Yapılandırması ---
st.set_page_config(page_title="Gelişmiş Finansal Tarama", layout="wide")
st.title("📊 Akademik Düzey Hisse Senedi Analiz Platformu")
st.markdown("Veri Kaynağı: **Finviz** (Temel) & **Yahoo Finance** (Teknik)")

# --- Yan Menü (Filtreler) ---
st.sidebar.header("🔍 Filtreleme Kriterleri")

sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=10) # Varsayılan: Teknoloji

pe_ratio = st.sidebar.selectbox("F/K Oranı (P/E)", ["Any", "Low (<15)", "Under 20", "Under 25", "High (>50)"], index=0)
roe = st.sidebar.selectbox("Özkaynak Kârlılığı (ROE)", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)"], index=0)

# --- Akıllı Veri Çekme Motoru ---
@st.cache_data
def get_finviz_data(sec, pe, roe_val):
    filters = []
    
    # Sektör Mapping
    if sec != "Any":
        sec_map = {
            "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
            "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
            "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
            "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
            "Technology": "sec_technology", "Utilities": "sec_utilities"
        }
        filters.append(f"s={sec_map.get(sec, '')}")

    # Rasyo Mapping
    if pe == "Low (<15)": filters.append("fa_pe_u15")
    elif pe == "Under 20": filters.append("fa_pe_u20")
    elif pe == "Under 25": filters.append("fa_pe_u25")
    elif pe == "High (>50)": filters.append("fa_pe_o50")
    
    if roe_val == "Positive (>0%)": filters.append("fa_roe_pos")
    elif roe_val == "High (>15%)": filters.append("fa_roe_o15")
    elif roe_val == "Very High (>20%)": filters.append("fa_roe_o20")

    filter_string = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_string}"
    
    # Header Spoofing (Tarayıcı gibi davran)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    try:
        response = requests.get(base_url, headers=headers)
        # Tüm tabloları çekiyoruz
        tables = pd.read_html(response.text)
        
        target_df = pd.DataFrame()
        
        # --- TABLO SEÇME ALGORİTMASI ---
        # Sayfadaki her bir tabloyu kontrol ediyoruz
        for t in tables:
            # 1. Kontrol: Sütun isimlerinde 'Ticker' ve 'Price' var mı?
            # 2. Kontrol: Tablo boş değil mi?
            # 3. Kontrol: İlk satır "Reset Filters" gibi bir menü yazısı DEĞİL mi?
            if 'Ticker' in t.columns and 'Price' in t.columns and len(t) > 1:
                # Verinin gerçek olup olmadığını anlamak için Ticker sütununa bakıyoruz
                first_ticker = str(t.iloc[0]['Ticker'])
                if first_ticker not in ['nan', 'None', 'Ticker']:
                    target_df = t
                    break # Doğru tabloyu bulduk, döngüden çık
        
        if not target_df.empty:
            # Veri Temizliği
            target_df = target_df[['Ticker', 'Company', 'Sector', 'P/E', 'Price', 'Change', 'Volume']]
            target_df = target_df.dropna(subset=['Ticker']) # Ticker'ı boş olan satırları sil
            return target_df, base_url
        else:
            return pd.DataFrame(), base_url
            
    except Exception as e:
        return pd.DataFrame(), str(e)

# --- Ana Akış ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner('Veriler analiz ediliyor...'):
        df_results, info = get_finviz_data(sector, pe_ratio, roe)
    
    if not df_results.empty:
        st.success(f"Analiz Tamamlandı: **{len(df_results)}** şirket listelendi.")
        st.dataframe(df_results, use_container_width=True)
        
        st.divider()
        st.subheader("📈 Teknik Grafik")
        
        # Seçim Kutusu (Ticker listesi kesinlikle string ve dolu)
        ticker_list = df_results['Ticker'].astype(str).tolist()
        selected_ticker = st.selectbox("Detaylı inceleme için şirket seçiniz:", ticker_list)
        
        if selected_ticker and selected_ticker != 'nan':
            try:
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                if not stock_data.empty:
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'])])
                    fig.update_layout(title=f"{selected_ticker} Fiyat Hareketi", height=500)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Yahoo Finance verisi alınamadı.")
            except Exception as e:
                st.error(f"Grafik oluşturulamadı: {e}")
    else:
        st.error("Veri çekilemedi veya kriterlere uygun sonuç yok.")
        if info: st.caption(f"Debug Bilgisi: {info[:200]}...") # Hata mesajını kısaca göster
else:
    st.info("Sol menüden kriterleri belirleyip butona basınız.")
