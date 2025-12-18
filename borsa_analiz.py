import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v28", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Akıllı FCF Modu)")
st.markdown("""
**Yenilik:** Nakit Akışı (FCF) verisi için 'Akıllı Eşleşme' algoritması eklendi.
**Kapsam:** Tüm Piyasa Taraması + Kesin Bilanço Verisi.
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

st.sidebar.markdown("### 1. Temel Filtreler")
pe_ratio = st.sidebar.selectbox("F/K", ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Under 50", "Over 20"], index=0)
peg_ratio = st.sidebar.selectbox("PEG", ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"], index=0)
roe = st.sidebar.selectbox("ROE", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Under 0%"], index=0)
debt_eq = st.sidebar.selectbox("Borç/Özkaynak", ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"], index=0)

st.sidebar.markdown("### 2. Teknik Filtreler")
rsi_filter = st.sidebar.selectbox("RSI", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)

# --- YARDIMCI: AKILLI VERİ BULUCU ---
def find_value_in_df(df, keywords):
    """
    DataFrame indekslerinde anahtar kelimeleri arar (Büyük/küçük harf duyarsız).
    Örn: 'operating' ve 'cash' kelimelerini içeren satırı bulur.
    """
    for index_name in df.index:
        name_str = str(index_name).lower()
        if all(k in name_str for k in keywords):
            return df.loc[index_name]
    return None

# --- HESAPLAMA MOTORU (v28 - Fuzzy Logic) ---
def fetch_robust_metrics(ticker):
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Source': '-'}
    
    try:
        stock = yf.Ticker(ticker)
        
        # 1. FCF HESAPLAMA (Öncelikli)
        try:
            cf = stock.cashflow
            if not cf.empty:
                # En güncel sütun (ilk sütun)
                curr_cf = cf.iloc[:, 0]
                
                # Akıllı Arama: İsmi ne olursa olsun bul
                ocf = find_value_in_df(curr_cf, ['operating', 'cash'])
                capex = find_value_in_df(curr_cf, ['capital', 'expenditure'])
                
                # Eğer bulamazsa 'investing' içinden ara
                if capex is None:
                    capex = find_value_in_df(curr_cf, ['purchase', 'property']) # PPE alımı

                if ocf is not None:
                    # Capex genelde negatiftir. FCF = OCF - |Capex|
                    capex_val = abs(capex) if capex is not None else 0
                    metrics['FCF'] = ocf - capex_val
        except:
            pass
            
        # Yedek FCF (Info'dan)
        if metrics['FCF'] is None:
             metrics['FCF'] = stock.info.get('freeCashflow')

        # 2. EV/EBITDA HESAPLAMA
        try:
            # Önce hazır
            metrics['EV/EBITDA'] = stock.info.get('enterpriseToEbitda')
            
            # Yoksa Manuel
            if metrics['EV/EBITDA'] is None:
                mcap = stock.fast_info['market_cap']
                bs = stock.balance_sheet
                inc = stock.income_stmt
                
                if not bs.empty and not inc.empty:
                    curr_bs = bs.iloc[:, 0]
                    curr_inc = inc.iloc[:, 0]
                    
                    debt = find_value_in_df(curr_bs, ['total', 'debt'])
                    if debt is None: debt = find_value_in_df(curr_bs, ['long', 'debt'])
                    
                    cash = find_value_in_df(curr_bs, ['cash', 'equivalents'])
                    if cash is None: cash = find_value_in_df(curr_bs, ['cash'])
                    
                    ebitda = find_value_in_df(curr_inc, ['ebitda'])
                    if ebitda is None: 
                        # EBIT + Amortisman (Basit Yaklaşım)
                        ebit = find_value_in_df(curr_inc, ['ebit'])
                        dep = find_value_in_df(stock.cashflow.iloc[:,0], ['depreciation'])
                        if ebit and dep: ebitda = ebit + dep
                    
                    if mcap and ebitda and ebitda > 0:
                        debt_val = debt if debt is not None else 0
                        cash_val = cash if cash is not None else 0
                        ev = mcap + debt_val - cash_val
                        metrics['EV/EBITDA'] = ev / ebitda
                        metrics['Source'] = 'Bilanço (Manuel)'
        except:
            pass
            
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

# --- BÜTÜNÇÜL YORUM MOTORU ---
def generate_holistic_report(ticker, finviz_row, metrics, hist):
    last = hist.iloc[-1]
    curr = last['Close']
    ma200 = last['MA200']
    rsi = last['RSI']
    evebitda = metrics.get('EV/EBITDA')
    fcf = metrics.get('FCF')
    dd = last['Drawdown']
    
    # NİHAİ KANAAT
    st.markdown("#### 🏛️ Yönetici Özeti (Nihai Kanaat)")
    
    sentiment = "NÖTR / İZLE"
    color = "blue"
    reason = "Verilerde belirgin bir fırsat veya risk sinyali ayrışmıyor."
    
    is_uptrend = curr > ma200
    is_cheap = (evebitda and evebitda < 12)
    has_cash = (fcf and fcf > 0)
    is_expensive = (evebitda and evebitda > 20)
    
    if is_uptrend:
        if is_cheap and has_cash:
            sentiment = "GÜÇLÜ ALIM (Growth at Reasonable Price)"
            color = "green"
            reason = "Mükemmel Senaryo: Hisse yükseliş trendinde, temel olarak ucuz ve nakit üretiyor."
        elif is_expensive:
            sentiment = "TUT / KÂR AL (Pahalı Momentum)"
            color = "orange"
            reason = "Trend çok güçlü ancak değerleme (EV/EBITDA) şişmiş. Yeni alım riskli olabilir, trend takip edilmeli."
        else:
            sentiment = "ALIM (Trend Takibi)"
            color = "green"
            reason = "Değerleme makul, trend pozitif. Nakit akışı destekliyor."
    else: # Düşüş Trendi
        if is_cheap and has_cash:
            sentiment = "DEĞER YATIRIMI (Uzun Vade Toplama)"
            color = "blue"
            reason = "Hisse teknik olarak düşüşte (ayı piyasası) ancak temel verileri (Nakit ve Çarpanlar) çok cazip. Sabırlı yatırımcı için fırsat."
        elif not is_cheap:
            sentiment = "SAT / UZAK DUR"
            color = "red"
            reason = "Hisse hem düşüş trendinde hem de pahalı. Düşen bıçak."

    st.markdown(f":{color}-background[**{sentiment}**]")
    st.caption(f"**Gerekçe:** {reason}")
    st.markdown("---")
    
    # DETAYLAR
    c1, c2 = st.columns(2)
    
    with c1:
        st.write("**Teknik Görünüm:**")
        trend_label = "Yükseliş (Boğa)" if is_uptrend else "Düşüş (Ayı)"
        st.write(f"• **Trend:** {trend_label} (Fiyat MA200 üstünde)")
        st.write(f"• **Momentum (RSI):** {rsi:.0f}")
        st.write(f"• **Risk (Drawdown):** %{dd:.1f}")
        
    with c2:
        st.write("**Temel Görünüm:**")
        if evebitda:
            val_lbl = "Ucuz" if evebitda < 10 else ("Pahalı" if evebitda > 20 else "Makul")
            st.write(f"• **EV/EBITDA:** {evebitda:.2f} ({val_lbl})")
        else:
            st.write("• **EV/EBITDA:** -")
            
        if fcf:
            st.write(f"• **FCF (Nakit):** ${fcf/1e9:.2f} Milyar")
        else:
            st.write("• **FCF:** -")
            
        st.write(f"• **F/K:** {finviz_row.get('P/E', '-')}")

# --- FİNVİZ TARAYICI (v26) ---
def get_finviz_v28(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
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
        df, url = get_finviz_v28(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
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
            with st.spinner(f"{tik} için Bilanço analizi (FCF & EV/EBITDA) yapılıyor..."):
                try:
                    adv = fetch_robust_metrics(tik)
                    stock = yf.Ticker(tik)
                    hist = stock.history(period="1y")
                    
                    if not hist.empty:
                        hist = calculate_ta(hist)
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist.index, y=hist['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(height=500, title=f"{tik} - Teknik Görünüm", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi bulunamadı.")
                except Exception as e:
                    st.error(f"Hata: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            fin_row = df[df['Ticker'] == tik].iloc[0]
            generate_holistic_report(tik, fin_row, adv, hist)
            st.markdown("---")
            st.caption("Not: FCF verisi Bilanço'daki 'Operating Cash Flow' ve 'Capex' kalemlerinden hesaplanmıştır.")

elif st.session_state.scan_data.empty:
    st.info("👈 Filtreleri ayarlayıp 'Analizi Başlat' butonuna basın.")
