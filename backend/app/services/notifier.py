import json
import httpx
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.models.models import Tender, NotificationChannel, NotificationLog

CATEGORY_COLORS = {
    "VA_PENTEST": 0xE11D48,         # Red-Pink
    "AUDIT_COMPLIANCE": 0x10B981,   # Green
    "SOC_MSSP": 0x3B82F6,           # Blue
    "SOLUTION_IMPLEMENTATION": 0x8B5CF6, # Purple
    "INCIDENT_RESPONSE": 0xF59E0B,  # Amber
    "TRAINING_DRILL": 0x06B6D4,     # Cyan
    "OTHER": 0x64748B               # Slate
}

CATEGORY_LABELS = {
    "VA_PENTEST": "VA / Pentest / Red Teaming",
    "AUDIT_COMPLIANCE": "Security Audit & Assessment",
    "SOC_MSSP": "SOC & Managed Services",
    "SOLUTION_IMPLEMENTATION": "Security Solution Implementation",
    "INCIDENT_RESPONSE": "Incident Response & Forensics",
    "TRAINING_DRILL": "Security Training & Cyber Drill",
    "OTHER": "Cybersecurity General"
}

async def dispatch_tender_notification(tender: Tender, db: Session) -> int:
    """
    Sends notification for a newly found or updated tender across all active channels
    that match the tender's criteria.
    """
    channels = db.query(NotificationChannel).filter(NotificationChannel.is_enabled == True).all()
    sent_count = 0

    category_label = CATEGORY_LABELS.get(tender.category, tender.category)
    budget_fmt = f"{tender.budget:,.2f} บาท" if (tender.budget or 0) > 0 else "ไม่ระบุงบประมาณ"
    median_fmt = f"{tender.median_price:,.2f} บาท" if (tender.median_price or 0) > 0 else "ไม่ระบุราคากลาง"

    # Always create an in-app notification
    in_app_log = NotificationLog(
        tender_id=tender.id,
        channel_type="IN_APP",
        title=f"ประกาศจัดซื้อใหม่: {tender.title[:100]}",
        message=f"[{category_label}] {tender.agency} - งบประมาณ: {budget_fmt} (กำหนดรับข้อเสนอ: {tender.submission_deadline or 'ไม่ระบุในข้อมูลต้นทาง'})",
        status="UNREAD",
        created_at=datetime.utcnow()
    )
    db.add(in_app_log)
    sent_count += 1

    async with httpx.AsyncClient(timeout=10.0) as client:
        for ch in channels:
            # Check budget criteria
            if ch.min_budget > 0 and (tender.budget is None or tender.budget < ch.min_budget):
                continue

            # Check category criteria
            if ch.categories_filter:
                allowed_cats = [c.strip().upper() for c in ch.categories_filter.split(",") if c.strip()]
                if allowed_cats and tender.category.upper() not in allowed_cats:
                    continue

            # Check keyword criteria
            if ch.keywords_filter:
                kw_list = [k.strip().lower() for k in ch.keywords_filter.split(",") if k.strip()]
                text_to_search = f"{tender.title} {tender.agency} {tender.description or ''}".lower()
                if kw_list and not any(k in text_to_search for k in kw_list):
                    continue

            # Send per channel type
            try:
                if ch.channel_type == "LINE_NOTIFY":
                    # LINE Notify ended service on 31 March 2025. Do not call a
                    # retired endpoint or claim a message was delivered.
                    db.add(NotificationLog(
                        tender_id=tender.id,
                        channel_type="LINE_NOTIFY",
                        title=tender.title[:100],
                        message="LINE Notify retired on 2025-03-31; channel disabled.",
                        status="FAILED"
                    ))

                elif ch.channel_type == "LINE_MESSAGING" and ch.token and ch.chat_id:
                    line_msg = (
                        f"🔔 พบข้อมูลจัดซื้อจัดจ้าง Cybersecurity\n"
                        f"โครงการ: {tender.title}\n"
                        f"หน่วยงาน: {tender.agency}\n"
                        f"งบประมาณ: {budget_fmt}\n"
                        f"สถานะ: {tender.status}\n"
                        f"หลักฐาน: {tender.tor_url or tender.source_url or 'ไม่ระบุ'}"
                    )
                    headers = {
                        "Authorization": f"Bearer {ch.token}",
                        "Content-Type": "application/json",
                    }
                    resp = await client.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers=headers,
                        json={
                            "to": ch.chat_id,
                            "messages": [{"type": "text", "text": line_msg[:5000]}],
                        },
                    )
                    db.add(NotificationLog(
                        tender_id=tender.id,
                        channel_type="LINE_MESSAGING",
                        title=tender.title[:100],
                        message=line_msg,
                        status="SENT" if resp.is_success else f"ERROR_{resp.status_code}",
                    ))
                    sent_count += 1

                elif ch.channel_type == "DISCORD" and ch.target_url:
                    embed = {
                        "title": f"🚨 {tender.title}",
                        "description": tender.description[:300] if tender.description else f"โครงการจัดซื้อจัดจ้างด้าน {category_label}",
                        "color": CATEGORY_COLORS.get(tender.category, 0x3B82F6),
                        "fields": [
                            {"name": "🏢 หน่วยงาน", "value": tender.agency, "inline": True},
                            {"name": "🏷️ หมวดหมู่", "value": category_label, "inline": True},
                            {"name": "💰 งบประมาณ", "value": budget_fmt, "inline": True},
                            {"name": "📊 ราคากลาง", "value": median_fmt, "inline": True},
                            {"name": "📅 กำหนดยื่นซอง", "value": tender.submission_deadline or "ไม่ระบุในข้อมูลต้นทาง", "inline": True},
                            {"name": "🔖 เลขที่โครงการ", "value": tender.tender_code, "inline": True}
                        ],
                        "footer": {"text": f"ที่มา: {tender.source_name} | CyberWatch"}
                    }
                    if tender.tor_url:
                        embed["url"] = tender.tor_url

                    payload = {
                        "content": "⚡ **พบประกาศจัดซื้อจัดจ้าง Cybersecurity ใหม่!**",
                        "embeds": [embed]
                    }
                    resp = await client.post(ch.target_url, json=payload)
                    log = NotificationLog(
                        tender_id=tender.id,
                        channel_type="DISCORD",
                        title=tender.title[:100],
                        message="Sent Discord Embed",
                        status="SENT" if resp.status_code in [200, 204] else f"ERROR_{resp.status_code}"
                    )
                    db.add(log)
                    sent_count += 1

                elif ch.channel_type == "TELEGRAM" and ch.token and ch.chat_id:
                    tg_msg = (
                        f"🛡️ *ประกาศงาน Cyber ใหม่!*\n\n"
                        f"*{tender.title}*\n"
                        f"🏢 *หน่วยงาน:* {tender.agency}\n"
                        f"🏷️ *หมวดหมู่:* {category_label}\n"
                        f"💰 *งบประมาณ:* {budget_fmt}\n"
                        f"⏳ *กำหนดยื่นซอง:* {tender.submission_deadline or 'ไม่ระบุในข้อมูลต้นทาง'}\n"
                        f"🔗 [เปิดหลักฐานต้นทาง]({tender.tor_url or tender.source_url or '#'})"
                    )
                    tg_url = f"https://api.telegram.org/bot{ch.token}/sendMessage"
                    resp = await client.post(tg_url, json={"chat_id": ch.chat_id, "text": tg_msg, "parse_mode": "Markdown"})
                    log = NotificationLog(
                        tender_id=tender.id,
                        channel_type="TELEGRAM",
                        title=tender.title[:100],
                        message=tg_msg,
                        status="SENT" if resp.status_code == 200 else f"ERROR_{resp.status_code}"
                    )
                    db.add(log)
                    sent_count += 1

                elif ch.channel_type == "WEBHOOK" and ch.target_url:
                    payload = {
                        "event": "NEW_CYBER_TENDER",
                        "tender": {
                            "code": tender.tender_code,
                            "title": tender.title,
                            "agency": tender.agency,
                            "category": tender.category,
                            "budget": tender.budget,
                            "median_price": tender.median_price,
                            "deadline": tender.submission_deadline,
                            "tor_url": tender.tor_url,
                            "source_name": tender.source_name
                        }
                    }
                    resp = await client.post(ch.target_url, json=payload)
                    log = NotificationLog(
                        tender_id=tender.id,
                        channel_type="WEBHOOK",
                        title=tender.title[:100],
                        message="Webhook payload dispatched",
                        status="SENT" if resp.is_success else f"ERROR_{resp.status_code}"
                    )
                    db.add(log)
                    sent_count += 1

            except Exception as e:
                log = NotificationLog(
                    tender_id=tender.id,
                    channel_type=ch.channel_type,
                    title=tender.title[:100],
                    message=f"Failed: {str(e)}",
                    status="FAILED"
                )
                db.add(log)

    db.commit()
    return sent_count

