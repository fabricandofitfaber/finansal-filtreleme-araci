import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="S&P 500 Tam Tarama", layout="wide")
st.title("📊 Akademik Piyasa Analizörü: S&P 500")
st.markdown("""
Bu program, statik bir liste yerine **Wikipedia üzerinden güncel S&P 500 endeksini** çeker ve analiz eder.
*Veri Kaynağı: Wikipedia (Ticker Listesi) + Yahoo Finance (Finansal Veriler)*
""")

# --- 1. ADIM: Dinamik Hisse Listesi (Wikipedia) ---
@st.cache_data
def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        # Wikipedia'daki ilk tablo her zaman S&P 500 listesidir
        df = tables[0]
        tickers = df['Symbol'].tolist()
        
        # Yahoo Finance için bazı ticker düzeltmeleri (Örn: BRK.B -> BRK-B)
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        st.error(f"Liste çekilemedi: {e}")
        # Acil durum listesi (Fallback)
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

# --- 2. ADIM: Veri Çekme Motoru ---
def fetch_market_data(ticker_list, limit):
    data = []
    
    # İlerleme Çubuğu
    progress_text = "Piyasa taranıyor. Bu işlem canlı veri çektiği için zaman alabilir..."
    my_bar = st.progress(0, text=progress_text)
    
    # Kullanıcının seçtiği limit kadar hisseyi tara
    target_list = ticker_list[:limit]
    
    for i, ticker in enumerate(target_list):
        try:
            # Yahoo'dan 'Info' çekmek en maliyetli işlemdir, yavaş ama detaylıdır.
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Sadece temel verileri alıyoruz
            stock_data = {
                'Ticker': ticker,
                'Şirket': info.get('shortName', 'N/A'),
                'Sektör': info.get('sector', 'Bilinmiyor'),
                'Fiyat ($)': info.get('currentPrice', 0),
                'F/K': info.get('trailingPE', 0),
                'İleri F/K': info.get('forwardPE', 0),
                'ROE (%)': (info.get('returnOnEquity', 0) or 0) * 100,
                'Borç/Özkaynak': info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0,
                'Temettü (%)': (info.get('dividendYield', 0) or 0) * 100,
                'Hedef Fiyat': info.get('targetMeanPrice', 0)
            }
            
            # Veri temizliği: Sadece anlamlı verisi olanları ekle
            if stock_data['Fiyat ($)'] > 0:
                data.append(stock_data)
                
            # İlerleme çubuğunu güncelle
            my_bar.progress((i + 1) / len(target_list), text=f"Taranıyor: {ticker}")
            
        except Exception:
            continue # Hata veren hisseyi atla
            
    my_bar.empty()
    return pd.DataFrame(data)

# --- Arayüz ve Kontroller ---

# Önce listeyi çek
all_tickers = get_sp500_tickers()

st.sidebar.header("⚙️ Tarama Ayarları")

# Tarama Derinliği (Hız vs Kapsam Dengesi)
scan_limit = st.sidebar.slider(
    "Tarama Derinliği (Hisse Sayısı)", 
    min_value=10, 
    max_value=len(all_tickers), 
    value=50, 
    step=10,
    help="Yahoo Finance API hızı sınırlıdır. Tüm endeksi (500+) taramak 10-15 dakika sürebilir. Hızlı sonuç için 50-100 arası seçiniz."
)

if st.sidebar.button("Canlı Taramayı Başlat"):
    with st.spinner(f'{scan_limit} adet hisse senedi canlı analiz ediliyor...'):
        # Veriyi çek
        raw_df = fetch_market_data(all_tickers, scan_limit)
        # Session state'e kaydet
        st.session_state.market_data = raw_df

# --- Veri Varsa Göster ---
if 'market_data' in st.session_state and not st.session_state.market_data.empty:
    df = st.session_state.market_data
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Sonuçları Filtrele")
    
    # Dinamik Filtreler (Çekilen veriye göre oluşur)
    
    # 1. Sektör
    available_sectors = ["Tümü"] + sorted(df['Sektör'].unique().tolist())
    sec_filter = st.sidebar.selectbox("Sektör Filtresi", available_sectors)
    
    # 2. F/K Filtresi
    pe_filter = st.sidebar.slider("Maksimum F/K", 0, 100, 30)
    
    # 3. ROE Filtresi
    roe_filter = st.sidebar.slider("Minimum ROE (%)", 0, 50, 10)
    
    # Filtreleme İşlemi
    filtered_df = df.copy()
    
    if sec_filter != "Tümü":
        filtered_df = filtered_df[filtered_df['Sektör'] == sec_filter]
        
    filtered_df = filtered_df[
        (filtered_df['F/K'] < pe_filter) & 
        (filtered_df['F/K'] > 0) & # Zarar edenleri ele
        (filtered_df['ROE (%)'] > roe_filter)
    ]
    
    # --- Ana Ekran ---
    st.success(f"Analiz Tamamlandı: {len(df)} hisse tarandı, kriterlere uyan **{len(filtered_df)}** hisse listeleniyor.")
    
    # Veri Tablosu
    st.dataframe(
        filtered_df.style.format({
            "Fiyat ($)": "{:.2f}",
            "F/K": "{:.2f}",
            "İleri F/K": "{:.2f}",
            "ROE (%)": "{:.2f}%",
            "Borç/Özkaynak": "{:.2f}",
            "Temettü (%)": "{:.2f}%",
            "Hedef Fiyat": "{:.2f}"
        }),
        use_container_width=True
    )
    
    st.markdown("---")
    
    # --- Grafik ve Detay Analiz ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("📉 Teknik Analiz")
        # Filtrelenmiş listeden seçim yap
        if not filtered_df.empty:
            selected_ticker = st.selectbox("Grafik için hisse seçiniz:", filtered_df['Ticker'].tolist())
            
            if selected_ticker:
                # Grafik verisi (sadece seçilen için hızlıca çekilir)
                chart_data = yf.download(selected_ticker, period="1y", progress=False)
                
                fig = go.Figure(data=[go.Candlestick(x=chart_data.index,
                                open=chart_data['Open'], high=chart_data['High'],
                                low=chart_data['Low'], close=chart_data['Close'],
                                name=selected_ticker)])
                fig.update_layout(height=500, title=f"{selected_ticker} Fiyat Hareketi", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Filtreleme kriterlerinize uyan hisse kalmadı.")

    with col2:
        if not filtered_df.empty and selected_ticker:
            st.subheader("📝 Rasyo Kartı")
            # Seçilen hissenin verilerini bul
            row = filtered_df[filtered_df['Ticker'] == selected_ticker].iloc[0]
            
            st.metric("F/K Oranı", f"{row['F/K']:.2f}")
            st.metric("ROE (Kârlılık)", f"%{row['ROE (%)']:.1f}")
            
            potansiyel = 0
            if row['Hedef Fiyat'] > 0:
                potansiyel = ((row['Hedef Fiyat'] - row['Fiyat ($)']) / row['Fiyat ($)']) * 100
                color = "green" if potansiyel > 0 else "red"
                st.markdown(f"**Analist Hedefi:** ${row['Hedef Fiyat']:.2f}")
                st.markdown(f"**Potansiyel:** :{color}[%{potansiyel:.1f}]")
            else:
                st.write("Analist hedefi yok.")

else:
    st.info("👈 Lütfen sol menüden tarama derinliğini seçip 'Canlı Taramayı Başlat' butonuna basınız.")
    st.caption("Not: '50' seçeneği yaklaşık 30 saniye, '500' seçeneği 5-10 dakika sürebilir.")
