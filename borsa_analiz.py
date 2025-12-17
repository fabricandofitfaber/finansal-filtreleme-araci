import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Piyasa Analiz v10", layout="wide")
st.title("📊 Pro Hisse Senedi Analiz (Multi-Page & Getiri)")
st.markdown("**Veri Kaynağı:** Finviz (Çoklu Sayfa Taraması) | **Grafik:** Kümülatif Getiri")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- Yan Menü (Genişletilmiş Hassas Filtreler) ---
st.sidebar.header("🔍 Detaylı Filtreler")

# 0. Tarama Derinliği (YENİ - Pagination İçin)
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Tarama Limiti (Hisse Sayısı)", list(limit_opts.keys()), index=1, help="Daha fazla hisse seçmek süreyi uzatır.")

# 1. Borsa
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

# 2. Sektör
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 3. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 4. F/K (P/E) - GENİŞLETİLMİŞ
pe_opts = [
    "Any", "Low (<15)", "Profitable (<0)", "High (>50)", 
    "Under 5", "Under 10", "Under 15", "Under 20", "Under 25", "Under 30", "Under 35", "Under 40", "Under 45", "Under 50", "Under 60",
    "Over 5", "Over 10", "Over 15", "Over 20", "Over 25", "Over 30", "Over 50"
]
pe_ratio = st.sidebar.selectbox("F/K Oranı (P/E)", pe_opts, index=0)

# 5. ROE - GENİŞLETİLMİŞ
roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%", "Over 40%", "Over 50%", "Under 0% (Zarar)"]
roe = st.sidebar.selectbox("ROE (Kârlılık)", roe_opts, index=0)

# 6. Temettü
dividend = st.sidebar.selectbox("Temettü Verimi", ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)", "Over 1%", "Over 2%", "Over 3%"], index=0)

# --- Veri Çekme Motoru (Döngülü Cerrah Modu) ---
def get_finviz_pagination(limit_count, exc, sec, mc, pe, roe_val, div):
    # Temel URL Parametreleri
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

    # Genişletilmiş P/E Mapping
    pe_map = {
        "Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50",
        "Under 5": "fa_pe_u5", "Under 10": "fa_pe_u10", "Under 15": "fa_pe_u15", "Under 20": "fa_pe_u20",
        "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "Under 35": "fa_pe_u35", "Under 40": "fa_pe_u40", 
        "Under 45": "fa_pe_u45", "Under 50": "fa_pe_u50", "Under 60": "fa_pe_u60",
        "Over 5": "fa_pe_o5", "Over 10": "fa_pe_o10", "Over 15": "fa_pe_o15", "Over 20": "fa_pe_o20", 
        "Over 25": "fa_pe_o25", "Over 30": "fa_pe_o30", "Over 50": "fa_pe_o50"
    }
    if pe in pe_map: filters.append(pe_map[pe])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30", "Over 40%": "fa_roe_o40", "Over 50%": "fa_roe_o50", "Under 0% (Zarar)": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    div_map = {"Positive (>0%)": "fa_div_pos", "High (>5%)": "fa_div_o5", "Very High (>10%)": "fa_div_o10", "Over 1%": "fa_div_o1", "Over 2%": "fa_div_o2", "Over 3%": "fa_div_o3"}
    if div in div_map: filters.append(div_map[div])

    filter_str = ",".join(filters)
    
    # --- DÖNGÜ BAŞLIYOR ---
    all_dfs = []
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    # İlerleme Çubuğu
    prog_bar = st.progress(0)
    pages_to_scan = range(1, limit_count + 1, 20) # 1, 21, 41...
    
    for i, start_row in enumerate(pages_to_scan):
        current_url = f"{base_url}&r={start_row}"
        
        try:
            response = requests.get(current_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tablo Bulma (Cerrah Modu)
            target_table = None
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) > 1:
                    header_text = rows[0].get_text()
                    if 'No.' in header_text and 'Ticker' in header_text and 'Price' in header_text:
                        target_table = table
                        break
            
            if target_table:
                # Manuel Ayrıştırma
                parsed_data = []
                rows = target_table.find_all('tr')
                col_headers = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
                
                for row in rows[1:]:
                    cols = row.find_all('td')
                    cols_text = [ele.get_text(strip=True) for ele in cols]
                    if len(cols_text) >= len(col_headers):
                        parsed_data.append(cols_text[:len(col_headers)])
                
                if parsed_data:
                    temp_df = pd.DataFrame(parsed_data, columns=col_headers)
                    all_dfs.append(temp_df)
                else:
                    break # Tablo var ama içi boşsa bitir
            else:
                break # Tablo yoksa bitir
                
            # Nezaket Beklemesi (Bot korumasına takılmamak için)
            time.sleep(0.5)
            prog_bar.progress((i + 1) / len(pages_to_scan))
            
        except Exception:
            break
            
    prog_bar.empty()
    
    if all_dfs:
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
        return final_df, base_url, "Başarılı"
    return pd.DataFrame(), base_url, "Veri Bulunamadı"