async def send_test_notification(channel: NotificationChannel) -> dict:
    """
    Sends a test message to verify a notification channel configuration.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if channel.channel_type == "LINE_NOTIFY":
                return {
                    "success": False,
                    "detail": "LINE Notify ยุติบริการแล้วเมื่อ 31 มีนาคม 2025 กรุณาใช้ LINE Messaging API",
                }

            elif channel.channel_type == "LINE_MESSAGING" and channel.token and channel.chat_id:
                headers = {
                    "Authorization": f"Bearer {channel.token}",
                    "Content-Type": "application/json",
                }
                resp = await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers=headers,
                    json={
                        "to": channel.chat_id,
                        "messages": [{"type": "text", "text": "🟢 [CyberWatch] ทดสอบการเชื่อมต่อสำเร็จ"}],
                    },
                )
                return {"success": resp.is_success, "status_code": resp.status_code}

            elif channel.channel_type == "DISCORD" and channel.target_url:
                payload = {
                    "content": "🟢 **[CyberWatch] ทดสอบการเชื่อมต่อแจ้งเตือนสำเร็จ!** ระบบพร้อมส่งประกาศจัดซื้อจัดจ้างงาน Cybersecurity แบบเรียลไทม์"
                }
                resp = await client.post(channel.target_url, json=payload)
                return {"success": resp.status_code in [200, 204], "status_code": resp.status_code}

            elif channel.channel_type == "TELEGRAM" and channel.token and channel.chat_id:
                tg_url = f"https://api.telegram.org/bot{channel.token}/sendMessage"
                resp = await client.post(tg_url, json={"chat_id": channel.chat_id, "text": "🟢 *[CyberWatch]* ทดสอบการเชื่อมต่อสำเร็จ!", "parse_mode": "Markdown"})
                return {"success": resp.status_code == 200, "status_code": resp.status_code}

            elif channel.channel_type == "WEBHOOK" and channel.target_url:
                resp = await client.post(channel.target_url, json={"event": "TEST_CONNECTION", "message": "CyberWatch connection test"})
                return {"success": resp.is_success, "status_code": resp.status_code}
                
            return {"success": True, "detail": "Channel verified"}
        except Exception as e:
            return {"success": False, "error": str(e)}
