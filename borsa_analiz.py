import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v24", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Detaylı Yorum Modu)")
st.markdown("""
**Yenilik:** Kimlik gizleme ile Yahoo engelini aşma (EV/EBITDA Fix).
**Yorum:** Sadece veri okumayan, 'Neden?' ve 'Ne Anlama Gelir?' sorularını yanıtlayan anlatı motoru.
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

# --- VERİ ÇEKME MOTORU (User-Agent Fix) ---
def get_yahoo_session():
    """Yahoo'ya 'Ben Tarayıcıyım' demek için özel oturum açar"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session

def fetch_robust_metrics(ticker):
    """
    EV/EBITDA için zorlayıcı yöntem.
    Hem .info hem de manuel hesaplama dener.
    """
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Debt/Eq': None, 'Source': '-'}
    
    try:
        # Session ile Ticker oluştur (Bloklanmayı önler)
        session = get_yahoo_session()
        stock = yf.Ticker(ticker, session=session)
        
        # 1. Hazır Veriyi Dene
        info = stock.info
        metrics['EV/EBITDA'] = info.get('enterpriseToEbitda')
        metrics['FCF'] = info.get('freeCashflow')
        if info.get('debtToEquity'):
            metrics['Debt/Eq'] = info.get('debtToEquity') / 100
            
        metrics['Source'] = 'Yahoo Info'

        # 2. Hazır Veri Yoksa MANUEL HESAPLA
        if metrics['EV/EBITDA'] is None:
            try:
                # Bilançoları Çek
                bs = stock.balance_sheet
                inc = stock.income_stmt
                
                if not bs.empty and not inc.empty:
                    # En güncel veriler
                    curr_bs = bs.iloc[:, 0]
                    curr_inc = inc.iloc[:, 0]
                    
                    # Veri Normalizasyonu (Farklı isimleri yakala)
                    total_debt = 0
                    for k in ['Total Debt', 'TotalDebt', 'Long Term Debt']:
                        if k in curr_bs.index: total_debt = curr_bs[k]; break
                            
                    cash = 0
                    for k in ['Cash', 'CashAndCashEquivalents', 'Cash And Cash Equivalents']:
                        if k in curr_bs.index: cash = curr_bs[k]; break
                            
                    ebitda = 0
                    for k in ['EBITDA', 'Normalized EBITDA']:
                        if k in curr_inc.index: ebitda = curr_inc[k]; break
                    
                    # EV Hesapla
                    mcap = stock.fast_info['market_cap']
                    if mcap and ebitda and ebitda > 0:
                        ev = mcap + total_debt - cash
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Bilanço Hesabı'
            except:
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
    
    # Volatilite
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(30).std() * np.sqrt(252) * 100
    
    # Drawdown
    rolling_max = df['Close'].expanding().max()
    df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    return df

# --- AKILLI YORUM MOTORU (Geliştirilmiş) ---
def generate_narrative_report(ticker, finviz_row, metrics, hist):
    comments = []
    last = hist.iloc[-1]
    
    curr = last['Close']
    ma50 = last['MA50']
    ma200 = last['MA200']
    rsi = last['RSI']
    vol = last['Volatility']
    dd = last['Drawdown']
    
    evebitda = metrics.get('EV/EBITDA')
    
    # --- 1. TREND ANALİZİ (Hikayeleştirilmiş) ---
    st.markdown("#### 1. Trend ve Momentum Analizi")
    
    # Trend Durumu
    if curr > ma200:
        if curr > ma50:
            msg = f"Hisse şu anda **Güçlü Boğa (Yükseliş)** trendindedir. Fiyat hem kısa vadeli (50 gün) hem de uzun vadeli (200 gün) ortalamaların üzerinde seyrediyor. Bu, alıcıların iştahlı olduğunu ve düşüşlerin alım fırsatı olarak değerlendirildiğini gösterir."
            st.success(f"📈 **Trend:** {msg}")
        else:
            msg = f"Hisse uzun vadeli yükseliş trendini korusa da (Fiyat > MA200), kısa vadede bir **Düzeltme/Dinlenme** sürecindedir (Fiyat < MA50). Bu bölge trendin devamı için kritik bir destek testidir."
            st.info(f"⚖️ **Trend:** {msg}")
    else:
        msg = f"Hisse teknik olarak **Ayı (Düşüş)** trendindedir. Fiyatın 200 günlük ortalamanın altında olması, yatırımcı güveninin zayıf olduğunu ve tepki yükselişlerinin satışla karşılaşabileceğini işaret eder."
        st.error(f"📉 **Trend:** {msg}")

    # RSI Yorumu
    if rsi < 30:
        st.info(f"💎 **Momentum (RSI {rsi:.0f}):** Hisse aşırı satılmış durumda. Satıcılar yorulmuş olabilir, teknik olarak bir tepki yükselişi olasılığı masada.")
    elif rsi > 70:
        st.warning(f"🔥 **Momentum (RSI {rsi:.0f}):** Hisse aşırı ısınmış. Fiyat çok hızlı yükseldiği için kısa vadede kâr realizasyonu (satış) riski yüksek.")
    else:
        st.write(f"⏱️ **Momentum (RSI {rsi:.0f}):** Gösterge nötr bölgede. Fiyat aşırılık içermiyor, trend yönünde hareket etmesi beklenebilir.")

    st.markdown("---")
    
    # --- 2. DEĞERLEME VE RİSK ---
    st.markdown("#### 2. Değerleme ve Risk Profili")
    
    # EV/EBITDA Yorumu
    if evebitda and evebitda > 0:
        val_text = f"Şirketin İşletme Değeri / FAVÖK oranı **{evebitda:.2f}** seviyesinde."
        if evebitda < 10:
            val_text += " Bu seviye, şirketin nakit yaratma gücüne kıyasla **çok ucuz** fiyatlandığını gösterir (Kelepir Bölge)."
            st.success(f"💰 **Değerleme:** {val_text}")
        elif evebitda > 25:
            val_text += " Bu seviye, piyasanın şirketten **yüksek büyüme** beklediğini gösterir. Eğer büyüme gelmezse fiyat sert düzeltme yiyebilir (Pahalı/Primli)."
            st.warning(f"⚠️ **Değerleme:** {val_text}")
        else:
            val_text += " Bu, sektör ortalamaları dahilinde **makul** bir değerlemedir."
            st.info(f"⚖️ **Değerleme:** {val_text}")
    else:
        st.warning("ℹ️ **Değerleme:** EV/EBITDA hesaplanamadı. Şirket zarar ediyor olabilir (EBITDA negatif) veya bilanço verisi eksik.")

    # Risk Yorumu
    risk_msg = f"Yıllık volatilite **%{vol:.1f}**. "
    if vol < 20:
        risk_msg += "Hisse fiyatı istikrarlı, defansif bir karakter sergiliyor."
    elif vol > 40:
        risk_msg += "Fiyat hareketleri çok sert, risk toleransı düşük yatırımcılar dikkatli olmalı."
        
    st.write(f"🛡️ **Risk Profili:** {risk_msg} Zirveden düşüş (Drawdown) ise **%{dd:.1f}** seviyesinde.")

# --- FİNVİZ TARAYICI ---
def get_finviz_v24(limit_count, exc, sec, pe, roe_val, rsi_val):
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
        df, url = get_finviz_v24(scan_limit, exchange, sector, pe_ratio, roe, rsi_filter)
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
                    session = get_yahoo_session()
                    stock = yf.Ticker(tik, session=session)
                    hist = stock.history(period="1y")
                    
                    if not hist.empty:
                        hist = calculate_ta(hist)
                        
                        # 2. Grafik
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(height=500, title=f"{tik} - Günlük Grafik", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi bulunamadı.")
                except Exception as e:
                    st.error(f"Bağlantı Hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            # Finviz satırı
            fin_row = df[df['Ticker'] == tik].iloc[0]
            st.caption(f"**Sektör:** {fin_row['Sector']} | **Fiyat:** ${fin_row['Price']} | **F/K:** {fin_row['P/E']}")
            
            # Yorumları Üret
            generate_narrative_report(tik, fin_row, adv, hist)
            
            # Alt Özet Kartları
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric("FCF (Nakit Akışı)", f"${(adv.get('FCF') or 0)/1e9:.2f}B" if adv.get('FCF') else "-")
            c2.metric("Max Drawdown", f"%{hist.iloc[-1]['Drawdown']:.1f}")

elif st.session_state.scan_data.empty:
    st.info("👈 Analize başlamak için sol menüdeki **'Analizi Başlat'** butonuna basınız.")
