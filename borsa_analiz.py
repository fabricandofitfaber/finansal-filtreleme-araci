import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v26", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Bütünçül Sentez)")
st.markdown("""
**Altyapı:** v16 Filtre Derinliği + v25 Hesaplama Motoru
**Yenilik:** Verileri tek tek okumak yerine birleştirip 'Nihai Kanaat' üreten yorumlayıcı.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (Tam Kadro Filtreler) ---
st.sidebar.header("🔍 Çok Katmanlı Filtreleme")

# 0. Evren Genişliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Evren Genişliği (Sayfa)", list(limit_opts.keys()), index=2)

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector = st.sidebar.selectbox("Sektör", ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"], index=0)

# 2. Temel Filtreler (Değer & Kalite)
st.sidebar.markdown("### 1. Temel Filtreler (Değer & Kalite)")
pe_opts = ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Under 50", "Over 20"]
pe_ratio = st.sidebar.selectbox("F/K (Değerleme)", pe_opts, index=0)

peg_opts = ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"]
peg_ratio = st.sidebar.selectbox("PEG (Büyüme)", peg_opts, index=0)

roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kalite)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak (Risk)", debt_opts, index=0)

# 3. Teknik Filtreler (Zamanlama)
st.sidebar.markdown("### 2. Teknik Filtreler (Zamanlama)")
rsi_filter = st.sidebar.selectbox("RSI (Momentum)", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)


# --- HESAPLAMA MOTORU (Calculation Engine) ---
def fetch_robust_metrics(ticker):
    """EV/EBITDA ve FCF için Bilanço Hesaplaması"""
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Source': '-'}
    
    try:
        stock = yf.Ticker(ticker)
        
        # 1. Hazır Veri Denemesi
        try:
            info = stock.info
            metrics['EV/EBITDA'] = info.get('enterpriseToEbitda')
            metrics['FCF'] = info.get('freeCashflow')
            metrics['Source'] = 'Yahoo Info'
        except: pass

        # 2. Manuel Hesaplama (Yedek Plan)
        if metrics['EV/EBITDA'] is None:
            try:
                mcap = stock.fast_info['market_cap']
                bs = stock.balance_sheet
                inc = stock.income_stmt
                
                if not bs.empty and not inc.empty:
                    curr_bs = bs.iloc[:, 0]
                    curr_inc = inc.iloc[:, 0]
                    
                    debt = 0
                    for k in ['Total Debt', 'TotalDebt', 'Long Term Debt']:
                        if k in curr_bs.index: debt = curr_bs[k]; break
                    
                    cash = 0
                    for k in ['Cash', 'CashAndCashEquivalents']:
                        if k in curr_bs.index: cash = curr_bs[k]; break
                    
                    ebitda = 0
                    for k in ['EBITDA', 'Normalized EBITDA']:
                        if k in curr_inc.index: ebitda = curr_inc[k]; break
                    
                    if mcap and ebitda and ebitda > 0:
                        ev = mcap + debt - cash
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Bilanço Hesabı'
            except: pass
            
    except: pass
    return metrics

# --- İNDİKATÖRLER ---
def calculate_ta(df):
    df = df.copy()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(30).std() * np.sqrt(252) * 100
    
    rolling_max = df['Close'].expanding().max()
    df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    return df

# --- BÜTÜNÇÜL YORUM MOTORU (Holistic Engine) ---
def generate_holistic_report(ticker, finviz_row, metrics, hist):
    last = hist.iloc[-1]
    curr = last['Close']
    ma200 = last['MA200']
    rsi = last['RSI']
    evebitda = metrics.get('EV/EBITDA')
    
    # 1. NİHAİ AKADEMİK KANAAT (Sentez)
    st.markdown("#### 🏛️ Yönetici Özeti (Nihai Kanaat)")
    
    sentiment = "NÖTR"
    color = "blue"
    reason = "Veriler karmaşık sinyaller üretiyor."
    
    # Sentez Mantığı
    is_uptrend = curr > ma200
    is_cheap = (evebitda and evebitda < 12)
    is_oversold = rsi < 35
    is_overbought = rsi > 70
    
    if is_uptrend and is_cheap:
        sentiment = "GÜÇLÜ ALIM ADAYI (Growth at Reasonable Price)"
        color = "green"
        reason = "Hisse hem teknik olarak yükseliş trendinde hem de temel olarak (EV/EBITDA) ucuz fiyatlanıyor. İdeal 'Smart Beta' senaryosu."
    elif is_uptrend and is_overbought:
        sentiment = "KÂR REALİZASYONU (Düzeltme Riski)"
        color = "orange"
        reason = "Trend güçlü ancak momentum (RSI) aşırı ısınmış. Fiyat soluklanmak isteyebilir."
    elif not is_uptrend and is_cheap:
        sentiment = "DEĞER TUZAĞI RİSKİ (İzleme Listesi)"
        color = "red"
        reason = "Şirket temel olarak ucuz olsa da teknik trend negatif (Ayı Piyasası). Piyasa henüz ucuzluğu fiyatlamıyor, düşen bıçak tutulmamalı."
    elif not is_uptrend and not is_cheap:
        sentiment = "ZAYIF GÖRÜNÜM (Uzak Dur)"
        color = "red"
        reason = "Hisse hem pahalı hem de düşüş trendinde."

    st.markdown(f":{color}-background[**{sentiment}**]")
    st.caption(f"**Gerekçe:** {reason}")
    
    st.markdown("---")
    
    # 2. DETAYLI KANITLAR
    c1, c2 = st.columns(2)
    
    with c1:
        st.write("**Teknik Kanıtlar:**")
        trend_txt = "Pozitif (Boğa)" if is_uptrend else "Negatif (Ayı)"
        st.write(f"• **Trend:** {trend_txt} (Fiyat MA200'ün {'üzerinde' if is_uptrend else 'altında'})")
        st.write(f"• **Momentum:** RSI {rsi:.0f} seviyesinde.")
        
    with c2:
        st.write("**Temel Kanıtlar:**")
        if evebitda:
            val_txt = "Kelepir" if evebitda < 10 else ("Pahalı" if evebitda > 20 else "Makul")
            st.write(f"• **Değerleme:** {evebitda:.2f} EV/EBITDA ({val_txt})")
        else:
            st.write("• **Değerleme:** Veri yok (Riskli)")
            
        pe_val = finviz_row.get('P/E', '-')
        st.write(f"• **F/K Oranı:** {pe_val}")

# --- FİNVİZ TARAYICI ---
def get_finviz_v26(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
    filters = []
    # Borsa & Sektör
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    # Temel Filtreler
    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50", "Under 20": "fa_pe_u20", "Under 30": "fa_pe_u30", "Under 50": "fa_pe_u50", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    peg_map = {"Low (<1)": "fa_peg_u1", "Under 2": "fa_peg_u2", "High (>3)": "fa_peg_o3", "Growth (>1.5)": "fa_peg_o1.5"}
    if peg in peg_map: filters.append(peg_map[peg])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Under 0%": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

    # Teknik Filtreler
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
                        target = t; break
            if target:
                data = []
                head = ["No.", "Ticker", "Company", "Sector", "Industry", "Country", "Market Cap", "P/E", "Price", "Change", "Volume"]
                for row in target.find_all('tr')[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cols) >= 11: data.append(cols[:11])
                if data: all_dfs.append(pd.DataFrame(data, columns=head))
            else: break
            time.sleep(0.5)
            prog_bar.progress((i + 1) / len(pages))
        except: break
    prog_bar.empty()
    if all_dfs: return pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True), base_url
    return pd.DataFrame(), base_url

# --- UI AKIŞI ---
if st.sidebar.button("Analizi Başlat"):
    with st.spinner("Piyasa taranıyor..."):
        df, url = get_finviz_v26(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.dataframe(df, use_container_width=True)
    st.divider()
    
    col1, col2 = st.columns([5, 4])
    
    with col1:
        st.subheader("📉 Teknik Grafik")
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        adv = {}
        
        if tik:
            with st.spinner("Bilanço verileri çekiliyor ve hesaplanıyor..."):
                try:
                    # 1. Veri ve Hesaplama
                    adv = fetch_robust_metrics(tik)
                    
                    # 2. Tarihçe
                    stock = yf.Ticker(tik)
                    hist = stock.history(period="1y")
                    
                    if not hist.empty:
                        hist = calculate_ta(hist)
                        
                        # 3. Grafik
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(height=500, title=f"{tik} - Günlük Grafik", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi bulunamadı.")
                except Exception as e:
                    st.error(f"Hata: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            fin_row = df[df['Ticker'] == tik].iloc[0]
            
            # YENİ: Bütünçül Yorum Motoru
            generate_holistic_report(tik, fin_row, adv, hist)
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            fcf_val = adv.get('FCF')
            c1.metric("Serbest Nakit (FCF)", f"${fcf_val/1e9:.2f}B" if fcf_val else "-")
            c2.metric("Max Drawdown", f"%{hist.iloc[-1]['Drawdown']:.1f}")

elif st.session_state.scan_data.empty:
    st.info("👈 Filtreleri ayarlayıp 'Analizi Başlat' butonuna basın.")
