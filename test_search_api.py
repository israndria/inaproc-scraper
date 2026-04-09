import sys
import os
import json

# Tambahkan path ke V22_InaprocOrder agar bisa import api_client
sys.path.append(r"D:\Dokumen\@ POKJA 2026\V19_Scheduler\WPy64-313110\V22_InaprocOrder")

try:
    from api_client import buat_client
except ImportError:
    print("Gagal import api_client. Pastikan path benar.")
    sys.exit(1)

# Query GraphQL yang SEBENARNYA (Hasil Intercept)
_Q_SEARCH_FINAL = """
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
        defaultPriceWithTax
        location {
          name
          regionCode
          child {
            name
          }
        }
        images
        slug
      }
    }
    ... on GenericError {
      __typename
      message
    }
  }
}
"""

def test_final_api_search(keyword="laptop"):
    print(f"--- Memulai Test FINAL API Search untuk: {keyword} ---")
    
    try:
        # 1. Buat client
        client = buat_client()
        
        # 2. Siapkan variabel sesuai hasil intercept
        variables = {
          "_v0_input": {
            "sort": [
              {
                "field": "RELEVANCE",
                "order": "DESC"
              }
            ],
            "filter": {
              "strategy": "SRP",
              "keyword": keyword,
              "regionCode": "63.05.04.1004", # Tapin Selatan (sesuai browser)
              "labels": [],
              "sellerTypes": [],
              "sellerRegionCodes": [""],
              "minPrice": None,
              "maxPrice": None,
              "rateTypes": [],
              "productTypes": [],
              "ratingAvgGte": None
            },
            "pagination": {
              "page": 1,
              "perPage": 60
            }
          }
        }
        
        # 3. Panggil API
        print("Memanggil GraphQL searchProducts (via alias _v0)...")
        result = client._graphql(_Q_SEARCH_FINAL, variables=variables)
        
        # 4. Analisa hasil
        if "errors" in result:
            print("ERROR dari GraphQL:")
            print(json.dumps(result["errors"], indent=2))
            return
            
        data = result.get("data", {}).get("_v0_searchProducts", {})
        if data.get("__typename") == "GenericError":
            print(f"GenericError: {data.get('message')}")
            return
            
        total = data.get("total", 0)
        items = data.get("items", [])
        
        print(f"SUKSES BESAR! Ditemukan total {total} produk.")
        print(f"Mengambil {len(items)} produk dari halaman 1.")
        
        for i, it in enumerate(items[:10]): # Tampilkan 10 saja
            name = it.get("name", "N/A")
            price = it.get("defaultPriceWithTax", 0)
            vendor = it.get("sellerName", "N/A")
            
            loc_obj = it.get("location", {})
            loc_name = loc_obj.get("name", "N/A")
            child = loc_obj.get("child", {})
            if child:
                loc_name = f"{loc_name} > {child.get('name', '')}"
            
            slug = it.get("slug", "")
            product_id = it.get("id", "")
            link_slug = f"https://katalog.inaproc.id/product/{slug}" if slug else ""
            link = f"https://katalog.inaproc.id/product/{product_id}" if product_id else link_slug
            
            print(f"[{i+1}] {name} | Rp {price:,.0f} | {vendor} | {loc_name}")

    except Exception as e:
        print(f"Error fatal: {e}")

if __name__ == "__main__":
    test_final_api_search()
