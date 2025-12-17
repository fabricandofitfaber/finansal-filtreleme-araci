import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v15", layout="wide")
st.title("📊 Akademik Piyasa Analizörü (Şeffaf Yorum Modu)")
st.markdown("""
**Yenilikler:** 1. **Kanıtlı Yorum:** Yorumların hangi matematiksel veriye dayandığı açıkça yazılır.
2. **Onarılmış Filtreler:** Sektör ve Rasyo filtreleri Finviz URL yapısına tam uyumlu hale getirildi.
""")

# --- Session State ---
if 'scan_data' not in st.session_state:
    st.session_state.scan_data = pd.DataFrame()

# --- YAN MENÜ (Filtreler) ---
st.sidebar.header("🔍 Hassas Filtreleme")

# 0. Tarama Derinliği
limit_opts = {20: 1, 40: 2, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Tarama Limiti (Sayfa Sayısı)", list(limit_opts.keys()), index=2)

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)

sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Değerleme Rasyoları
st.sidebar.markdown("### Değerleme")
pe_opts = [
    "Any", "Low (<15)", "Profitable (<0)", "High (>50)", 
    "Under 5", "Under 10", "Under 15", "Under 20", "Under 25", "Under 30", "Under 35", "Under 40", "Under 45", "Under 50", 
    "Over 15", "Over 20", "Over 30", "Over 50"
]
pe_ratio = st.sidebar.selectbox("F/K Oranı (P/E)", pe_opts, index=0)

pb_opts = ["Any", "Low (<1)", "Under 2", "Under 3", "High (>5)", "Over 5"]
pb_ratio = st.sidebar.selectbox("P/B Oranı (Defter Değeri)", pb_opts, index=0)

peg_opts = ["Any", "Low (<1)", "Under 2", "High (>3)", "Growth (>1.5)"]
peg_ratio = st.sidebar.selectbox("PEG (Büyüme/Değer)", peg_opts, index=0)

# 3. Finansal Sağlık & Temettü
st.sidebar.markdown("### Sağlık & Getiri")
roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%", "Under 0%"]
roe = st.sidebar.selectbox("ROE (Kârlılık)", roe_opts, index=0)

debt_opts = ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>1)"]
debt_eq = st.sidebar.selectbox("Borç/Özkaynak", debt_opts, index=0)

div_opts = ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)", "Over 2%", "Over 3%"]
dividend = st.sidebar.selectbox("Temettü Verimi", div_opts, index=0)

# --- TEKNİK HESAPLAMA MODÜLÜ ---
def calculate_technical_indicators(df):
    """RSI ve Hareketli Ortalamaları Hesaplar"""
    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    
    # RSI Hesabı
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    return df

# --- ŞEFFAF YORUM MOTORU ---
def generate_transparent_commentary(ticker, df_hist):
    """Veriyi kanıtıyla birlikte yorumlar"""
    comments = []
    
    last_row = df_hist.iloc[-1]
    curr_price = last_row['Close']
    start_price = df_hist['Close'].iloc[0]
    
    # 1. Getiri Analizi (Kanıtlı)
    total_return = ((curr_price - start_price) / start_price) * 100
    evidence = f"(Güncel: ${curr_price:.2f} vs Başlangıç: ${start_price:.2f})"
    
    if total_return > 30:
        comments.append(f"🚀 **Yüksek Getiri:** Hisse son 1 yılda **%{total_return:.1f}** değer kazanmıştır {evidence}. Bu, piyasa ortalamasının (genelde %10-15) çok üzerindedir.")
    elif total_return > 0:
        comments.append(f"📈 **Pozitif Getiri:** Hisse **%{total_return:.1f}** getiri ile yılı artıda götürmektedir {evidence}.")
    else:
        comments.append(f"📉 **Negatif Getiri:** Yatırımcılar son 1 yılda **%{total_return:.1f}** zarar etmiştir {evidence}.")

    # 2. Trend Analizi (MA50 Kanıtlı)
    ma50 = last_row['MA50']
    if pd.notna(ma50):
        if curr_price > ma50:
            diff = ((curr_price - ma50) / ma50) * 100
            comments.append(f"✅ **Kısa Vadeli Trend:** Fiyat (${curr_price:.2f}), 50 günlük ortalamasının (${ma50:.2f}) üzerindedir. Ortalamadan **%{diff:.1f}** yukarıda olması alıcıların güçlü olduğunu gösterir.")
        else:
            diff = ((ma50 - curr_price) / ma50) * 100
            comments.append(f"⚠️ **Trend Zayıflığı:** Fiyat (${curr_price:.2f}), 50 günlük ortalamasının (${ma50:.2f}) altına sarkmıştır.")

    # 3. RSI Analizi (Kanıtlı)
    rsi = last_row['RSI']
    if pd.notna(rsi):
        if rsi < 30:
            comments.append(f"💎 **Aşırı Satım (Fırsat?):** RSI göstergesi **{rsi:.0f}** seviyesindedir. 30'un altı teknik analizde genelde 'aşırı satım' olarak yorumlanır ve tepki yükselişi beklenebilir.")
        elif rsi > 70:
            comments.append(f"🔥 **Aşırı Alım (Risk):** RSI göstergesi **{rsi:.0f}** seviyesindedir. 70'in üzeri hissenin çok hızlı yükseldiğini ve kâr satışı gelebileceğini işaret eder.")
        else:
            comments.append(f"⚖️ **Nötr Bölge:** RSI **{rsi:.0f}** seviyesiyle dengeli bir bölgededir (30-70 arası normal kabul edilir).")

    return comments

