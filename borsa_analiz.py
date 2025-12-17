import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Piyasa Analiz v9", layout="wide")
st.title("📊 Pro Hisse Senedi Analiz (Grafik Onarımlı)")
st.markdown("**Veri Kaynağı:** Finviz (Tablo) + Yahoo Finance (Grafik & Detay)")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- Yan Menü (Genişletilmiş Filtreler) ---
st.sidebar.header("🔍 Detaylı Filtreler")

# 1. Borsa
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

# 2. Sektör
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 3. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 4. F/K (P/E) - Değerleme
pe_ratio = st.sidebar.selectbox("F/K Oranı (P/E)", ["Any", "Low (<15)", "Under 20", "Under 25", "Under 30", "High (>50)", "Under 50"], index=0)

# 5. Fiyat / Defter Değeri (P/B) - YENİ
pb_ratio = st.sidebar.selectbox("P/B Oranı (Değerleme)", ["Any", "Low (<1)", "Under 2", "Under 3", "High (>5)"], index=0)

# 6. ROE - Kârlılık
roe = st.sidebar.selectbox("ROE (Kârlılık)", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%"], index=0)

# 7. Borç / Özkaynak - YENİ
debt_eq = st.sidebar.selectbox("Borç/Özkaynak (Risk)", ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"], index=0)

# 8. Temettü
dividend = st.sidebar.selectbox("Temettü Verimi", ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)"], index=0)

# --- Veri Çekme Motoru (Stabil Cerrah Modu) ---
def get_finviz_stable(exc, sec, mc, pe, pb, roe_val, de, div):
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

    # Rasyo Mappingleri
    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "High (>50)": "fa_pe_o50", "Under 50": "fa_pe_u50"}
    if pe in pe_map: filters.append(pe_map[pe])

    pb_map = {"Low (<1)": "fa_pb_u1", "Under 2": "fa_pb_u2", "Under 3": "fa_pb_u3", "High (>5)": "fa_pb_o5"}
    if pb in pb_map: filters.append(pb_map[pb])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

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
                if 'No.' in header_text and 'Ticker' in header_text and 'Price' in header_text:
                    target_table = table
                    break
        
        if not target_table:
            return pd.DataFrame(), url, "Tablo Bulunamadı"

        # 2. Manuel Ayrıştırma (En Güvenli Yöntem)
        parsed_data = []
        rows = target_table.find_all('tr')
        
        # Finviz Overview Sütunları
        headers = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
        
        for row in rows[1:]:
            cols = row.find_all('td')
            cols_text = [ele.get_text(strip=True) for ele in cols]
            if len(cols_text) >= len(headers):
                parsed_data.append(cols_text[:len(headers)])

        df = pd.DataFrame(parsed_data, columns=headers)
        return df, url, "Başarılı"

    except Exception as e:
        return pd.DataFrame(), url, str(e)

# --- Ana Akış ---

if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Piyasa taranıyor ve veriler işleniyor..."):
        df_result, link, msg = get_finviz_stable(exchange, sector, mcap, pe_ratio, pb_ratio, roe, debt_eq, dividend)
        
        if not df_result.empty:
            st.session_state.scan_data = df_result
            st.session_state.data_url = link
        else:
            st.error(f"Sonuç bulunamadı: {msg}")

# --- Veri Gösterimi ---
if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.dataframe(df, use_container_width=True)

    st.divider()
    
    # --- GRAFİK VE DETAY ALANI ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📉 Fiyat Grafiği")
        ticker_list = df['Ticker'].tolist()
        selected_ticker = st.selectbox("Analiz İçin Hisse Seç:", ticker_list)
        
        if selected_ticker:
            try:
                # Yahoo Finance Verisi
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                
                # --- GRAFİK DÜZELTME YAMASI ---
                # Yfinance bazen MultiIndex döndürür (Price, Ticker). Bunu düzeltiyoruz.
                if isinstance(stock_data.columns, pd.MultiIndex):
                    stock_data.columns = stock_data.columns.get_level_values(0)
                
                # Sütun isimlerini kontrol et (Büyük/Küçük harf duyarlılığı için)
                stock_data.columns = [c.capitalize() for c in stock_data.columns]
                
                if not stock_data.empty and 'Close' in stock_data.columns:
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'],
                                    name=selected_ticker)])
                    
                    fig.update_layout(height=500, title=f"{selected_ticker} - Günlük Grafik", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"{selected_ticker} için grafik verisi eksik.")
            except Exception as e:
                st.error(f"Grafik hatası: {e}")
    
    with col2:
        if selected_ticker:
            st.subheader("ℹ️ Genişletilmiş Özet")
            
            # 1. Temel Veriler (Tablodan - Hızlı)
            try:
                row = df[df['Ticker'] == selected_ticker].iloc[0]
                st.write(f"**Şirket:** {row['Company']}")
                st.write(f"**Sektör:** {row['Sector']}")
                st.metric("Fiyat", row['Price'], row['Change'])
            except:
                pass
            
            st.markdown("---")
            
            # 2. Detaylı Rasyolar (Yahoo'dan - YENİ)
            # Finviz tablosunu bozmadan ekstra rasyoları buradan çekiyoruz.
            try:
                with st.spinner("Detaylar..."):
                    ticker_obj = yf.Ticker(selected_ticker)
                    info = ticker_obj.info
                    
                    # Değerleme
                    pb = info.get('priceToBook', 'N/A')
                    pe = info.get('trailingPE', row.get('P/E', 'N/A'))
                    
                    # Kârlılık
                    roe_y = info.get('returnOnEquity', 0)
                    pm = info.get('profitMargins', 0)
                    
                    # Borçluluk
                    de = info.get('debtToEquity', 'N/A')
                    
                    c_a, c_b = st.columns(2)
                    c_a.metric("F/K (P/E)", f"{pe}")
                    c_b.metric("P/B", f"{pb}")
                    
                    if isinstance(roe_y, (int, float)):
                        st.metric("ROE", f"%{roe_y*100:.2f}")
                    if isinstance(pm, (int, float)):
                        st.metric("Net Kâr Marjı", f"%{pm*100:.2f}")
                    
                    if isinstance(de, (int, float)):
                         st.metric("Borç/Özkaynak", f"{de/100:.2f}")
                    
                    # Hedef Fiyat
                    target = info.get('targetMeanPrice', None)
                    current = info.get('currentPrice', None)
                    if target and current:
                        upside = ((target - current) / current) * 100
                        st.metric("Analist Hedefi", f"${target}", f"%{upside:.1f}")

            except Exception as e:
                st.caption("Detay veriler Yahoo'dan alınamadı.")

elif st.session_state.scan_data.empty:
    st.info("👈 Kriterleri seçip 'Sonuçları Getir' butonuna basınız.")
