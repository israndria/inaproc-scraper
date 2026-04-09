import asyncio
import sys
import os
import io

# PENTING: Fix untuk error asyncio "NotImplementedError" di Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import pandas as pd
from scraper import search_inaproc, HAS_API_CLIENT, login_bot
import time
import traceback
import re
from datetime import datetime

st.set_page_config(page_title="Inaproc Market Survey Tool", layout="wide")

# Custom CSS untuk tampilan lebih modern
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .status-box { background-color: #f0f4f8; padding: 15px; border-radius: 10px; border-left: 5px solid #007bff; margin-bottom: 20px; }
    .highlight-price { background-color: #d4edda; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

if "survey_log_lines" not in st.session_state:
    st.session_state.survey_log_lines = []

st.title("🛍️ Inaproc Market Survey Tool")
st.markdown("""
<div class="status-box">
    <strong>Tujuan:</strong> Survei Pasar untuk Dokumen Persiapan Pengadaan (DPP). 
    Gunakan <strong>Batch Search</strong> untuk mencari banyak barang sekaligus. 
    Mode API sangat cepat dan mendukung data TKDN.
</div>
""", unsafe_allow_html=True)

# Helper
def clean_price_value(value):
    if not value: return 0
    clean = re.sub(r'[^0-9]', '', str(value))
    return int(clean) if clean else 0

def format_price_str(value):
    val = clean_price_value(value)
    return f"{val:,}" if val > 0 else "0"

# Sidebar
with st.sidebar:
    st.header("⚙️ Konfigurasi Survei")
    
    with st.expander("Login Inaproc (Mode API)", expanded=False):
        st.caption(
            "Mode API butuh Chrome login yang dibuka dengan CDP. "
            "Klik tombol di bawah, login ke katalog.inaproc.id, lalu jangan tutup Chromenya."
        )
        if st.button("Buka Chrome Login", use_container_width=True, disabled=login_bot is None):
            try:
                login_bot()
                st.success("Chrome login sudah dibuka. Silakan login lalu kembali ke app ini.")
            except Exception as e:
                st.error(f"Gagal membuka Chrome login: {e}")
        if login_bot is None:
            st.error("Fungsi login tidak tersedia dari V22_InaprocOrder.")

    search_type = st.radio("Tipe Pencarian", ["Single Keyword", "Batch Search (Daftar Barang)"], index=0)
    
    if search_type == "Single Keyword":
        keywords = [st.text_input("Kata Kunci", "laptop")]
    else:
        raw_keywords = st.text_area("Daftar Barang (Satu baris satu barang)", "laptop\nprinter\nscanner")
        keywords = [k.strip() for k in raw_keywords.split("\n") if k.strip()]

    st.subheader("🛠️ Mode & Engine")
    scraping_mode = st.radio(
        "Pilih Mode",
        ["Listing (Cepat via API)", "Comparison (Detail + Screenshot via Playwright)"],
        index=0,
        help="API: Sangat cepat, include TKDN. Playwright: Buka browser, include screenshot detail."
    )
    
    use_api = (scraping_mode == "Listing (Cepat via API)")
    if use_api and not HAS_API_CLIENT:
        st.error("⚠️ API Client tidak ditemukan! Mengalihkan ke Playwright.")
        use_api = False

    st.subheader("💰 Filter Harga")
    if use_api and HAS_API_CLIENT:
        st.caption("Jika muncul error CDP 9222, buka login dulu dari panel di atas.")
    min_price = st.number_input("Harga Min (Rp)", 0, step=100000)
    max_price = st.number_input("Harga Max (Rp)", 0, step=100000)
    
    st.subheader("📍 Lokasi")
    KALSEL_LOCATIONS = [
        "Kab. Balangan", "Kab. Banjar", "Kab. Barito Kuala", "Kab. Hulu Sungai Selatan",
        "Kab. Hulu Sungai Tengah", "Kab. Hulu Sungai Utara", "Kab. Kotabaru",
        "Kab. Tabalong", "Kab. Tanah Bumbu", "Kab. Tanah Laut", "Kab. Tapin",
        "Kota Banjarbaru", "Kota Banjarmasin",
    ]
    
    def toggle_all():
        val = st.session_state.select_all_loc
        for loc in KALSEL_LOCATIONS:
            st.session_state[f"loc_{loc}"] = val

    selected_locations = []
    with st.expander("Pilih Wilayah Kalsel"):
        st.checkbox("Pilih Semua", key="select_all_loc", on_change=toggle_all)
        for loc in KALSEL_LOCATIONS:
            if f"loc_{loc}" not in st.session_state: st.session_state[f"loc_{loc}"] = False
            if st.checkbox(loc, key=f"loc_{loc}"): selected_locations.append(loc)
    location_filter = ", ".join(selected_locations) if selected_locations else ""

    st.subheader("📊 Batasan")
    sort_option = st.selectbox("Urutkan", ["Paling Sesuai", "Harga Terendah", "Harga Tertinggi"])
    limit_per_keyword = st.slider("Produk per Barang", 1, 60, 20 if use_api else 5)
    
    st.markdown("---")
    run_btn = st.button("🚀 JALANKAN SURVEI PASAR", type="primary")

# Main Logic
if run_btn:
    if not any(keywords):
        st.warning("Masukkan kata kunci terlebih dahulu.")
    else:
        st.session_state.survey_log_lines = []
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        start_time = time.time()
        
        for i, kw in enumerate(keywords):
            status_text.text(f"🔎 Men-scrape ({i+1}/{len(keywords)}): {kw}...")
            try:
                # Dispatcher ke scraper.py
                res = search_inaproc(
                    kw, 
                    use_api=use_api,
                    min_price=min_price,
                    max_price=max_price,
                    location_filter=location_filter,
                    max_pages=1 if use_api else (limit_per_keyword // 10 + 1),
                    enable_comparison=(not use_api),
                    limit_products=limit_per_keyword,
                    sort_order=sort_option
                )
                # Batasi hasil per keyword jika dari API (API ambil per page 60)
                all_results.extend(res[:limit_per_keyword])
            except Exception as e:
                st.error(f"Gagal scrape {kw}: {e}")
                st.code(traceback.format_exc())
                if use_api:
                    st.info(
                        "Mode API membutuhkan session login Inaproc di Chrome. "
                        "Buka login dari sidebar, login ke katalog.inaproc.id, lalu ulangi survei."
                    )
            
            progress_bar.progress(int(((i+1)/len(keywords))*100))
        
        status_text.empty()
        progress_bar.empty()
        
        if all_results:
            df = pd.DataFrame(all_results)
            
            # --- ANALISIS HARGA TERENDAH ---
            df['Is Termurah'] = False
            for kw in keywords:
                mask = df['Keyword'] == kw
                if any(mask):
                    min_price_val = df[mask]['Harga'].min()
                    df.loc[mask & (df['Harga'] == min_price_val), 'Is Termurah'] = True

            duration = time.time() - start_time
            st.success(f"✅ Berhasil mengumpulkan {len(df)} data produk pembanding dalam {duration:.2f} detik.")

            # Tampilkan Tabel Utama
            st.subheader("📋 Hasil Survei Pasar")
            
            df_display = df.copy()
            # Rapikan kolom: sembunyikan kolom debug/teknis dari tampilan.
            kolom_sembunyi = {
                "Product ID",
                "Slug",
                "Seller ID",
                "Seller Slug",
                "Link 1",
                "Link 2",
                "Link 3",
                "Link 4",
            }
            kolom_tampil = [c for c in df_display.columns if c not in kolom_sembunyi]
            urutan_prioritas = [
                "Keyword",
                "Nama Produk",
                "Brand",
                "Harga",
                "Total TKDN+BMP",
                "Status PDN",
                "Penyedia",
                "Lokasi",
                "Link",
                "Score",
                "Source",
            ]
            kolom_akhir = []
            for c in urutan_prioritas:
                if c in kolom_tampil and c not in kolom_akhir:
                    kolom_akhir.append(c)
            for c in kolom_tampil:
                if c not in kolom_akhir:
                    kolom_akhir.append(c)
            df_display = df_display[kolom_akhir]
            # Formatter untuk mata uang jika tipenya int
            if df_display['Harga'].dtype != object:
                df_display['Harga'] = df_display['Harga'].apply(lambda x: f"Rp {x:,.0f}")
            
            col_config = {
                "Link": st.column_config.LinkColumn("Link Produk"),
                "Gambar": st.column_config.ImageColumn("Preview"),
                "Is Termurah": st.column_config.CheckboxColumn("Termurah?"),
            }
            if 'Total TKDN+BMP' in df_display.columns:
                col_config["Total TKDN+BMP"] = st.column_config.NumberColumn("TKDN+BMP", format="%.2f%%")
            
            st.dataframe(df_display, use_container_width=True, column_config=col_config)

            # --- SCREENSHOT VIEW (Jika ada) ---
            if 'Screenshot' in df.columns and any(df['Screenshot']):
                st.subheader("📸 Screenshot Detail Produk")
                cols = st.columns(3)
                for idx, row in df[df['Screenshot'].notna()].iterrows():
                    with cols[idx % 3]:
                        st.image(row['Screenshot'], caption=f"{row['Penyedia']} - {row['Harga']}", use_container_width=True)

            # --- EXPORT AREA ---
            st.markdown("### 📥 Export ke Excel (Lampiran DPP)")
            
            df_export = df.copy()
            df_export.insert(0, 'No.', range(1, len(df_export) + 1))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Survei Pasar')
            excel_data = output.getvalue()
            
            st.download_button(
                label="Download Excel Survei Pasar",
                data=excel_data,
                file_name=f"survei_pasar_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # --- HIGHLIGHT REKOMENDASI ---
            st.subheader("⭐ Produk Rekomendasi (Termurah/TKDN Tinggi)")
            for kw in keywords:
                kw_data = df[df['Keyword'] == kw].copy()
                if not kw_data.empty:
                    # Sort by Termurah DESC, then TKDN DESC (if exists)
                    sort_cols = ['Is Termurah']
                    if 'Total TKDN+BMP' in kw_data.columns: sort_cols.append('Total TKDN+BMP')
                    
                    kw_data = kw_data.sort_values(by=sort_cols, ascending=False)
                    best = kw_data.iloc[0]
                    
                    with st.expander(f"Terbaik untuk '{kw}': {best['Penyedia']} ({best['Harga'] if isinstance(best['Harga'], str) else f'Rp {best['Harga']:,.0f}'})"):
                        c1, c2 = st.columns([1, 3])
                        with c1:
                            st.image(best['Gambar'], use_container_width=True)
                        with c2:
                            st.write(f"**Nama**: {best['Nama Produk']}")
                            if 'Total TKDN+BMP' in best:
                                st.write(f"**TKDN+BMP**: {best['Total TKDN+BMP']:.2f}% ({best.get('Status PDN', 'N/A')})")
                            st.write(f"**Lokasi**: {best['Lokasi']}")
                            st.write(f"[Buka di Katalog]({best['Link']})")

        else:
            st.warning("Tidak ditemukan data untuk kriteria tersebut.")
