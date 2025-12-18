import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v25", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Native Mod)")
st.markdown("""
**Durum:** yfinance kütüphanesinin yerleşik koruması kullanılıyor (Session hatası giderildi).
**Özellik:** Bilanço üzerinden Manuel EV/EBITDA Hesaplama + Detaylı Yorum.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ ---
st.sidebar.header("🔍 Filtreleme Paneli")
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5}
scan_limit = st.sidebar.selectbox("Evren Genişliği", list(limit_opts.keys()), index=1)

exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector = st.sidebar.selectbox("Sektör", ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"], index=0)

st.sidebar.markdown("### Temel & Teknik")
pe_ratio = st.sidebar.selectbox("F/K", ["Any", "Low (<15)", "Under 20", "Over 20"], index=0)
roe = st.sidebar.selectbox("ROE", ["Any", "Positive (>0%)", "High (>15%)"], index=0)
rsi_filter = st.sidebar.selectbox("RSI", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)

# --- ZIRHLI VERİ ÇEKİCİ (Manuel Hesaplama) ---
def fetch_robust_metrics(ticker):
    """
    EV/EBITDA için önce hazır veriye bakar, yoksa bilançodan hesaplar.
    """
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Debt/Eq': None, 'Source': '-'}
    
    try:
        # Session kullanmıyoruz! yfinance kendi halletsin.
        stock = yf.Ticker(ticker)
        
        # 1. Hazır Veriyi Dene (.info)
        # Bazen burası boş gelir, sorun değil, aşağıda hesaplayacağız.
        try:
            info = stock.info
            metrics['EV/EBITDA'] = info.get('enterpriseToEbitda')
            metrics['FCF'] = info.get('freeCashflow')
            if info.get('debtToEquity'):
                metrics['Debt/Eq'] = info.get('debtToEquity') / 100
            metrics['Source'] = 'Yahoo Info'
        except:
            pass # Info patlarsa devam et

        # 2. MANUEL HESAPLAMA (Garantili Yöntem)
        # Eğer hazır veri yoksa (Apple örneğindeki gibi), kolları sıvıyoruz.
        if metrics['EV/EBITDA'] is None:
            try:
                # Market Cap (Hızlı Info'dan)
                mcap = stock.fast_info['market_cap']
                
                # Finansal Tablolar
                bs = stock.balance_sheet
                inc = stock.income_stmt
                
                if not bs.empty and not inc.empty:
                    curr_bs = bs.iloc[:, 0] # En güncel dönem
                    curr_inc = inc.iloc[:, 0]
                    
                    # Borç Bul
                    debt = 0
                    for k in ['Total Debt', 'TotalDebt', 'Long Term Debt']:
                        if k in curr_bs.index: debt = curr_bs[k]; break
                    
                    # Nakit Bul
                    cash = 0
                    for k in ['Cash', 'CashAndCashEquivalents', 'Cash And Cash Equivalents']:
                        if k in curr_bs.index: cash = curr_bs[k]; break
                    
                    # EBITDA Bul
                    ebitda = 0
                    for k in ['EBITDA', 'Normalized EBITDA', 'Ebitda']:
                        if k in curr_inc.index: ebitda = curr_inc[k]; break
                    
                    # EV = Market Cap + Debt - Cash
                    # EV/EBITDA = EV / EBITDA
                    if mcap and ebitda and ebitda > 0:
                        ev = mcap + debt - cash
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Bilanço Hesabı'
                        
            except Exception as e:
                # Hesaplama hatası olursa sessizce geç
                pass
                
    except Exception:
        pass
        
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

# --- AKILLI YORUM MOTORU ---
def generate_narrative_report(ticker, finviz_row, metrics, hist):
    comments = []
    last = hist.iloc[-1]
    
    curr = last['Close']
    ma50 = last['MA50']
    ma200 = last['MA200']
    rsi = last['RSI']
    vol = last['Volatility']
    
    evebitda = metrics.get('EV/EBITDA')
    
    # 1. Trend Analizi
    st.markdown("#### 1. Trend ve Momentum")
    if curr > ma200:
        trend = "YÜKSELİŞ (BOĞA)"
        st.success(f"📈 **Uzun Vade:** {trend}. Fiyat 200 günlük ortalamanın üzerinde, ana yön yukarı.")
    else:
        trend = "DÜŞÜŞ (AYI)"
        st.error(f"📉 **Uzun Vade:** {trend}. Fiyat 200 günlük ortalamanın altında, baskı sürüyor.")
        
    if curr > ma50:
        st.info(f"✅ **Kısa Vade:** Fiyat (${curr:.2f}), 50 günlük ortalamanın (${ma50:.2f}) üzerinde. Alıcılar istekli.")
    else:
        st.warning(f"⚠️ **Kısa Vade:** Fiyat (${curr:.2f}), 50 günlük ortalamanın (${ma50:.2f}) altına sarktı. Dinlenme/Düzeltme sürecinde.")

    # 2. Değerleme (EV/EBITDA)
    st.markdown("#### 2. Akademik Değerleme")
    if evebitda and evebitda > 0:
        val_msg = f"Şirketin **EV/EBITDA** oranı: **{evebitda:.2f}** ({metrics['Source']})."
        
        if evebitda < 8:
            val_msg += " Bu seviye, şirketin nakit yaratma gücüne göre **Kelepir** olduğunu gösterir."
            st.success(f"💰 {val_msg}")
        elif evebitda > 20:
            val_msg += " Piyasa şirketten yüksek büyüme bekliyor (Primli Fiyatlama)."
            st.warning(f"⚠️ {val_msg}")
        else:
            val_msg += " Makul değerleme aralığında."
            st.info(f"⚖️ {val_msg}")
    else:
        st.write("ℹ️ **EV/EBITDA:** Hesaplanamadı (Şirket zarar ediyor olabilir).")

    # 3. Risk
    st.markdown("#### 3. Risk Profili")
    st.write(f"🛡️ **Volatilite:** %{vol:.1f} (Yıllık). RSI: {rsi:.0f}.")

# --- FİNVİZ TARAYICI ---
def get_finviz_v25(limit_count, exc, sec, pe, roe_val, rsi_val):
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    if rsi_val == "Oversold (<30)": filters.append("ta_rsi_os30")
    elif rsi_val == "Overbought (>70)": filters.append("ta_rsi_ob70")
    elif rsi_val == "Neutral (40-60)": filters.append("ta_rsi_n4060")

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
        df, url = get_finviz_v25(scan_limit, exchange, sector, pe_ratio, roe, rsi_filter)
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
            with st.spinner(f"{tik} için Bilanço analizi yapılıyor..."):
                try:
                    # 1. Veri ve Hesaplama (Native)
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
                    st.error(f"Veri çekme hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            # Finviz satırı
            fin_row = df[df['Ticker'] == tik].iloc[0]
            st.caption(f"**Sektör:** {fin_row['Sector']} | **Fiyat:** ${fin_row['Price']} | **F/K:** {fin_row['P/E']}")
            
            # Yorumları Üret
            generate_narrative_report(tik, fin_row, adv, hist)
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("FCF", f"${(adv.get('FCF') or 0)/1e9:.2f}B" if adv.get('FCF') else "-")
            c2.metric("Max Drawdown", f"%{hist.iloc[-1]['Drawdown']:.1f}")

elif st.session_state.scan_data.empty:
    st.info("👈 Analize başlamak için sol menüdeki **'Analizi Başlat'** butonuna basınız.")
