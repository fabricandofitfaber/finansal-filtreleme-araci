import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go

# --- Sayfa Ayarları ---
st.set_page_config(page_title="Akademik Tarama v5.0", layout="wide")
st.title("📊 Akademik Düzey Hisse Tarama (Bot Korumalı)")
st.markdown("""
**Durum:** Bu sistem Finviz bot korumasını aşmak için 'Browser Spoofing' ve 'Pattern Matching' tekniklerini kullanır.
""")

# --- Session State ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame()

# --- Yan Menü ---
st.sidebar.header("🎛️ Filtreler")

# 1. Sektör
sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=10)

# 2. Hassas F/K (Slider)
target_pe = st.sidebar.slider("Maksimum F/K (P/E)", 0.0, 100.0, 25.0, 0.5)

# 3. Hassas ROE (Slider)
target_roe = st.sidebar.slider("Minimum ROE (%)", 0.0, 50.0, 15.0, 1.0)

# 4. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# --- Veri Motoru ---
def get_data_v5(sec, mc, user_pe, user_roe):
    # Filtreleri Hazırla
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

    # F/K Funnel (Daraltma)
    if user_pe < 15: filters.append("fa_pe_u15")
    elif user_pe < 25: filters.append("fa_pe_u25")
    elif user_pe < 50: filters.append("fa_pe_u50")
    
    # ROE Funnel
    if user_roe > 0: filters.append("fa_roe_pos")
    if user_roe > 15: filters.append("fa_roe_o15")

    filter_str = ",".join(filters)
    
    # --- İSTEK ATMA (Bot Koruması Önlemi) ---
    # Gerçek bir Chrome tarayıcısı taklidi yapıyoruz
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://finviz.com/'
    }
    
    all_dfs = []
    # İlk 2 sayfayı (40 hisse) tarayalım
    pages = [1, 21] 
    
    status_msg = st.empty()
    
    for i, start_row in enumerate(pages):
        try:
            url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}&r={start_row}"
            
            # Request
            r = requests.get(url, headers=headers, timeout=10)
            
            # Hata Kontrolü (403 Forbidden vb.)
            if r.status_code != 200:
                st.error(f"⚠️ Bağlantı Hatası: Sunucu {r.status_code} kodu döndürdü. (Bot koruması olabilir)")
                break
            
            # --- TABLO AYRIŞTIRMA (Sihirli Kısım) ---
            # match="Ticker" parametresi: İçinde 'Ticker' kelimesi geçen tabloyu bulur.
            # Bu sayede menü yazılarını, reklamları vs. atlar.
            dfs = pd.read_html(r.text, match="Ticker", header=0)
            
            if len(dfs) > 0:
                df = dfs[0]
                # Sütun kontrolü (Garantiye almak için)
                if 'Ticker' in df.columns and 'Price' in df.columns:
                    all_dfs.append(df)
            else:
                # Tablo yoksa sayfa boştur
                break
                
        except ValueError as ve:
            # "No tables found" hatası gelirse buraya düşer
            if i == 0: st.warning("Finviz tablosu bulunamadı. Filtreler çok sıkı olabilir.")
            break
        except Exception as e:
            st.error(f"Beklenmedik Hata: {e}")
            break
            
    status_msg.empty()
    
    if all_dfs:
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker'])
        
        # Sayısal Dönüşüm
        for col in ['P/E', 'Price', 'Change', 'Volume']:
            if col in final_df.columns:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce')
        
        return final_df
    return pd.DataFrame()

# --- Ana Akış ---
if st.sidebar.button("Taramayı Başlat"):
    with st.spinner('Veriler çekiliyor...'):
        raw_df = get_data_v5(sector, mcap, target_pe, target_roe)
        
        if not raw_df.empty:
            # Python tarafında hassas eleme
            filtered_df = raw_df[
                (raw_df['P/E'] <= target_pe) & 
                (raw_df['P/E'] > 0)
            ]
            # ROE verisi Overview tablosunda gelmediği için (Finviz kısıtı),
            # ROE filtresini sadece "Giriş" aşamasında yapabiliyoruz.
            
            st.session_state.data = filtered_df
        else:
            st.session_state.data = pd.DataFrame()

# --- Gösterim ---
df_display = st.session_state.data

if not df_display.empty:
    st.success(f"✅ {len(df_display)} şirket bulundu.")
    st.dataframe(df_display, use_container_width=True)
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Grafik Analiz")
        tik = st.selectbox("Hisse Seç:", df_display['Ticker'].astype(str).unique())
        if tik:
            d = yf.download(tik, period="1y", progress=False)
            if not d.empty:
                fig = go.Figure(data=[go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'])])
                fig.update_layout(height=400, margin=dict(l=0,r=0,t=30,b=0))
                st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if tik:
            st.subheader("Özet")
            try:
                inf = yf.Ticker(tik).info
                st.metric("Fiyat", f"${inf.get('currentPrice', '-')}")
                st.metric("Hedef", f"${inf.get('targetMeanPrice', '-')}")
                st.info(inf.get('longBusinessSummary', '')[:150] + "...")
            except:
                st.write("Bilgi yok.")
elif st.session_state.data.empty and st.sidebar.button("Tekrar Dene"): # Buton state trick
    st.warning("Sonuç bulunamadı.")
else:
    st.info("Filtreleri ayarlayıp 'Taramayı Başlat' butonuna basınız.")
