import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
import time

# --- Sayfa Yapılandırması ---
st.set_page_config(page_title="Akademik Tarama v4.0", layout="wide")
st.title("📊 Akademik Düzey Hisse Tarama (Hibrit Motor)")
st.markdown("""
**Çalışma Prensibi:** Bu sistem, Finviz'den veriyi "Geniş Bant" çeker ve Python içinde "Hassas Filtreleme" uygular.
*Veri Kaynağı: Finviz (Fundamental) + Yahoo Finance (Technical)*
""")

# --- Session State (Veri Kalıcılığı) ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame()

# --- Yan Menü (Hassas Filtreler) ---
st.sidebar.header("🎛️ Parametre Kontrolü")

# 1. Sektör
sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=10) # Varsayılan: Teknoloji

# 2. Hassas F/K (Slider - Sürekli Değişken)
# Kullanıcı küsuratlı sayı seçebilir (Örn: 12.5)
target_pe = st.sidebar.slider("Maksimum F/K (P/E) Oranı", min_value=0.0, max_value=100.0, value=25.0, step=0.5)

# 3. Hassas ROE (Slider)
target_roe = st.sidebar.slider("Minimum ROE (%)", min_value=0.0, max_value=50.0, value=15.0, step=1.0)

# 4. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# --- Veri Çekme Motoru (Anti-Garbage Algoritması) ---
def get_clean_data(sec, mc, user_pe, user_roe):
    # ADIM 1: URL Parametrelerini Belirle (Geniş Filtreleme)
    # Kullanıcının seçtiği rakamdan daha geniş bir aralığı Finviz'den istiyoruz.
    # Örn: Kullanıcı 12.5 istediyse, Finviz'den "Under 15" istiyoruz ki veri kaçmasın.
    
    filters = []
    
    # Sektör Mapping
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": filters.append(f"s={sec_map[sec]}")

    # Market Cap
    if mc == "Large ($10bln+)": filters.append("cap_large")
    elif mc == "Mid ($2bln+)": filters.append("cap_mid")
    elif mc == "Small ($300mln+)": filters.append("cap_small")

    # Akıllı F/K Mapping (Funnel Method)
    # Kullanıcının slider değerine göre Finviz'e en yakın üst limiti gönderiyoruz.
    if user_pe < 5: filters.append("fa_pe_u5")
    elif user_pe < 10: filters.append("fa_pe_u10")
    elif user_pe < 15: filters.append("fa_pe_u15")
    elif user_pe < 20: filters.append("fa_pe_u20")
    elif user_pe < 25: filters.append("fa_pe_u25")
    elif user_pe < 30: filters.append("fa_pe_u30")
    elif user_pe < 40: filters.append("fa_pe_u40")
    elif user_pe < 50: filters.append("fa_pe_u50")
    # 50 üzeriyse filtre koymuyoruz, hepsini çekip Python'da eleriz.

    # ROE Mapping
    if user_roe > 0: filters.append("fa_roe_pos") # En azından pozitif olsun

    filter_str = ",".join(filters)
    
    # ADIM 2: Sayfalama ve Veri İndirme (İlk 3 Sayfa)
    all_data = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    status_text = st.empty()
    bar = st.progress(0)
    
    pages = [1, 21, 41] # Toplam 60 hisse tarar (20'şerli)
    
    for i, start_row in enumerate(pages):
        try:
            status_text.text(f"Veri tabanı taranıyor... Sayfa {i+1}/3")
            bar.progress((i+1) * 33)
            
            url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}&r={start_row}"
            response = requests.get(url, headers=headers)
            
            # --- KRİTİK DÜZELTME: Tablo Doğrulama ---
            # read_html header=0 diyerek ilk satırı başlık yapmasını sağlıyoruz
            tables = pd.read_html(response.text, header=0) 
            
            found_table = False
            for t in tables:
                # O çöp veride 'Ticker', 'P/E', 'Price' sütunları aynı anda bulunmaz.
                # Sadece gerçek veride bu üçü aynı anda vardır.
                if 'Ticker' in t.columns and 'Price' in t.columns and 'P/E' in t.columns:
                    all_data.append(t)
                    found_table = True
                    break 
            
            if not found_table:
                # Eğer sayfada hisse yoksa döngüyü kır (Sonuçlar bitti)
                break
                
            time.sleep(0.5) # Nezaket beklemesi
            
        except Exception as e:
            continue

    bar.empty()
    status_text.empty()

    if all_data:
        # Tüm parçaları birleştir
        df_concat = pd.concat(all_data).drop_duplicates(subset=['Ticker'])
        
        # Sütunları sayıya çevir (Temizlik)
        cols = ['P/E', 'Price', 'Change', 'Volume']
        for c in cols:
            df_concat[c] = pd.to_numeric(df_concat[c], errors='coerce')
            
        return df_concat
    return pd.DataFrame()

# --- Ana Akış ---
if st.sidebar.button("Sonuçları Getir"):
    # 1. Geniş veriyi çek
    raw_df = get_clean_data(sector, mcap, target_pe, target_roe)
    
    if not raw_df.empty:
        # 2. ADIM: Hassas Filtreleme (Python Tarafı)
        # İşte "Sürekli Değişken" filtrelemesi burada yapılıyor
        filtered_df = raw_df[
            (raw_df['P/E'] <= target_pe) & 
            (raw_df['P/E'] > 0) # Negatif veya boşları at
        ]
        
        # İstenirse ROE sütunu varsa ona göre de filtrelenebilir
        # Finviz ana tabloda ROE göstermediği için (Overview modu), 
        # ROE filtresini sadece URL tarafında bıraktık.
        
        st.session_state.data = filtered_df
    else:
        st.session_state.data = pd.DataFrame()

# --- Ekran Gösterimi ---
df_display = st.session_state.data

if not df_display.empty:
    st.success(f"Kriterlere uyan **{len(df_display)}** şirket bulundu.")
    
    # Tabloyu Güzelleştir
    st.dataframe(
        df_display[['Ticker', 'Company', 'Sector', 'P/E', 'Price', 'Change', 'Volume']], 
        use_container_width=True
    )
    
    st.divider()
    
    # --- Grafik Bölümü ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📈 Teknik Analiz")
        t_list = df_display['Ticker'].astype(str).tolist()
        selected = st.selectbox("Grafik Seçiniz:", t_list)
        
        if selected:
            data = yf.download(selected, period="1y", progress=False)
            if not data.empty:
                fig = go.Figure(data=[go.Candlestick(x=data.index,
                                open=data['Open'], high=data['High'],
                                low=data['Low'], close=data['Close'])])
                fig.update_layout(title=f"{selected} Günlük", height=450, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Veri yok.")

    with col2:
        if selected:
            st.subheader("ℹ️ Bilgi")
            try:
                info = yf.Ticker(selected).info
                st.metric("F/K", info.get('trailingPE', '-'))
                st.metric("Hedef Fiyat", info.get('targetMeanPrice', '-'))
                st.write(f"**Endüstri:** {info.get('industry', '-')}")
            except:
                st.write("-")

elif st.sidebar.button("Tekrar Dene") or st.session_state.data.empty:
    st.info("Lütfen kriterleri seçip 'Sonuçları Getir' butonuna basınız.")
