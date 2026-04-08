from bs4 import BeautifulSoup
import re

def analyze_html():
    with open("search_rendered.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Cari semua link produk
    product_links = soup.find_all("a", href=re.compile(r"^/product/"))
    print(f"Ditemukan {len(product_links)} link produk.")
    
    for i, a in enumerate(product_links[:5]):
        href = a['href']
        # Cari harga dan nama di dalam <a> atau elemen tetangganya
        text = a.get_text(separator="|").strip()
        print(f"[{i+1}] Link: {href}")
        print(f"    Text: {text[:200]}...")

if __name__ == "__main__":
    analyze_html()
