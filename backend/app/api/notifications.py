from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List

from backend.app.core.database import get_db
from backend.app.models.models import NotificationChannel, NotificationLog
from backend.app.models.schemas import (
    NotificationChannelResponse, NotificationChannelCreate, NotificationLogResponse
)
from backend.app.services.notifier import send_test_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/channels", response_model=List[NotificationChannelResponse])
def get_channels(db: Session = Depends(get_db)):
    return db.query(NotificationChannel).all()

@router.post("/channels", response_model=NotificationChannelResponse)
def create_channel(data: NotificationChannelCreate, db: Session = Depends(get_db)):
    channel = NotificationChannel(**data.model_dump())
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel

@router.patch("/channels/{channel_id}", response_model=NotificationChannelResponse)
def update_channel(channel_id: int, data: NotificationChannelCreate, db: Session = Depends(get_db)):
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="ไม่พบช่องทางการแจ้งเตือน")
    
    for key, val in data.model_dump().items():
        setattr(channel, key, val)
        
    db.commit()
    db.refresh(channel)
    return channel

@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="ไม่พบช่องทางการแจ้งเตือน")
    db.delete(channel)
    db.commit()
    return {"message": "ลบช่องทางแจ้งเตือนสำเร็จ"}

@router.post("/test/{channel_id}")
async def test_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="ไม่พบช่องทางการแจ้งเตือน")
    result = await send_test_notification(channel)
    return result

@router.get("/logs", response_model=List[NotificationLogResponse])
def get_notification_logs(limit: int = 20, db: Session = Depends(get_db)):
    return db.query(NotificationLog).order_by(desc(NotificationLog.id)).limit(limit).all()

@router.post("/mark-read")
def mark_notifications_read(db: Session = Depends(get_db)):
    db.query(NotificationLog).filter(NotificationLog.status == "UNREAD").update({"status": "READ"})
    db.commit()
    return {"message": "ทำเครื่องหมายอ่านแล้วทั้งหมด"}
