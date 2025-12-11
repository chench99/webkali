from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime

class WiFiNetwork(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bssid: str = Field(unique=True, index=True)
    ssid: str
    channel: int
    signal_dbm: int
    encryption: str
    last_seen: datetime = Field(default_factory=datetime.utcnow)