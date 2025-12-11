from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime


class Host(SQLModel, table=True):
    """主机资产表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    ip: str = Field(index=True, unique=True)
    mac: Optional[str] = None
    hostname: Optional[str] = None
    os_fingerprint: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)