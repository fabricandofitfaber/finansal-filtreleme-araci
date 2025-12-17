import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Piyasa Analiz v14", layout="wide")
st.title("📊 Sınırsız Hisse Tarama & Teknik Yorum")
st.markdown("**Kaynak:** Finviz (Tüm Piyasalar) | **Odak:** Getiri Grafiği ve Yorumu")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- Yan Menü (Genişletilmiş Filtreler) ---
st.sidebar.header("🔍 Detaylı Filtreler")

# 0. Tarama Derinliği (Pagination)
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Tarama Limiti", list(limit_opts.keys()), index=2)

# 1. Borsa
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

# 2. Sektör
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 3. F/K (P/E)
pe_opts = ["Any", "Low (<15)", "Under 20", "Under 25", "High (>50)", "Under 50", "Over 15"]
pe_ratio = st.sidebar.selectbox("F/K Oranı", pe_opts, index=0)

# 4. ROE
roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%"]
roe = st.sidebar.selectbox("ROE", roe_opts, index=0)

# --- Yorumlayıcı Fonksiyon ---
def interpret_technical(ticker, return_series, current_price, ma50):
    """Grafik hareketine göre yorum üretir"""
    comments = []
    
    # 1. Getiri Performansı
    total_return = return_series.iloc[-1]
    if total_return > 50:
        comments.append(f"🚀 **Güçlü Performans:** {ticker}, son 1 yılda **%{total_return:.1f}** getiri sağlayarak piyasayı ezip geçmiş. Momentum çok yüksek.")
    elif total_return > 20:
        comments.append(f"📈 **Pozitif Trend:** Hissenin yıllık getirisi **%{total_return:.1f}**. İstikrarlı bir yükseliş sergiliyor.")
    elif total_return < -20:
        comments.append(f"📉 **Düşüş Trendi:** Hisse son bir yılda **%{total_return:.1f}** değer kaybetmiş. Satış baskısı hakim.")
    else:
        comments.append(f"⚖️ **Yatay Seyir:** Getiri **%{total_return:.1f}** seviyesinde. Hisse belirgin bir yön bulmakta zorlanıyor.")

    # 2. Hareketli Ortalama (Trend)
    if current_price > ma50:
        comments.append("✅ **Kısa Vadeli Trend:** Fiyat, 50 günlük ortalamasının üzerinde. Bu, alıcıların hala istekli olduğunu gösterir.")
    else:
        comments.append("⚠️ **Kısa Vadeli Trend:** Fiyat, 50 günlük ortalamasının altına sarkmış. Kısa vadede zayıflık sinyali.")

    return comments

# --- Veri Motoru (Finviz Pagination - Cerrah Modu) ---
def get_finviz_data(limit_count, exc, sec, pe, roe_val):
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"s={sec_map[sec]}")
    
    pe_map = {"Low (<15)": "fa_pe_u15", "Under 20": "fa_pe_u20", "Under 25": "fa_pe_u25", "High (>50)": "fa_pe_o50", "Under 50": "fa_pe_u50", "Over 15": "fa_pe_o15"}
    if pe in pe_map: filters.append(pe_map[pe])
    
    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])

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
            
            # Doğru Tabloyu Bul (Cerrah Yöntemi)
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
        return final_df
    return pd.DataFrame()

# --- Ana Akış ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner(f"Finviz taranıyor... ({scan_limit} hisse)"):
        df = get_finviz_data(scan_limit, exchange, sector, pe_ratio, roe)
        st.session_state.scan_data = df

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi (Tüm Piyasa)")
    st.dataframe(df, use_container_width=True)
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    # --- DEĞİŞKEN TANIMLARI ---
    hist = pd.DataFrame()
    
    with col1:
        st.subheader("📉 Teknik Grafik & Getiri")
        tik = st.selectbox("Hisse Seç:", df['Ticker'].tolist())
        
        if tik:
            try:
                # Yahoo'dan Grafik Verisi (Rate Limit yemeyen kısım)
                hist = yf.download(tik, period="1y", progress=False)
                
                # Sütun Yaması (Fix)
                if isinstance(hist.columns, pd.MultiIndex): 
                    hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty and 'Close' in hist.columns:
                    # Getiri Hesabı
                    start_p = hist['Close'].iloc[0]
                    hist['Return'] = ((hist['Close'] - start_p) / start_p) * 100
                    
                    fig = go.Figure()
                    # Getiri Çizgisi
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Return'], fill='tozeroy', name='Getiri %', line=dict(color='#0068C9')))
                    fig.update_layout(title=f"{tik} - Kümülatif Getiri (%)", height=400, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                    
                else: 
                    st.warning("Grafik verisi boş geldi.")
            except Exception as e: 
                st.error(f"Grafik Hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧐 Teknik Yorum")
            
            # Yorumlayıcıyı Çalıştır
            try:
                curr_price = hist['Close'].iloc[-1]
                ma50 = hist['Close'].rolling(50).mean().iloc[-1]
                
                comments = interpret_technical(tik, hist['Return'], curr_price, ma50)
                
                for c in comments:
                    st.info(c)
                    
            except Exception as e:
                st.error("Yorumlanamadı.")
            
            st.markdown("---")
            # Temel Bilgiler (Tablodan)
            row = df[df['Ticker'] == tik].iloc[0]
            st.write(f"**Şirket:** {row['Company']}")
            st.metric("Fiyat", row['Price'], row['Change'])
            st.metric("F/K", row['P/E'])

elif st.session_state.scan_data.empty:
    st.info("👈 Kriterleri seçip 'Sonuçları Getir' butonuna basın.")
