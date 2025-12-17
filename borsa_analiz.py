import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
import time

# --- Sayfa Yapılandırması ---
st.set_page_config(page_title="Pro Akademik Analiz", layout="wide")
st.title("📊 Akademik Düzey Genişletilmiş Hisse Tarama")
st.markdown("Veri Kaynağı: **Finviz** (Çoklu Sayfa Tarama) | Teknik: **Yahoo Finance**")

# --- Session State (Veri Kalıcılığı İçin) ---
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame()

# --- Yan Menü Filtreleri ---
st.sidebar.header("🔍 Detaylı Filtreleme")

# 1. Sektör (Tam Liste)
sector_list = [
    "Any", "Basic Materials", "Communication Services", "Consumer Cyclical", 
    "Consumer Defensive", "Energy", "Financial", "Healthcare", 
    "Industrials", "Real Estate", "Technology", "Utilities"
]
sector = st.sidebar.selectbox("Sektör", sector_list, index=0)

# 2. Piyasa Değeri
mcap = st.sidebar.selectbox("Piyasa Değeri", ["Any", "Mega ($200bln+)", "Large ($10bln+)", "Mid ($2bln+)", "Small ($300mln+)"], index=0)

# 3. Genişletilmiş F/K (P/E) Seçenekleri
pe_opts = [
    "Any", "Low (<15)", "Profitable (<0)", "High (>50)", 
    "Under 5", "Under 10", "Under 15", "Under 20", "Under 25", "Under 30", "Under 35",
    "Over 5", "Over 10", "Over 15", "Over 20", "Over 25", "Over 30", "Over 50"
]
pe_ratio = st.sidebar.selectbox("F/K Oranı (Değerleme)", pe_opts, index=0)

# 4. ROE
roe_opts = ["Any", "Positive (>0%)", "High (>15%)", "Very High (>20%)", "Over 30%", "Over 40%", "Over 50%"]
roe = st.sidebar.selectbox("ROE (Kârlılık)", roe_opts, index=0)

# 5. Yeni Eklenen Rasyolar
debt_equity = st.sidebar.selectbox("Borç/Özkaynak (Risk)", ["Any", "Low (<0.1)", "Under 0.5", "Under 1", "High (>0.5)"], index=0)
dividend = st.sidebar.selectbox("Temettü Verimi", ["Any", "Positive (>0%)", "High (>5%)", "Very High (>10%)"], index=0)
margin = st.sidebar.selectbox("Net Kâr Marjı", ["Any", "Positive (>0%)", "High (>20%)", "Very High (>30%)"], index=0)

# --- Veri Çekme Motoru (Sayfalama Destekli) ---
def get_finviz_data_multi_page(sec, mc, pe, roe_val, de, div, marg):
    all_dfs = []
    base_filters = []
    
    # Mapping
    sec_map = {
        "Basic Materials": "sec_basicmaterials", "Communication Services": "sec_communicationservices",
        "Consumer Cyclical": "sec_consumercyclical", "Consumer Defensive": "sec_consumerdefensive",
        "Energy": "sec_energy", "Financial": "sec_financial", "Healthcare": "sec_healthcare",
        "Industrials": "sec_industrials", "Real Estate": "sec_realestate",
        "Technology": "sec_technology", "Utilities": "sec_utilities"
    }
    if sec != "Any": base_filters.append(f"s={sec_map[sec]}")

    # Market Cap
    if mc == "Mega ($200bln+)": base_filters.append("cap_mega")
    elif mc == "Large ($10bln+)": base_filters.append("cap_large")
    elif mc == "Mid ($2bln+)": base_filters.append("cap_mid")
    elif mc == "Small ($300mln+)": base_filters.append("cap_small")

    # P/E Mapping
    pe_map = {
        "Low (<15)": "fa_pe_u15", "Profitable (<0)": "fa_pe_profitable", "High (>50)": "fa_pe_o50",
        "Under 5": "fa_pe_u5", "Under 10": "fa_pe_u10", "Under 15": "fa_pe_u15", "Under 20": "fa_pe_u20",
        "Under 25": "fa_pe_u25", "Under 30": "fa_pe_u30", "Under 35": "fa_pe_u35",
        "Over 5": "fa_pe_o5", "Over 10": "fa_pe_o10", "Over 15": "fa_pe_o15", "Over 20": "fa_pe_o20",
        "Over 25": "fa_pe_o25", "Over 30": "fa_pe_o30", "Over 50": "fa_pe_o50"
    }
    if pe in pe_map: base_filters.append(pe_map[pe])

    # ROE Mapping
    if roe_val == "Positive (>0%)": base_filters.append("fa_roe_pos")
    elif roe_val == "High (>15%)": base_filters.append("fa_roe_o15")
    elif roe_val == "Very High (>20%)": base_filters.append("fa_roe_o20")
    elif roe_val == "Over 30%": base_filters.append("fa_roe_o30")
    elif roe_val == "Over 40%": base_filters.append("fa_roe_o40")
    elif roe_val == "Over 50%": base_filters.append("fa_roe_o50")

    # Diğer Rasyolar
    if de == "Low (<0.1)": base_filters.append("fa_debteq_u0.1")
    elif de == "Under 0.5": base_filters.append("fa_debteq_u0.5")
    elif de == "Under 1": base_filters.append("fa_debteq_u1")
    
    if div == "Positive (>0%)": base_filters.append("fa_div_pos")
    elif div == "High (>5%)": base_filters.append("fa_div_o5")
    elif div == "Very High (>10%)": base_filters.append("fa_div_o10")
    
    if marg == "Positive (>0%)": base_filters.append("fa_netmargin_pos")
    elif marg == "High (>20%)": base_filters.append("fa_netmargin_o20")
    elif marg == "Very High (>30%)": base_filters.append("fa_netmargin_o30")

    filter_str = ",".join(base_filters)
    
    # --- ÇOKLU SAYFA TARAMA (PAGINATION) ---
    # İlk 3 sayfayı (60 hisse) çekmek için döngü
    # r=1 (1. sayfa), r=21 (2. sayfa), r=41 (3. sayfa)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    progress_bar = st.progress(0)
    
    for i, start_row in enumerate([1, 21, 41]):
        try:
            url = f"https://finviz.com/screener.ashx?v=111&f={filter_str}&r={start_row}"
            response = requests.get(url, headers=headers)
            tables = pd.read_html(response.text)
            
            # Doğru tabloyu bulma mantığı
            for t in tables:
                if 'Ticker' in t.columns and len(t) > 1:
                    t_clean = t[['Ticker', 'Company', 'Sector', 'P/E', 'Price', 'Change', 'Volume']]
                    all_dfs.append(t_clean)
                    break
            
            progress_bar.progress((i + 1) * 33)
            time.sleep(0.5) # Anti-bot beklemesi
            
        except Exception:
            break # Hata olursa veya sayfa biterse döngüyü kır
            
    progress_bar.empty()
    
    if all_dfs:
        final_df = pd.concat(all_dfs).drop_duplicates(subset=['Ticker']).reset_index(drop=True)
        return final_df
    return pd.DataFrame()

