import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v21", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Restorasyon Sürümü)")
st.markdown("""
**Altyapı:** v16 Mimarisi (Stabil) + Finviz Pagination (Tüm Piyasa)
**Özellik:** Fiyat/Ortalama Grafikleri + Kanıta Dayalı Yorumlama + Hibrit Veri
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (v16 Filtreleri - EKSİKSİZ) ---
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

# --- MATEMATİKSEL HESAPLAMA MODÜLÜ ---
def calculate_indicators(df):
    """
    Yahoo'dan gelen ham fiyat verisinden (History) indikatörleri biz hesaplarız.
    Bu yöntem .info verisine göre çok daha güvenilirdir.
    """
    df = df.copy()
    # Hareketli Ortalamalar
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Volatilite (Yıllık)
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(window=30).std() * np.sqrt(252) * 100
    
    # Max Drawdown
    rolling_max = df['Close'].expanding().max()
    df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    
    return df

# --- VERİ MOTORU (Finviz Scraper - Cerrah Modu) ---
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

# --- AKILLI YORUM MOTORU ---
def generate_academic_report(ticker, finviz_row, yahoo_info, hist_df):
    comments = []
    
    # Veri Hazırlığı
    last_row = hist_df.iloc[-1]
    curr_price = last_row['Close']
    ma50 = last_row['MA50']
    ma200 = last_row['MA200']
    rsi = last_row['RSI']
    volatility = last_row['Volatility']
    
    ev_ebitda = yahoo_info.get('enterpriseToEbitda', None)
    
    try: pe = float(str(finviz_row['P/E']).replace('-', '0'))
    except: pe = 0

    # 1. TEKNİK TREND ANALİZİ (Kanıta Dayalı)
    if curr_price > ma200:
        trend = "YÜKSELİŞ"
        icon = "📈"
        desc = "Fiyat 200 günlük ortalamanın üzerinde."
    else:
        trend = "DÜŞÜŞ/ZAYIF"
        icon = "📉"
        desc = "Fiyat 200 günlük ortalamanın altında."
        
    comments.append(f"{icon} **Genel Trend:** {trend} ({desc})")
    
    if curr_price > ma50:
        comments.append(f"✅ **Kısa Vade:** Fiyat (${curr_price:.2f}), 50 günlük ortalamanın (${ma50:.2f}) üzerinde, momentum pozitif.")
    else:
        comments.append(f"⚠️ **Kısa Vade:** Fiyat (${curr_price:.2f}), 50 günlük ortalamanın (${ma50:.2f}) altına sarkmış.")

    # 2. RİSK VE MOMENTUM
    if rsi < 30:
        comments.append(f"💎 **RSI Sinyali:** {rsi:.0f} (Aşırı Satım). Teknik olarak tepki alımı beklenebilir.")
    elif rsi > 70:
        comments.append(f"🔥 **RSI Sinyali:** {rsi:.0f} (Aşırı Alım). Düzeltme riski artmış.")
    else:
        comments.append(f"⚖️ **RSI:** {rsi:.0f} (Nötr Bölge).")
        
    if volatility > 60:
        comments.append(f"⚡ **Yüksek Volatilite:** Yıllık oynaklık %{volatility:.1f}. Risk iştahı düşük yatırımcı için uygun olmayabilir.")

    # 3. DEĞERLEME SENTEZİ (Finviz + Yahoo)
    valuation_note = ""
    if ev_ebitda:
        if pe > 0 and pe < 15 and ev_ebitda > 20:
             valuation_note = "🚨 **Uyarı:** F/K düşük ama EV/EBITDA yüksek. Borçluluk veya amortisman kaynaklı bir değer tuzağı olabilir."
        elif ev_ebitda < 10:
             valuation_note = "✅ **Onay:** EV/EBITDA rasyosu 10'un altında, şirket işletme değeri açısından da ucuz."
        else:
             valuation_note = f"ℹ️ **EV/EBITDA:** {ev_ebitda:.2f}"
    else:
        # PDYN gibi durumlar için
        valuation_note = "ℹ️ **EV/EBITDA:** Hesapla-namadı (Şirket zarar ediyor veya veri eksik)."

    comments.append(valuation_note)
    
    return comments

# --- ANA AKIŞ ---
if st.sidebar.button("Karar Destek Analizini Başlat"):
    with st.spinner("Finviz tüm piyasa taranıyor..."):
        df, url = get_finviz_data(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Bulundu")
    st.caption(f"Veri Kaynağı: {st.session_state.url}")
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([5, 4])
    
    with col1:
        st.subheader("📉 Teknik Grafik & İndikatörler")
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        yahoo_info = {}
        hist = pd.DataFrame()
        
        if tik:
            try:
                # Yahoo Veri Çekme (Lazy Load)
                stock = yf.Ticker(tik)
                hist = stock.history(period="1y")
                
                # Grafik oluşturmak için geçmiş veri şart
                if not hist.empty:
                    # İndikatörleri Hesapla
                    hist = calculate_indicators(hist)
                    
                    # GRAFİK ÇİZİMİ (Candlestick + MA) - v16 Tipi
                    fig = go.Figure()
                    
                    # Mum Grafiği
                    fig.add_trace(go.Candlestick(x=hist.index,
                                    open=hist['Open'], high=hist['High'],
                                    low=hist['Low'], close=hist['Close'],
                                    name='Fiyat'))
                    
                    # Hareketli Ortalamalar
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                    
                    fig.update_layout(title=f"{tik} - Teknik Analiz", height=500, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Yan Veri Çekme (Info)
                    try: yahoo_info = stock.info
                    except: yahoo_info = {}
                    
                else:
                    st.warning("Bu hisse için grafik verisi bulunamadı.")
            except Exception as e:
                st.error(f"Hata: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            
            # Finviz Satırı
            row = df[df['Ticker'] == tik].iloc[0]
            
            # Rapor Oluştur
            comments = generate_academic_report(tik, row, yahoo_info, hist)
            
            # Yorumları Yazdır
            for c in comments:
                st.info(c)
            
            st.markdown("---")
            # Risk Kartları
            last = hist.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Volatilite", f"%{last['Volatility']:.1f}")
            c2.metric("Max Drawdown", f"%{last['Drawdown']:.1f}")
            c3.metric("RSI (14)", f"{last['RSI']:.0f}")

elif st.session_state.scan_data.empty:
    st.info("👈 Sol menüden kriterleri seçip **'Karar Destek Analizini Başlat'** butonuna basınız.")
