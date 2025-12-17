import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Buffett Analiz v11.1", layout="wide")
st.title("📊 Akıllı Hisse Analizörü (Hata Korumalı)")
st.markdown("**Durum:** Yahoo Finance 'Rate Limit' hatasına karşı korumalı mod.")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YARDIMCI FONKSİYONLAR ---

def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def generate_commentary(ticker, row, history, info):
    """Yatırım Komitesi Yorumlayıcısı"""
    comments = []
    score = 0
    
    # Veri kontrolü (Boş gelirse işlem yapma)
    if history.empty:
        return ["Veri alınamadığı için yorum yapılamıyor."], 0, 0

    try:
        # 1. TEMEL ANALİZ
        pe_str = str(row.get('P/E', '-'))
        pe = float(pe_str) if pe_str != '-' else 0
        
        # Değerleme
        if 0 < pe < 15:
            comments.append(f"🟢 **Değerleme:** {pe} F/K ile makul/ucuz seviyede.")
            score += 1
        elif 15 <= pe < 25:
            comments.append(f"🟡 **Değerleme:** {pe} F/K ile piyasa ortalamasında.")
        elif pe >= 25:
            comments.append(f"🔴 **Değerleme:** {pe} F/K ile primli fiyatlanıyor.")

        # Kârlılık (Hata korumalı)
        roe = info.get('returnOnEquity', 0)
        if roe is not None and roe > 0.15:
            comments.append(f"🟢 **Kalite:** ROE %{roe*100:.1f} ile güçlü sermaye kârlılığı.")
            score += 1
        
        # Borç
        debt_eq = info.get('debtToEquity', None)
        if debt_eq and debt_eq < 50:
            comments.append("🟢 **Sağlık:** Düşük borçluluk yapısı.")
            score += 1

        # 2. TEKNİK ANALİZ
        if len(history) > 200:
            ma200 = history['Close'].rolling(200).mean().iloc[-1]
            curr = history['Close'].iloc[-1]
            if curr > ma200:
                comments.append("📈 **Trend:** Fiyat 200 günlük ortalamanın üzerinde (Pozitif).")
                score += 1
            else:
                comments.append("📉 **Trend:** Fiyat 200 günlük ortalamanın altında (Negatif).")

        # RSI
        rsi = calculate_rsi(history).iloc[-1]
        if rsi < 30: comments.append(f"💎 **RSI:** {rsi:.0f} (Aşırı Satım Bölgesi).")
        elif rsi > 70: comments.append(f"⚠️ **RSI:** {rsi:.0f} (Aşırı Alım Bölgesi).")
        
    except Exception as e:
        comments.append(f"Yorumlama sırasında hata: {str(e)}")
        
    return comments, score, 0

# --- Yan Menü ---
st.sidebar.header("🔍 Kriterler")
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5}
scan_limit = st.sidebar.selectbox("Tarama Limiti", list(limit_opts.keys()), index=1)
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)
pe_ratio = st.sidebar.selectbox("F/K Oranı", ["Any", "Low (<15)", "Under 20", "Under 25", "High (>50)", "Under 50", "Over 15"], index=0)
roe = st.sidebar.selectbox("ROE", ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%"], index=0)
dividend = st.sidebar.selectbox("Temettü", ["Any", "Positive (>0%)", "High (>5%)", "Over 2%"], index=0)

# --- Veri Motoru (Finviz) ---
def get_finviz_data(limit_count, exc, sec, mc, pe, roe_val, div):
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"s={sec_map[sec]}")
    if mc == "Mega ($200bln+)": filters.append("cap_mega")
    elif mc == "Large ($10bln+)": filters.append("cap_large")
    elif mc == "Mid ($2bln+)": filters.append("cap_mid")
    elif mc == "Small ($300mln+)": filters.append("cap_small")
    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 25": "fa_pe_u25", "High (>50)": "fa_pe_o50", "Under 50": "fa_pe_u50", "Over 15": "fa_pe_o15"}
    if pe in pe_map: filters.append(pe_map[pe])
    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    div_map = {"Positive (>0%)": "fa_div_pos", "High (>5%)": "fa_div_o5", "Over 2%": "fa_div_o2"}
    if div in div_map: filters.append(div_map[div])

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
                if len(rows) > 1 and 'No.' in rows[0].get_text() and 'Price' in rows[0].get_text():
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
        return final_df
    return pd.DataFrame()

# --- Ana Akış ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Piyasa taranıyor..."):
        df = get_finviz_data(scan_limit, exchange, sector, mcap, pe_ratio, roe, dividend)
        st.session_state.scan_data = df

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.dataframe(df, use_container_width=True)
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    # --- DEĞİŞKENLERİ ÖNCEDEN TANIMLA (NameError Koruması) ---
    hist = pd.DataFrame()
    comments = []
    score = 0
    
    with col1:
        st.subheader("📉 Teknik & Getiri")
        tik = st.selectbox("Analiz Edilecek Hisse:", df['Ticker'].tolist())
        
        if tik:
            try:
                # Yahoo'dan Veri Çekme (Rate Limit Riskli Bölge)
                hist = yf.download(tik, period="1y", progress=False)
                
                # Sütun Düzeltme
                if isinstance(hist.columns, pd.MultiIndex): 
                    hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty:
                    # Getiri Grafiği
                    start_p = hist['Close'].iloc[0]
                    hist['Return'] = ((hist['Close'] - start_p) / start_p) * 100
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Return'], fill='tozeroy', name='Getiri %', line=dict(color='#0068C9')))
                    fig.update_layout(title=f"{tik} - Kümülatif Getiri (%)", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Verileri Hesapla (Hata korumalı blok)
                    try:
                        row = df[df['Ticker'] == tik].iloc[0]
                        t_info = yf.Ticker(tik).info
                        comments, score, rsi_val = generate_commentary(tik, row, hist, t_info)
                    except Exception as e:
                        st.warning(f"Yahoo detay verisi çekilemedi (Rate Limit): {e}")
                        score = 0
                        comments = ["Veri çekilemediği için analiz yapılamadı."]
                        
                else: 
                    st.warning("Grafik verisi boş geldi.")
            except Exception as e: 
                st.error(f"Bağlantı Hatası: {e}")

    with col2:
        # Eğer veri başarıyla çekildiyse ve hist boş değilse göster
        if tik and not hist.empty:
            st.subheader("🧐 Akıllı Yatırım Özeti")
            
            # Skor Kartı
            st.write("Buffett Uygunluk Puanı:")
            stars = "⭐" * score + "⚪" * (4 - score)
            st.markdown(f"### {stars} ({score}/4)")
            
            st.markdown("---")
            st.markdown("#### 🧠 Analiz Notları")
            
            for comment in comments:
                st.markdown(comment)
            
            st.markdown("---")
            st.caption("Yapay zeka destekli yorum modülü.")
        elif tik:
             st.info("Veriler yüklenemediği için özet oluşturulamadı. Lütfen birkaç saniye bekleyip tekrar deneyin (Rate Limit).")

elif st.session_state.scan_data.empty:
    st.info("Sol menüden kriterleri seçip 'Sonuçları Getir' butonuna basın.")
