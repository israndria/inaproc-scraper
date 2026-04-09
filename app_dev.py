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

# Custom CSS
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .status-box { background-color: #f0f4f8; padding: 15px; border-radius: 10px; border-left: 5px solid #007bff; margin-bottom: 20px; }
    .highlight-price { background-color: #d4edda; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🛍️ Inaproc Market Survey Tool (API v2)")
st.markdown("""
<div class="status-box">
    <strong>Tujuan:</strong> Survei Pasar untuk Dokumen Persiapan Pengadaan (DPP). 
    Mencari perbandingan harga, TKDN, dan status PDN secara otomatis.
</div>
""", unsafe_allow_html=True)

# Helper
def clean_price_value(value):
    if not value: return 0
    clean = re.sub(r'[^0-9]', '', str(value))
    return int(clean) if clean else 0

# Sidebar
with st.sidebar:
    st.header("⚙️ Konfigurasi Survei")
    
    search_type = st.radio("Tipe Pencarian", ["Single Keyword", "Batch Search (Daftar Barang)"], index=0)
    
    if search_type == "Single Keyword":
        keywords = [st.text_input("Kata Kunci", "laptop")]
    else:
        raw_keywords = st.text_area("Daftar Barang (Satu baris satu barang)", "laptop\nprinter\nscanner")
        keywords = [k.strip() for k in raw_keywords.split("\n") if k.strip()]

    st.subheader("💰 Filter Harga")
    min_price = st.number_input("Harga Min (Rp)", 0, step=100000)
    max_price = st.number_input("Harga Max (Rp)", 0, step=100000)
    
    st.subheader("📍 Lokasi")
    KALSEL_LOCATIONS = [
        "Kab. Balangan", "Kab. Banjar", "Kab. Barito Kuala", "Kab. Hulu Sungai Selatan",
        "Kab. Hulu Sungai Tengah", "Kab. Hulu Sungai Utara", "Kab. Kotabaru",
        "Kab. Tabalong", "Kab. Tanah Bumbu", "Kab. Tanah Laut", "Kab. Tapin",
        "Kota Banjarbaru", "Kota Banjarmasin",
    ]
    selected_locations = []
    with st.expander("Pilih Wilayah Kalsel"):
        for loc in KALSEL_LOCATIONS:
            if st.checkbox(loc, key=f"loc_{loc}"): selected_locations.append(loc)
    location_filter = ", ".join(selected_locations) if selected_locations else ""

    st.subheader("📊 Batasan")
    sort_option = st.selectbox("Urutkan", ["Paling Sesuai", "Harga Terendah", "Harga Tertinggi"])
    limit_per_keyword = st.slider("Produk per Barang", 10, 60, 20)
    
    st.markdown("---")
    run_btn = st.button("🚀 JALANKAN SURVEI PASAR", type="primary")

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
        except: return None
        finally: 
            if 'page' in locals(): page.close()

# Main Logic
if run_btn:
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, kw in enumerate(keywords):
        status_text.text(f"🔎 Men-scrape ({i+1}/{len(keywords)}): {kw}...")
        try:
            res = search_inaproc_api(
                kw, 
                min_price=min_price if min_price > 0 else None,
                max_price=max_price if max_price > 0 else None,
                location_filter=location_filter,
                max_pages=1, # Cukup 1 halaman per keyword untuk survei cepat
                sort_order=sort_option
            )
            # Batasi hasil per keyword
            all_results.extend(res[:limit_per_keyword])
        except Exception as e:
            st.error(f"Gagal scrape {kw}: {e}")
        progress_bar.progress(int(((i+1)/len(keywords))*100))
    
    status_text.empty()
    progress_bar.empty()
    
    if all_results:
        df = pd.DataFrame(all_results)
        
        # --- ANALISIS HARGA TERENDAH ---
        # Untuk setiap keyword, tandai mana yang termurah
        df['Is Termurah'] = False
        for kw in keywords:
            mask = df['Keyword'] == kw
            if any(mask):
                min_price_val = df[mask]['Harga'].min()
                df.loc[mask & (df['Harga'] == min_price_val), 'Is Termurah'] = True

        st.success(f"✅ Berhasil mengumpulkan {len(df)} data produk pembanding.")

        # Tampilkan Tabel Utama
        st.subheader("📋 Hasil Survei Pasar")
        
        # Formatter untuk mata uang
        df_display = df.copy()
        df_display['Harga'] = df_display['Harga'].apply(lambda x: f"Rp {x:,.0f}")
        
        st.dataframe(df_display, use_container_width=True, column_config={
            "Link": st.column_config.LinkColumn("Link Produk"),
            "Gambar": st.column_config.ImageColumn("Preview"),
            "Total TKDN+BMP": st.column_config.NumberColumn("TKDN+BMP", format="%.2f%%"),
            "Is Termurah": st.column_config.CheckboxColumn("Termurah?"),
        })

        # --- EXPORT AREA ---
        st.markdown("### 📥 Export ke Excel (Lampiran DPP)")
        
        # Tambahkan nomor urut
        df_export = df.copy()
        df_export.insert(0, 'No.', range(1, len(df_export) + 1))
        
        # Buat file excel
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
        
        # --- HIGHLIGHT TERBAIK ---
        st.subheader("⭐ Produk Rekomendasi (Termurah/TKDN Tinggi)")
        for kw in keywords:
            kw_data = df[df['Keyword'] == kw].sort_values(by=['Is Termurah', 'Total TKDN+BMP'], ascending=[False, False])
            if not kw_data.empty:
                best = kw_data.iloc[0]
                with st.expander(f"Terbaik untuk '{kw}': {best['Penyedia']} (Rp {best['Harga']:,.0f})"):
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        st.image(best['Gambar'], use_container_width=True)
                    with col2:
                        st.write(f"**Nama**: {best['Nama Produk']}")
                        st.write(f"**TKDN+BMP**: {best['Total TKDN+BMP']:.2f}% ({best['Status PDN']})")
                        st.write(f"**Lokasi**: {best['Lokasi']}")
                        st.write(f"[Buka di Katalog]({best['Link']})")

    else:
        st.warning("Tidak ditemukan data untuk kriteria tersebut.")
