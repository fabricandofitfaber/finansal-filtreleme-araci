import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np
import re

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v40", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (EV/EBITDA Fix)")
st.markdown("""
**Düzeltme:** EV/EBITDA verisi için 3 katmanlı (Hazır Veri -> Parçalı Veri -> Manuel Hesap) algoritma kuruldu.
**Durum:** Tüm modüller (Haberler, Dedektif, Sözel Analiz) aktiftir.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ ---
st.sidebar.header("🔍 Filtreleme Paneli")
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5}
scan_limit = st.sidebar.selectbox("Evren Genişliği", list(limit_opts.keys()), index=2)

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

# --- YARDIMCI: GOOGLE TRANSLATE ---
@st.cache_data(show_spinner=False)
def translate_to_turkish(text):
    if text == "Bulunamadı" or not text: return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "en", "tl": "tr", "dt": "t", "q": text}
        r = requests.get(url, params=params, timeout=3)
        if r.status_code == 200:
            result = r.json()
            full_translation = ""
            for sentence in result[0]:
                if sentence[0]: full_translation += sentence[0]
            return full_translation
    except: pass
    return text

# --- YARDIMCI FONKSİYONLAR ---
def find_value_in_df(df, keywords):
    """DataFrame içinde anahtar kelime arar ve bulduğu ilk değeri döner."""
    if df is None or df.empty: return None
    for index_name in df.index:
        name_str = str(index_name).lower()
        if all(k in name_str for k in keywords):
            val = df.loc[index_name]
            if isinstance(val, pd.Series): return val.iloc[0]
            return val
    return None

def format_currency(val):
    if val is None: return "-"
    abs_val = abs(val)
    if abs_val >= 1e9: return f"${val/1e9:.2f} Milyar"
    if abs_val >= 1e6: return f"${val/1e6:.2f} Milyon"
    return f"${val:,.2f}"

# --- ANALİZ MOTORU 1: HABER ÖZETİ ---
def generate_news_summary(news_list):
    if not news_list: return "Yorumlanacak güncel haber akışı bulunamadı.", "gray"
    score = 0
    pos_keywords = ['beat', 'surge', 'jump', 'gain', 'profit', 'growth', 'positive', 'up', 'high', 'partnership', 'expand', 'launch', 'approve', 'buy', 'dividend', 'strong', 'reaffirm', 'tops', 'broke out']
    neg_keywords = ['miss', 'fall', 'drop', 'loss', 'down', 'decline', 'negative', 'low', 'lawsuit', 'investigation', 'cut', 'fail', 'weak', 'risk', 'compliance']
    titles = " ".join([n['Title'].lower() for n in news_list])
    for word in pos_keywords:
        if word in titles: score += 1
    for word in neg_keywords:
        if word in titles: score -= 1
    if score > 1: return "Son dönemdeki haber akışı ağırlıklı olarak **POZİTİF**. Büyüme ve beklenti üzeri sonuçlar öne çıkıyor.", "green"
    elif score < -1: return "Son dönemdeki haber akışı ağırlıklı olarak **NEGATİF**. Düşüş ve risk unsurları dikkat çekiyor.", "red"
    else: return "Haber akışı **DENGELİ/NÖTR** seyrediyor.", "blue"

# --- ANALİZ MOTORU 2: DEDEKTİF ---
@st.cache_data(ttl=1800) 
def generate_skeptic_analysis(ticker):
    analysis = []
    time.sleep(1.0) 
    try:
        stock = yf.Ticker(ticker)
        inc = stock.income_stmt
        if inc is None or inc.empty: return ["Finansal detay verisi sağlanamadı."]
        if inc.shape[1] > 1:
            curr_rev = find_value_in_df(inc.iloc[:, 0], ['total', 'revenue'])
            prev_rev = find_value_in_df(inc.iloc[:, 1], ['total', 'revenue'])
            curr_net = find_value_in_df(inc.iloc[:, 0], ['net', 'income'])
            prev_net = find_value_in_df(inc.iloc[:, 1], ['net', 'income'])
            if curr_rev and prev_rev and curr_rev < prev_rev:
                if curr_net and prev_net and curr_net > prev_net:
                    analysis.append("✂️ **Kemer Sıkma:** Ciro düşerken Net Kâr artmış. Küçülerek kâr ediliyor.")
            if curr_rev and prev_rev and curr_rev > (prev_rev * 1.20):
                if curr_net and curr_net < 0:
                    analysis.append("🚀 **Büyüme Sancısı:** Ciro hızla artıyor (%20+) ancak şirket zarar ediyor.")
    except Exception: return ["Dedektif analizi atlandı."]
    return analysis

# --- ANALİZ MOTORU 3: SÖZEL FİNANSAL ANALİZ ---
@st.cache_data(ttl=3600)
def generate_verbal_financial_analysis(ticker):
    analysis = []
    time.sleep(0.5)
    try:
        stock = yf.Ticker(ticker)
        inc = stock.income_stmt
        bs = stock.balance_sheet
        if not inc.empty and not bs.empty:
            curr_inc = inc.iloc[:, 0]
            curr_bs = bs.iloc[:, 0]
            rev = find_value_in_df(curr_inc, ['total', 'revenue'])
            gp = find_value_in_df(curr_inc, ['gross', 'profit'])
            if rev and gp:
                margin = (gp / rev) * 100
                desc = "Çok Yüksek" if margin > 70 else ("Sağlıklı" if margin > 40 else "Düşük")
                analysis.append(f"📊 **Gelir Yapısı:** Şirket **{format_currency(rev)}** ciro üzerinden **{format_currency(gp)}** brüt kâr elde etmiştir. Marj: **%{margin:.1f}** ({desc}).")
            net = find_value_in_df(curr_inc, ['net', 'income'])
            if net:
                if net > 0: analysis.append(f"💰 **Net Kârlılık:** **{format_currency(net)}** net kâr (Pozitif).")
                else: analysis.append(f"⚠️ **Kârlılık:** **{format_currency(net)}** net zarar.")
            op_inc = find_value_in_df(curr_inc, ['operating', 'income']) or find_value_in_df(curr_inc, ['operating', 'profit'])
            if op_inc: analysis.append(f"⚙️ **Operasyonel Güç:** Faaliyet Kârı **{format_currency(op_inc)}**.")
            cash = find_value_in_df(curr_bs, ['cash']) or 0
            debt = find_value_in_df(curr_bs, ['total', 'debt']) or find_value_in_df(curr_bs, ['long', 'debt']) or 0
            analysis.append(f"🛡️ **Bilanço:** Nakit: **{format_currency(cash)}** | Borç: **{format_currency(debt)}**.")
            if cash > debt: analysis.append(f"✅ **Nakit Zengini:** Net Nakit Pozisyonu (**{format_currency(cash-debt)}**).")
            else: analysis.append(f"⚡ **Borçluluk:** Borçlar nakitten fazla.")
        else: analysis.append("Finansal veriler eksik.")
    except Exception: return ["Veri çekilemedi."]
    return analysis

# --- FİNVİZ HABER ---
@st.cache_data(ttl=1800)
def get_finviz_news_profile(ticker):
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = {"Profile": "Bulunamadı", "News": []}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        profile_td = soup.find("td", class_="fullview-profile")
        if profile_td: 
            raw_profile = profile_td.get_text(strip=True)
            data["Profile"] = translate_to_turkish(raw_profile)
        news_table = soup.find("table", id="news-table")
        if news_table:
            rows = news_table.find_all("tr")
            for row in rows[:8]:
                cols = row.find_all("td")
                if len(cols) > 1:
                    date_str = cols[0].get_text(strip=True)
                    headline = cols[1].get_text(strip=True)
                    link = cols[1].find("a")['href']
                    data["News"].append({"Date": date_str, "Title": headline, "Link": link})
    except: pass
    return data

# --- METRİKLER VE TEKNİK (DÜZELTİLEN YER) ---
def fetch_robust_metrics(ticker):
    metrics = {'EV/EBITDA': None, 'FCF': None, 'Source': '-'}
    try:
        stock = yf.Ticker(ticker)
        
        # --- ADIM 1: FCF (Nakit Akışı) ---
        try:
            cf = stock.cashflow
            if not cf.empty:
                curr_cf = cf.iloc[:, 0]
                ocf = find_value_in_df(curr_cf, ['operating', 'cash']) or find_value_in_df(curr_cf, ['operating', 'activities'])
                capex = find_value_in_df(curr_cf, ['capital', 'expenditure']) or find_value_in_df(curr_cf, ['purchase', 'property']) or 0
                if ocf is not None: metrics['FCF'] = ocf - abs(capex)
        except: pass
        if metrics['FCF'] is None: metrics['FCF'] = stock.info.get('freeCashflow')

        # --- ADIM 2: EV/EBITDA (KESİN ÇÖZÜM) ---
        
        # YÖNTEM A: Önce Hazır Veriyi Kontrol Et (En Güveniliri)
        ev_ebitda_info = stock.info.get('enterpriseToEbitda')
        if ev_ebitda_info and ev_ebitda_info > 0:
            metrics['EV/EBITDA'] = ev_ebitda_info
            metrics['Source'] = 'Yahoo Info'
            return metrics # Bulduysan dön, daha fazla uğraşma

        # YÖNTEM B: Hazır Bileşenlerden Hesapla
        ev_info = stock.info.get('enterpriseValue')
        ebitda_info = stock.info.get('ebitda')
        if ev_info and ebitda_info and ebitda_info > 0:
            metrics['EV/EBITDA'] = ev_info / ebitda_info
            metrics['Source'] = 'Yahoo Parçalı Hesap'
            return metrics

        # YÖNTEM C: Manuel İnşaat (Son Çare)
        mcap = stock.fast_info.get('market_cap')
        if mcap:
            bs = stock.balance_sheet
            inc = stock.income_stmt
            if not bs.empty and not inc.empty:
                curr_bs = bs.iloc[:, 0]; curr_inc = inc.iloc[:, 0]
                
                # EV Hesabı
                debt = find_value_in_df(curr_bs, ['total', 'debt'])
                if debt is None:
                    debt = (find_value_in_df(curr_bs, ['long', 'debt']) or 0) + (find_value_in_df(curr_bs, ['short', 'debt']) or 0)
                cash = find_value_in_df(curr_bs, ['cash', 'equivalents']) or 0
                ev_calc = mcap + (debt or 0) - cash
                
                # EBITDA Hesabı
                ebitda_calc = find_value_in_df(curr_inc, ['normalized', 'ebitda'])
                if ebitda_calc is None: ebitda_calc = find_value_in_df(curr_inc, ['ebitda'])
                if ebitda_calc is None:
                    op_inc = find_value_in_df(curr_inc, ['operating', 'income']) or 0
                    dep = find_value_in_df(stock.cashflow.iloc[:, 0], ['depreciation']) or 0 if not stock.cashflow.empty else 0
                    if op_inc: ebitda_calc = op_inc + dep
                
                if ev_calc and ebitda_calc and ebitda_calc > 0:
                    metrics['EV/EBITDA'] = ev_calc / ebitda_calc
                    metrics['Source'] = 'Bilanço (Manuel)'

    except Exception: pass
    return metrics

def calculate_ta(df):
    df = df.copy()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    delta = df['Close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss; df['RSI'] = 100 - (100 / (1 + rs))
    df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
    df['Volatility'] = df['Log_Ret'].rolling(30).std() * np.sqrt(252) * 100
    rolling_max = df['Close'].expanding().max(); df['Drawdown'] = (df['Close'] - rolling_max) / rolling_max * 100
    return df

def generate_technical_synthesis(hist):
    last = hist.iloc[-1]; curr = last['Close']; ma200 = last['MA200']; rsi = last['RSI']; dd = last['Drawdown']
    trend_txt = "Veri Yetersiz."
    if pd.notna(ma200):
        if curr > ma200: trend_txt = "Hisse, uzun vadeli hareketli ortalamasının (MA200) üzerinde seyrederek ana yönün **Yükseliş (Boğa)** trendinde olduğunu teyit etmektedir."
        else: trend_txt = "Hisse, 200 günlük ortalamasının altında fiyatlanarak **Düşüş (Ayı)** trendi baskısı altındadır."
    mom_txt = f"Momentum RSI: **{rsi:.0f}**."
    risk_txt = f" Zirveden düşüş **%{abs(dd):.1f}**."
    return f"{trend_txt} {mom_txt} {risk_txt}"

def generate_holistic_report(ticker, finviz_row, metrics, hist):
    last = hist.iloc[-1]; curr = last['Close']; ma200 = last['MA200']; evebitda = metrics.get('EV/EBITDA'); fcf = metrics.get('FCF')
    is_uptrend = curr > (ma200 if pd.notna(ma200) else 0)
    valuation = "Bilinmiyor"
    if evebitda and evebitda > 0:
        if evebitda < 12: valuation = "Ucuz"
        elif evebitda <= 20: valuation = "Makul"
        else: valuation = "Pahalı"
    sentiment = "NÖTR"; color = "blue"; reason = "Veri yetersiz."
    if is_uptrend:
        if valuation == "Ucuz": sentiment = "GÜÇLÜ ALIM"; color = "green"; reason = "Trend Yukarı + EV/EBITDA < 12 (Kelepir)"
        elif valuation == "Makul": sentiment = "KALİTELİ TREND"; color = "green"; reason = "Trend Yukarı + EV/EBITDA 12-20 Arası"
        elif valuation == "Pahalı": sentiment = "MOMENTUM (Pahalı)"; color = "orange"; reason = "Trend Yukarı + EV/EBITDA > 20"
        else: sentiment = "SPEKÜLATİF"; color = "blue"; reason = "Trend Yukarı (Veri Yok)"
    else:
        if valuation == "Ucuz": sentiment = "DEĞER YATIRIMI"; color = "blue"; reason = "Trend Aşağı + EV/EBITDA < 10"
        elif valuation == "Pahalı": sentiment = "SAT / UZAK DUR"; color = "red"; reason = "Hem düşüşte hem pahalı."
        else: sentiment = "ZAYIF GÖRÜNÜM"; color = "red"
    
    st.markdown(f"#### 🏛️ Yönetici Özeti: :{color}[{sentiment}]")
    st.info(f"**Gerekçe:** {reason}")
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📉 Teknik Göstergeler**")
        st.write(f"• **Trend:** {'Yükseliş (Boğa)' if is_uptrend else 'Düşüş (Ayı)'}")
        st.write(f"• **RSI (14):** {last['RSI']:.0f}")
        st.write(f"• **Volatilite:** %{last['Volatility']:.1f}")
        st.write(f"• **Max Drawdown:** %{last['Drawdown']:.1f}")
    
    with c2:
        st.markdown("**💰 Temel Göstergeler**")
        val_str = f"{evebitda:.2f}" if evebitda else "-"
        st.write(f"• **EV/EBITDA:** {val_str} ({valuation})")
        fcf_str = f"${fcf/1e9:.2f}B" if fcf else "-"
        st.write(f"• **FCF (Nakit):** {fcf_str}")
        st.write(f"• **F/K:** {finviz_row.get('P/E', '-')}")
    st.markdown("---")

# --- FİNVİZ TARAYICI ---
def get_finviz_v40(limit_count, exc, sec, pe, peg, roe_val, de, rsi_val, ma_val):
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
    
    base_url = f"https://finviz.com/screener.ashx?v=111&f={','.join(filters)}"
    headers = {'User-Agent': 'Mozilla/5.0'}
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
                    if 'No.' in txt and 'Ticker' in txt and 'Price' in txt: target = t; break
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
        df, url = get_finviz_v40(scan_limit, exchange, sector, pe_ratio, peg_ratio, roe, debt_eq, rsi_filter, price_ma)
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
        time_period = c_opt.selectbox("Süre", ["1 Ay", "3 Ay", "6 Ay", "1 Yıl", "3 Yıl", "5 Yıl"], index=3)
        tik = st.selectbox("Detaylı Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        if tik:
            with st.spinner(f"{tik} detaylı analiz ediliyor..."):
                try:
                    adv = fetch_robust_metrics(tik)
                    stock = yf.Ticker(tik)
                    hist_long = stock.history(period="5y") 
                    if not hist_long.empty:
                        hist_long = calculate_ta(hist_long)
                        if time_period == "1 Ay": slice_days = 30
                        elif time_period == "3 Ay": slice_days = 90
                        elif time_period == "6 Ay": slice_days = 180
                        elif time_period == "1 Yıl": slice_days = 365
                        elif time_period == "3 Yıl": slice_days = 365*3
                        else: slice_days = 365*5
                        hist_view = hist_long.tail(slice_days)
                        
                        if not hist_view.empty:
                            start_p = hist_view['Close'].iloc[0]
                            end_p = hist_view['Close'].iloc[-1]
                            ret_pct = ((end_p - start_p) / start_p) * 100
                            m1, m2, m3 = st.columns(3)
                            m1.metric("Dönem Başı", f"${start_p:.2f}")
                            m2.metric("Dönem Sonu", f"${end_p:.2f}")
                            m3.metric(f"{time_period} Getirisi", f"%{ret_pct:.1f}", delta=f"{ret_pct:.1f}%")
                        
                        fig = go.Figure()
                        fig.add_trace(go.Candlestick(x=hist_view.index, open=hist_view['Open'], high=hist_view['High'], low=hist_view['Low'], close=hist_view['Close'], name='Fiyat'))
                        fig.add_trace(go.Scatter(x=hist_view.index, y=hist_view['MA50'], line=dict(color='blue', width=1), name='SMA 50'))
                        fig.add_trace(go.Scatter(x=hist_view.index, y=hist_view['MA200'], line=dict(color='orange', width=2), name='SMA 200'))
                        fig.update_layout(title=f"{tik} - {time_period} Grafik", height=500, xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else: st.warning("Veri bulunamadı.")
                except Exception as e: st.error(f"Hata: {e}")

    with col2:
        if tik and not hist_long.empty:
            tab_main, tab_news, tab_verbal = st.tabs(["📊 Karar Raporu", "📰 Haber Analizi", "💬 Sözel & Dedektif"])
            fin_row = df[df['Ticker'] == tik].iloc[0]
            
            with tab_main:
                st.subheader("🧠 Akademik Karar Raporu")
                generate_holistic_report(tik, fin_row, adv, hist_long)
                st.markdown("#### 📝 Teknik Görünüm Sentezi")
                st.write(generate_technical_synthesis(hist_long))
                with st.expander("ℹ️ Karar Kategorileri Kılavuzu"):
                    st.markdown("""
                    * 🟢 **GÜÇLÜ ALIM:** Trend Yukarı + EV/EBITDA < 12
                    * 🟢 **KALİTELİ TREND:** Trend Yukarı + EV/EBITDA 12-20
                    * 🟠 **MOMENTUM:** Trend Yukarı + EV/EBITDA > 20
                    * 🔵 **DEĞER YATIRIMI:** Trend Aşağı + EV/EBITDA < 10
                    * 🔵 **SPEKÜLATİF:** Trend Yukarı (Veri Yok)
                    """)
            
            with tab_news:
                st.subheader("Şirket Profili & Haberler")
                with st.spinner("Haberler analiz ediliyor..."):
                    finviz_data = get_finviz_news_profile(tik)
                    st.markdown("### 🏢 Şirket Profili (Türkçe)")
                    st.caption(finviz_data.get('Profile', 'Bulunamadı'))
                    
                    st.markdown("### 🗞️ Haber Akışı Özeti")
                    summary_text, summary_color = generate_news_summary(finviz_data['News'])
                    st.markdown(f":{summary_color}-background[{summary_text}]")
                    
                    with st.expander("Orijinal Haber Kaynakları (İngilizce)"):
                        for n in finviz_data['News']:
                            st.markdown(f"**{n['Date']}** | [{n['Title']}]({n['Link']})")
            
            with tab_verbal:
                st.subheader("🕵️ Dedektif Modu")
                skeptic_comments = generate_skeptic_analysis(tik)
                if skeptic_comments:
                    for s in skeptic_comments: st.warning(s)
                else: st.success("Bariz bir olumsuzluk tespit edilmedi.")
                
                st.markdown("---")
                st.subheader("💬 Sözel Finansal Analiz")
                from_v35 = generate_verbal_financial_analysis(tik)
                for s in from_v35: st.info(s)

elif st.session_state.scan_data.empty:
    st.info("👈 Analize başlamak için sol menüdeki **'Analizi Başlat'** butonuna basınız.")
