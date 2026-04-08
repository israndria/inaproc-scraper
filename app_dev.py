import asyncio
import sys
import os
import io

# PENTING: Fix untuk error asyncio "NotImplementedError" di Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
from scraper_api_dev import search_inaproc_api
from playwright.sync_api import sync_playwright
import time
import traceback
import re
from datetime import datetime

st.set_page_config(page_title="Inaproc Scraper API (v2 Dev)", layout="wide")

# Custom CSS untuk UI yang lebih bersih
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    .status-box {
        background-color: #e1f5fe;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #03a9f4;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🛍️ Inaproc Catalog Scraper API (v2)")
st.markdown("""
<div class="status-box">
    <strong>Mode Pengembangan (API):</strong> Mengambil data langsung dari server Inaproc. 
    Tanpa simulasi klik, 10x lebih cepat, dan data lebih akurat.
</div>
""", unsafe_allow_html=True)


# Validasi Helper
def clean_price_value(value):
    if not value: return 0
    clean = re.sub(r'[^0-9]', '', str(value))
    return int(clean) if clean else 0

def format_price_str(value):
    val = clean_price_value(value)
    return f"{val:,}" if val > 0 else "0"

# Callbacks
def on_min_price_change():
    st.session_state.min_price_input_dev = format_price_str(st.session_state.min_price_input_dev)

def on_max_price_change():
    st.session_state.max_price_input_dev = format_price_str(st.session_state.max_price_input_dev)

# Sidebar
with st.sidebar:
    st.header("⚙️ Pengaturan")
    keyword = st.text_input("Kata Kunci", "laptop", key="kw_dev", help="Contoh: laptop, printer, sewa mobil")
    
    st.subheader("Mode")
    scraping_mode = st.radio(
        "Pilih Mode",
        ["Listing API", "Comparison (API + Screenshot)"],
        index=0,
        key="mode_dev",
        help="Listing: Hanya data tabel. Comparison: Data tabel + Screenshot tiap produk."
    )
    
    # Filter Harga
    st.subheader("💰 Filter Harga")
    if 'min_price_input_dev' not in st.session_state: st.session_state.min_price_input_dev = "0"
    if 'max_price_input_dev' not in st.session_state: st.session_state.max_price_input_dev = "0"

    st.text_input("Harga Min (Rp)", key="min_price_input_dev", on_change=on_min_price_change)
    st.text_input("Harga Max (Rp)", key="max_price_input_dev", on_change=on_max_price_change)
    
    min_price = clean_price_value(st.session_state.min_price_input_dev)
    max_price = clean_price_value(st.session_state.max_price_input_dev)
    
    # Filter Lokasi
    st.subheader("📍 Lokasi")
    KALSEL_LOCATIONS = [
        "Kab. Balangan", "Kab. Banjar", "Kab. Barito Kuala", "Kab. Hulu Sungai Selatan",
        "Kab. Hulu Sungai Tengah", "Kab. Hulu Sungai Utara", "Kab. Kotabaru",
        "Kab. Tabalong", "Kab. Tanah Bumbu", "Kab. Tanah Laut", "Kab. Tapin",
        "Kota Banjarbaru", "Kota Banjarmasin",
    ]

    selected_locations = []
    def toggle_all_dev():
        val = st.session_state.select_all_loc_dev
        for loc in KALSEL_LOCATIONS: st.session_state[f"loc_dev_{loc}"] = val

    with st.expander("Pilih Wilayah Kalsel", expanded=False):
        st.checkbox("Pilih Semua", key="select_all_loc_dev", on_change=toggle_all_dev)
        for loc in KALSEL_LOCATIONS:
            if f"loc_dev_{loc}" not in st.session_state: st.session_state[f"loc_dev_{loc}"] = False
            if st.checkbox(loc, key=f"loc_dev_{loc}"): selected_locations.append(loc)

    location_filter = ", ".join(selected_locations) if selected_locations else ""
    
    # Limit & Sort
    st.subheader("📊 Batasan")
    sort_option = st.selectbox("Urutkan", ["Paling Sesuai", "Harga Terendah", "Harga Tertinggi"], key="sort_dev")
    
    limit_count = st.selectbox(
        "Maksimal Produk", 
        [60, 120, 300, 600, 1200], 
        index=1, 
        help="Satu halaman Inaproc berisi 60 produk. Kami akan mengambil beberapa halaman secara otomatis."
    )
    max_pages = limit_count // 60

    limit_screenshots = 0
    if scraping_mode == "Comparison (API + Screenshot)":
        limit_screenshots = st.number_input("Jumlah Produk untuk Screenshot", 1, 20, 2, key="limit_dev")

    st.markdown("---")
    run_btn = st.button("🚀 MULAI SCRAPING", type="primary", key="run_dev")

# Fungsi Screenshot
def take_screenshot(url, vendor):
    if not os.path.exists("screenshots"): os.makedirs("screenshots")
    clean_vendor = re.sub(r'[\\/*?:\u0022<>|]', '', vendor)[:30].strip()
    filename = f"{clean_vendor}_{int(time.time())}.png"
    filepath = os.path.join(os.getcwd(), "screenshots", filename)
    
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            page.screenshot(path=filepath, full_page=True)
            return filepath
        except Exception as e:
            print(f"Gagal screenshot {vendor}: {e}")
            return None
        finally:
            if 'page' in locals(): page.close()

# Main Area
if run_btn:
    if not keyword:
        st.warning("Silakan masukkan kata kunci pencarian.")
    else:
        st.info(f"🔎 Mencari **{keyword}** (Limit: {limit_count} produk)...")
        start_time = time.time()
        
        try:
            # 1. Scraping via API
            data = search_inaproc_api(
                keyword, 
                min_price=min_price, 
                max_price=max_price, 
                location_filter=location_filter, 
                max_pages=max_pages,
                sort_order=sort_option
            )
            
            if data:
                # Potong data jika melebihi limit (karena 1 page = 60)
                data = data[:limit_count]
                
                # 2. Proses Screenshot jika mode Comparison
                if scraping_mode == "Comparison (API + Screenshot)":
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    for i in range(min(len(data), limit_screenshots)):
                        item = data[i]
                        status_text.text(f"📸 Screenshot {i+1}/{limit_screenshots}: {item['Penyedia']}")
                        path = take_screenshot(item['Link'], item['Penyedia'])
                        data[i]['Screenshot'] = path
                        progress_bar.progress(int(((i+1)/limit_screenshots)*100))
                    status_text.empty()
                    progress_bar.empty()

                # Tambahkan Nomor Urut di Dataframe untuk Export
                df_export = pd.DataFrame(data)
                df_export.insert(0, 'No.', range(1, len(df_export) + 1))
                
                # Tambahkan info TKDN ke export jika ada (API v2 punya data ini)
                # Note: Kita ambil data mentah dari 'data' list sebelum diclean untuk UI jika perlu
                
                # Tampilkan Tabel di UI (tanpa kolom No agar tidak menumpuk dengan index streamlit)
                df_display = pd.DataFrame(data)
                st.dataframe(df_display, use_container_width=True, column_config={
                    "Link": st.column_config.LinkColumn("Link Produk"),
                    "Gambar": st.column_config.ImageColumn("Preview"),
                    "Harga": st.column_config.TextColumn("Harga", width="medium"),
                })
                
                # DOWNLOAD AREA
                st.markdown("### 📥 Download Hasil")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_filename = f"inaproc_{keyword.replace(' ', '_')}_{timestamp}"
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # CSV
                    csv = df_export.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📄 Download CSV",
                        data=csv,
                        file_name=f"{base_filename}.csv",
                        mime="text/csv",
                    )
                
                with col2:
                    # EXCEL (via BytesIO agar bersih)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_export.to_excel(writer, index=False, sheet_name='Data Produk')
                    excel_data = output.getvalue()
                    st.download_button(
                        label="Excel Download Excel",
                        data=excel_data,
                        file_name=f"{base_filename}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                # Screenshot Perbandingan
                if scraping_mode == "Comparison (API + Screenshot)":
                     st.write("### 📸 Cuplikan Produk")
                     cols = st.columns(3)
                     for idx, row in df.head(limit_screenshots).iterrows():
                         with cols[idx % 3]:
                             if row.get('Screenshot'):
                                 st.image(row['Screenshot'], caption=f"{row['Penyedia']}", use_container_width=True)
                             with st.expander("Detail"):
                                 st.write(f"**{row['Nama Produk']}**")
                                 st.write(f"Harga: {row['Harga']}")
                                 st.write(f"Lokasi: {row['Lokasi']}")

            else:
                st.warning("Tidak ada produk yang ditemukan dengan kriteria tersebut.")
                
        except Exception as e:
            st.error(f"Terjadi kesalahan teknis: {e}")
            st.code(traceback.format_exc())