# --- Ana Akış ---

if st.sidebar.button("Sonuçları Getir"):
    with st.spinner(f"İlk {scan_limit} hisse taranıyor..."):
        df_result, link, msg = get_finviz_pagination(scan_limit, exchange, sector, mcap, pe_ratio, roe, dividend)
        
        if not df_result.empty:
            st.session_state.scan_data = df_result
            st.session_state.data_url = link
        else:
            st.error(f"Sonuç yok: {msg}")

# --- Veri Gösterimi ---
if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    
    st.success(f"✅ Toplam {len(df)} Şirket Listelendi")
    st.dataframe(df, use_container_width=True)

    st.divider()
    
    # --- GRAFİK ALANI (Getiri Grafiği) ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📈 Kümülatif Getiri Grafiği (%)")
        ticker_list = df['Ticker'].tolist()
        selected_ticker = st.selectbox("Analiz İçin Hisse Seç:", ticker_list)
        
        if selected_ticker:
            try:
                # Yahoo Finance Verisi
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                
                # MultiIndex Düzeltme
                if isinstance(stock_data.columns, pd.MultiIndex):
                    stock_data.columns = stock_data.columns.get_level_values(0)
                stock_data.columns = [c.capitalize() for c in stock_data.columns]
                
                if not stock_data.empty and 'Close' in stock_data.columns:
                    # --- GETİRİ HESAPLAMA ---
                    # Başlangıç fiyatını referans alıp yüzdesel değişimi hesaplıyoruz
                    start_price = stock_data['Close'].iloc[0]
                    stock_data['Return'] = ((stock_data['Close'] - start_price) / start_price) * 100
                    
                    # Çizgi Grafik (Line Chart) daha uygundur
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=stock_data.index, 
                        y=stock_data['Return'],
                        mode='lines',
                        name='Kümülatif Getiri',
                        line=dict(color='green', width=2),
                        fill='tozeroy' # Altını doldurarak momentumu göster
                    ))
                    
                    fig.update_layout(
                        height=500, 
                        title=f"{selected_ticker} - 1 Yıllık Getiri Performansı",
                        yaxis_title="Getiri (%)",
                        xaxis_rangeslider_visible=False,
                        template="plotly_white"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"{selected_ticker} için grafik verisi eksik.")
            except Exception as e:
                st.error(f"Grafik hatası: {e}")
    
    with col2:
        if selected_ticker:
            st.subheader("ℹ️ Şirket Özeti")
            try:
                row = df[df['Ticker'] == selected_ticker].iloc[0]
                
                # Rasyoları sayıya çevirmeyi deneyelim (Formatlama için)
                try:
                    curr_price = float(row.get('Price', 0))
                except: curr_price = 0
                
                st.write(f"**Şirket:** {row['Company']}")
                st.write(f"**Sektör:** {row['Sector']}")
                st.write(f"**Endüstri:** {row['Industry']}")
                st.divider()
                st.metric("Fiyat", f"${curr_price}")
                st.metric("F/K (P/E)", row.get('P/E', '-'))
                st.metric("Değişim", row.get('Change', '-'))
                st.metric("Piyasa Değ.", row.get('Market Cap', '-'))
                
            except:
                st.write("Veri okunamadı.")

elif st.session_state.scan_data.empty:
    st.info("👈 Sol menüden 'Tarama Limiti'ni ve diğer kriterleri seçip 'Sonuçları Getir'e basınız.")
