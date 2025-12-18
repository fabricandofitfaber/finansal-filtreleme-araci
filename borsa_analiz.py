import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from bs4 import BeautifulSoup
import time
import numpy as np

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Analiz v17", layout="wide")
st.title("📊 Akademik Karar Destek Sistemi (Ultimate Merge)")
st.markdown("""
**Yöntem:** Veri Birleştirme (Join). Overview + Valuation + Financial tabloları tek bir veri setinde birleştirilir.
**Yeni Metrikler:** EV/EBITDA, P/B, Marjlar, Borçluluk.
""")

# --- Session State ---
if 'merged_data' not in st.session_state:
    st.session_state.merged_data = pd.DataFrame()

# --- YAN MENÜ (Gelişmiş Filtreler) ---
st.sidebar.header("🛠️ Veri Motoru")
scan_pages = st.sidebar.select_slider("Tarama Derinliği (Sayfa)", options=[1, 2, 3, 5], value=2, help="Her sayfa 20 hissedir. Süre: Sayfa başına ~4 sn.")

# --- FİLTRELER (Veri geldikten sonra aktifleşir) ---
st.sidebar.markdown("---")
st.sidebar.header("🔍 Akademik Filtreler")

# 1. Borsa & Sektör
exchange = st.sidebar.selectbox("Borsa", ["Any", "AMEX", "NASDAQ", "NYSE"], index=0)
sector_list = ["Any", "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy", "Financial", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities"]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Değerleme (EV/EBITDA Burada!)
st.sidebar.subheader("1. Değerleme")
f_pe = st.sidebar.slider("Maksimum F/K", 0, 100, 40)
f_evebitda = st.sidebar.slider("Maksimum EV/EBITDA", 0, 50, 30, help="Düşük olması (örn < 10) şirketin ucuz olduğunu gösterir. Borç yapısını dikkate alır.")

# 3. Kalite
st.sidebar.subheader("2. Kalite & Risk")
f_roe = st.sidebar.slider("Minimum ROE (%)", -50, 100, 0)
f_debt = st.sidebar.selectbox("Borç/Özkaynak Risk", ["Tümü", "Güvenli (<1)", "Riskli (>2)"], index=0)
f_margin = st.sidebar.slider("Min Net Kâr Marjı (%)", -50, 50, 0)

# --- YARDIMCI: HTML TABLO ÇEKİCİ (Cerrah Modu) ---
def fetch_table_from_soup(soup, required_cols):
    """Verilen soup içinden istenen sütunları içeren tabloyu bulur ve DF döndürür."""
    for t in soup.find_all('table'):
        rows = t.find_all('tr')
        if len(rows) > 1:
            header_txt = rows[0].get_text()
            # Aradığımız sütunlar başlıkta var mı?
            if all(col in header_txt for col in required_cols):
                # Tabloyu bulduk, parse edelim
                data = []
                # Başlıkları al
                headers = [c.get_text(strip=True) for c in rows[0].find_all('td')]
                
                for row in rows[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all('td')]
                    if len(cols) == len(headers):
                        data.append(cols)
                
                return pd.DataFrame(data, columns=headers)
    return pd.DataFrame()

# --- ANA MOTOR: MULTI-FETCH & MERGE ---
def get_ultimate_data(pages_count, exc, sec):
    # 1. URL Parametreleri
    filters = []
    if exc != "Any": filters.append(f"exch_{exc.lower()}")
    sec_map = {"Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices", "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive", "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare", "Industrials": "sec_industrials", "Real Estate": "sec_realestate", "Technology": "sec_technology", "Utilities": "sec_utilities"}
    if sec != "Any": filters.append(f"{sec_map[sec]}")
    filter_str = ",".join(filters)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    master_data = []
    prog_bar = st.progress(0)
    status = st.empty()
    
    for i in range(pages_count):
        row_num = i * 20 + 1
        status.text(f"Sayfa {i+1}/{pages_count} taranıyor... (Overview + Valuation + Financial)")
        
        try:
            # A) OVERVIEW (Fiyat, Hacim, Sektör) - v=111
            url_overview = f"https://finviz.com/screener.ashx?v=111&f={filter_str}&r={row_num}"
            r1 = requests.get(url_overview, headers=headers, timeout=10)
            df_overview = fetch_table_from_soup(BeautifulSoup(r1.text, 'html.parser'), ['Ticker', 'Price', 'Company'])
            
            # B) VALUATION (EV/EBITDA, PEG, P/B) - v=121
            time.sleep(0.5) # Nezaket
            url_val = f"https://finviz.com/screener.ashx?v=121&f={filter_str}&r={row_num}"
            r2 = requests.get(url_val, headers=headers, timeout=10)
            df_val = fetch_table_from_soup(BeautifulSoup(r2.text, 'html.parser'), ['Ticker', 'EV/EBITDA', 'P/B'])
            
            # C) FINANCIAL (ROE, Debt, Margins) - v=161
            time.sleep(0.5)
            url_fin = f"https://finviz.com/screener.ashx?v=161&f={filter_str}&r={row_num}"
            r3 = requests.get(url_fin, headers=headers, timeout=10)
            df_fin = fetch_table_from_soup(BeautifulSoup(r3.text, 'html.parser'), ['Ticker', 'ROE', 'Debt/Eq'])
            
            # --- MERGE İŞLEMİ (Sihirli Kısım) ---
            if not df_overview.empty and not df_val.empty and not df_fin.empty:
                # Sadece gerekli sütunları alalım ki karmaşa olmasın
                # Overview Ana Tablo
                
                # Valuation'dan ekle
                cols_val = ['Ticker', 'EV/EBITDA', 'P/B', 'PEG', 'P/S'] # Varsa al
                available_val = [c for c in cols_val if c in df_val.columns]
                df_merged = pd.merge(df_overview, df_val[available_val], on='Ticker', how='inner')
                
                # Financial'dan ekle
                cols_fin = ['Ticker', 'ROE', 'Debt/Eq', 'Gross M', 'Oper M', 'Profit M']
                available_fin = [c for c in cols_fin if c in df_fin.columns]
                df_merged = pd.merge(df_merged, df_fin[available_fin], on='Ticker', how='inner')
                
                master_data.append(df_merged)
            
        except Exception as e:
            # Bir sayfa hata verirse devam et
            continue
            
        prog_bar.progress((i + 1) / pages_count)
        
    status.empty()
    prog_bar.empty()
    
    if master_data:
        return pd.concat(master_data).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
    return pd.DataFrame()

# --- VERİ TEMİZLEME (String -> Float) ---
def clean_numeric_data(df):
    # Temizlenecek sütunlar
    cols = ['P/E', 'Price', 'Change', 'EV/EBITDA', 'P/B', 'ROE', 'Debt/Eq', 'Profit M']
    
    for c in cols:
        if c in df.columns:
            # % ve , temizle
            df[c] = df[c].astype(str).str.replace('%', '').str.replace(',', '')
            # '-' işaretini NaN yap ve sayıya çevir
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df

# --- UI AKIŞI ---

if st.sidebar.button("ANALİZİ BAŞLAT (3 Tablolu Tarama)"):
    with st.spinner("Finviz veri tabanları birleştiriliyor... Lütfen bekleyiniz."):
        raw_df = get_ultimate_data(scan_pages, exchange, sector)
        if not raw_df.empty:
            clean_df = clean_numeric_data(raw_df)
            st.session_state.merged_data = clean_df
        else:
            st.error("Veri çekilemedi. Finviz yanıt vermiyor olabilir.")

# --- SONUÇ VE FİLTRELEME ---
if not st.session_state.merged_data.empty:
    df = st.session_state.merged_data.copy()
    
    # LOKAL FİLTRELEME (Python Tarafında)
    # 1. F/K
    df = df[(df['P/E'] > 0) & (df['P/E'] <= f_pe)]
    # 2. EV/EBITDA
    if 'EV/EBITDA' in df.columns:
        # 0'dan büyükleri al (negatifler anlamsız olabilir)
        df = df[(df['EV/EBITDA'] > 0) & (df['EV/EBITDA'] <= f_evebitda)]
    # 3. ROE
    if 'ROE' in df.columns:
        df = df[df['ROE'] >= f_roe]
    # 4. Borç
    if 'Debt/Eq' in df.columns:
        if f_debt == "Güvenli (<1)": df = df[df['Debt/Eq'] < 1]
        elif f_debt == "Riskli (>2)": df = df[df['Debt/Eq'] > 2]
    # 5. Marj
    if 'Profit M' in df.columns: # Net Kar Marjı
        df = df[df['Profit M'] >= f_margin]

    # --- TABLO ---
    st.success(f"Analiz Tamamlandı: {len(df)} şirket kriterlerinize uyuyor.")
    
    # Gösterilecek Sütunları Seç (Temiz Görünüm)
    display_cols = ['Ticker', 'Company', 'Sector', 'Price', 'P/E', 'EV/EBITDA', 'ROE', 'Debt/Eq', 'Profit M']
    # Mevcut olanları filtrele
    final_cols = [c for c in display_cols if c in df.columns]
    
    st.dataframe(df[final_cols].style.format({
        'Price': '{:.2f}', 'P/E': '{:.2f}', 'EV/EBITDA': '{:.2f}', 
        'ROE': '{:.2f}%', 'Debt/Eq': '{:.2f}', 'Profit M': '{:.2f}%'
    }), use_container_width=True)
    
    st.divider()
    
    # --- KARAR DESTEK KARTLARI ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📉 Teknik & Getiri")
        tik = st.selectbox("Detaylı Analiz:", df['Ticker'].tolist())
        
        if tik:
            try:
                hist = yf.download(tik, period="1y", progress=False)
                if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                hist.columns = [c.capitalize() for c in hist.columns]
                
                if not hist.empty:
                    # Kümülatif Getiri
                    start_p = hist['Close'].iloc[0]
                    hist['Return'] = ((hist['Close'] - start_p) / start_p) * 100
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['Return'], fill='tozeroy', name='Getiri %', line=dict(color='#0068C9')))
                    fig.update_layout(height=400, title=f"{tik} - Yıllık Getiri Performansı", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except:
                st.error("Grafik oluşturulamadı.")

    with col2:
        if tik:
            st.subheader("🧠 Akademik Değerlendirme")
            row = df[df['Ticker'] == tik].iloc[0]
            
            # --- EV/EBITDA YORUMU ---
            evebitda = row.get('EV/EBITDA', 0)
            pe = row.get('P/E', 0)
            
            st.info(f"**Değerleme Analizi:**")
            if evebitda > 0:
                if evebitda < 10:
                    st.write(f"✅ **EV/EBITDA ({evebitda}):** Şirket nakit akışına göre çok ucuz. Olası bir devralma hedefi olabilir.")
                elif evebitda > 20:
                    st.write(f"⚠️ **EV/EBITDA ({evebitda}):** Piyasa şirketin gelecekteki büyümesini şimdiden fiyatlamış görünüyor.")
                else:
                    st.write(f"⚖️ **EV/EBITDA ({evebitda}):** Makul değerleme aralığında.")
            
            # ÇELİŞKİ ANALİZİ (P/E vs EV/EBITDA)
            if pe > 0 and evebitda > 0:
                if pe < 15 and evebitda > 20:
                    st.warning("🚨 **Sinyal Çelişkisi:** F/K düşük ama EV/EBITDA yüksek. Bu durum şirketin bilançosunda YÜKSEK BORÇ yükü olduğuna işaret edebilir. Değer tuzağına dikkat!")
                elif pe > 30 and evebitda < 15:
                    st.success("💎 **Gizli Değer:** F/K yüksek ama EV/EBITDA düşük. Şirketin elinde yüklü NAKİT olabilir veya amortisman giderleri kârı baskılıyor. İncelemeye değer!")

            # KALİTE
            roe = row.get('ROE', 0)
            if roe > 20:
                st.write(f"🌟 **Kalite:** %{roe} ROE ile sektör üstü kârlılık.")
            
            st.markdown("---")
            st.caption("Veriler Finviz'in 3 farklı tablosunun (Overview, Valuation, Financial) birleştirilmesiyle oluşturulmuştur.")

elif st.session_state.merged_data.empty:
    st.info("👈 Başlamak için sol menüden 'ANALİZİ BAŞLAT' butonuna basınız.")