# --- Uygulama Mantığı ---

# Butona basılınca veriyi çek ve session_state'e kaydet
if st.sidebar.button("Sonuçları Getir"):
    with st.spinner('Çoklu sayfa taraması yapılıyor...'):
        df = get_finviz_data_multi_page(sector, mcap, pe_ratio, roe, debt_equity, dividend, margin)
        st.session_state.data = df

# Eğer data boş değilse (daha önce çekildiyse veya yeni çekildiyse)
if not st.session_state.data.empty:
    df_display = st.session_state.data
    
    st.success(f"Analiz Sonucu: Toplam **{len(df_display)}** şirket bulundu.")
    st.dataframe(df_display, use_container_width=True)
    
    st.divider()
    
    # --- Grafik Bölümü ---
    # Session State sayesinde buradaki seçim sayfayı yenilese bile 
    # yukarıdaki dataframe kaybolmaz.
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📈 Teknik Analiz")
        # Selectbox listesini güvenli string'e çevir
        ticker_options = df_display['Ticker'].astype(str).tolist()
        selected_ticker = st.selectbox("Grafik Görüntüle:", ticker_options)
        
        if selected_ticker:
            try:
                # Veri indir
                stock_data = yf.download(selected_ticker, period="1y", progress=False)
                
                if not stock_data.empty:
                    # Grafik çiz
                    fig = go.Figure(data=[go.Candlestick(x=stock_data.index,
                                    open=stock_data['Open'], high=stock_data['High'],
                                    low=stock_data['Low'], close=stock_data['Close'],
                                    name=selected_ticker)])
                    fig.update_layout(title=f"{selected_ticker} Günlük Grafik", height=500, xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Grafik verisi yüklenemedi.")
            except Exception as e:
                st.error(f"Hata: {e}")

    with col2:
        if selected_ticker:
            st.subheader("ℹ️ Özet")
            try:
                info = yf.Ticker(selected_ticker).info
                st.write(f"**Endüstri:** {info.get('industry', '-')}")
                st.write(f"**Çalışan:** {info.get('fullTimeEmployees', '-')}")
                
                beta = info.get('beta', None)
                if beta: st.metric("Beta (Risk)", f"{beta:.2f}")
                
                target = info.get('targetMeanPrice', None)
                current = info.get('currentPrice', None)
                if target and current:
                    upside = ((target - current) / current) * 100
                    st.metric("Analist Hedefi", f"${target}", f"%{upside:.1f}")
            except:
                st.write("Detay bilgi yok.")

elif st.session_state.data.empty:
    st.info("Lütfen filtreleri ayarlayıp 'Sonuçları Getir' butonuna basınız.")
