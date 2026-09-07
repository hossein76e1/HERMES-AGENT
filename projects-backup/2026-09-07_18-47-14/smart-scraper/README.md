# 🕷️ Smart Scraper — استخراج داده هوشمند

ربات استخراج داده از وب‌سایت‌ها با هوش مصنوعی

## ✨ امکانات

- 🔍 استخراج هوشمند داده با AI
- 📊 خروجی CSV و JSON
- 🕷️ پشتیبانی از انواع وب‌سایت‌ها
- 🎯 استخراج هدفمند با prompt دلخواه
- 💰 دو حالت: AI (پولی) و BeautifulSoup (رایگان)

## 🚀 نصب

```bash
pip install -r requirements.txt
```

## 📖 استفاده

### خط فرمان

```bash
# استخراج ساده
python scraper.py https://example.com

# استخراج با AI و پرامپت خاص
python scraper.py https://shop.com --prompt "قیمت محصولات"

# استخراج رایگان (بدون AI)
python scraper.py https://news.com --no-ai

# ذخیره با نام دلخواه
python scraper.py https://site.com --output my_data
```

### به عنوان کتابخانه

```python
from scraper import scrape

# استخراج با AI
result = scrape(
    "https://example.com",
    ai_mode=True,
    prompt="Extract all product prices"
)

# استخراج سنتی
result = scrape(
    "https://example.com",
    ai_mode=False
)

print(result)
```

## 📁 ساختار خروجی

```
smart-scraper/
├── scraper.py          # اسکریپت اصلی
├── bot.py              # رابط تلگرام
├── requirements.txt    # پکیج‌ها
├── output_site.json    # خروجی JSON
└── output_site.csv     # خروجی CSV
```

## 💡 نکات

- **حالت AI**: از OpenAI API استفاده می‌کنه، دقیق‌تره ولی هزینه داره
- **حالت BeautifulSoup**: رایگان و سریع، ولی ساختاری‌تر
- **پرامپت**: می‌تونی دقیقاً بگی چی استخراج کنه

## 🎯 پروژه‌های پیشنهادی

1. **ربات قیمت‌یابی**: استخراج قیمت از فروشگاه‌ها
2. **جمع‌آوری اخبار**: استخراج عناوین و لینک‌ها
3. **لیست مشاغل**: استخراج اطلاعات تماس
4. **مقایسه محصولات**: مقایسه قیمت چند سایت

## 📝 لایسنس

Free for personal and commercial use
