#!/usr/bin/env python3
"""🔍 استخراج و مانیتورینگ رقبا — Competitor Monitor"""

import os
import json
import csv
from datetime import datetime
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

DATA_DIR = "/data/workspace/projects/competitor_data"
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8'
}

def monitor_site(url, name=""):
    """Monitor a competitor website and extract key data"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()
        
        # Extract products/items
        products = []
        for item in soup.find_all(['div', 'li', 'article'], class_=True):
            classes = ' '.join(item.get('class', []))
            if any(kw in classes.lower() for kw in ['product', 'item', 'card', 'listing']):
                text = item.get_text(strip=True)[:200]
                if text:
                    products.append(text)
        
        # Extract prices
        prices = []
        for price in soup.find_all(string=lambda s: s and ('تومان' in s or 'ریال' in s or '$' in s)):
            prices.append(price.strip()[:50])
        
        # Extract headings
        headings = []
        for h in soup.find_all(['h1', 'h2', 'h3']):
            text = h.get_text(strip=True)
            if text and len(text) > 3:
                headings.append(text[:100])
        
        # Extract links
        links = []
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)[:80]
            if text and len(text) > 5:
                links.append({"text": text, "url": a['href'][:200]})
        
        domain = urlparse(url).netloc.replace('www.', '').replace('.', '_')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        data = {
            "name": name or domain,
            "url": url,
            "scraped_at": datetime.now().isoformat(),
            "status": "success",
            "products": products[:30],
            "prices": prices[:20],
            "headings": headings[:15],
            "top_links": links[:20],
            "html_size": len(response.content),
            "summary": {
                "products_found": len(products),
                "prices_found": len(prices),
                "headings_found": len(headings),
                "links_found": len(links)
            }
        }
        
        # Save JSON
        json_file = os.path.join(DATA_DIR, f"{domain}_{timestamp}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Save CSV
        csv_file = os.path.join(DATA_DIR, f"{domain}_{timestamp}.csv")
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["نوع", "محتوا", "لینک"])
            for p in products[:30]:
                writer.writerow(["محصول", p, ""])
            for pr in prices[:20]:
                writer.writerow(["قیمت", pr, ""])
            for h in headings[:15]:
                writer.writerow(["عنوان", h, ""])
        
        return data, json_file, csv_file
    
    except Exception as e:
        return {"error": str(e), "url": url, "status": "failed"}, None, None

def compare_sites(urls_with_names):
    """Compare multiple competitor sites"""
    results = []
    for url, name in urls_with_names:
        data, jf, cf = monitor_site(url, name)
        results.append(data)
    
    # Save comparison
    compare_file = os.path.join(DATA_DIR, f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(compare_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    return results, compare_file

def format_report(data):
    """Format a nice report"""
    if "error" in data:
        return f"❌ خطا: {data['error']}\n🔗 {data['url']}"
    
    report = []
    report.append(f"📊 گزارش مانیتورینگ: {data['name']}")
    report.append(f"🔗 {data['url']}")
    report.append(f"⏰ {data['scraped_at']}")
    report.append(f"📦 محصولات: {data['summary']['products_found']}")
    report.append(f"💰 قیمت‌ها: {data['summary']['prices_found']}")
    report.append(f"📝 عناوین: {data['summary']['headings_found']}")
    report.append(f"🔗 لینک‌ها: {data['summary']['links_found']}")
    
    if data['products']:
        report.append("\n📦 نمونه محصولات:")
        for i, p in enumerate(data['products'][:5], 1):
            report.append(f"  {i}. {p[:80]}")
    
    if data['prices']:
        report.append("\n💰 نمونه قیمت‌ها:")
        for pr in data['prices'][:5]:
            report.append(f"  • {pr}")
    
    return "\n".join(report)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
🔍 استخراج و مانیتورینگ رقبا

Usage:
  python competitor_monitor.py <URL> [name]
  python competitor_monitor.py --compare url1 name1 url2 name2 ...

Examples:
  python competitor_monitor.py https://digikala.com "دیجی‌کالا"
  python competitor_monitor.py https://torob.com "ترب"
  python competitor_monitor.py --compare https://digikala.com "دیجی‌کالا" https://torob.com "ترب"
""")
        sys.exit(0)
    
    if sys.argv[1] == "--compare":
        args = sys.argv[2:]
        pairs = [(args[i], args[i+1]) for i in range(0, len(args), 2)]
        results, cf = compare_sites(pairs)
        for r in results:
            print(format_report(r))
            print("---")
        print(f"\n📁 مقایسه ذخیره شد: {cf}")
    else:
        url = sys.argv[1]
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        data, jf, cf = monitor_site(url, name)
        print(format_report(data))
        if jf:
            print(f"\n📁 JSON: {jf}")
            print(f"📁 CSV: {cf}")
