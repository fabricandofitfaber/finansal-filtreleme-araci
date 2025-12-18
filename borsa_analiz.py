import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v20", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Ultimate v20)")
st.markdown("""
**Temel:** Finviz (Tüm Piyasayı Tara) | **Detay:** Yahoo Finance (EV/EBITDA & FCF)
**Özellik:** v16 Filtreleme Mimarisi + İleri Seviye Rasyo Entegrasyonu
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (v16 Mimarisi - Geri Getirildi) ---
st.sidebar.header("🔍 Çok Katmanlı Filtreleme")

# 0. Evren Genişliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Evren Genişliği (Sayfa)", list(limit_opts.keys()), index=1)

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Temel Filtreler (Değer & Kalite)
st.sidebar.markdown("### 1. Temel Filtreler")
pe_opts = ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Under 50", "Over 20"]
pe_ratio = st.sidebar.selectbox("F/K (Değerleme)", pe_opts, index=0)

peg_opts = ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"]
peg_ratio = st.sidebar.selectbox("PEG (Büyüme)", peg_opts, index=0)

roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kalite)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak (Risk)", debt_opts, index=0)

# 3. Teknik Filtreler (Zamanlama)
st.sidebar.markdown("### 2. Teknik Filtreler")
rsi_filter = st.sidebar.selectbox("RSI (Momentum)", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)

# --- YAHOO DETAY ÇEKİCİ (Güvenli Mod) ---
def fetch_yahoo_advanced(ticker):
    """
    Seçilen hisse için EV/EBITDA ve FCF gibi Finviz'de olmayan verileri çeker.
    Hata verirse boş dönmez, varsayılan değer döner.
    """
    metrics = {
        'EV/EBITDA': None,
        'FCF': None,
        'Beta': None,
        'Target': None,
        'Desc': "Açıklama yok."
    }
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        metrics['EV/EBITDA'] = info.get('enterpriseToEbitda', None)
        metrics['FCF'] = info.get('freeCashflow', None)
        metrics['Beta'] = info.get('beta', None)
        metrics['Target'] = info.get('targetMeanPrice', None)
        metrics['Desc'] = info.get('longBusinessSummary', "Açıklama yok.")
    except:
        pass # Hata olursa None döner, analiz kısmı bunu yönetir.
        
    return metrics

# --- SİNYAL ÇELİŞKİ ANALİZİ (Geliştirilmiş) ---
def analyze_advanced_signals(finviz_row, yahoo_data):
    signals = []
    
    # Veri Dönüştürme
    try: pe = float(str(finviz_row['P/E']).replace('-','0'))
    except: pe = 0
    
    evebitda = yahoo_data['EV/EBITDA']
    fcf = yahoo_data['FCF']
    
    # 1. DEĞERLEME SAVAŞI (F/K vs EV/EBITDA)
    if isinstance(evebitda, (int, float)):
        if pe > 0 and pe < 12 and evebitda > 15:
            signals.append("🚨 **Değer Tuzağı Riski:** F/K düşük (<12) görünüyor ANCAK EV/EBITDA yüksek (>15). Şirketin borç yükü veya amortisman giderleri F/K'yı yanıltıcı kılıyor olabilir.")
        elif pe < 15 and evebitda < 8:
            signals.append("✅ **Çifte Onay (Değer):** Hem F/K hem de EV/EBITDA çok düşük seviyelerde. Gerçek bir kelepir olabilir.")
        else:
            signals.append(f"ℹ️ **EV/EBITDA Seviyesi:** {evebitda:.2f} (Sektörle kıyaslayınız).")
    
    # 2. NAKİT GÜCÜ (FCF Yield Proxy)
    if isinstance(fcf, (int, float)):
        if fcf > 0:
            signals.append(f"💰 **Nakit Akışı:** Şirket son 12 ayda ${(fcf/1e9):.2f} Milyar serbest nakit akışı yarattı. (Kalite Sinyali)")
        else:
            signals.append("⚠️ **Nakit Uyarısı:** Serbest nakit akışı negatif. Şirket nakit yakıyor olabilir.")
            
    return signals

# --- VERİ MOTORU (Finviz Scraper - Cerrah Modu) ---
def get_finviz_data_v20(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
    filters = []
    
    # URL Parametreleri (v16 ile aynı)
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50", "Under 20": "fa_pe_u20", "Under 30": "fa_pe_u30", "Under 50": "fa_pe_u50", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    peg_map = {"Low (<1)": "fa_peg_u1", "Under 2": "fa_peg_u2", "High (>3)": "fa_peg_o3", "Growth (>1.5)": "fa_peg_o1.5"}
    if peg in peg_map: filters.append(peg_map[peg])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Under 0%": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

    # Teknik
    if rsi_val == "Oversold (<30)": filters.append("ta_rsi_os30")
    elif rsi_val == "Overbought (>70)": filters.append("ta_rsi_ob70")
    elif rsi_val == "Neutral (40-60)": filters.append("ta_rsi_n4060")
    
    if ma_val == "Above SMA200": filters.append("ta_sma200_pa")
    elif ma_val == "Below SMA200": filters.append("ta_sma200_pb")

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
            for t in soup.find_all('table'):
                rows = t.find_all('tr')
                if len(rows) > 1:
                    txt = rows[0].get_text()
                    if 'No.' in txt and 'Ticker' in txt and 'Price' in txt:
                        target = t
                        break
            
            if target:
                data = []
                head = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
                for row in target.find_all('tr')[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cols) >= 11: data.append(cols[:11])
                if data: all_dfs.append(pd.DataFrame(data, columns=head))
            else:
                break # Tablo yoksa
            time.sleep(0.5)
            prog_bar.progress((i + 1) / len(pages))
        except: break
            
    prog_bar.empty()
    if all_dfs:
        return pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True), base_url
    return pd.DataFrame(), base_url

# --- ANA AKIŞ ---
if st.sidebar.button("Karar Destek Analizini Başlat"):
    with st.spinner("Finviz tüm piyasa taranıyor..."):
        df, url = get_finviz_data_v20(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Bulundu")
    st.caption(f"Veri Kaynağı: {st.session_state.url}")
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    # --- DETAYLI ANALİZ KISMI ---
    with col1:
        st.subheader("📉 Teknik & Getiri")
        tik = st.selectbox("Derinlemesine Analiz İçin Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        if tik:
            try:
                # 1. Grafik Verisi (Yahoo)
                hist = yf.download(tik, period="1y", progress=False)
                if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty:
                    # Getiri Hesabı
                    start_p = hist['Close'].iloc[0]
                    hist['Return'] = ((hist['Close'] - start_p) / start_p) * 100
                    
                    # 2. İleri Metrikler (Yahoo Info - Lazy Load)
                    # Burası v19'da çalışmayan kısımdı, şimdi try-except ile korumalı.
                    with st.spinner("İleri rasyolar (EV/EBITDA, FCF) alınıyor..."):
                        y_adv = fetch_yahoo_advanced(tik)
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Return'], fill='tozeroy', name='Getiri %', line=dict(color='#0068C9')))
                    fig.update_layout(title=f"{tik} - Kümülatif Getiri", height=400, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                    
                else:
                    st.warning("Grafik verisi gelmedi.")
            except Exception as e:
                st.error(f"Grafik/Veri Hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            # Finviz Satırı
            row = df[df['Ticker'] == tik].iloc[0]
            
            # Analizi Çalıştır
            signals = analyze_advanced_signals(row, y_adv)
            
            # Sonuçları Yazdır
            for s in signals:
                st.markdown(s)
            
            st.markdown("---")
            st.write("**Temel Veri (Finviz):**")
            st.write(f"- Fiyat: ${row['Price']}")
            st.write(f"- F/K: {row['P/E']}")
            st.write(f"- Sektör: {row['Sector']}")
            
            st.markdown("---")
            st.write("**İleri Veri (Yahoo - Yeni):**")
            if y_adv['EV/EBITDA']:
                st.write(f"- **EV/EBITDA:** {y_adv['EV/EBITDA']:.2f}")
            else:
                st.write("- EV/EBITDA: *Veri Yok*")
                
            if y_adv['Beta']:
                st.write(f"- **Beta (Risk):** {y_adv['Beta']:.2f}")
            
            if y_adv['Target']:
                curr = float(str(row['Price']))
                tgt = y_adv['Target']
                pot = ((tgt - curr) / curr) * 100
                st.write(f"- **Analist Hedefi:** ${tgt} (%{pot:.1f})")

            with st.expander("Şirket Ne İş Yapar?"):
                st.caption(y_adv['Desc'][:300] + "...")

elif st.session_state.scan_data.empty:
    st.info("👈 Lütfen kriterleri belirleyip 'Karar Destek Analizini Başlat' butonuna basınız.")
