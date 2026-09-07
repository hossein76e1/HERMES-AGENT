#!/usr/bin/env python3
"""
Smart Scraper — ربات استخراج داده هوشمند
Extracts structured data from any website using AI
Author: Hossein | Freelance AI Automation
"""

import sys
import json
import csv
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── AI-powered extraction ──────────────────────────────────────────────
def ai_extract(html_content: str, url: str, user_prompt: str = "") -> dict:
    """Use OpenAI to extract structured data from HTML"""
    from openai import OpenAI
    
    # Read API key from env or config
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # Truncate HTML to avoid token limits
    clean_html = html_content[:15000]
    
    prompt = f"""You are a data extraction AI. Extract structured data from this HTML page.

URL: {url}
User request: {user_prompt if user_prompt else "Extract all useful structured data"}

HTML content:
{clean_html}

Return ONLY valid JSON with this structure:
{{
  "page_title": "string",
  "extracted_data": [list of items found],
  "data_type": "products|articles|contacts|prices|listings|other",
  "fields": ["field1", "field2", ...],
  "summary": "brief summary of what was found"
}}

Important: Return ONLY the JSON, no markdown, no explanation."""

    try:
        response = client.chat.completions.create(
            model="coder",
            messages=[
                {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=4000
        )
        
        result_text = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        result_text = re.sub(r'```json\s*', '', result_text)
        result_text = re.sub(r'```\s*', '', result_text)
        
        return json.loads(result_text)
    except Exception as e:
        return {"error": f"AI extraction failed: {str(e)}"}


# ── Traditional extraction ─────────────────────────────────────────────
def traditional_extract(html_content: str, url: str) -> dict:
    """Extract data using BeautifulSoup without AI"""
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Clean up
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    
    data = {
        "page_title": soup.title.string if soup.title else "No title",
        "url": url,
        "extracted_data": [],
        "data_type": "other",
        "summary": ""
    }
    
    # Extract links
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)[:100]
        if text and href.startswith(('http', '/')):
            links.append({"text": text, "url": href})
    
    # Extract tables
    tables = []
    for table in soup.find_all('table'):
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    
    # Extract lists
    lists = []
    for ul in soup.find_all(['ul', 'ol']):
        items = [li.get_text(strip=True) for li in ul.find_all('li') if li.get_text(strip=True)]
        if items:
            lists.append(items)
    
    # Extract headings structure
    headings = []
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4']):
        text = h.get_text(strip=True)
        if text:
            headings.append({"level": h.name, "text": text})
    
    # Extract all text blocks
    paragraphs = []
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if len(text) > 20:
            paragraphs.append(text[:500])
    
    # Extract images
    images = []
    for img in soup.find_all('img', src=True):
        alt = img.get('alt', '')
        src = img['src']
        if src.startswith(('http', '/')):
            images.append({"src": src, "alt": alt})
    
    # Build result
    data["extracted_data"] = {
        "links": links[:50],
        "tables": tables,
        "lists": lists[:20],
        "headings": headings,
        "paragraphs": paragraphs[:20],
        "images": images[:30]
    }
    
    data["data_type"] = "mixed"
    data["summary"] = f"Found: {len(links)} links, {len(tables)} tables, {len(headings)} headings, {len(paragraphs)} paragraphs, {len(images)} images"
    
    return data


# ── Fetch URL ──────────────────────────────────────────────────────────
def fetch_url(url: str) -> tuple:
    """Fetch URL and return (html_content, status_code)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        return response.text, response.status_code
    except requests.exceptions.RequestException as e:
        return "", 0


# ── Save to CSV ────────────────────────────────────────────────────────
def save_to_csv(data: dict, filename: str):
    """Save extracted data to CSV"""
    extracted = data.get("extracted_data", {})
    
    if isinstance(extracted, list) and extracted:
        # List of items (AI mode)
        if extracted:
            # Collect all fieldnames from all items
            all_keys = set()
            for item in extracted:
                if isinstance(item, dict):
                    all_keys.update(item.keys())
            fieldnames = list(all_keys) if all_keys else ['value']
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for item in extracted:
                    if isinstance(item, dict):
                        writer.writerow(item)
                    else:
                        writer.writerow({'value': str(item)})
    
    elif isinstance(extracted, dict):
        # Mixed data (traditional mode)
        rows = []
        for link in extracted.get('links', [])[:50]:
            rows.append({'type': 'link', 'text': link.get('text', ''), 'url': link.get('url', '')})
        for item in extracted.get('lists', [])[:10]:
            for li in item[:20]:
                rows.append({'type': 'list_item', 'text': li, 'url': ''})
        
        if rows:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['type', 'text', 'url'])
                writer.writeheader()
                writer.writerows(rows)
    
    print(f"✅ CSV saved: {filename}")


# ── Save to JSON ───────────────────────────────────────────────────────
def save_to_json(data: dict, filename: str):
    """Save extracted data to JSON"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON saved: {filename}")


