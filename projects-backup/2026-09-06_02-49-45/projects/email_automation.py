#!/usr/bin/env python3
"""📧 خودکارسازی ایمیل — Email Automation"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

DATA_DIR = "/data/workspace/projects/email_data"
os.makedirs(DATA_DIR, exist_ok=True)

def load_templates():
    file = os.path.join(DATA_DIR, "templates.json")
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "welcome": {
            "name": "خوش‌آمدگویی",
            "subject": "🎉 به ما خوش اومدید!",
            "body": "سلام {name}!\n\nاز عضویت شما ممنونیم.\n\nبا ما در ارتباط باشید.\n\nبا احترام،\nتیم پشتیبانی"
        },
        "promo": {
            "name": "تبلیغاتی",
            "subject": "🔥 تخفیف ویژه {discount}%",
            "body": "سلام {name}!\n\nفقط امروز! {discount}% تخفیف روی تمام محصولات.\n\nکد تخفیف: {code}\n\nبا احترام،\nتیم فروش"
        },
        "followup": {
            "name": "پیگیری",
            "subject": "📋 پیگیری سفارش شما",
            "body": "سلام {name}!\n\nسفارش شما با کد {order_id} در حال پردازش است.\n\nزمان تحویل تقریبی: {delivery_date}\n\nبا احترام،\nتیم ارسال"
        }
    }

def save_templates(templates):
    file = os.path.join(DATA_DIR, "templates.json")
    with open(file, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

def send_email(to, subject, body, smtp_config=None):
    """Send email (demo mode - saves to file)"""
    if not smtp_config:
        # Demo mode - save to file
        email_data = {
            "to": to,
            "subject": subject,
            "body": body,
            "sent_at": datetime.now().isoformat(),
            "status": "demo (not actually sent)"
        }
        filename = os.path.join(DATA_DIR, f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(email_data, f, ensure_ascii=False, indent=2)
        return True, filename
    
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_config['from']
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(smtp_config['host'], smtp_config['port'])
        server.starttls()
        server.login(smtp_config['user'], smtp_config['password'])
        server.send_message(msg)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)

def send_bulk(emails, template_name, variables=None):
    """Send bulk emails using template"""
    templates = load_templates()
    if template_name not in templates:
        return False, f"Template '{template_name}' not found"
    
    template = templates[template_name]
    results = []
    
    for email_data in emails:
        subject = template['subject']
        body = template['body']
        
        if variables and email_data.get('email') in variables:
            vars = variables[email_data['email']]
            for key, val in vars.items():
                subject = subject.replace(f'{{{key}}}', str(val))
                body = body.replace(f'{{{key}}}', str(val))
        
        for key, val in email_data.items():
            if key != 'email':
                subject = subject.replace(f'{{{key}}}', str(val))
                body = body.replace(f'{{{key}}}', str(val))
        
        success, result = send_email(email_data['email'], subject, body)
        results.append({
            "email": email_data['email'],
            "success": success,
            "result": result
        })
    
    # Save report
    report = {
        "template": template_name,
        "total": len(emails),
        "successful": sum(1 for r in results if r['success']),
        "failed": sum(1 for r in results if not r['success']),
        "results": results,
        "sent_at": datetime.now().isoformat()
    }
    
    report_file = os.path.join(DATA_DIR, f"bulk_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return True, report


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
📧 خودکارسازی ایمیل

Usage:
  python email_automation.py send <to> <subject> <body>
  python email_automation.py template <name>
  python email_automation.py bulk <template> <emails_file>

Examples:
  python email_automation.py send user@example.com "سلام" "متن ایمیل"
  python email_automation.py template welcome
  python email_automation.py bulk promo emails.json
""")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "send" and len(sys.argv) >= 5:
        to = sys.argv[2]
        subject = sys.argv[3]
        body = sys.argv[4]
        success, result = send_email(to, subject, body)
        print(f"{'✅' if success else '❌'} {result}")
    
    elif cmd == "template" and len(sys.argv) >= 3:
        templates = load_templates()
        name = sys.argv[2]
        if name in templates:
            t = templates[name]
            print(f"📝 قالب: {t['name']}\n📌 عنوان: {t['subject']}\n💬 متن:\n{t['body']}")
        else:
            print(f"❌ قالب '{name}' پیدا نشد.")
            print(f"قالب‌های موجود: {', '.join(templates.keys())}")
    
    elif cmd == "bulk" and len(sys.argv) >= 4:
        template_name = sys.argv[2]
        emails_file = sys.argv[3]
        with open(emails_file, "r", encoding="utf-8") as f:
            emails = json.load(f)
        success, result = send_bulk(emails, template_name)
        print(f"{'✅' if success else '❌'} ارسال گروهی: {result.get('successful', 0)}/{result.get('total', 0)} موفق")
