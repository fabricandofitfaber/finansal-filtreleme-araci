import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Piyasa Analiz", layout="wide")
st.title("📊 Pro Hisse Senedi Tarama (Manuel Ayrıştırma)")
st.markdown("**Durum:** Otomatik okuma kapatıldı. Veriler HTML etiketlerinden tek tek ayıklanıyor.")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- Yan Menü ---
st.sidebar.header("🔍 Filtreler")

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

# --- Manuel Veri Çekme Motoru ---
def get_finviz_manual(exc, sec, mc, pe, roe_val, div):
    # URL Hazırlığı (Aynı mantık)
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
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Doğru Tabloyu Bul
        target_table = None
        all_tables = soup.find_all('table')
        
        for table in all_tables:
            rows = table.find_all('tr')
            if len(rows) > 1:
                header_text = rows[0].get_text()
                # Başlık kontrolü
                if 'No.' in header_text and 'Ticker' in header_text and 'Price' in header_text:
                    target_table = table
                    break
        
        if not target_table:
            return pd.DataFrame(), url, "Tablo Bulunamadı"

        # 2. MANUEL SATIR AYRIŞTIRMA (Pandas kullanmadan)
        parsed_data = []
        rows = target_table.find_all('tr')
        
        # İlk satır başlık olduğu için 1'den başlıyoruz
        # Başlıkları elle tanımlıyoruz ki kayma olmasın
        headers = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
        
        for row in rows[1:]:
            cols = row.find_all('td')
            # Her hücrenin sadece metin kısmını al ve boşlukları temizle
            cols_text = [ele.get_text(strip=True) for ele in cols]
            
            if len(cols_text) >= len(headers): # Yeterli sütun varsa al
                parsed_data.append(cols_text[:len(headers)]) # Sadece ihtiyacımız olan sütunları al

        df = pd.DataFrame(parsed_data, columns=headers)
        return df, url, "Başarılı"

    except Exception as e:
        return pd.DataFrame(), url, str(e)

# --- Ana Akış ---

if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Veriler hücre hücre işleniyor..."):
        df_result, link, msg = get_finviz_manual(exchange, sector, mcap, pe_ratio, roe, dividend)
        
        if not df_result.empty:
            st.session_state.scan_data = df_result
            st.session_state.data_url = link
        else:
            st.error(f"Hata: {msg}")

# Veri Gösterimi
if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    
    st.success(f"✅ {len(df)} Şirket Ayrıştırıldı")
    st.dataframe(df, use_container_width=True)

    st.divider()
    
    # GRAFİK BÖLÜMÜ
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📉 Fiyat Grafiği")
        ticker_list = df['Ticker'].tolist()
        selected_ticker = st.selectbox("Hisse Seç:", ticker_list)
        
        if selected_ticker:
            try:
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                if not stock_data.empty:
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'],
                                    name=selected_ticker)])
                    fig.update_layout(height=500, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Grafik verisi yok.")
            except:
                st.error("Grafik hatası.")
    
    with col2:
        if selected_ticker:
            st.subheader("Özet")
            # Seçilen satırı bul
            row = df[df['Ticker'] == selected_ticker].iloc[0]
            st.metric("Fiyat", row['Price'])
            st.metric("F/K", row['P/E'])
            st.metric("Değişim", row['Change'])
            st.write(f"**Sektör:** {row['Sector']}")
            st.write(f"**Ülke:** {row['Country']}")

elif st.session_state.scan_data.empty:
    st.info("👈 Kriterleri seçip 'Sonuçları Getir' butonuna basınız.")
