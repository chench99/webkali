from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime

class WiFiNetwork(SQLModel, table=True):
    """(原有表) 基础 WiFi 列表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    bssid: str = Field(unique=True, index=True)
    ssid: str
    channel: int
    signal_dbm: int
    encryption: str
    last_seen: datetime = Field(default_factory=datetime.utcnow)

class TargetedClient(SQLModel, table=True):
    """(新) 定向监听表：点击“查看监听”时存储"""
    __tablename__ = "targeted_clients"
    id: Optional[int] = Field(default=None, primary_key=True)
    network_bssid: str = Field(index=True)  # 关联的 AP
    client_mac: str = Field(index=True)
    packet_count: int = Field(default=0)
    signal: int = Field(default=0)
    last_seen: datetime = Field(default_factory=datetime.utcnow)

class DeepScanClient(SQLModel, table=True):
    """(新) 深度扫描表：每次点击深度扫描时清空"""
    __tablename__ = "deep_scan_clients"
    id: Optional[int] = Field(default=None, primary_key=True)
    client_mac: str = Field(unique=True, index=True)
    connected_bssid: Optional[str] = None # 当前连接的 AP
    probed_essids: Optional[str] = None   # 历史探测记录
    vendor: Optional[str] = None
    signal: int = Field(default=0)
    capture_channel: int = Field(default=0)
    last_seen: datetime = Field(default_factory=datetime.utcnow)