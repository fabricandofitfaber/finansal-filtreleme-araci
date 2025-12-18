import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v29", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Zaman & Sentez)")
st.markdown("""
**Yenilik:** Dinamik Grafik Süresi (1 Ay - 5 Yıl) ve **Bütünçül Teknik Sentez** yorumu.
**Kapsam:** Tüm Piyasa + Kesin Bilanço Verisi (FCF).
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
pe_ratio = st.sidebar.selectbox("F/K", ["Any", "Low (<15)", "Profitable (<0)", "High (>50)", "Under 20", "Under 30", "Over 20"], index=0)
peg_ratio = st.sidebar.selectbox("PEG", ["Any", "Low (<1)", "Under 2", "High (>3)"], index=0)
roe = st.sidebar.selectbox("ROE", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)"], index=0)
debt_eq = st.sidebar.selectbox("Borç/Özkaynak", ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"], index=0)

st.sidebar.markdown("### 2. Teknik Filtreler")
rsi_filter = st.sidebar.selectbox("RSI", ["Any", "Oversold (<30)", "Overbought (>70)", "Neutral (40-60)"], index=0)
price_ma = st.sidebar.selectbox("Fiyat vs MA200", ["Any", "Above SMA200", "Below SMA200"], index=0)

# --- YARDIMCI: AKILLI VERİ BULUCU (Fuzzy Logic) ---
def find_value_in_df(df, keywords):
    for index_name in df.index:
        name_str = str(index_name).lower()
        if all(k in name_str for k in keywords):
            return df.loc[index_name]
    return None

# --- HESAPLAMA MOTORU ---
def fetch_robust_metrics(ticker):
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Source': '-'}
    try:
        stock = yf.Ticker(ticker)
        # 1. FCF HESAPLAMA
        try:
            cf = stock.cashflow
            if not cf.empty:
                curr_cf = cf.iloc[:, 0]
                ocf = find_value_in_df(curr_cf, ['operating', 'cash'])
                capex = find_value_in_df(curr_cf, ['capital', 'expenditure'])
                if capex is None: capex = find_value_in_df(curr_cf, ['purchase', 'property'])
                
                if ocf is not None:
                    capex_val = abs(capex) if capex is not None else 0
                    metrics['FCF'] = ocf - capex_val
        except: pass
        if metrics['FCF'] is None: metrics['FCF'] = stock.info.get('freeCashflow')

        # 2. EV/EBITDA HESAPLAMA
        try:
            metrics['EV/EBITDA'] = stock.info.get('enterpriseToEbitda')
            if metrics['EV/EBITDA'] is None:
                mcap = stock.fast_info['market_cap']
                bs = stock.balance_sheet
                inc = stock.income_stmt
                if not bs.empty and not inc.empty:
                    curr_bs = bs.iloc[:, 0]; curr_inc = inc.iloc[:, 0]
                    debt = find_value_in_df(curr_bs, ['total', 'debt']) or find_value_in_df(curr_bs, ['long', 'debt']) or 0
                    cash = find_value_in_df(curr_bs, ['cash', 'equivalents']) or find_value_in_df(curr_bs, ['cash']) or 0
                    ebitda = find_value_in_df(curr_inc, ['ebitda'])
                    if ebitda is None:
                        ebit = find_value_in_df(curr_inc, ['ebit'])
                        dep = find_value_in_df(stock.cashflow.iloc[:,0], ['depreciation'])
                        if ebit and dep: ebitda = ebit + dep
                    
                    if mcap and ebitda and ebitda > 0:
                        metrics['EV/EBITDA'] = (mcap + debt - cash) / ebitda
                        metrics['Source'] = 'Bilanço (Manuel)'
        except: pass
    except: pass
    return metrics

# --- İNDİKATÖRLER ---
def calculate_ta(df):
    df = df.copy()
    # En az 2 yıllık veri çektiğimiz için MA200 hesaplanabilir
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

# --- YENİ: TEKNİK SENTEZ YORUMCU ---
def generate_technical_synthesis(hist):
    """Teknik verileri birleştirip akıcı bir paragraf yazar."""
    last = hist.iloc[-1]
    curr = last['Close']
    ma50 = last['MA50']
    ma200 = last['MA200']
    rsi = last['RSI']
    dd = last['Drawdown']
    
    # 1. Ana Trend Cümlesi
    if pd.notna(ma200):
        if curr > ma200:
            trend_txt = "Hisse, uzun vadeli hareketli ortalamasının (MA200) üzerinde seyrederek ana yönün **Yükseliş (Boğa)** trendinde olduğunu teyit etmektedir."
            if curr < ma50: trend_txt += " Ancak kısa vadede 50 günlük ortalamanın altına sarkması, trend içinde bir **düzeltme/dinlenme** sürecinde olunduğunu gösterir."
            else: trend_txt += " Fiyatın 50 günlük ortalamanın da üzerinde olması, kısa vadeli momentumun da güçlü korunduğuna işaret eder."
        else:
            trend_txt = "Hisse, 200 günlük ortalamasının altında fiyatlanarak **Düşüş (Ayı)** trendi baskısı altındadır."
            if curr > ma50: trend_txt += " Ancak son dönemde 50 günlük ortalamanın üzerine çıkması, bir **tepki yükselişi** veya taban oluşumu çabası olarak yorumlanabilir."
    else:
        trend_txt = "Hisse için yeterli geçmiş veri (200 gün) oluşmadığı için uzun vadeli trend analizi yapılamamaktadır."

    # 2. Momentum ve Risk Cümlesi
    mom_txt = f"Momentum tarafında RSI göstergesi **{rsi:.0f}** seviyesindedir."
    if rsi < 30: mom_txt += " Bu seviye 'Aşırı Satım' bölgesidir ve teknik olarak tepki alımları için potansiyel bir fırsat sunabilir."
    elif rsi > 70: mom_txt += " Bu seviye 'Aşırı Alım' bölgesidir ve fiyatın çok hızlı yükseldiğini, kâr realizasyonu riskinin arttığını gösterir."
    else: mom_txt += " Gösterge şu an nötr bölgededir ve trendin devamını destekleyen dengeli bir yapıdadır."
    
    risk_txt = f" Risk açısından bakıldığında, hisse son 1 yılın zirvesinden **%{abs(dd):.1f}** oranında bir geri çekilme yaşamıştır."
    if abs(dd) < 10: risk_txt += " Bu sınırlı geri çekilme, hissenin düşüşlere karşı dirençli olduğunu gösterir."
    elif abs(dd) > 30: risk_txt += " Bu yüksek kayıp oranı, hissenin volatil ve riskli bir yapıda olduğunu, toparlanmanın zaman alabileceğini ifade eder."

    return f"{trend_txt} {mom_txt} {risk_txt}"

# --- FİNVİZ TARAYICI ---
def get_finviz_v29(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50", "Under 20": "fa_pe_u20", "Under 30": "fa_pe_u30", "Over 20": "fa_pe_o20"}
    if pe in pe_map: filters.append(pe_map[pe])
    
    peg_map = {"Low (<1)": "fa_peg_u1", "Under 2": "fa_peg_u2", "High (>3)": "fa_peg_o3"}
    if peg in peg_map: filters.append(peg_map[peg])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20"}
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
        df, url = get_finviz_v29(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.dataframe(df, use_container_width=True)
    st.divider()
    
    col1, col2 = st.columns([5, 4])
    
    with col1:
        c_head, c_opt = st.columns([2, 1])
        c_head.subheader("📉 Teknik Grafik")
        
        # Grafik Süresi Seçimi
        time_period = c_opt.selectbox("Süre", ["1 Ay", "3 Ay", "6 Ay", "1 Yıl", "3 Yıl", "5 Yıl"], index=3)
        time_map = {"1 Ay": "1mo", "3 Ay": "3mo", "6 Ay": "6mo", "1 Yıl": "1y", "3 Yıl": "3y", "5 Yıl": "5y"}
        
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        adv = {}
        
        if tik:
            with st.spinner(f"{tik} analiz ediliyor..."):
                try:
                    adv = fetch_robust_metrics(tik)
                    stock = yf.Ticker(tik)
                    
                    # ÖNEMLİ: İndikatörler için her zaman uzun veri (2 yıl) çekilir
                    # Görüntüleme için ise filtrelenir.
                    hist_long = stock.history(period="5y") 
                    
                    if not hist_long.empty:
                        hist_long = calculate_ta(hist_long)
                        
                        # Grafiği kullanıcının seçtiği süreye göre kes (Slice)
                        if time_period == "1 Ay": slice_days = 30
                        elif time_period == "3 Ay": slice_days = 90
                        elif time_period == "6 Ay": slice_days = 180
                        elif time_period == "1 Yıl": slice_days = 365
                        elif time_period == "3 Yıl": slice_days = 365*3
                        else: slice_days = 365*5
                        
                        # Son X günü al
                        hist_view = hist_long.tail(slice_days)
                        
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist_view.index, open=hist_view['Open'], high=hist_view['High'], low=hist_view['Low'], close=hist_view['Close'], name='Fiyat'))
                        
                        # Ortalamaları her zaman göster (Data varsa)
                        fig.add_trace(go.Scatter(x=hist_view.index, y=hist_view['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist_view.index, y=hist_view['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        
                        fig.update_layout(title=f"{tik} - {time_period} Grafik", height=500, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Veri bulunamadı.")
                except Exception as e:
                    st.error(f"Hata: {e}")

    with col2:
        if tik and not hist_long.empty:
            st.subheader("🧠 Akademik Karar Raporu")
            fin_row = df[df['Ticker'] == tik].iloc[0]
            
            # 1. YÖNETİCİ ÖZETİ
            evebitda = adv.get('EV/EBITDA')
            fcf = adv.get('FCF')
            curr = hist_long['Close'].iloc[-1]
            ma200 = hist_long['MA200'].iloc[-1]
            
            is_uptrend = curr > ma200
            is_cheap = (evebitda and evebitda < 12)
            has_cash = (fcf and fcf > 0)
            
            sentiment = "NÖTR"
            color = "blue"
            if is_uptrend and is_cheap and has_cash:
                sentiment = "GÜÇLÜ ALIM ADAYI"
                color = "green"
            elif not is_uptrend and is_cheap:
                sentiment = "DEĞER YATIRIMI (Düşüş Trendinde)"
                color = "orange"
            elif is_uptrend and not is_cheap:
                sentiment = "MOMENTUM (Pahalı)"
                color = "orange"
            
            st.markdown(f"#### 🏛️ Yönetici Özeti: :{color}[{sentiment}]")
            
            # 2. TEKNİK SENTEZ (YENİ PARAGRAF)
            st.markdown("#### 📝 Teknik Görünüm Sentezi")
            synthesis = generate_technical_synthesis(hist_long)
            st.info(synthesis)
            
            st.markdown("---")
            
            # 3. MADDELER HALİNDE VERİLER
            c_tech, c_fund = st.tabs(["Teknik Detaylar", "Temel Detaylar"])
            
            with c_tech:
                last = hist_long.iloc[-1]
                st.write(f"• **Trend:** {'Boğa' if is_uptrend else 'Ayı'} (Fiyat vs MA200)")
                st.write(f"• **RSI (14):** {last['RSI']:.0f}")
                st.write(f"• **Max Drawdown:** %{last['Drawdown']:.1f}")
                st.write(f"• **Volatilite:** %{last['Volatility']:.1f}")
            
            with c_fund:
                st.write(f"• **Fiyat:** ${fin_row['Price']}")
                if evebitda: st.write(f"• **EV/EBITDA:** {evebitda:.2f}")
                else: st.write("• **EV/EBITDA:** -")
                
                if fcf: st.write(f"• **FCF (Nakit):** ${fcf/1e9:.2f} Milyar")
                else: st.write("• **FCF:** -")
                
                st.write(f"• **F/K:** {fin_row.get('P/E', '-')}")

elif st.session_state.scan_data.empty:
    st.info("👈 Analize başlamak için sol menüdeki **'Analizi Başlat'** butonuna basınız.")
