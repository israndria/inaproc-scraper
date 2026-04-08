import sys
import os
import json
import time

# Tambahkan path ke V22_InaprocOrder agar bisa import api_client
sys.path.append(r"D:\Dokumen\@ POKJA 2026\V19_Scheduler\WPy64-313110\V22_InaprocOrder")

try:
    from api_client import buat_client
except ImportError:
    print("Gagal import api_client. Pastikan environment benar.")
    raise

# Query GraphQL Utama - Versi Diperkaya (TKDN, Brand, Score)
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

def search_inaproc_api(keyword, min_price=None, max_price=None, location_filter=None, max_pages=1, sort_order="Paling Sesuai"):
    """
    Scraper Inaproc menggunakan GraphQL API (v2 Dev).
    Sangat cepat dan stabil.
    """
    results = []
    client = buat_client()
    
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
    seller_region_codes = [""]
    if location_filter:
        seller_region_codes = []
        locs = [l.strip() for l in location_filter.split(",")]
        for l in locs:
            if l in REGION_MAP:
                seller_region_codes.append(REGION_MAP[l])
            else:
                if "63" not in seller_region_codes:
                    seller_region_codes.append("63")

    # 3. Main Pagination Loop
    for p in range(1, max_pages + 1):
        variables = {
          "_v0_input": {
            "sort": [{"field": sort_field, "order": sort_dir}],
            "filter": {
              "strategy": "SRP",
              "keyword": keyword,
              "regionCode": "63.05.04.1004",
              "labels": [],
              "sellerTypes": [],
              "sellerRegionCodes": seller_region_codes,
              "minPrice": float(min_price) if min_price else None,
              "maxPrice": float(max_price) if max_price else None,
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
            if not items:
                break
                
            for it in items:
                # Parsing Lokasi
                loc_obj = it.get("location", {})
                loc_name = loc_obj.get("name", "N/A")
                child = loc_obj.get("child", {})
                if child:
                    loc_name = child.get("name", loc_name)
                
                # Parsing TKDN
                tkdn_obj = it.get("tkdn") or {}
                tkdn_val = tkdn_obj.get("value", 0)
                bmp_val = tkdn_obj.get("bmpValue", 0)
                tkdn_total = tkdn_obj.get("tkdnBmp", 0)
                
                # Label PDN
                labels = it.get("labels", [])
                is_pdn = "PDN" in labels
                
                img_url = it.get("images", [""])[0] if it.get("images") else ""
                slug = it.get("slug", "")
                link = f"https://katalog.inaproc.id/product/{slug}"
                
                results.append({
                    "Keyword": keyword,
                    "Nama Produk": it.get("name", "N/A"),
                    "Brand": it.get("brand", {}).get("brandName", "N/A") if it.get("brand") else "N/A",
                    "Harga": it.get('defaultPriceWithTax', 0),
                    "TKDN %": tkdn_val,
                    "BMP %": bmp_val,
                    "Total TKDN+BMP": tkdn_total,
                    "Status PDN": "PDN" if is_pdn else "Impor",
                    "Penyedia": it.get("sellerName", "N/A"),
                    "Lokasi": loc_name,
                    "Link": link,
                    "Gambar": img_url,
                    "Score": it.get("score", 0)
                })
            
            if p >= data.get("lastPage", 1):
                break
                
        except Exception as e:
            print(f"Gagal mengambil halaman {p}: {e}")
            break
            
    return results
