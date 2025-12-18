import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Hibrit Analiz v19", layout="wide")
st.title("📊 Akademik Hibrit Analiz (Finviz + Yahoo)")
st.markdown("""
**Yöntem:** Geniş tarama **Finviz** üzerinden yapılır (Tüm Piyasa).
**Detay:** Seçilen hissenin derinlemesine analizi (EV/EBITDA, Risk) **Yahoo Finance** üzerinden anlık çekilir.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (Finviz Filtreleri) ---
st.sidebar.header("🔍 1. Piyasa Taraması (Finviz)")

# Tarama Derinliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Tarama Limiti (Hisse Sayısı)", list(limit_opts.keys()), index=2)

# Filtreler
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

pe_opts = ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Under 50", "Over 20"]
pe_ratio = st.sidebar.selectbox("F/K (Değerleme)", pe_opts, index=0)

roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kârlılık)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak", debt_opts, index=0)

# --- FİNVİZ MOTORU (Cerrah Modu - v16 Tabanlı) ---
def get_finviz_data(limit_count, exc, sec, pe, roe_val, de):
    filters = []
    
    # URL Parametre Haritalama
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50", "Under 20": "fa_pe_u20", "Under 30": "fa_pe_u30", "Under 50": "fa_pe_u50", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Under 0%": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

    filter_str = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    all_dfs = []
    prog_bar = st.progress(0)
    pages = range(1, limit_count + 1, 20)
    
    for i, start_row in enumerate(pages):
        try:
            r = requests.get(f"{base_url}&r={start_row}", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            target = None
            
            # Tabloyu Bul (Cerrah Modu)
            for t in soup.find_all('table'):
                rows = t.find_all('tr')
                if len(rows) > 1:
                    txt = rows[0].get_text()
                    if 'No.' in txt and 'Ticker' in txt and 'Price' in txt:
                        target = t
                        break
            
            if target:
                data = []
                # Overview Sütunları
                head = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
                for row in target.find_all('tr')[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cols) >= 11: data.append(cols[:11])
                if data: all_dfs.append(pd.DataFrame(data, columns=head))
            else:
                break
            
            time.sleep(0.5) # Anti-ban beklemesi
            prog_bar.progress((i + 1) / len(pages))
        except: break
            
    prog_bar.empty()
    if all_dfs:
        return pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True), base_url
    return pd.DataFrame(), base_url

# --- YAHOO DETAY MOTORU (Lazy Loading) ---
def get_yahoo_details(ticker):
    """Sadece seçilen hisse için detay çeker"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="1y")
        
        details = {
            'EV/EBITDA': info.get('enterpriseToEbitda', 'N/A'),
            'P/B': info.get('priceToBook', 'N/A'),
            'FCF': info.get('freeCashflow', 'N/A'),
            'Total Debt': info.get('totalDebt', 'N/A'),
            'Quick Ratio': info.get('quickRatio', 'N/A'),
            'Short Ratio': info.get('shortRatio', 'N/A'),
            'Target Price': info.get('targetMeanPrice', 'N/A')
        }
        return details, hist
    except:
        return None, pd.DataFrame()

# --- SİNYAL ÇELİŞKİ ANALİZİ ---
def analyze_conflict(finviz_row, yahoo_details, hist):
    comments = []
    
    # Veri Dönüşümleri
    try: pe = float(str(finviz_row['P/E']).replace('-','0'))
    except: pe = 0
    
    ev_ebitda = yahoo_details.get('EV/EBITDA', 'N/A')
    
    # 1. DEĞERLEME ÇELİŞKİSİ (Value Trap)
    if isinstance(ev_ebitda, (int, float)):
        if pe > 0 and pe < 10 and ev_ebitda > 15:
            comments.append("🚨 **Value Trap Uyarısı:** F/K oranı çok düşük (<10) ancak EV/EBITDA yüksek (>15). Bu, şirketin borç yükünün F/K'yı olduğundan düşük gösterdiğini işaret edebilir.")
        elif pe < 15 and ev_ebitda < 8:
            comments.append("✅ **Gerçek Değer:** Hem F/K hem EV/EBITDA düşük. Şirket bilançosuyla birlikte gerçekten ucuz.")
            
    # 2. TEKNİK ÇELİŞKİ
    if not hist.empty:
        curr = hist['Close'].iloc[-1]
        ma200 = hist['Close'].rolling(200).mean().iloc[-1]
        
        if pe < 15 and curr < ma200:
            comments.append("⚠️ **Momentum Uyumsuzluğu:** Şirket temel olarak ucuz olsa da, fiyat 200 günlük ortalamanın altında (Düşüş Trendi). Piyasa henüz bu ucuzluğu fiyatlamamış.")
            
    # 3. NAKİT GÜCÜ
    fcf = yahoo_details.get('FCF', 'N/A')
    if isinstance(fcf, (int, float)) and fcf > 0:
        comments.append("💰 **Nakit Makinesi:** Şirket pozitif Serbest Nakit Akışı (FCF) üretiyor. Temettü veya geri alım potansiyeli var.")
        
    return comments

# --- ANA AKIŞ ---
if st.sidebar.button("Taramayı Başlat"):
    with st.spinner("Finviz tüm piyasa taranıyor..."):
        df, url = get_finviz_data(scan_limit, exchange, sector, pe_ratio, roe, debt_eq)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Bulundu (Tüm Piyasadan)")
    st.caption(f"Veri Kaynağı: {st.session_state.url}")
    
    # Ana Liste
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    # --- DETAYLI ANALİZ BÖLÜMÜ ---
    col1, col2 = st.columns([5, 4])
    
    with col1:
        st.subheader("🔬 Derinlemesine Analiz")
        tik = st.selectbox("İncelemek İçin Hisse Seç:", df['Ticker'].tolist())
        
        if tik:
            with st.spinner(f"{tik} için Yahoo Finance verileri çekiliyor..."):
                details, hist = get_yahoo_details(tik)
                
            if details and not hist.empty:
                # Grafik
                hist['Return'] = ((hist['Close'] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]) * 100
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], name='Fiyat'))
                fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'].rolling(50).mean(), name='SMA 50', line=dict(dash='dot')))
                fig.update_layout(title=f"{tik} Fiyat Grafiği", height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # Detay Kartları (Yahoo Verileri)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("EV/EBITDA", f"{details.get('EV/EBITDA', '-')}")
                c2.metric("P/B Oranı", f"{details.get('P/B', '-')}")
                c3.metric("Hedef Fiyat", f"${details.get('Target Price', '-')}")
                
                fcf_val = details.get('FCF', 0)
                if isinstance(fcf_val, (int, float)):
                    c4.metric("FCF", f"${fcf_val/1e9:.2f}B")
                else:
                    c4.metric("FCF", "-")

    with col2:
        if tik and details:
            st.subheader("🧠 Karar Destek Raporu")
            
            # Finviz satırını al
            fin_row = df[df['Ticker'] == tik].iloc[0]
            
            # Temel Bilgiler
            st.info(f"**Sektör:** {fin_row['Sector']} | **Endüstri:** {fin_row['Industry']}")
            
            # Çelişki Analizi Çalıştır
            comments = analyze_conflict(fin_row, details, hist)
            
            if comments:
                st.write("**Tespit Edilen Sinyaller:**")
                for c in comments:
                    st.markdown(c)
            else:
                st.success("Bariz bir temel-teknik uyumsuzluk görülmedi.")
                
            st.markdown("---")
            st.write("**Veri Özeti (Finviz + Yahoo):**")
            st.write(f"- **Fiyat:** ${fin_row['Price']}")
            st.write(f"- **F/K (Finviz):** {fin_row['P/E']}")
            st.write(f"- **Borç/Özkaynak (Yahoo):** {details.get('Total Debt', 'N/A')}")

elif st.session_state.scan_data.empty:
    st.info("👈 Sol menüden kriterleri seçip **'Taramayı Başlat'** butonuna basınız.")
