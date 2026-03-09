import asyncio
import sys

# PENTING: Fix untuk error asyncio "NotImplementedError" di Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
from scraper import search_inaproc
import time
import traceback
import re
from datetime import datetime

st.set_page_config(page_title="Inaproc Scraper", layout="wide")

st.title("🛍️ Inaproc Catalog Scraper")
st.markdown("Scrape data produk dari katalog.inaproc.id dengan mudah.")


# Validasi Helper
def clean_price_value(value):
    """Clean string to int, separate from formatting."""
    if not value: return 0
    clean = re.sub(r'[^0-9]', '', str(value))
    return int(clean) if clean else 0

def format_price_str(value):
    """Format int to string with commas."""
    val = clean_price_value(value)
    return f"{val:,}" if val > 0 else "0"

# Callbacks
def on_min_price_change():
    st.session_state.min_price_input = format_price_str(st.session_state.min_price_input)

def on_max_price_change():
    st.session_state.max_price_input = format_price_str(st.session_state.max_price_input)

# Sidebar
with st.sidebar:
    st.header("Pengaturan Pencarian")
    keyword = st.text_input("Kata Kunci", "laptop")
    
    st.subheader("Mode Scraping")
    scraping_mode = st.radio(
        "Pilih Mode",
        ["Listing (Cepat)", "Comparison (Detail + Screenshot)"],
        index=0,
        help="Listing: Ambil banyak data cepat. Comparison: Ambil detail produk & screenshot full page."
    )
    
    # Filter Harga with Callbacks
    st.subheader("Filter Harga")
    # Initialize session state if not set
    if 'min_price_input' not in st.session_state: st.session_state.min_price_input = "0"
    if 'max_price_input' not in st.session_state: st.session_state.max_price_input = "0"

    st.text_input(
        "Harga Min (Rp)", 
        key="min_price_input", 
        on_change=on_min_price_change,
        help="Ketikan angka, otomatis diformat"
    )
    st.text_input(
        "Harga Max (Rp)", 
        key="max_price_input", 
        on_change=on_max_price_change,
        help="Ketikan angka, otomatis diformat"
    )
    
    min_price = clean_price_value(st.session_state.min_price_input)
    max_price = clean_price_value(st.session_state.max_price_input)
    
    # Filter Lokasi
    st.subheader("Filter Lokasi")

    KALSEL_LOCATIONS = [
        "Kab. Balangan",
        "Kab. Banjar",
        "Kab. Barito Kuala",
        "Kab. Hulu Sungai Selatan",
        "Kab. Hulu Sungai Tengah",
        "Kab. Hulu Sungai Utara",
        "Kab. Kotabaru",
        "Kab. Tabalong",
        "Kab. Tanah Bumbu",
        "Kab. Tanah Laut",
        "Kab. Tapin",
        "Kota Banjarbaru",
        "Kota Banjarmasin",
    ]

    selected_locations = []

    # Callback untuk Pilih Semua — update semua checkbox via session_state
    def toggle_all():
        val = st.session_state.select_all_loc
        for loc in KALSEL_LOCATIONS:
            st.session_state[f"loc_{loc}"] = val

    with st.expander("Pilih Lokasi (Kalimantan Selatan)", expanded=False):
        st.checkbox("Pilih Semua", key="select_all_loc", on_change=toggle_all)
        for loc in KALSEL_LOCATIONS:
            if f"loc_{loc}" not in st.session_state:
                st.session_state[f"loc_{loc}"] = False
            checked = st.checkbox(loc, key=f"loc_{loc}")
            if checked:
                selected_locations.append(loc)

    # Gabungkan jadi string comma-separated untuk scraper
    location_filter = ", ".join(selected_locations) if selected_locations else ""

    if selected_locations:
        if len(selected_locations) > 10:
            st.caption(f"Lokasi dipilih: {len(selected_locations)} (⚠️ maks 10 oleh website, {len(selected_locations)-10} akan diskip)")
        else:
            st.caption(f"Lokasi dipilih: {len(selected_locations)}")
    
    # Sort Option
    sort_option = st.selectbox("Urutkan", ["Paling Sesuai", "Harga Terendah", "Harga Tertinggi"])
    
    limit_products = 0 # Unlimited
    num_pages = 1
    
    if scraping_mode == "Listing (Cepat)":
        num_pages = st.slider("Jumlah Halaman", 1, 5, 1)
    else:
        limit_products = st.number_input("Jumlah Produk untuk Dibandingkan", min_value=1, max_value=10, value=2)
        st.info("Mode ini akan membuka setiap produk dan mengambil screenshot. Lebih lambat.")

    run_btn = st.button("Mulai Scraping", type="primary")

