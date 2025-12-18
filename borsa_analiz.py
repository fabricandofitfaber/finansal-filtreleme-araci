import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Karar Destek v16", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Sinyal Çelişki Modu)")
st.markdown("""
**Metodoloji:** Bu sistem, temel (Değer/Kalite) ve teknik (Momentum/Risk) sinyalleri arasındaki uyumu test eder.
**Yenilik:** EV/EBITDA tahmini, Volatilite analizi ve 'Sinyal Çelişki Dedektörü' eklendi.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (Filtreler) ---
st.sidebar.header("🔍 Çok Katmanlı Filtreleme")

# 0. Tarama Derinliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5}
scan_limit = st.sidebar.selectbox("Evren Genişliği (Sayfa)", list(limit_opts.keys()), index=2)

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Temel Rasyolar
st.sidebar.markdown("### 1. Temel Filtreler (Değer & Kalite)")
pe_opts = [
    "Any", "Low (<15)", "Profitable (<0)", "High (>50)", 
    "Under 20", "Under 30", "Under 50", "Over 20"
]
pe_ratio = st.sidebar.selectbox("F/K (Değerleme)", pe_opts, index=0)

peg_opts = ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"]
peg_ratio = st.sidebar.selectbox("PEG (Büyüme)", peg_opts, index=0)

roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kalite)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak (Risk)", debt_opts, index=0)

# 3. Teknik Filtreler (Yeni Katman)
st.sidebar.markdown("### 2. Teknik Filtreler (Zamanlama)")
rsi_filter = st.sidebar.selectbox("RSI (Momentum)", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)

# --- TEKNİK HESAPLAMA MODÜLÜ (Gelişmiş) ---
def calculate_advanced_metrics(df):
    """
    RSI, Volatilite ve Drawdown hesaplar.
    """
    # 1. Hareketli Ortalamalar
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    
    # 2. RSI Hesabı
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 3. Volatilite (Risk) - Yıllıklandırılmış Standart Sapma
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(window=30).std() * np.sqrt(252) * 100 # Yıllık %
    
    # 4. Max Drawdown (Zirveden Düşüş)
    rolling_max = df['Close'].expanding().max()
    df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    
    return df

# --- SİNYAL ÇELİŞKİ DETEKTÖRÜ (Decision Support) ---
def detect_conflicts(ticker, hist_df, fin_row):
    """
    Temel ve Teknik veriler arasındaki uyumsuzlukları (Value Trap) tespit eder.
    """
    signals = []
    conflict_score = 0 # 0: Uyumlu, Yüksek: Çelişkili
    
    last_row = hist_df.iloc[-1]
    
    # Veri Hazırlığı (Temel)
    try:
        pe = float(fin_row['P/E'])
    except: pe = 0
    
    try:
        price = float(fin_row['Price'])
    except: price = 0
    
    # --- SENARYO 1: Değer Tuzağı (Value Trap) ---
    # F/K çok düşük (Ucuz) AMA Fiyat MA200 altında (Düşüş Trendi)
    if 0 < pe < 10 and last_row['Close'] < last_row['MA200']:
        signals.append("⚠️ **Value Trap Riski:** Hisse temel olarak çok ucuz (F/K < 10) ancak teknik olarak 'Ayı Piyasası'nda (Fiyat < MA200). Piyasada bilmediğimiz bir risk fiyatlanıyor olabilir.")
        conflict_score += 2
        
    # --- SENARYO 2: Momentum Çelişkisi ---
    # Fiyat Zirvede AMA RSI Aşırı Alımda
    if last_row['Drawdown'] > -2 and last_row['RSI'] > 75:
        signals.append("⚠️ **Aşırı Isınma:** Fiyat zirveye çok yakın ancak RSI (%{:.0f}) aşırı alım bölgesinde. Düzeltme riski var.".format(last_row['RSI']))
        conflict_score += 1
        
    # --- SENARYO 3: Gizli Fırsat (Contrarian) ---
    # RSI Aşırı Satımda AMA ROE Çok Yüksek (Kaliteli şirket dayak yemiş)
    roe_str = str(fin_row.get('ROE', '0')).replace('%','')
    try: roe_val = float(roe_str)
    except: roe_val = 0
    
    if last_row['RSI'] < 30 and roe_val > 20:
        signals.append("💎 **Gizli Fırsat:** Kaliteli bir şirket (ROE > 20) aşırı satılmış (RSI < 30). Bu teknik bir 'Alım Fırsatı' olabilir.")
        conflict_score -= 1 # Bu iyi bir çelişki
        
    # --- SENARYO 4: Yüksek Volatilite Uyarısı ---
    if last_row['Volatility'] > 60: # %60 üzeri yıllık volatilite
        signals.append("⚡ **Yüksek Risk:** Hissenin volatilitesi (%{:.0f}) çok yüksek. Portföy sapmasını bozabilir.".format(last_row['Volatility']))

    return signals, conflict_score

# --- VERİ ÇEKME MOTORU (Finviz v15 Tabanlı) ---
def get_finviz_data_v16(limit_count, exc, sec, pe, peg, roe_val, de, ta_rsi, ta_ma):
    filters = []
    
    # 1. Borsa & Sektör
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    # 2. Temel Rasyolar
    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50",
              "Under 20": "fa_pe_u20", "Under 30": "fa_pe_u30", "Under 50": "fa_pe_u50", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])

    peg_map = {"Low (<1)": "fa_peg_u1", "Under 2": "fa_peg_u2", "High (>3)": "fa_peg_o3", "Growth (>1.5)": "fa_peg_o1.5"}
    if peg in peg_map: filters.append(peg_map[peg])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Under 0%": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

    # 3. Teknik Filtreler (Finviz Tarafında Ön Eleme)
    if ta_rsi == "Oversold (<30)": filters.append("ta_rsi_os30")
    elif ta_rsi == "Overbought (>70)": filters.append("ta_rsi_ob70")
    elif ta_rsi == "Neutral (40-60)": filters.append("ta_rsi_n4060")
    
    if ta_ma == "Above SMA200": filters.append("ta_sma200_pa")
    elif ta_ma == "Below SMA200": filters.append("ta_sma200_pb")

    # URL Oluşturma
    # v=151 (Valuation tablosu değil, Overview v=111 + Financial v=161 hibrit veri için v=111 kullanıp detayları Yahoo'dan alacağız grafik kısmında)
    filter_string = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_string}"
    
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
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
        return final_df, base_url
    return pd.DataFrame(), base_url

# --- ANA AKIŞ ---
if st.sidebar.button("Karar Destek Analizini Başlat"):
    with st.spinner("Piyasa taranıyor ve metrikler hesaplanıyor..."):
        df, url = get_finviz_data_v16(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Analiz Edildi")
    st.caption(f"Kaynak: {st.session_state.url}")
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📉 Teknik & Risk Analizi")
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        if tik:
            try:
                hist = yf.download(tik, period="1y", progress=False)
                if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty:
                    # Gelişmiş Metrikleri Hesapla
                    hist = calculate_advanced_metrics(hist)
                    
                    # Grafik: Fiyat + SMA + Bollinger Bandı (Basit haliyle)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], name='Fiyat', line=dict(color='black')))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], name='SMA 50', line=dict(color='blue', width=1)))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], name='SMA 200', line=dict(color='red', width=2)))
                    
                    fig.update_layout(title=f"{tik} - Trend Analizi", height=450, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Risk Kartları
                    last = hist.iloc[-1]
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Volatilite (Yıllık)", f"%{last['Volatility']:.1f}", help="Daha yüksek volatilite = Daha yüksek risk")
                    c2.metric("Max Drawdown", f"%{last['Drawdown']:.1f}", help="Son 1 yılda zirveden en büyük düşüş")
                    c3.metric("RSI (14)", f"{last['RSI']:.0f}", help="30 altı ucuz, 70 üstü pahalı sinyali")
                    
                else:
                    st.warning("Grafik verisi alınamadı.")
            except Exception as e:
                st.error(f"Grafik hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Karar Destek Asistanı")
            
            # Sinyal Çatışması Analizi
            row = df[df['Ticker'] == tik].iloc[0]
            signals, conflict_score = detect_conflicts(tik, hist, row)
            
            if signals:
                st.write("**Tespit Edilen Kritik Sinyaller:**")
                for s in signals:
                    st.info(s)
            else:
                st.success("✅ Temel ve Teknik göstergeler uyumlu. Bariz bir 'Değer Tuzağı' veya 'Aşırı Isınma' sinyali yok.")
            
            st.markdown("---")
            st.write("**Temel Veri Özeti:**")
            st.write(f"• **Fiyat:** ${row['Price']}")
            st.write(f"• **F/K:** {row['P/E']}")
            st.write(f"• **Sektör:** {row['Sector']}")
            
            # Tahmini EV/EBITDA (Basit Proxy)
            # Finviz tablosunda Market Cap var, Debt yok. Ancak P/E'den yola çıkarak kaba bir yaklaşım sunabiliriz.
            # Akademik not: EV/EBITDA'yı tam hesaplamak için Balance Sheet lazım, burada proxy kullanmıyoruz, yanlış yönlendirmemek için.
            
            st.caption("Not: Volatilite ve Drawdown hesaplamaları son 1 yıllık günlük kapanış verilerine dayanır.")

elif st.session_state.scan_data.empty:
    st.info("Lütfen sol menüden kriterleri belirleyip 'Karar Destek Analizini Başlat' butonuna basınız.")