# --- VERİ ÇEKME MOTORU (Düzeltilmiş URL Yapısı) ---
def get_finviz_data_v15(limit_count, exc, sec, pe, pb, peg, roe_val, de, div):
    filters = []
    
    # 1. Borsa
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    
    # 2. Sektör (DÜZELTİLDİ: Artık 'f' parametresine ekleniyor)
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": filters.append(f"{sec_map[sec]}")

    # 3. Rasyolar
    pe_map = {"Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50",
              "Under 5": "fa_pe_u5", "Under 10": "fa_pe_u10", "Under 15": "fa_pe_u15", "Under 20": "fa_pe_u20",
              "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "Under 35": "fa_pe_u35", "Under 40": "fa_pe_u40",
              "Under 45": "fa_pe_u45", "Under 50": "fa_pe_u50", "Over 15": "fa_pe_o15", "Over 20": "fa_pe_o20",
              "Over 30": "fa_pe_o30", "Over 50": "fa_pe_o50"}
    if pe in pe_map: filters.append(pe_map[pe])

    pb_map = {"Low (<1)": "fa_pb_u1", "Under 2": "fa_pb_u2", "Under 3": "fa_pb_u3", "High (>5)": "fa_pb_o5", "Over 5": "fa_pb_o5"}
    if pb in pb_map: filters.append(pb_map[pb])
    
    peg_map = {"Low (<1)": "fa_peg_u1", "Under 2": "fa_peg_u2", "High (>3)": "fa_peg_o3", "Growth (>1.5)": "fa_peg_o1.5"}
    if peg in peg_map: filters.append(peg_map[peg])

    roe_map = {"Positive (>0%)": "fa_roe_pos", "High (>15%)": "fa_roe_o15", "Very High (>20%)": "fa_roe_o20", "Over 30%": "fa_roe_o30", "Under 0%": "fa_roe_neg"}
    if roe_val in roe_map: filters.append(roe_map[roe_val])
    
    de_map = {"Low (<0.1)": "fa_debteq_u0.1", "Under 0.5": "fa_debteq_u0.5", "Under 1": "fa_debteq_u1", "High (>1)": "fa_debteq_o1"}
    if de in de_map: filters.append(de_map[de])

    div_map = {"Positive (>0%)": "fa_div_pos", "High (>5%)": "fa_div_o5", "Very High (>10%)": "fa_div_o10", "Over 2%": "fa_div_o2", "Over 3%": "fa_div_o3"}
    if div in div_map: filters.append(div_map[div])

    # URL Oluşturma
    filter_string = ",".join(filters)
    base_url = f"https://finviz.com/screener.ashx?v=111&f={filter_string}"
    
    # Veri Çekme (Sayfalama)
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
                break # Tablo yoksa döngüyü kır
                
            time.sleep(0.5)
            prog_bar.progress((i + 1) / len(pages))
        except: break
            
    prog_bar.empty()
    if all_dfs:
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
        return final_df, base_url
    return pd.DataFrame(), base_url

# --- ANA AKIŞ ---
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner("Piyasa taranıyor..."):
        df, url = get_finviz_data_v15(scan_limit, exchange, sector, pe_ratio, pb_ratio, peg_ratio, roe, debt_eq, dividend)
        st.session_state.scan_data = df
        st.session_state.url = url

if not st.session_state.scan_data.empty:
    df = st.session_state.scan_data
    st.success(f"✅ {len(df)} Şirket Listelendi")
    st.caption(f"Veri Kaynağı: {st.session_state.url}")
    st.dataframe(df, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📉 Teknik Analiz")
        tik = st.selectbox("Analiz İçin Hisse Seç:", df['Ticker'].tolist())
        
        hist = pd.DataFrame()
        if tik:
            try:
                hist = yf.download(tik, period="1y", progress=False)
                if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty:
                    # İndikatörleri Hesapla
                    hist = calculate_technical_indicators(hist)
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], name='Fiyat'))
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['MA50'], name='50 Günlük Ort.', line=dict(width=1, dash='dash')))
                    fig.update_layout(title=f"{tik} - Fiyat ve Ortalama", height=450)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Grafik verisi alınamadı.")
            except Exception as e:
                st.error(f"Grafik hatası: {e}")

    with col2:
        if tik and not hist.empty:
            st.subheader("🧐 Şeffaf Yorumlar")
            st.caption("Aşağıdaki yorumlar, sol taraftaki grafikten hesaplanan matematiksel verilere dayanır.")
            
            comments = generate_transparent_commentary(tik, hist)
            
            for c in comments:
                st.info(c)
                
            st.markdown("---")
            row = df[df['Ticker'] == tik].iloc[0]
            st.write(f"**Sektör:** {row['Sector']}")
            st.write(f"**Fiyat:** {row['Price']}")
            st.write(f"**F/K:** {row['P/E']}")

elif st.session_state.scan_data.empty:
    st.info("Lütfen filtreleri ayarlayıp 'Sonuçları Getir' butonuna basınız.")
