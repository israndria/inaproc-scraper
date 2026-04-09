from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import os
import sys
import json

# --- CONFIGURATION & DEPENDENCIES ---
# Tambahkan path ke V22_InaprocOrder agar bisa import api_client
ORDER_BOT_PATH = r"D:\Dokumen\@ POKJA 2026\V19_Scheduler\WPy64-313110\V22_InaprocOrder"
if ORDER_BOT_PATH not in sys.path:
    sys.path.append(ORDER_BOT_PATH)

try:
    from api_client import buat_client
    from order_bot import login_bot
    HAS_API_CLIENT = True
except ImportError:
    HAS_API_CLIENT = False
    login_bot = None

# --- GRAPHQL QUERIES ---
_Q_SEARCH_PRODUCTS = """
query ($_v0_input: SearchProductInput!) {
  _v0_searchProducts: searchProducts(input: $_v0_input) {
    ... on ListSearchProductResponse {
      total
      perPage
      currentPage
      lastPage
      items {
        id
        name
        sellerName
        sellerId
        defaultPriceWithTax
        location {
          name
          regionCode
          child {
            name
          }
        }
        tkdn {
          value
          bmpValue
          tkdnBmp
          status
        }
        labels
        brand {
          brandName
        }
        category {
          name
        }
        images
        slug
        score
      }
    }
    ... on GenericError {
      __typename
      message
    }
  }
}
"""

REGION_MAP = {
    "Kab. Balangan": "63.11",
    "Kab. Banjar": "63.03",
    "Kab. Barito Kuala": "63.04",
    "Kab. Hulu Sungai Selatan": "63.06",
    "Kab. Hulu Sungai Tengah": "63.07",
    "Kab. Hulu Sungai Utara": "63.08",
    "Kab. Kotabaru": "63.02",
    "Kab. Tabalong": "63.09",
    "Kab. Tanah Bumbu": "63.10",
    "Kab. Tanah Laut": "63.01",
    "Kab. Tapin": "63.05",
    "Kota Banjarbaru": "63.72",
    "Kota Banjarmasin": "63.71",
}

# --- UTILS ---
def _normalize_location(text):
    """Normalisasi nama lokasi untuk perbandingan yang lebih akurat."""
    t = text.lower().strip()
    t = t.replace("kab.", "kabupaten").replace("kab ", "kabupaten ")
    t = t.replace("kota ", "kota ")
    t = re.sub(r'\s+', ' ', t)
    return t

def _best_location_match(search_term, candidates):
    """Pilih lokasi terbaik dari daftar kandidat."""
    search_norm = _normalize_location(search_term)
    best_idx = -1
    best_score = -1 
    best_len = 9999
    for i, candidate_text in enumerate(candidates):
        cand_norm = _normalize_location(candidate_text)
        if cand_norm == search_norm: return i
        if search_norm in cand_norm:
            score = 2
            cand_len = len(cand_norm)
            if score > best_score or (score == best_score and cand_len < best_len):
                best_score = score
                best_idx = i
                best_len = cand_len
        elif cand_norm in search_norm:
            score = 1
            cand_len = len(cand_norm)
            if score > best_score or (score == best_score and cand_len < best_len):
                best_score = score
                best_idx = i
                best_len = cand_len
    return best_idx


def _slugify_seller_name(name: str) -> str:
    """
    Konversi sellerName (mis. "CV. Kuddusiah") -> "kuddusiah".
    Ini dipakai untuk membentuk URL produk yang valid: /<seller-slug>/<product-slug>.
    """
    t = (name or "").strip().lower()
    # Buang prefix umum
    t = re.sub(r"^(cv|pt|ud|pd|toko)\.?\s+", "", t, flags=re.IGNORECASE)
    # Sisakan a-z0-9 saja, jadikan dash
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t


def _build_product_links(product_id: str, slug: str, seller_id: str) -> dict:
    """
    Inaproc web routing beberapa kali berubah; sediakan beberapa kandidat URL.
    Kita pilih satu `Link` utama (paling umum), sisanya untuk fallback manual.
    """
    product_id = (product_id or "").strip()
    slug = (slug or "").strip()
    seller_id = (seller_id or "").strip()

    # Kandidat route yang sering dipakai (urutan: paling mungkin)
    candidates = []
    # Pola paling umum yang terbukti: /<seller-slug>/<product-slug>
    # seller slug diambil dari sellerName (heuristik slugify).
    # (seller_id tidak dipakai untuk URL ini, tapi tetap disimpan untuk debug)
    # NOTE: `slug` dari GraphQL biasanya sudah product-slug.
    # seller slug disuntikkan saat pemanggilan _build_product_links() dari loop items.
    if slug and product_id:
        candidates.append(f"https://katalog.inaproc.id/product/{slug}/{product_id}")
    if slug:
        candidates.append(f"https://katalog.inaproc.id/product/{slug}")
    if product_id:
        candidates.append(f"https://katalog.inaproc.id/product/{product_id}")
    if slug and seller_id:
        candidates.append(f"https://katalog.inaproc.id/product/{slug}?sellerId={seller_id}")

    # Dedup tapi pertahankan urutan
    seen = set()
    uniq = []
    for u in candidates:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)

    out = {"Link": uniq[0] if uniq else ""}
    for i, u in enumerate(uniq[:4], start=1):
        out[f"Link {i}"] = u
    return out

