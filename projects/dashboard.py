#!/usr/bin/env python3
"""📊 داشبورد هوشمند — Smart Dashboard"""

import os
import json
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

DATA_DIR = "/data/workspace/projects/dashboard_data"
os.makedirs(DATA_DIR, exist_ok=True)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 داشبورد هوشمند</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); 
            color: #fff; 
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; padding: 30px 0; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ color: #8892b0; font-size: 1.1em; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 30px 0; }}
        .card {{ 
            background: rgba(255,255,255,0.05); 
            border-radius: 15px; 
            padding: 25px; 
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }}
        .card:hover {{ transform: translateY(-5px); }}
        .card h3 {{ color: #64ffda; margin-bottom: 15px; font-size: 1.2em; }}
        .card .value {{ font-size: 2.5em; font-weight: bold; margin: 10px 0; }}
        .card .label {{ color: #8892b0; font-size: 0.9em; }}
        .card .change {{ font-size: 0.9em; margin-top: 10px; }}
        .card .change.up {{ color: #64ffda; }}
        .card .change.down {{ color: #ff6b6b; }}
        .section {{ 
            background: rgba(255,255,255,0.05); 
            border-radius: 15px; 
            padding: 25px; 
            margin: 20px 0;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .section h2 {{ color: #64ffda; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        th {{ color: #64ffda; font-weight: 600; }}
        tr:hover {{ background: rgba(255,255,255,0.05); }}
        .chart {{ 
            height: 200px; 
            background: rgba(255,255,255,0.05); 
            border-radius: 10px; 
            display: flex; 
            align-items: flex-end; 
            padding: 20px;
            gap: 10px;
        }}
        .bar {{ 
            flex: 1; 
            background: linear-gradient(180deg, #64ffda 0%, #0a192f 100%); 
            border-radius: 5px 5px 0 0;
            transition: height 0.5s;
            position: relative;
        }}
        .bar::after {{
            content: attr(data-value);
            position: absolute;
            top: -25px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 0.8em;
            color: #64ffda;
        }}
        .footer {{ text-align: center; padding: 30px; color: #8892b0; }}
        @media (max-width: 768px) {{
            .cards {{ grid-template-columns: 1fr; }}
            .header h1 {{ font-size: 1.8em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 داشبورد هوشمند</h1>
            <p>آخرین بروزرسانی: {{timestamp}}</p>
        </div>
        
        <div class="cards">
            <div class="card">
                <h3>📦 پروژه‌ها</h3>
                <div class="value">{{total_projects}}</div>
                <div class="label">پروژه فعال</div>
                <div class="change up">↑ +{{new_projects}} این هفته</div>
            </div>
            <div class="card">
                <h3>💰 درآمد</h3>
                <div class="value">{{income}}</div>
                <div class="label">تومان این ماه</div>
                <div class="change up">↑ +{{income_change}}%</div>
            </div>
            <div class="card">
                <h3>👥 مشتریان</h3>
                <div class="value">{{customers}}</div>
                <div class="label">مشتری فعال</div>
                <div class="change up">↑ +{{new_customers}} جدید</div>
            </div>
            <div class="card">
                <h3>⏰ ساعات کار</h3>
                <div class="value">{{hours}}</div>
                <div class="label">ساعت این ماه</div>
                <div class="change down">↓ -{{hours_change}}%</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📈 عملکرد هفتگی</h2>
            <div class="chart">
                {{chart_bars}}
            </div>
            <div style="display: flex; justify-content: space-around; margin-top: 10px; color: #8892b0;">
                <span>شنبه</span><span>یکشنبه</span><span>دوشنبه</span><span>سه‌شنبه</span><span>چهارشنبه</span><span>پنجشنبه</span><span>جمعه</span>
            </div>
        </div>
        
        <div class="section">
            <h2>📋 آخرین پروژه‌ها</h2>
            <table>
                <tr><th>پروژه</th><th>مشتری</th><th>وضعیت</th><th>مبلغ</th></tr>
                {{projects_table}}
            </table>
        </div>
        
        <div class="footer">
            <p>ساخته شده توسط حسین | اتوماسیون هوشمند با هوش مصنوعی</p>
        </div>
    </div>
</body>
</html>"""

def generate_dashboard():
    """Generate dashboard HTML with sample data"""
    import random
    
    weekly_data = [random.randint(2, 10) for _ in range(7)]
    max_val = max(weekly_data) if weekly_data else 1
    chart_bars = ""
    for val in weekly_data:
        height = int((val / max_val) * 100)
        chart_bars += f'<div class="bar" style="height: {{height}}%" data-value="{{val}}"></div>'
    
    projects = [
        ("ربات پشتیبانی", "فروشگاه الف", "✅ تحویل شده", "۱۵۰ دلار"),
        ("مانیتورینگ رقبا", "شرکت ب", "🔄 در حال انجام", "۲۰۰ دلار"),
        ("تولید محتوا", "بلاگر ج", "⏳ شروع نشده", "۱۰۰ دلار"),
    ]
    projects_table = ""
    for p in projects:
        projects_table += f"<tr><td>{{p[0]}}</td><td>{{p[1]}}</td><td>{{p[2]}}</td><td>{{p[3]}}</td></tr>"
    
    html = DASHBOARD_HTML.format(
        timestamp=datetime.now().strftime('%Y/%m/%d %H:%M'),
        total_projects=10,
        income="۴,۵۰۰,۰۰۰",
        income_change=25,
        customers=8,
        new_customers=3,
        hours=120,
        hours_change=5,
        chart_bars=chart_bars,
        projects_table=projects_table,
        new_projects=3
    )
    
    filename = os.path.join(DATA_DIR, "dashboard.html")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    
    return filename

if __name__ == "__main__":
    print("📊 در حال ساخت داشبورد...")
    filename = generate_dashboard()
    print(f"✅ داشبورد ساخته شد: {{filename}}")
    print(f"🌐 برای مشاهده: file://{{filename}}")
