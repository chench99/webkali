from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# 客户端 Schema
class WiFiClientBase(BaseModel):
    client_mac: str
    packet_count: int = 0
    signal_dbm: int = -100
    last_seen: Optional[datetime] = None

class WiFiClientCreate(WiFiClientBase):
    pass

class WiFiClient(WiFiClientBase):
    id: int
    network_bssid: str # 对应 model 的 network_bssid
    created_at: datetime
    class Config:
        from_attributes = True

# 网络 Schema
class WiFiNetworkBase(BaseModel):
    ssid: str
    bssid: str
    channel: int
    signal_dbm: int # 原 signal
    encryption: str
    vendor: str = "Unknown"
    client_count: int = 0
    last_seen: Optional[datetime] = None

class WiFiNetworkCreate(WiFiNetworkBase):
    # 接收扫描结果时，允许带入 clients 列表
    clients: List[str] = [] 

class WiFiNetwork(WiFiNetworkBase):
    id: int
    updated_at: datetime
    # 返回给前端时，包含客户端列表
    clients: List[WiFiClient] = [] 
    
    class Config:
        from_attributes = True
