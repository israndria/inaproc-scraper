from playwright.sync_api import sync_playwright

def extract_full_html():
    print("--- Extracting Full Rendered HTML ---")
    with sync_playwright() as p:
        # Hubungkan ke Chrome yang sedang terbuka
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = context.new_page()
        
        # Navigasi ke search
        keyword = "laptop"
        url = f"https://katalog.inaproc.id/search?keyword={keyword}"
        print(f"Navigasi ke: {url}")
        page.goto(url, wait_until="networkidle")
        
        # Tunggu render
        page.wait_for_timeout(5000)
        
        # Ambil HTML penuh setelah render
        full_html = page.content()
        with open("search_rendered.html", "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"HTML rendered disimpan ke search_rendered.html ({len(full_html)} karakter).")
        
        page.close()

if __name__ == "__main__":
    extract_full_html()