# --- ENGINE 1: GRAPHQL API (Fast & Reliable) ---
def search_inaproc_api(keyword, min_price=None, max_price=None, location_filter=None, max_pages=1, sort_order="Paling Sesuai"):
    """Scraper Inaproc menggunakan GraphQL API (v2)."""
    if not HAS_API_CLIENT:
        raise Exception("api_client tidak ditemukan. Pastikan folder V22_InaprocOrder tersedia.")
    
    results = []
    try:
        client = buat_client()
    except Exception as e:
        msg = str(e)
        if "ECONNREFUSED 127.0.0.1:9222" in msg or "connect_over_cdp" in msg:
            raise RuntimeError(
                "Mode API membutuhkan Chrome login Inaproc di port CDP 9222. "
                "Buka login dari app ini, login ke katalog.inaproc.id, lalu jalankan survei lagi."
            ) from e
        raise
    
    # 1. Tentukan Sorting
    sort_field = "RELEVANCE"
    sort_dir = "DESC"
    if sort_order == "Harga Terendah":
        sort_field = "PRICE"
        sort_dir = "ASC"
    elif sort_order == "Harga Tertinggi":
        sort_field = "PRICE"
        sort_dir = "DESC"

    # 2. Tentukan Filter Lokasi
    seller_region_codes = []
    if location_filter:
        locs = [l.strip() for l in location_filter.split(",")]
        for l in locs:
            if l in REGION_MAP:
                seller_region_codes.append(REGION_MAP[l])
            else:
                # Fallback to Kalsel General if any Kalsel loc mentioned but not in map
                if "63" not in seller_region_codes:
                    seller_region_codes.append("63")
    
    if not seller_region_codes:
        seller_region_codes = [""] # No location filter

    # 3. Main Pagination Loop
    for p in range(1, max_pages + 1):
        variables = {
          "_v0_input": {
            "sort": [{"field": sort_field, "order": sort_dir}],
            "filter": {
              "strategy": "SRP",
              "keyword": keyword,
              "regionCode": "63.05.04.1004", # Default region context
              "labels": [],
              "sellerTypes": [],
              "sellerRegionCodes": seller_region_codes,
              "minPrice": float(min_price) if min_price and min_price > 0 else None,
              "maxPrice": float(max_price) if max_price and max_price > 0 else None,
              "rateTypes": [],
              "productTypes": [],
              "ratingAvgGte": None
            },
            "pagination": {
              "page": p,
              "perPage": 60
            }
          }
        }
        
        try:
            resp = client._graphql(_Q_SEARCH_PRODUCTS, variables=variables)
            data = resp.get("data", {}).get("_v0_searchProducts", {})
            
            if data.get("__typename") == "GenericError":
                print(f"Error dari Inaproc: {data.get('message')}")
                break
                
            items = data.get("items", [])
            if not items: break
                
            for it in items:
                loc_obj = it.get("location", {})
                loc_name = loc_obj.get("name", "N/A")
                child = loc_obj.get("child", {})
                if child: loc_name = child.get("name", loc_name)
                
                tkdn_obj = it.get("tkdn") or {}
                tkdn_val = tkdn_obj.get("value", 0)
                bmp_val = tkdn_obj.get("bmpValue", 0)
                tkdn_total = tkdn_obj.get("tkdnBmp", 0)
                
                labels = it.get("labels", [])
                is_pdn = "PDN" in labels
                
                img_url = it.get("images", [""])[0] if it.get("images") else ""
                slug = it.get("slug", "")
                product_id = it.get("id", "")
                seller_id = it.get("sellerId", "")
                seller_name = it.get("sellerName", "")
                seller_slug = _slugify_seller_name(seller_name)

                links = _build_product_links(product_id=product_id, slug=slug, seller_id=seller_id)
                if seller_slug and slug:
                    # Sisipkan kandidat yang benar di depan (paling prioritas)
                    primary = f"https://katalog.inaproc.id/{seller_slug}/{slug}"
                    links = {"Link": primary, "Link 1": primary, **{k: v for k, v in links.items() if k != "Link"}}
                
                results.append({
                    "Keyword": keyword,
                    "Product ID": product_id,
                    "Slug": slug,
                    "Nama Produk": it.get("name", "N/A"),
                    "Brand": it.get("brand", {}).get("brandName", "N/A") if it.get("brand") else "N/A",
                    "Harga": it.get('defaultPriceWithTax', 0),
                    "TKDN %": tkdn_val,
                    "BMP %": bmp_val,
                    "Total TKDN+BMP": tkdn_total,
                    "Status PDN": "PDN" if is_pdn else "Impor",
                    "Penyedia": it.get("sellerName", "N/A"),
                    "Seller ID": seller_id,
                    "Seller Slug": seller_slug,
                    "Lokasi": loc_name,
                    **links,
                    "Gambar": img_url,
                    "Score": it.get("score", 0),
                    "Source": "API"
                })
            
            if p >= data.get("lastPage", 1): break
                
        except Exception as e:
            print(f"Gagal mengambil halaman {p}: {e}")
            break
            
    return results