# ── Main ───────────────────────────────────────────────────────────────
def scrape(url: str, ai_mode: bool = True, prompt: str = "", output: str = "") -> dict:
    """Main scraping function"""
    print(f"\n🔍 Fetching: {url}")
    
    html, status = fetch_url(url)
    if not html:
        return {"error": f"Failed to fetch URL (status: {status})"}
    
    print(f"📄 Page loaded ({len(html)} bytes, status: {status})")
    
    if ai_mode:
        print("🤖 Extracting with AI...")
        data = ai_extract(html, url, prompt)
    else:
        print("📊 Extracting with BeautifulSoup...")
        data = traditional_extract(html, url)
    
    data['source_url'] = url
    data['scraped_at'] = datetime.now().isoformat()
    data['html_size'] = len(html)
    
    # Save output
    if not output:
        domain = urlparse(url).netloc.replace('www.', '').replace('.', '_')
        output = f"output_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    save_dir = os.path.dirname(os.path.abspath(__file__))
    
    json_file = os.path.join(save_dir, f"{output}.json")
    save_to_json(data, json_file)
    
    csv_file = os.path.join(save_dir, f"{output}.csv")
    save_to_csv(data, csv_file)
    
    data['output_json'] = json_file
    data['output_csv'] = csv_file
    
    return data


# ── CLI ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
╔══════════════════════════════════════════════════════════╗
║           🕷️  Smart Scraper — استخراج داده هوشمند         ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Usage:                                                  ║
║    python scraper.py <URL> [options]                      ║
║                                                          ║
║  Options:                                                ║
║    --no-ai      Use BeautifulSoup only (no API cost)     ║
║    --prompt "X" Tell AI what to extract specifically      ║
║    --output X   Custom output filename (without ext)     ║
║                                                          ║
║  Examples:                                               ║
║    python scraper.py https://example.com                  ║
║    python scraper.py https://shop.com --prompt "prices"   ║
║    python scraper.py https://news.com --no-ai             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
        """)
        sys.exit(0)
    
    url = sys.argv[1]
    ai_mode = "--no-ai" not in sys.argv
    prompt = ""
    output = ""
    
    if "--prompt" in sys.argv:
        idx = sys.argv.index("--prompt")
        if idx + 1 < len(sys.argv):
            prompt = sys.argv[idx + 1]
    
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]
    
    result = scrape(url, ai_mode=ai_mode, prompt=prompt, output=output)
    
    if "error" in result:
        print(f"\n❌ Error: {result['error']}")
    else:
        print(f"\n{'='*50}")
        print(f"📊 Data Type: {result.get('data_type', 'unknown')}")
        print(f"📝 Summary: {result.get('summary', 'N/A')}")
        print(f"📁 JSON: {result.get('output_json', 'N/A')}")
        print(f"📁 CSV: {result.get('output_csv', 'N/A')}")
        print(f"{'='*50}")
