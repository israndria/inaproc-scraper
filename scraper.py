from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import os


def _normalize_location(text):
    """Normalisasi nama lokasi untuk perbandingan yang lebih akurat."""
    t = text.lower().strip()
    # Normalisasi singkatan umum
    t = t.replace("kab.", "kabupaten").replace("kab ", "kabupaten ")
    t = t.replace("kota ", "kota ")
    # Hapus spasi berlebih
    t = re.sub(r'\s+', ' ', t)
    return t


def _best_location_match(search_term, candidates):
    """
    Pilih lokasi terbaik dari daftar kandidat.
    Prioritas: exact match > starts with > shortest containing match
    Returns: index of best match, atau -1 jika tidak ada yang cocok.
    """
    search_norm = _normalize_location(search_term)

    best_idx = -1
    best_score = -1  # higher is better
    best_len = 9999

    for i, candidate_text in enumerate(candidates):
        cand_norm = _normalize_location(candidate_text)

        # Exact match (setelah normalisasi) = skor tertinggi
        if cand_norm == search_norm:
            return i

        # Cek apakah search term ada di candidate
        if search_norm in cand_norm:
            score = 2
            # Prefer yang lebih pendek (lebih spesifik)
            # "Kab. Banjar" (10 char) lebih baik dari "Kab. Banjarnegara" (18 char)
            cand_len = len(cand_norm)
            if score > best_score or (score == best_score and cand_len < best_len):
                best_score = score
                best_idx = i
                best_len = cand_len
        elif cand_norm in search_norm:
            # Candidate adalah substring dari search (jarang tapi mungkin)
            score = 1
            cand_len = len(cand_norm)
            if score > best_score or (score == best_score and cand_len < best_len):
                best_score = score
                best_idx = i
                best_len = cand_len

    return best_idx


