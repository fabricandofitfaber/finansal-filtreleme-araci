import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v23", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Zırhlı Sürüm)")
st.markdown("""
**Durum:** Apple (AAPL) dahil tüm hisseler için **EV/EBITDA** ve **FCF** hesaplar.
**Düzeltme:** Türkçe karakter hataları ve kayıp teknik yorumlar giderildi.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ ---
st.sidebar.header("🔍 Çok Katmanlı Filtreleme")
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Evren Genişliği (Sayfa)", list(limit_opts.keys()), index=2)

exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector = st.sidebar.selectbox("Sektör", ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"], index=0)

st.sidebar.markdown("### Temel & Teknik")
pe_ratio = st.sidebar.selectbox("F/K", ["Any", "Low (<15)", "Under 20", "Under 50", "Over 20"], index=0)
roe = st.sidebar.selectbox("ROE", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)"], index=0)
rsi_filter = st.sidebar.selectbox("RSI", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)

# --- ZIRHLI VERİ ÇEKİCİ (Triple-Check Engine) ---
def get_robust_metrics(ticker):
    """
    EV/EBITDA ve FCF için 3 farklı yöntemi sırayla dener.
    Asla pes etmez.
    """
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Source': 'Yok'}
    
    try:
        stock = yf.Ticker(ticker)
        
        # YÖNTEM 1: Hazır Veri (.info)
        info = stock.info
        metrics['EV/EBITDA'] = info.get('enterpriseToEbitda')
        metrics['FCF'] = info.get('freeCashflow')
        metrics['Source'] = 'Yahoo Info'

        # YÖNTEM 2: Eksikse Manuel Hesapla
        if metrics['EV/EBITDA'] is None:
            try:
                # Market Cap
                mcap = info.get('marketCap')
                if not mcap: mcap = stock.fast_info['market_cap']
                
                # Finansal Tabloları Çek
                bs = stock.balance_sheet
                inc = stock.income_stmt
                
                if not bs.empty and not inc.empty:
                    # En güncel sütunu al
                    curr_bs = bs.iloc[:, 0]
                    curr_inc = inc.iloc[:, 0]
                    
                    # Esnek Arama (Farklı isimler olabilir)
                    debt = 0
                    for key in ['Total Debt', 'TotalDebt', 'Long Term Debt']:
                        if key in curr_bs: 
                            debt = curr_bs[key]
                            break
                            
                    cash = 0
                    for key in ['Cash And Cash Equivalents', 'Cash', 'CashAndCashEquivalents']:
                        if key in curr_bs:
                            cash = curr_bs[key]
                            break
                    
                    ebitda = 0
                    for key in ['EBITDA', 'Normalized EBITDA', 'Ebitda']:
                        if key in curr_inc:
                            ebitda = curr_inc[key]
                            break
                    
                    # Hesaplama: EV = Mcap + Debt - Cash
                    if mcap and ebitda and ebitda > 0:
                        ev = mcap + debt - cash
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Manuel Hesaplama (Bilanço)'
            except:
                pass

        # YÖNTEM 3: FCF İçin Nakit Akım Tablosu
        if metrics['FCF'] is None:
            try:
                cf = stock.cashflow
                if not cf.empty:
                    curr_cf = cf.iloc[:, 0]
                    ocf = curr_cf.get('Operating Cash Flow', 0)
                    capex = curr_cf.get('Capital Expenditure', 0)
                    if ocf:
                        metrics['FCF'] = ocf + capex # Capex genelde negatiftir
            except:
                pass
                
    except Exception:
        pass
    
    return metrics

# --- TEKNİK HESAPLAMA ---
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

# --- RAPORLAMA MOTORU (Düzeltilmiş Karakterler) ---
def generate_full_report(ticker, finviz_row, metrics, hist):
    comments = []
    last = hist.iloc[-1]
    
    curr = last['Close']
    ma50 = last['MA50']
    ma200 = last['MA200']
    rsi = last['RSI']
    
    evebitda = metrics.get('EV/EBITDA')
    
    # 1. KISA VADE (MA50) - Özel Format
    diff_50 = ((curr - ma50) / ma50) * 100
    trend_50 = "ÜZERİNDE" if curr > ma50 else "ALTINDA"
    icon_50 = "✅" if curr > ma50 else "⚠️"
    
    # f-string kullanarak temiz metin (karakter hatası olmaz)
    msg_50 = f"{icon_50} **Kısa Vade:** Fiyat ({curr:.2f}), 50 Günlük Ortalamanın ({ma50:.2f}) {trend_50}. (Fark: %{diff_50:.1f})"
    comments.append(msg_50)

    # 2. UZUN VADE (MA200)
    trend_200 = "YÜKSELİŞ (BOĞA)" if curr > ma200 else "DÜŞÜŞ (AYI)"
    comments.append(f"📈 **Uzun Vade Trend:** {trend_200}")

    # 3. RSI DURUMU
    if rsi < 30: rsi_msg = "Aşırı Satım (Tepki Beklenir)"
    elif rsi > 70: rsi_msg = "Aşırı Alım (Düzeltme Riski)"
    else: rsi_msg = "Nötr Bölge (Yatay Seyir)"
    comments.append(f"⏱️ **Momentum (RSI):** {rsi:.0f} - {rsi_msg}")

    # 4. EV/EBITDA YORUMU
    if evebitda and evebitda > 0:
        val_msg = f"ℹ️ **EV/EBITDA:** {evebitda:.2f}"
        if evebitda < 10: val_msg += " (Kelepir Bölgesi)"
        elif evebitda > 25: val_msg += " (Büyüme/Pahalı Fiyatlama)"
        comments.append(val_msg)
    else:
        comments.append("ℹ️ **EV/EBITDA:** Negatif veya Veri Yok (Zarar Eden Şirket Olabilir)")
        
    return comments

# --- FİNVİZ TARAMA ---
def get_finviz_data_v23(limit_count, exc, sec, pe, roe_val, rsi_val):
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 50": "fa_pe_u50", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20"}
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
                        target = t
                        break
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
    if all_dfs:
        return pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True), base_url
    return pd.DataFrame(), base_url

# --- ANA AKIŞ ---
if st.sidebar.button("Analizi Başlat"):
    with st.spinner("Piyasa taranıyor..."):
        df, url = get_finviz_data_v23(scan_limit, exchange, sector, pe_ratio, roe, rsi_filter)
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
        tik = st.selectbox("Detaylı Analiz:", df['Ticker'].tolist())
        hist = pd.DataFrame()
        adv = {}
        
        if tik:
            with st.spinner("Hesaplamalar yapılıyor..."):
                try:
                    # Yahoo'dan Veri Çekme
                    adv = get_robust_metrics(tik)
                    stock = yf.Ticker(tik)
                    hist = stock.history(period="1y")
                    
                    if not hist.empty:
                        hist = calculate_ta(hist)
                        
                        # Candlestick Grafik
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(height=450, title=f"{tik} Teknik Görünüm", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi yok.")
                except Exception as e:
                    st.error(f"Hata: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            row = df[df['Ticker'] == tik].iloc[0]
            
            # Yorumları Üret
            comments = generate_full_report(tik, row, adv, hist)
            
            for c in comments:
                st.info(c)
                
            st.markdown("---")
            # Risk ve Değerleme Kartları
            last = hist.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Volatilite", f"%{last['Volatility']:.1f}")
            c2.metric("Max Drawdown", f"%{last['Drawdown']:.1f}")
            
            fcf_val = adv.get('FCF')
            if fcf_val:
                c3.metric("FCF", f"${fcf_val/1e9:.2f}B")
            else:
                c3.metric("FCF", "-")

elif st.session_state.scan_data.empty:
    st.info("👈 Filtreleri ayarlayıp 'Analizi Başlat' butonuna basın.")
