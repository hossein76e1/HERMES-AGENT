#!/usr/bin/env python3
"""📝 تولید خودکار محتوا — Content Generator"""

import os
import json
from datetime import datetime
from openai import OpenAI

DATA_DIR = "/data/workspace/projects/generated_content"
os.makedirs(DATA_DIR, exist_ok=True)

def get_client():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)

def generate_content(topic, content_type="post", style="professional", lang="fa"):
    """Generate content using AI"""
    client = get_client()
    
    prompts = {
        "post": f"یه پست اینستاگرام حرفه‌ای درباره '{topic}' بنویس. سبک: {style}. شامل ایموجی و هشتگ باشه.",
        "article": f"یه مقاله ۵۰۰ کلمه‌ای درباره '{topic}' بنویس. سبک: {style}. ساختارمند و حرفه‌ای.",
        "tweet": f"یه توییت جذاب درباره '{topic}' بنویس. حداکثر ۲۸۰ کاراکتر. سبک: {style}.",
        "email": f"یه ایمیل تبلیغاتی درباره '{topic}' بنویس. سبک: {style}. شامل عنوان، متن و CTA باشه.",
        "story": f"یه داستان کوتاه ۲۰۰ کلمه‌ای درباره '{topic}' بنویس. سبک: {style}.",
        "ad": f"یه متن تبلیغاتی کوتاه درباره '{topic}' بنویس. سبک: {style}. جذاب و تأثیرگذار.",
    }
    
    prompt = prompts.get(content_type, prompts["post"])
    
    try:
        response = client.chat.completions.create(
            model="coder",
            messages=[
                {"role": "system", "content": f"تو یه نویسنده حرفه‌ای {lang} هستی. محتوای جذاب و حرفه‌ای بنویس."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1500
        )
        
        content = response.choices[0].message.content.strip()
        
        # Save
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(DATA_DIR, f"{content_type}_{timestamp}.json")
        
        result = {
            "topic": topic,
            "type": content_type,
            "style": style,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "word_count": len(content.split())
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return content, filename
    
    except Exception as e:
        return f"❌ خطا: {str(e)}", None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
📝 تولید خودکار محتوا

Usage:
  python content_generator.py <topic> [type] [style]

Types: post, article, tweet, email, story, ad
Styles: professional, casual, funny, serious

Examples:
  python content_generator.py "هوش مصنوعی" post professional
  python content_generator.py "فروش تابستانی" ad casual
  python content_generator.py "تکنولوژی" article serious
""")
        sys.exit(0)
    
    topic = sys.argv[1]
    content_type = sys.argv[2] if len(sys.argv) > 2 else "post"
    style = sys.argv[3] if len(sys.argv) > 3 else "professional"
    
    content, filename = generate_content(topic, content_type, style)
    print(content)
    if filename:
        print(f"\n📁 ذخیره شد: {filename}")