def search_inaproc(keyword, headless=True, min_price=0, max_price=0, location_filter=None, max_pages=1, enable_comparison=False, limit_products=0, sort_order="Paling Sesuai"):
    """
    Scrapes katalog.inaproc.id using Playwright.
    sort_order: "Paling Sesuai", "Harga Terendah", "Harga Tertinggi"
    """
    results = []
    
    # Buat folder screenshot jika belum ada
    if enable_comparison:
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
    
    with sync_playwright() as p:
        # Launch browser dengan argumen anti-bot
        browser = p.chromium.launch(
            headless=False,  # Harus False agar tidak terdeteksi bot dengan mudah
            args=["--disable-blink-features=AutomationControlled"] 
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate
        # Base URL
        url = f"https://katalog.inaproc.id/search?keyword={keyword}"
        
        # Add Filters (Price URL)
        if min_price > 0:
            url += f"&minPrice={min_price}"
        if max_price > 0:
            url += f"&maxPrice={max_price}"
            
        print(f"Mengakses: {url}")
        page.goto(url, timeout=60000)

        # --- LOGIKA FILTER LOKASI (UI AUTOMATION) --- (harus SEBELUM sorting, karena filter lokasi me-reset sort)
        # Support multiple lokasi: "kab. banjar, kota banjarbaru" -> ["kab. banjar", "kota banjarbaru"]
        location_list = []
        if location_filter:
            location_list = [loc.strip() for loc in location_filter.split(",") if loc.strip()]

        # Helper functions untuk filter lokasi (didefinisikan di luar loop agar reusable)
        def collect_modal_labels(modal):
            labels = modal.locator("label")
            count = labels.count()
            texts = []
            for i in range(count):
                try:
                    texts.append(labels.nth(i).inner_text().strip())
                except:
                    texts.append("")
            return labels, texts

        def scroll_modal_content(page, modal):
            """Coba berbagai cara scroll di dalam modal."""
            try:
                page.evaluate("""
                    () => {
                        const modal = document.querySelector("div[role='dialog']");
                        if (!modal) return;
                        const divs = modal.querySelectorAll('div');
                        for (const div of divs) {
                            const style = window.getComputedStyle(div);
                            const overflowY = style.overflowY;
                            if ((overflowY === 'auto' || overflowY === 'scroll') && div.scrollHeight > div.clientHeight) {
                                div.scrollTop += 300;
                            }
                        }
                    }
                """)
            except: pass
            try:
                modal_box = modal.bounding_box()
                if modal_box:
                    page.mouse.move(
                        modal_box['x'] + modal_box['width'] / 2,
                        modal_box['y'] + modal_box['height'] * 0.75
                    )
                    page.mouse.wheel(0, 500)
            except: pass
            try:
                page.keyboard.press("PageDown")
            except: pass

        def search_and_find_location(page, modal, search_input, loc_term, search_term):
            """Search, scroll, dan cari match untuk satu lokasi."""
            search_input.fill("")
            time.sleep(1)
            search_input.fill(search_term)
            print(f"Mengetik '{search_term}' di search box...")
            time.sleep(6)

            labels, candidates = collect_modal_labels(modal)
            print(f"Hasil search '{search_term}' ({len(candidates)}): {candidates}")

            best_check = _best_location_match(loc_term, candidates)
            if best_check >= 0:
                if _normalize_location(candidates[best_check]) == _normalize_location(loc_term):
                    print(f"Exact match langsung ditemukan: '{candidates[best_check]}'")
                    return labels, candidates, best_check

            prev_count = len(candidates)
            for scroll_attempt in range(8):
                scroll_modal_content(page, modal)
                time.sleep(2)

                labels, candidates = collect_modal_labels(modal)
                new_count = len(candidates)

                if new_count > prev_count:
                    print(f"Scroll #{scroll_attempt+1}: {prev_count} -> {new_count} label")

                best_check = _best_location_match(loc_term, candidates)
                if best_check >= 0:
                    if _normalize_location(candidates[best_check]) == _normalize_location(loc_term):
                        print(f"Scroll #{scroll_attempt+1}: Exact match '{candidates[best_check]}'")
                        return labels, candidates, best_check

                if new_count > prev_count and scroll_attempt > 0:
                    prev_count = new_count
                    continue

                if new_count == prev_count:
                    if scroll_attempt < 5:
                        try:
                            page.evaluate("""
                                () => {
                                    const modal = document.querySelector("div[role='dialog']");
                                    if (!modal) return;
                                    const divs = modal.querySelectorAll('div');
                                    for (const div of divs) {
                                        if (div.scrollHeight > div.clientHeight + 10) {
                                            div.scrollTop = div.scrollTop + 500;
                                        }
                                    }
                                }
                            """)
                        except: pass
                        time.sleep(2)
                        labels, candidates = collect_modal_labels(modal)
                        if len(candidates) > prev_count:
                            print(f"JS scroll #{scroll_attempt+1}: {prev_count} -> {len(candidates)} label")
                            prev_count = len(candidates)
                            continue
                    print(f"Scroll stabil di {new_count} label setelah {scroll_attempt+1} percobaan.")
                    break
                prev_count = new_count

            best = _best_location_match(loc_term, candidates)
            return labels, candidates, best

        def open_location_modal(page):
            """Buka modal lokasi: klik accordion -> klik Lihat Selengkapnya -> return modal."""
            page.wait_for_selector("text=Rp", timeout=15000)
            time.sleep(2)

            try:
                page.wait_for_selector("text=Lokasi Pengiriman", timeout=10000)
            except:
                print("Timeout menunggu accordion lokasi.")

            loc_btn = page.locator("div").filter(has_text="Lokasi Pengiriman").last
            if loc_btn.count() > 0:
                print("Klik accordion 'Lokasi Pengiriman'...")
                loc_btn.click()
                time.sleep(2)

            try:
                page.wait_for_selector("text=Lihat Selengkapnya", timeout=5000)
            except:
                print("Timeout menunggu 'Lihat Selengkapnya'.")

            show_more_btns = page.locator("text=Lihat Selengkapnya").all()
            for btn_idx, btn in enumerate(show_more_btns):
                try:
                    if not btn.is_visible():
                        continue
                    print(f"Clicking 'Lihat Selengkapnya' #{btn_idx}...")
                    btn.click()
                    time.sleep(2)
                    modal = page.locator("div[role='dialog']")
                    if modal.count() > 0 and modal.is_visible():
                        return modal
                except:
                    continue
            return None

        def select_locations_in_modal(page, modal, loc_batch):
            """Pilih beberapa lokasi di modal yang sudah terbuka. Return jumlah berhasil."""
            search_input = modal.locator("input[placeholder*='Cari']")
            applied = 0

            for loc_term in loc_batch:
                print(f"\n--- Mencari lokasi: '{loc_term}' ---")

                if search_input.count() == 0:
                    print("[WARN] Search box tidak ditemukan di modal.")
                    break

                # Strategi 1: Search dengan term lengkap
                all_labels, candidates, best = search_and_find_location(page, modal, search_input, loc_term, loc_term)

                is_exact = False
                if best >= 0:
                    is_exact = _normalize_location(candidates[best]) == _normalize_location(loc_term)

                # Strategi 2: Coba search dengan kata kunci inti
                if not is_exact:
                    core_term = re.sub(r'^(kab\.|kabupaten|kota)\s+', '', loc_term.strip(), flags=re.IGNORECASE).strip()
                    if core_term and core_term.lower() != loc_term.lower():
                        print(f"[RETRY] Tidak exact match. Coba search dengan '{core_term}'...")
                        all_labels, candidates, best = search_and_find_location(page, modal, search_input, loc_term, core_term)
                        if best >= 0:
                            is_exact = _normalize_location(candidates[best]) == _normalize_location(loc_term)

                if best >= 0:
                    chosen = candidates[best]
                    if is_exact:
                        print(f"[EXACT MATCH] '{chosen}' (index {best})")
                    else:
                        print(f"[BEST MATCH] '{chosen}' (index {best}) — bukan exact match")

                    target_label = all_labels.nth(best)
                    target_label.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    try:
                        target_label.click(timeout=5000)
                    except Exception as click_err:
                        if "not enabled" in str(click_err).lower() or "disabled" in str(click_err).lower():
                            print(f"[LIMIT] Checkbox disabled — website membatasi jumlah lokasi. Berhenti memilih.")
                            break
                        raise click_err
                    time.sleep(1)
                    applied += 1
                    print(f"[OK] '{chosen}' berhasil dipilih.")

                    # Reset scroll modal ke atas
                    try:
                        page.evaluate("""
                            () => {
                                const modal = document.querySelector("div[role='dialog']");
                                if (!modal) return;
                                const divs = modal.querySelectorAll('div');
                                for (const div of divs) {
                                    if (div.scrollHeight > div.clientHeight + 10) {
                                        div.scrollTop = 0;
                                    }
                                }
                            }
                        """)
                    except: pass
                else:
                    print(f"[WARN] Tidak ada match untuk '{loc_term}' dari kandidat: {candidates}")

            return applied

        # --- MAIN FILTER LOKASI ---
        if location_list:
            print(f"Mencoba menerapkan filter lokasi: {location_list}")
            total_applied = 0

            # Batch lokasi per 7 (batas website inaproc)
            BATCH_SIZE = 7
            batches = [location_list[i:i+BATCH_SIZE] for i in range(0, len(location_list), BATCH_SIZE)]
            print(f"Total {len(location_list)} lokasi, dibagi {len(batches)} batch (max {BATCH_SIZE}/batch)")

            try:
                for batch_idx, batch in enumerate(batches):
                    print(f"\n=== BATCH {batch_idx+1}/{len(batches)}: {batch} ===")

                    modal = open_location_modal(page)
                    if not modal:
                        print("[WARN] Modal lokasi tidak berhasil dibuka.")
                        break

                    print("Modal terbuka! Memilih lokasi...")
                    applied = select_locations_in_modal(page, modal, batch)
                    total_applied += applied

                    # Klik Terapkan
                    if applied > 0:
                        save_btns = modal.locator("button").filter(has_text="Terapkan").all()
                        if len(save_btns) > 0:
                            print("Klik 'Terapkan'...")
                            save_btns[0].click()
                        else:
                            close_btn = modal.locator("button svg").first
                            if close_btn.count() > 0: close_btn.click()
                            else: page.mouse.click(0, 0)

                        print(f"[OK] Batch {batch_idx+1}: {applied} lokasi diterapkan. Menunggu halaman reload...")
                        time.sleep(8)
                    else:
                        print(f"[WARN] Batch {batch_idx+1}: Tidak ada lokasi yang berhasil dipilih.")
                        page.keyboard.press("Escape")
                        time.sleep(1)

                print(f"\n[TOTAL] {total_applied} dari {len(location_list)} lokasi berhasil diterapkan.")

            except Exception as e:
                print(f"Gagal menerapkan filter lokasi UI: {e}")
                # Pastikan modal tertutup agar tidak menghalangi elemen lain
                try:
                    modal_check = page.locator("div[role='dialog']")
                    if modal_check.count() > 0 and modal_check.is_visible():
                        page.keyboard.press("Escape")
                        time.sleep(1)
                except: pass

        # --- LOGIKA SORTING (UI AUTOMATION) --- (SETELAH filter lokasi agar tidak ter-reset)
        if sort_order != "Paling Sesuai":
            print(f"Mencoba sorting: {sort_order}")
            try:
                page.wait_for_selector("text=Rp", timeout=15000)

                sort_btn = None
                for txt in ["Paling Sesuai", "Urutkan", "Relevansi"]:
                    candidate = page.locator(f"text={txt}").first
                    if candidate.count() > 0 and candidate.is_visible():
                        sort_btn = candidate
                        break

                if sort_btn:
                    print(f"Tombol sort ditemukan: {sort_btn.inner_text()}")
                    sort_btn.click()
                    time.sleep(1.5)

                    target_opt = page.locator(f"text={sort_order}").first
                    if target_opt.count() > 0 and target_opt.is_visible():
                         print(f"Clicking option: {sort_order}")
                         target_opt.click()
                         time.sleep(5)
                    else:
                         print(f"Opsi '{sort_order}' TIDAK muncul di dropdown.")
                else:
                    print("Tombol pembuka sort TIDAK ditemukan.")

            except Exception as e:
                print(f"Gagal sorting: {e}")

        # Variable untuk comparison limit
        comparison_count = 0
        
        # --- MAIN PAGINATION LOOP ---
        for current_page_num in range(1, max_pages + 1):
            print(f"--- Scraping Halaman {current_page_num} ---")
            
            try:
                # Tunggu skeleton loader menghilang atau setidaknya data muncul
                # Kita tunggu elemen yang BUKAN skeleton (animasi pulse)
                # Biasanya produk ada di dalam grid.
                # Strategy: Tunggu ada text harga "Rp"
                print("Menunggu data dimuat...")
                page.wait_for_selector("text=Rp", timeout=15000)
                
                # Scroll down to load images (lazy load)
                # Scroll berkali-kali untuk memastikan infinite scroll (dalam satu halaman) kelar
                # Meskipun kita pakai pagination, dalam satu page mungkin ada 60 item yg perlu load
                for _ in range(5):
                    page.mouse.wheel(0, 2000)
                    time.sleep(1)
                
                # Selector Produk yang VALID (Analisis dari debug_page.html)
                # Produk dibungkus dalam <a> tag yang merupakan anak langsung dari div.grid
                # Class grid di Inaproc: "mt-6 grid grid-cols-1 ..."
                product_cards = page.locator("div.grid > a").all()
                
                print(f"Ditemukan {len(product_cards)} produk di halaman ini.")
                
                inactive_count_on_page = 0
                
                for card in product_cards:
                    try:
                        # --- SMART PAGINATION LOGIC ---
                        # Cek status produk (Active/Inactive)
                        # Gunakan text content card untuk deteksi "Belum Aktif" dsb.
                        card_text = card.inner_text()
                        # Keywords yang diminta user + variasi
                        if "Belum Aktif" in card_text or "Stok Habis" in card_text:
                            inactive_count_on_page += 1
                            continue

                        # Extract Data
                        link = "https://katalog.inaproc.id" + card.get_attribute("href")
                        
                        # Judul (Class: line-clamp-2 text-sm text-tertiary500)
                        title_el = card.locator("div.line-clamp-2")
                        title = title_el.inner_text() if title_el.count() > 0 else "N/A"
                        
                        # Harga (Class: w-fit truncate text-sm font-bold)
                        price_el = card.locator("div.w-fit").first
                        price = price_el.inner_text() if price_el.count() > 0 else "N/A"
                        
                        # Vendor (Ada di dalam div h-4 cursor-pointer, span kedua biasanya nama vendor)
                        # Struktur: Div > Span (Kota) + Span (Vendor)
                        vendor_container = card.locator("div.h-4.cursor-pointer span")
                        
                        location = "N/A"
                        vendor = "N/A"
                        
                        if vendor_container.count() >= 2:
                            location = vendor_container.nth(0).inner_text()
                            vendor = vendor_container.nth(1).inner_text()
                        elif vendor_container.count() == 1:
                            # Fallback basic
                            text = vendor_container.first.inner_text()
                            if "Kab." in text or "Kota" in text:
                                location = text
                            else:
                                vendor = text

                        # --- STRICT POST-FILTERING (PYTHON SIDE) ---
                        # Pastikan lokasi sesuai permintaan user, jika filter UI gagal
                        if location_list:
                            loc_found_norm = _normalize_location(location)
                            match_any = False
                            for loc_req in location_list:
                                loc_req_norm = _normalize_location(loc_req)
                                if loc_req_norm in loc_found_norm or loc_found_norm in loc_req_norm:
                                    match_any = True
                                    break
                            if not match_any:
                                continue
                                
                        # Image
                        img_tag = card.locator("img").first
                        img_url = img_tag.get_attribute("src") if img_tag.count() > 0 else ""
                        
                        screenshot_path = None
                        
                        # --- COMPARISON MODE LOGIC ---
                        if enable_comparison:
                            print(f"[Comparison] Membuka detail produk: {title}...")
                            try:
                                # Open link in new page
                                detail_page = context.new_page()
                                detail_page.goto(link, timeout=45000)
                                detail_page.wait_for_load_state("networkidle")
                                time.sleep(2) # Give explicit render time
                                
                                # Sanitize vendor for filename
                                safe_name = re.sub(r'[\\/*?:"<>|]', "", vendor)[:50].strip()
                                # Fallback jika vendor kosong
                                if not safe_name:
                                    safe_name = re.sub(r'[\\/*?:"<>|]', "", title)[:20].strip()
                                    
                                filename = f"{safe_name}_{int(time.time())}.png"
                                filepath = os.path.join(os.getcwd(), "screenshots", filename)
                                
                                print(f"Saving screenshot to: {filepath}")
                                detail_page.screenshot(path=filepath, full_page=True)
                                detail_page.close()
                                
                                screenshot_path = filepath
                                comparison_count += 1
                                
                            except Exception as detail_e:
                                print(f"Gagal screenshot detail: {detail_e}")
                                if 'detail_page' in locals(): detail_page.close()
                        
                        results.append({
                            "Nama Produk": title,
                            "Harga": price,
                            "Penyedia": vendor,
                            "Lokasi": location,
                            "Link": link,
                            "Gambar": img_url,
                            "Screenshot": screenshot_path # New Field
                        })
                        
                        # Check Comparison Limit
                        if enable_comparison and limit_products > 0 and comparison_count >= limit_products:
                            print(f"Limit comparison {limit_products} tercapai. Berhenti.")
                            break
                            
                    except Exception as e:
                        print(f"Error parsing card: {e}")
                        continue
                        
                # --- SMART STOP CONDITION ---
                if len(product_cards) > 0:
                    inactive_ratio = inactive_count_on_page / len(product_cards)
                    # Jika > 50% produk di halaman ini inactive, kemungkinan halaman selanjutnya sampah.
                    if inactive_ratio > 0.5: 
                        print(f"[SMART STOP] {inactive_count_on_page}/{len(product_cards)} produk tidak aktif. Menghentikan pagination.")
                        break
                
                # Break outer loop if comparison limit reached
                if enable_comparison and limit_products > 0 and comparison_count >= limit_products:
                    break

                # --- NAVIGASI KE HALAMAN BERIKUTNYA ---
                if current_page_num < max_pages:
                    next_page_num = current_page_num + 1
                    print(f"Mencoba pindah ke halaman {next_page_num}...")
                    
                    # Cari tombol dengan angka halaman berikutnya
                    # Kita pakai locator tombol yang text-nya persis angka
                    # Karena kadang ada "10", "11", kita pakai exact match atau regex boundaries
                    
                    # Scroll ke bawah dulu pol
                    page.keyboard.press("End")
                    time.sleep(1)
                    
                    # Locator untuk tombol angka dengan EXACT MATCH regex
                    # ^2$ matches "2", but not "12"
                    next_btn = page.locator("button").filter(has_text=re.compile(r"^" + str(next_page_num) + "$")).first
                    
                    if next_btn.count() > 0 and next_btn.is_visible():
                        print(f"Klik tombol halaman {next_page_num}...")
                        next_btn.scroll_into_view_if_needed()
                        next_btn.click()
                        time.sleep(5) # Tunggu load halaman baru
                    else:
                        print(f"Tombol halaman {next_page_num} tidak ditemukan. Berhenti scraping.")
                        # Coba fallback ke tombol 'Next' chevron jika ada (biasanya tombol terakhir tanpa text angka)
                        # Tapi untuk 1-5, angka harusnya ada.
                        break
                        
            except Exception as e:
                print(f"Terjadi kesalahan saat halaman {current_page_num}: {e}")
                page.screenshot(path=f"error_page_{current_page_num}.png")
                # Jangan break, lanjut loop siapa tahu (meski aneh)
            
        browser.close()
    
    return results

if __name__ == "__main__":
    # Test run
    data = search_inaproc("laptop", headless=True)
    print(f"Hasil: {len(data)} produk")
    if data:
        print(data[0])
