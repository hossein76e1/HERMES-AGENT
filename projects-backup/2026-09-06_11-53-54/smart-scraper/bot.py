#!/usr/bin/env python3
"""
Telegram Bot interface for Smart Scraper
Sends a URL → gets structured data back
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import scrape

def handle_request(url: str, prompt: str = "", use_ai: bool = True) -> str:
    """Handle a scraping request and return formatted result"""
    try:
        result = scrape(url, ai_mode=use_ai, prompt=prompt)
        
        if "error" in result:
            return f"❌ خطا: {result['error']}"
        
        # Format output
        output = []
        output.append(f"📊 **نتیجه استخراج داده**")
        output.append(f"🔗 {url}")
        output.append(f"⏰ {result.get('scraped_at', 'N/A')}")
        output.append(f"")
        
        # Data type
        data_type = result.get('data_type', 'unknown')
        type_emoji = {
            'products': '🛍️',
            'articles': '📰',
            'contacts': '📇',
            'prices': '💰',
            'listings': '📋',
            'mixed': '📦',
            'other': '📄'
        }
        output.append(f"{type_emoji.get(data_type, '📄')} نوع داده: {data_type}")
        
        # Summary
        output.append(f"📝 {result.get('summary', 'N/A')}")
        output.append(f"")
        
        # Data preview
        extracted = result.get('extracted_data', {})
        if isinstance(extracted, list):
            output.append(f"📦 **{len(extracted)} آیتم یافت شد:**")
            for i, item in enumerate(extracted[:5], 1):
                if isinstance(item, dict):
                    preview = json.dumps(item, ensure_ascii=False)[:150]
                    output.append(f"  {i}. {preview}")
            if len(extracted) > 5:
                output.append(f"  ... و {len(extracted) - 5} آیتم دیگر")
        
        elif isinstance(extracted, dict):
            for key, value in extracted.items():
                if isinstance(value, list) and value:
                    output.append(f"📎 **{key}:** {len(value)} مورد")
        
        output.append(f"")
        output.append(f"📁 فایل‌ها ذخیره شدند")
        
        return "\n".join(output)
    
    except Exception as e:
        return f"❌ خطا در پردازش: {str(e)}"


# Test function
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bot.py <URL> [prompt]")
        sys.exit(1)
    
    url = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else ""
    
    result = handle_request(url, prompt)
    print(result)
