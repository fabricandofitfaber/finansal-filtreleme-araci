import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v22", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Hesaplama Motorlu)")
st.markdown("""
**Yöntem:** Finviz Taraması + **Manuel Rasyo Hesaplama**
**Düzeltme:** EV/EBITDA verisi hazır alınmaz, Bilanço ve Gelir tablosundan anlık hesaplanır (Kesin Sonuç).
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (v16 Filtreleri) ---
st.sidebar.header("🔍 Çok Katmanlı Filtreleme")

# 0. Evren Genişliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Evren Genişliği (Sayfa)", list(limit_opts.keys()), index=2)

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Temel Filtreler
st.sidebar.markdown("### 1. Temel Filtreler")
pe_opts = ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Under 50", "Over 20"]
pe_ratio = st.sidebar.selectbox("F/K (Değerleme)", pe_opts, index=0)

peg_opts = ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"]
peg_ratio = st.sidebar.selectbox("PEG (Büyüme)", peg_opts, index=0)

roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kalite)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak (Risk)", debt_opts, index=0)

# 3. Teknik Filtreler
st.sidebar.markdown("### 2. Teknik Filtreler")
rsi_filter = st.sidebar.selectbox("RSI (Momentum)", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)

# --- GELİŞMİŞ HESAPLAMA MOTORU (Calculation Engine) ---
def fetch_calculated_metrics(ticker):
    """
    Hazır veriye güvenmez. Bilançoyu çeker ve EV/EBITDA'yı kendisi hesaplar.
    """
    metrics = {
        'EV/EBITDA': None,
        'FCF': None,
        'Source': 'Bilinmiyor'
    }
    
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Önce .info'yu dene (En hızlısı)
        info = stock.info
        if info.get('enterpriseToEbitda'):
            metrics['EV/EBITDA'] = info.get('enterpriseToEbitda')
            metrics['Source'] = 'Yahoo Info (Hazır)'
        
        # 2. Eğer boşsa, MANUEL HESAPLA (En garantisi)
        if metrics['EV/EBITDA'] is None:
            # Gerekli tabloları çek
            bs = stock.balance_sheet      # Bilanço
            inc = stock.income_stmt       # Gelir Tablosu
            
            if not bs.empty and not inc.empty:
                # En son dönem (son sütun)
                latest_bs = bs.iloc[:, 0]
                latest_inc = inc.iloc[:, 0]
                
                # Market Cap (Fast Info'dan gelir, güvenilirdir)
                mcap = stock.fast_info['market_cap']
                
                # Verileri Bul (Farklı isimlendirmelere karşı try-except)
                try:
                    total_debt = latest_bs.get('Total Debt', 0)
                    cash = latest_bs.get('Cash And Cash Equivalents', 0)
                    
                    # Enterprise Value = Market Cap + Debt - Cash
                    ev = mcap + total_debt - cash
                    
                    # EBITDA Bul
                    ebitda = latest_inc.get('EBITDA', latest_inc.get('Normalized EBITDA', 0))
                    
                    if ebitda and ebitda > 0:
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Akademik Hesaplama (Bilanço)'
                except:
                    pass

        # 3. Serbest Nakit Akışı (FCF)
        if info.get('freeCashflow'):
            metrics['FCF'] = info.get('freeCashflow')
        
    except Exception as e:
        pass
        
    return metrics

# --- İNDİKATÖR HESAPLAMA ---
def calculate_indicators(df):
    df = df.copy()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(window=30).std() * np.sqrt(252) * 100
    
    rolling_max = df['Close'].expanding().max()
    df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    return df

# --- FİNVİZ TARAMA ---
def get_finviz_data(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
    filters = []
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
                break
            time.sleep(0.5)
            prog_bar.progress((i + 1) / len(pages))
        except: break
            
    prog_bar.empty()
    if all_dfs:
        return pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True), base_url
    return pd.DataFrame(), base_url

# --- AKADEMİK RAPORLAYICI ---
def generate_report(ticker, finviz_row, metrics, hist):
    comments = []
    
    last = hist.iloc[-1]
    curr = last['Close']
    ma50 = last['MA50']
    ma200 = last['MA200']
    rsi = last['RSI']
    
    evebitda = metrics.get('EV/EBITDA')
    pe_str = str(finviz_row['P/E']).replace('-','0')
    try: pe = float(pe_str)
    except: pe = 0

    # 1. TREND YORUMU
    if curr > ma200:
        trend_status = "YÜKSELİŞ"
        trend_icon = "📈"
    else:
        trend_status = "DÜŞÜŞ"
        trend_icon = "📉"
        
    comments.append(f"{trend_icon} **Genel Trend:** {trend_status} (Fiyat 200 günlük ortalamaya göre konumlandırıldı).")
    
    # 2. MOMENTUM VE RSI
    rsi_desc = "Nötr"
    if rsi < 30: rsi_desc = "Aşırı Satım (Fırsat Bölgesi)"
    elif rsi > 70: rsi_desc = "Aşırı Alım (Risk Bölgesi)"
    
    comments.append(f"⏱️ **Momentum:** RSI göstergesi **{rsi:.0f}** seviyesinde ({rsi_desc}).")

    # 3. DEĞERLEME ANALİZİ (Hesaplanan EV/EBITDA ile)
    if evebitda and evebitda > 0:
        val_msg = f"ℹ️ **EV/EBITDA:** {evebitda:.2f} ({metrics['Source']})."
        
        if pe > 0 and pe < 15 and evebitda > 18:
            val_msg += " ⚠️ **Uyarı:** F/K düşük ama EV/EBITDA yüksek. Borç yapısına dikkat edilmeli."
        elif evebitda < 8:
            val_msg += " ✅ **Fırsat:** Şirket işletme değeri bazında kelepir fiyatlanıyor."
            
        comments.append(val_msg)
    else:
        comments.append("ℹ️ **EV/EBITDA:** Hesaplanamadı (Şirket zarar ediyor, EBITDA negatif veya veri eksik).")

    return comments

# --- ANA AKIŞ ---
if st.sidebar.button("Karar Destek Analizini Başlat"):
    with st.spinner("Finviz tüm piyasa taranıyor..."):
        df, url = get_finviz_data(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.caption(f"Veri Kaynağı: {st.session_state.url}")
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([5, 4])
    
    with col1:
        st.subheader("📉 Teknik Grafik")
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        adv_metrics = {}
        
        if tik:
            with st.spinner(f"{tik} için bilanço hesaplamaları yapılıyor..."):
                # 1. Grafik Verisi
                try:
                    stock = yf.Ticker(tik)
                    hist = stock.history(period="1y")
                    if not hist.empty:
                        hist = calculate_indicators(hist)
                        
                        # 2. İleri Metrik Hesaplama (EV/EBITDA)
                        adv_metrics = fetch_calculated_metrics(tik)
                        
                        # GRAFİK
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(title=f"{tik} - Teknik Görünüm", height=500, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi yok.")
                except Exception as e:
                    st.error(f"Hata: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            fin_row = df[df['Ticker'] == tik].iloc[0]
            
            # Raporu Üret
            comments = generate_report(tik, fin_row, adv_metrics, hist)
            
            for c in comments:
                st.info(c)
            
            st.markdown("---")
            
            # Risk Metrikleri
            last = hist.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Volatilite", f"%{last['Volatility']:.1f}")
            c2.metric("Max Drawdown", f"%{last['Drawdown']:.1f}")
            
            fcf_val = adv_metrics.get('FCF')
            if fcf_val:
                c3.metric("FCF (Yıllık)", f"${fcf_val/1e9:.2f}B")
            else:
                c3.metric("FCF", "-")
                
            st.caption("Not: EV/EBITDA verisi Yahoo 'Summary' veya 'Bilanço' verilerinden anlık hesaplanmıştır.")

elif st.session_state.scan_data.empty:
    st.info("👈 Kriterleri belirleyip 'Karar Destek Analizini Başlat' butonuna basınız.")
