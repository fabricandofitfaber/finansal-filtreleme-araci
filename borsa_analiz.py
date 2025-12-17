import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Pro Analiz v12", layout="wide")
st.title("📊 Pro Hisse Analiz (Lokal Filtreleme Modu)")
st.markdown("""
**Durum:** Yahoo .info iptal edildi (Rate Limit çözüldü). Veriler Finviz 'Financial' tablosundan çekiliyor.
**Filtreleme:** Sunucu tarafında değil, Python içinde yapılıyor (Kesin çalışır).
""")

# --- Session State ---
if 'raw_data' not in st.session_state:
    st.session_state.raw_data = pd.DataFrame()

# --- Yan Menü (Lokal Filtreler) ---
st.sidebar.header("🔍 1. Veri Çekme Ayarı")
limit_opts = {20: 1, 60: 3, 100: 5, 200: 10}
scan_limit = st.sidebar.selectbox("Kaç Hisse Çekilsin?", list(limit_opts.keys()), index=2, help="Önce ham veriyi çekiyoruz, sonra filtreliyoruz.")

st.sidebar.markdown("---")
st.sidebar.header("🌪️ 2. Filtreleme (Canlı)")

# Python İçinde Çalışan Filtreler
f_pe = st.sidebar.slider("Maksimum F/K", 0, 100, 50)
f_roe = st.sidebar.slider("Minimum ROE (%)", -50, 100, 0)
f_debt = st.sidebar.selectbox("Borç/Özkaynak", ["Tümü", "Düşük (<1)", "Orta (<2)", "Yüksek (>2)"], index=0)
f_margin = st.sidebar.slider("Net Kâr Marjı (%)", -50, 50, 0)

# --- Veri Motoru (Finviz Financial View) ---
def fetch_financial_data(pages_count):
    # v=161 : Financial View (Burada ROE, Borç, Marjlar hazır gelir)
    base_url = "https://finviz.com/screener.ashx?v=161"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    all_dfs = []
    prog_bar = st.progress(0)
    
    # Sayfaları Tara
    for i in range(1, pages_count * 20 + 1, 20): # 1, 21, 41...
        try:
            url = f"{base_url}&r={i}"
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Tablo Bulucu
            target = None
            for t in soup.find_all('table'):
                rows = t.find_all('tr')
                # Financial tabloda 'Ticker', 'P/E', 'ROE' sütunları olur
                if len(rows) > 1:
                    txt = rows[0].get_text()
                    if 'Ticker' in txt and 'ROE' in txt and 'Debt/Eq' in txt:
                        target = t
                        break
            
            if target:
                rows = target.find_all('tr')
                # Başlıkları dinamik al
                headers_list = [c.get_text(strip=True) for c in rows[0].find_all('td')]
                
                data = []
                for row in rows[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cols) == len(headers_list):
                        data.append(cols)
                
                if data:
                    all_dfs.append(pd.DataFrame(data, columns=headers_list))
            
            time.sleep(0.5) # Bekleme
            prog_bar.progress((i) / (pages_count * 20))
            
        except Exception:
            break
            
    prog_bar.empty()
    
    if all_dfs:
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
        return final_df
    return pd.DataFrame()

# --- Veri Temizleme ve Dönüştürme ---
def clean_dataframe(df):
    # Sayısallaştırma (String -> Float)
    cols_to_fix = ['P/E', 'ROE', 'Debt/Eq', 'Net M', 'Price']
    
    for col in cols_to_fix:
        if col in df.columns:
            # % işaretini ve virgülleri temizle
            df[col] = df[col].astype(str).str.replace('%', '').str.replace(',', '')
            # '-' olanları NaN yap, sonra sayıya çevir
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

# --- Ana Akış ---

# 1. BUTON: Veriyi Çek (Sadece bir kere basılır)
if st.sidebar.button("HAM VERİYİ İNDİR"):
    with st.spinner("Finansal tablolar çekiliyor..."):
        raw = fetch_financial_data(limit_opts[scan_limit])
        if not raw.empty:
            clean_raw = clean_dataframe(raw)
            st.session_state.raw_data = clean_raw
        else:
            st.error("Veri çekilemedi.")

# 2. FİLTRELEME VE GÖSTERİM (Otomatik çalışır)
if not st.session_state.raw_data.empty:
    df = st.session_state.raw_data.copy()
    
    # --- FİLTRELEME MANTIĞI (Pandas) ---
    # Burası Python tarafında çalıştığı için %100 kesindir.
    
    # F/K Filtresi
    df = df[(df['P/E'] > 0) & (df['P/E'] <= f_pe)]
    
    # ROE Filtresi
    df = df[df['ROE'] >= f_roe]
    
    # Marj Filtresi
    if 'Net M' in df.columns:
        df = df[df['Net M'] >= f_margin]
    
    # Borç Filtresi
    if f_debt == "Düşük (<1)":
        df = df[df['Debt/Eq'] < 1]
    elif f_debt == "Orta (<2)":
        df = df[df['Debt/Eq'] < 2]
    elif f_debt == "Yüksek (>2)":
        df = df[df['Debt/Eq'] >= 2]

    # --- SONUÇLAR ---
    st.success(f"Ham Veri: {len(st.session_state.raw_data)} | Filtrelenmiş: {len(df)}")
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        
        st.divider()
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📉 Teknik Grafik")
            tik = st.selectbox("Hisse Seç:", df['Ticker'].tolist())
            
            if tik:
                try:
                    # Sadece Fiyat Çekiyoruz (Yahoo Info YOK -> Rate Limit YOK)
                    hist = yf.download(tik, period="1y", progress=False)
                    if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                    hist.columns = [c.capitalize() for c in hist.columns]
                    
                    if not hist.empty:
                        fig = go.Figure(data=[go.Candlestick(x=hist.index,
                                        open=hist['Open'], high=hist['High'],
                                        low=hist['Low'], close=hist['Close'])])
                        fig.update_layout(height=400, title=f"{tik} Fiyat", xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Grafik verisi gelmedi.")
                except:
                    st.error("Grafik hatası.")

        with col2:
            if tik:
                st.subheader("🧬 Buffett Skoru")
                # Veriyi tablodan alıyoruz (Yahoo'ya sormuyoruz!)
                row = df[df['Ticker'] == tik].iloc[0]
                
                score = 0
                reasons = []
                
                # Puanlama (Eldeki veriye göre)
                pe = row['P/E']
                if 0 < pe < 20: 
                    score += 1
                    reasons.append("✅ F/K Makul (<20)")
                else:
                    reasons.append("❌ F/K Yüksek")
                    
                roe = row['ROE']
                if roe > 15:
                    score += 1
                    reasons.append("✅ ROE Güçlü (>%15)")
                else:
                    reasons.append("❌ ROE Zayıf")
                    
                deb = row['Debt/Eq']
                if deb < 1:
                    score += 1
                    reasons.append("✅ Borç Düşük (<1)")
                else:
                    reasons.append("❌ Borç Yüksek")
                
                if 'Net M' in row and row['Net M'] > 10:
                    score += 1
                    reasons.append("✅ Marj Yüksek (>%10)")
                
                # Yıldızlar
                st.markdown(f"### {'⭐'*score}{'⚪'*(4-score)}")
                for r in reasons:
                    st.write(r)
                
                st.info(f"Fiyat: ${row['Price']} | Sektör Bilgisi Tabloda")

    else:
        st.warning("Bu kriterlere uyan hisse kalmadı. Sol menüden filtreleri gevşetin.")
        
else:
    st.info("👈 Önce 'Ham Veriyi İndir' butonuna basın.")
