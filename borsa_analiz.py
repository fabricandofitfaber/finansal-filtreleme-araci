import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Yapılandırması ---
st.set_page_config(page_title="Gelişmiş Finansal Tarama", layout="wide")
st.title("📊 Akademik Düzey Hisse Senedi Analiz Platformu")
st.markdown("Veri Kaynağı: **Finviz** (Temel) & **Yahoo Finance** (Teknik)")

# --- Yan Menü (Genişletilmiş Filtreler) ---
st.sidebar.header("🔍 Filtreleme Kriterleri")

# 1. Sektör Seçimi (Tam Liste)
sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Piyasa Değeri (Market Cap)
mcap = st.sidebar.selectbox("Piyasa Değeri", 
    ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 3. Değerleme Rasyoları (Valuation)
pe_ratio = st.sidebar.selectbox("F/K Oranı (P/E)", 
    ["Any", "Low (<15)", "Under 20", "Under 25", "Under 30", "High (>50)"], index=0)

# 4. Kârlılık (Profitability)
roe = st.sidebar.selectbox("Özkaynak Kârlılığı (ROE)", 
    ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)"], index=0)

# 5. Finansal Sağlık (Financial Health)
debt_equity = st.sidebar.selectbox("Borç / Özkaynak", 
    ["Any", "Low (<0.1)", "Under 0.5", "Under 1"], index=0)

# 6. Temettü (Dividend)
dividend = st.sidebar.selectbox("Temettü Verimi", 
    ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)"], index=0)

# --- Veri Çekme Motoru (Scraper) ---
@st.cache_data
def get_finviz_data(sec, mc, pe, roe_val, de, div):
    filters = []
    
    # URL Parametre Haritalama (Mapping)
    # Sektör
    if sec != "Any":
        sec_map = {
            "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
            "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
            "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
            "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
            "Technology": "sec_technology", "Utilities": "sec_utilities"
        }
        filters.append(f"s={sec_map.get(sec, '')}")

    # Market Cap
    if mc == "Mega ($200bln+)": filters.append("cap_mega")
    elif mc == "Large ($10bln+)": filters.append("cap_large")
    elif mc == "Mid ($2bln+)": filters.append("cap_mid")
    elif mc == "Small ($300mln+)": filters.append("cap_small")

    # F/K
    if pe == "Low (<15)": filters.append("fa_pe_u15")
    elif pe == "Under 20": filters.append("fa_pe_u20")
    elif pe == "Under 25": filters.append("fa_pe_u25")
    elif pe == "Under 30": filters.append("fa_pe_u30")
    elif pe == "High (>50)": filters.append("fa_pe_o50")

    # ROE
    if roe == "Positive (>0%)": filters.append("fa_roe_pos")
    elif roe == "High (>15%)": filters.append("fa_roe_o15")
    elif roe == "Very High (>20%)": filters.append("fa_roe_o20")

    # Debt/Equity
    if de == "Low (<0.1)": filters.append("fa_debteq_u0.1")
    elif de == "Under 0.5": filters.append("fa_debteq_u0.5")
    elif de == "Under 1": filters.append("fa_debteq_u1")
    
    # Dividend
    if div == "Positive (>0%)": filters.append("fa_div_pos")
    elif div == "High (>5%)": filters.append("fa_div_o5")
    elif div == "Very High (>10%)": filters.append("fa_div_o10")

    # URL Oluşturma
    filter_string = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_string}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(base_url, headers=headers)
        # Match parametresini 'Ticker' yaptık, çünkü her tabloda mutlaka Ticker vardır.
        dfs = pd.read_html(response.text, match="Ticker")
        df = dfs[0]
        
        # Sütunları Temizle ve Seç
        # Finviz sütun adlarını kontrol edelim
        wanted_cols = ['Ticker', 'Company', 'Sector', 'P/E', 'Price', 'Change', 'Volume']
        # Mevcut sütunlarla kesişimini al (Hata vermemesi için)
        available_cols = [c for c in wanted_cols if c in df.columns]
        return df[available_cols], base_url
    except Exception as e:
        st.error(f"Veri çekme hatası: {str(e)}")
        return pd.DataFrame(), base_url

# --- Ana Akış ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner('Finviz veritabanı taranıyor...'):
        df_results, query_url = get_finviz_data(sector, mcap, pe_ratio, roe, debt_equity, dividend)
    
    if not df_results.empty:
        # Sonuç Sayısı
        st.success(f"Kriterlere uyan **{len(df_results)}** şirket bulundu.")
        
        # Tabloyu Göster
        st.dataframe(df_results, use_container_width=True)
        st.markdown(f"[Finviz'de Görüntüle]({query_url})") # Doğrulama linki
        
        st.markdown("---")
        
        # Grafik Bölümü
        col_graph, col_info = st.columns([3, 1])
        
        with col_graph:
            st.subheader("📈 Teknik Analiz")
            selected_ticker = st.selectbox("Grafik için Şirket Seç:", df_results['Ticker'].tolist())
            
            if selected_ticker:
                try:
                    # Yahoo Finance'den Veri
                    stock_data = yf.download(selected_ticker, period="1y", progress=False)
                    
                    if not stock_data.empty:
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=stock_data.index,
                                        open=stock_data['Open'], high=stock_data['High'],
                                        low=stock_data['Low'], close=stock_data['Close'],
                                        name=selected_ticker))
                        fig.update_layout(title=f"{selected_ticker} - Günlük Grafik", height=500)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi bulunamadı.")
                except Exception as e:
                    st.error(f"Grafik hatası: {e}")

        with col_info:
            if selected_ticker:
                st.subheader("🏢 Şirket Profili")
                try:
                    info = yf.Ticker(selected_ticker).info
                    st.write(f"**Sektör:** {info.get('sector', '-')}")
                    st.write(f"**Endüstri:** {info.get('industry', '-')}")
                    st.write(f"**Beta:** {info.get('beta', '-')}")
                    
                    # Hedef Fiyat Analizi
                    current = info.get('currentPrice', 0)
                    target = info.get('targetMeanPrice', 0)
                    if current and target:
                        potansiyel = ((target - current) / current) * 100
                        color = "green" if potansiyel > 0 else "red"
                        st.markdown(f"**Analist Hedefi:** ${target}")
                        st.markdown(f"**Potansiyel:** :{color}[%{potansiyel:.2f}]")
                        
                except:
                    st.write("Detay bilgi alınamadı.")

    else:
        st.error("⚠️ Sonuç bulunamadı.")
        st.info("İpucu: Finviz bazen aşırı filtrelemede sonuç vermeyebilir veya bot korumasına takılmış olabilir. 'Any' seçeneklerini artırıp tekrar deneyin.")
else:
    st.info("👈 Lütfen sol menüden kriterleri seçip 'Sonuçları Getir' butonuna basın.")
