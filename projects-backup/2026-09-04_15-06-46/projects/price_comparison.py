#!/usr/bin/env python3
"""💰 مقایسه قیمت — Price Comparison Tool"""

import os
import json
import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup

DATA_DIR = "/data/workspace/projects/price_data"
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8'
}

def extract_prices(url):
    """Extract prices from a website"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        prices = []
        
        # Method 1: Look for common price patterns
        for elem in soup.find_all(string=lambda s: s and any(kw in s for kw in ['تومان', 'ریال', 'IRR', 'IRT', '$'])):
            text = elem.strip()
            if len(text) < 100:
                # Extract number
                import re
                numbers = re.findall(r'[\d,]+', text)
                for num in numbers:
                    clean_num = num.replace(',', '')
                    if clean_num.isdigit() and int(clean_num) > 1000:
                        prices.append({
                            "text": text[:50],
                            "value": int(clean_num),
                            "currency": "تومان" if "تومان" in text else ("ریال" if "ریال" in text else "$")
                        })
        
        # Method 2: Look for price classes
        for elem in soup.find_all(class_=lambda c: c and any(kw in str(c).lower() for kw in ['price', 'cost', 'amount', 'قیمت'])):
            text = elem.get_text(strip=True)
            import re
            numbers = re.findall(r'[\d,]+', text)
            for num in numbers:
                clean_num = num.replace(',', '')
                if clean_num.isdigit() and int(clean_num) > 1000:
                    prices.append({
                        "text": text[:50],
                        "value": int(clean_num),
                        "currency": "تومان"
                    })
        
        # Method 3: Look for meta tags
        for meta in soup.find_all('meta', property=True):
            if 'price' in meta.get('property', '').lower():
                content = meta.get('content', '')
                import re
                numbers = re.findall(r'[\d,]+', content)
                for num in numbers:
                    clean_num = num.replace(',', '')
                    if clean_num.isdigit() and int(clean_num) > 1000:
                        prices.append({
                            "text": f"meta: {meta.get('property', '')}",
                            "value": int(clean_num),
                            "currency": "تومان"
                        })
        
        # Remove duplicates and sort
        unique_prices = []
        seen = set()
        for p in prices:
            key = (p['value'], p['currency'])
            if key not in seen:
                seen.add(key)
                unique_prices.append(p)
        
        unique_prices.sort(key=lambda x: x['value'])
        
        return {
            "url": url,
            "domain": requests.utils.urlparse(url).netloc,
            "prices": unique_prices,
            "min_price": unique_prices[0]['value'] if unique_prices else None,
            "max_price": unique_prices[-1]['value'] if unique_prices else None,
            "avg_price": sum(p['value'] for p in unique_prices) // len(unique_prices) if unique_prices else None,
            "count": len(unique_prices),
            "extracted_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        return {
            "url": url,
            "error": str(e),
            "prices": [],
            "count": 0,
            "extracted_at": datetime.now().isoformat()
        }

def compare_prices(urls):
    """Compare prices across multiple sites"""
    results = []
    for url in urls:
        result = extract_prices(url)
        results.append(result)
    
    # Find best prices
    all_prices = []
    for r in results:
        for p in r.get('prices', []):
            all_prices.append({**p, 'source': r['domain']})
    
    all_prices.sort(key=lambda x: x['value'])
    
    comparison = {
        "sites": results,
        "all_prices": all_prices,
        "cheapest": all_prices[0] if all_prices else None,
        "most_expensive": all_prices[-1] if all_prices else None,
        "compared_at": datetime.now().isoformat()
    }
    
    # Save
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = os.path.join(DATA_DIR, f"comparison_{timestamp}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    
    # CSV
    csv_file = os.path.join(DATA_DIR, f"comparison_{timestamp}.csv")
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["منبع", "متن", "مبلغ", "واحدها"])
        for p in all_prices:
            writer.writerow([p['source'], p['text'], p['value'], p['currency']])
    
    return comparison, json_file, csv_file

def format_comparison(comparison):
    """Format comparison report"""
    report = []
    report.append("💰 گزارش مقایسه قیمت")
    report.append(f"⏰ {comparison['compared_at']}")
    report.append("")
    
    for site in comparison['sites']:
        report.append(f"🔗 {site['domain']}")
        if 'error' in site:
            report.append(f"  ❌ خطا: {site['error']}")
        else:
            report.append(f"  📊 قیمت‌ها: {site['count']}")
            if site['min_price']:
                report.append(f"  💵 کمترین: {site['min_price']:,} تومان")
            report.append("")
    
    if comparison['cheapest']:
        report.append(f"🏆 ارزان‌ترین: {comparison['cheapest']['value']:,} تومان")
        report.append(f"   📍 {comparison['cheapest']['source']}")
    
    if comparison['most_expensive']:
        report.append(f"💎 گران‌ترین: {comparison['most_expensive']['value']:,} تومان")
        report.append(f"   📍 {comparison['most_expensive']['source']}")
    
    return "\n".join(report)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
💰 مقایسه قیمت

Usage:
  python price_comparison.py <url1> [url2] [url3] ...

Examples:
  python price_comparison.py https://site1.com/product https://site2.com/product
  python price_comparison.py https://digikala.com/product/123 https://torob.com/product/123
""")
        sys.exit(0)
    
    urls = sys.argv[1:]
    comparison, jf, cf = compare_prices(urls)
    print(format_comparison(comparison))
    print(f"\n📁 JSON: {jf}")
    print(f"📁 CSV: {cf}")