# Main Area
if run_btn:
    if not keyword:
        st.warning("Masukkan kata kunci terlebih dahulu.")
    else:
        mode_label = "Listing" if scraping_mode == "Listing (Cepat)" else "Comparison"
        st.info(f"Memulai scraping **{mode_label}** untuk: **{keyword}**...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Membuka browser...")
        progress_bar.progress(10)
        
        try:
            start_time = time.time()
            
            # Panggil Scraper dengan parameter baru
            data = search_inaproc(
                keyword, 
                headless=False, 
                min_price=min_price, 
                max_price=max_price, 
                location_filter=location_filter, 
                max_pages=num_pages,
                enable_comparison=(scraping_mode == "Comparison (Detail + Screenshot)"),
                limit_products=limit_products,
                sort_order=sort_option
            )
            
            progress_bar.progress(90)
            status_text.text("Memproses data...")
            
            if data:
                df = pd.DataFrame(data)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                duration = time.time() - start_time
                st.success(f"Selesai! {len(df)} produk didapatkan (Waktu: {duration:.2f}s).")
                

                # Config Column buat gambar/screenshot
                col_config = {
                    "Link": st.column_config.LinkColumn("Link Produk"),
                    "Harga": st.column_config.TextColumn("Harga"),
                    "Gambar": st.column_config.ImageColumn("Preview")
                }
                
                # Tampilkan Dataframe (List Awal) untuk SEMUA mode
                st.dataframe(df, use_container_width=True, column_config=col_config)
                
                # Jika comparison mode, ada kolom 'Screenshot' (path lokal)
                if scraping_mode == "Comparison (Detail + Screenshot)":
                     st.write("### 📸 Screenshot Perbandingan")
                     # Grid layout untuk screenshot
                     cols = st.columns(len(df) if len(df) <= 3 else 3)
                     for idx, row in df.iterrows():
                         with cols[idx % 3]: # Wrap 3 columns
                             st.caption(f"**{row['Penyedia']}**")
                             if 'Screenshot' in row and row['Screenshot']:
                                 st.image(row['Screenshot'], caption=f"Harga: {row['Harga']}", use_container_width=True)
                             else:
                                 st.warning("No Screenshot")
                             with st.expander("Detail Produk"):
                                 st.write(f"Vendor: {row['Penyedia']}")
                                 st.write(f"Lokasi: {row['Lokasi']}")
                                 st.write(f"Link: {row['Link']}")

                # Export (Excel & CSV)
                csv_filename = f"inaproc_{keyword}_{timestamp}.csv"
                excel_filename = f"inaproc_{keyword}_{timestamp}.xlsx"
                
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), csv_filename, "text/csv")
                with c2:
                    # Excel
                    # Note: Excel won't embed images automatically without extra lib logic, keeping it text for now
                    try:
                        df.to_excel(excel_filename, index=False)
                        with open(excel_filename, "rb") as f:
                            st.download_button("Download Excel", f, excel_filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    except: pass
                    
            else:
                st.warning("Tidak ditemukan data produk.")
                
        except Exception as e:
            st.error(f"Terjadi kesalahan: {e}")
            st.code(traceback.format_exc())
        
        progress_bar.progress(100)