# --- ENGINE 2: PLAYWRIGHT (Detailed + Screenshots) ---
def search_inaproc_playwright(keyword, headless=False, min_price=0, max_price=0, location_filter=None, max_pages=1, enable_comparison=False, limit_products=0, sort_order="Paling Sesuai"):
    """Scrapes katalog.inaproc.id menggunakan Playwright."""
    results = []
    if enable_comparison:
        if not os.path.exists("screenshots"): os.makedirs("screenshots")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = context.new_page()
        
        url = f"https://katalog.inaproc.id/search?keyword={keyword}"
        if min_price > 0: url += f"&minPrice={min_price}"
        if max_price > 0: url += f"&maxPrice={max_price}"
            
        print(f"Mengakses: {url}")
        page.goto(url, timeout=60000)

        # --- LOGIKA FILTER LOKASI (UI AUTOMATION) ---
        location_list = [loc.strip() for loc in location_filter.split(",") if loc.strip()] if location_filter else []

        def collect_modal_labels(modal):
            labels = modal.locator("label")
            count = labels.count()
            texts = []
            for i in range(count):
                try: texts.append(labels.nth(i).inner_text().strip())
                except: texts.append("")
            return labels, texts

        def scroll_modal_content(page, modal):
            try:
                page.evaluate("""() => {
                    const modal = document.querySelector("div[role='dialog']");
                    if (!modal) return;
                    const divs = modal.querySelectorAll('div');
                    for (const div of divs) {
                        const style = window.getComputedStyle(div);
                        const overflowY = style.overflowY;
                        if ((overflowY === 'auto' || overflowY === 'scroll') && div.scrollHeight > div.clientHeight) div.scrollTop += 300;
                    }
                }""")
            except: pass

        def search_and_find_location(page, modal, search_input, loc_term, search_term):
            search_input.fill("")
            time.sleep(1)
            search_input.fill(search_term)
            time.sleep(6)
            labels, candidates = collect_modal_labels(modal)
            best_check = _best_location_match(loc_term, candidates)
            if best_check >= 0 and _normalize_location(candidates[best_check]) == _normalize_location(loc_term):
                return labels, candidates, best_check
            
            prev_count = len(candidates)
            for _ in range(8):
                scroll_modal_content(page, modal)
                time.sleep(2)
                labels, candidates = collect_modal_labels(modal)
                if _best_location_match(loc_term, candidates) >= 0: break
                if len(candidates) == prev_count: break
                prev_count = len(candidates)
            return labels, candidates, _best_location_match(loc_term, candidates)

        def open_location_modal(page):
            page.wait_for_selector("text=Rp", timeout=15000)
            loc_btn = page.locator("div").filter(has_text="Lokasi Pengiriman").last
            if loc_btn.count() > 0: loc_btn.click(); time.sleep(2)
            show_more_btns = page.locator("text=Lihat Selengkapnya").all()
            for btn in show_more_btns:
                try:
                    if not btn.is_visible(): continue
                    btn.click(); time.sleep(2)
                    modal = page.locator("div[role='dialog']")
                    if modal.count() > 0: return modal
                except: continue
            return None

        if location_list:
            BATCH_SIZE = 7
            batches = [location_list[i:i+BATCH_SIZE] for i in range(0, len(location_list), BATCH_SIZE)]
            for batch in batches:
                modal = open_location_modal(page)
                if not modal: break
                search_input = modal.locator("input[placeholder*='Cari']")
                applied = 0
                for loc_term in batch:
                    all_labels, candidates, best = search_and_find_location(page, modal, search_input, loc_term, loc_term)
                    if best < 0:
                        core_term = re.sub(r'^(kab\.|kabupaten|kota)\s+', '', loc_term.strip(), flags=re.IGNORECASE).strip()
                        all_labels, candidates, best = search_and_find_location(page, modal, search_input, loc_term, core_term)
                    if best >= 0:
                        target_label = all_labels.nth(best)
                        target_label.scroll_into_view_if_needed()
                        try: target_label.click(timeout=5000); applied += 1; time.sleep(1)
                        except: break
                if applied > 0:
                    modal.locator("button").filter(has_text="Terapkan").first.click()
                    time.sleep(8)
                else: page.keyboard.press("Escape")

        if sort_order != "Paling Sesuai":
            try:
                page.wait_for_selector("text=Rp", timeout=15000)
                sort_btn = page.locator("text=Paling Sesuai").first or page.locator("text=Urutkan").first
                if sort_btn:
                    sort_btn.click(); time.sleep(1.5)
                    page.locator(f"text={sort_order}").first.click(); time.sleep(5)
            except: pass

        comparison_count = 0
        for p_num in range(1, max_pages + 1):
            page.wait_for_selector("text=Rp", timeout=15000)
            for _ in range(3): page.mouse.wheel(0, 2000); time.sleep(1)
            product_cards = page.locator("div.grid > a").all()
            
            for card in product_cards:
                try:
                    card_text = card.inner_text()
                    if "Belum Aktif" in card_text or "Stok Habis" in card_text: continue
                    link = "https://katalog.inaproc.id" + card.get_attribute("href")
                    title = card.locator("div.line-clamp-2").inner_text()
                    price = card.locator("div.w-fit").first.inner_text()
                    vendor_container = card.locator("div.h-4.cursor-pointer span")
                    location = vendor_container.nth(0).inner_text() if vendor_container.count() >= 1 else "N/A"
                    vendor = vendor_container.nth(1).inner_text() if vendor_container.count() >= 2 else "N/A"
                    
                    screenshot_path = None
                    if enable_comparison:
                        detail_page = context.new_page()
                        detail_page.goto(link, timeout=45000); time.sleep(2)
                        safe_name = re.sub(r'[\\/*?:"<>|]', "", vendor)[:30].strip() or "detail"
                        filename = f"{safe_name}_{int(time.time())}.png"
                        filepath = os.path.join(os.getcwd(), "screenshots", filename)
                        detail_page.screenshot(path=filepath, full_page=True)
                        detail_page.close()
                        screenshot_path = filepath
                        comparison_count += 1
                    
                    results.append({
                        "Keyword": keyword,
                        "Nama Produk": title,
                        "Harga": int(re.sub(r'[^0-9]', '', price)) if price else 0,
                        "Penyedia": vendor,
                        "Lokasi": location,
                        "Link": link,
                        "Gambar": card.locator("img").first.get_attribute("src") if card.locator("img").count() > 0 else "",
                        "Screenshot": screenshot_path,
                        "Source": "Playwright"
                    })
                    if enable_comparison and limit_products > 0 and comparison_count >= limit_products: break
                except: continue
            
            if enable_comparison and limit_products > 0 and comparison_count >= limit_products: break
            if p_num < max_pages:
                page.keyboard.press("End"); time.sleep(1)
                next_btn = page.locator("button").filter(has_text=re.compile(r"^" + str(p_num + 1) + "$")).first
                if next_btn.count() > 0: next_btn.click(); time.sleep(5)
                else: break
        browser.close()
    return results

# --- DISPATCHER ---
def search_inaproc(keyword, use_api=True, **kwargs):
    """Fungsi utama yang memilih engine secara otomatis."""
    if use_api and HAS_API_CLIENT:
        # Map parameters dari format lama ke format API
        return search_inaproc_api(
            keyword, 
            min_price=kwargs.get('min_price'),
            max_price=kwargs.get('max_price'),
            location_filter=kwargs.get('location_filter'),
            max_pages=kwargs.get('max_pages', 1),
            sort_order=kwargs.get('sort_order', "Paling Sesuai")
        )
    else:
        return search_inaproc_playwright(keyword, **kwargs)

if __name__ == "__main__":
    # Test run
    data = search_inaproc("laptop", use_api=True)
    print(f"Hasil API: {len(data)} produk")
