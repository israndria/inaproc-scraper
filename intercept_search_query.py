import sys
import json
from playwright.sync_api import sync_playwright

def intercept_headers():
    print("--- Intercepting Inaproc GraphQL Request HEADERS ---")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = context.new_page()
        
        captured = []

        def on_request(request):
            if "/graphql" in request.url and request.method == "POST":
                try:
                    body = request.post_data_json
                    if body:
                        captured.append({
                            "url": request.url,
                            "headers": request.headers,
                            "payload": body
                        })
                        print(f"Captured Request: {body.get('operationName')}")
                except Exception:
                    pass

        page.on("request", on_request)
        
        # Trigger search
        keyword = "laptop"
        url = f"https://katalog.inaproc.id/search?keyword={keyword}"
        print(f"Navigasi ke: {url}")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        if captured:
            print("\n--- ANALISA HEADER ---")
            # Kita ambil query yang isinya _v0_searchProducts atau yang sejenis
            for c in captured:
                payload = c["payload"]
                if "_v0_searchProducts" in str(payload):
                    print(f"Ditemukan Request Target!")
                    print(f"URL: {c['url']}")
                    print(f"Headers: {json.dumps(c['headers'], indent=2)}")
                    print(f"Payload: {json.dumps(payload, indent=2)}")
                    
                    with open("api_request_full.json", "w", encoding="utf-8") as f:
                        json.dump(c, f, indent=2)
                    print("\nData lengkap disimpan ke api_request_full.json")
                    break
        else:
            print("Tidak ada request GraphQL tertangkap.")
            
        page.close()

if __name__ == "__main__":
    intercept_headers()
