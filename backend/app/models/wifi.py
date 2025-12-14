from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime


class WiFiNetwork(SQLModel, table=True):
    """
    [AP表] WiFi热点信息持久化
    存储扫描到的路由器信息，每次重新扫描时会重置
    """
    __tablename__ = "wifi_networks"

    id: Optional[int] = Field(default=None, primary_key=True)
    bssid: str = Field(unique=True, index=True)  # 物理地址，唯一键
    ssid: str = Field(default="<Hidden>")
    channel: int = Field(default=0)
    signal_dbm: int = Field(default=-100)  # 信号强度 (dBm)
    encryption: str = Field(default="OPEN")  # 加密方式 (WPA2/WEP/OPEN)
    vendor: Optional[str] = Field(default="Unknown")  # 设备厂商 (OUI查询结果)
    client_count: int = Field(default=0)  # 在线客户端数量
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class TargetedClient(SQLModel, table=True):
    """
    [Station表] 客户端信息持久化
    存储连接到特定 WiFi 的设备，通过 network_bssid 逻辑关联
    """
    __tablename__ = "targeted_clients"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_bssid: str = Field(index=True)  # 关联的 AP BSSID (逻辑外键)
    client_mac: str = Field(index=True)  # 客户端 MAC
    signal_dbm: int = Field(default=-100)
    packet_count: int = Field(default=0)  # 抓包数量
    last_seen: datetime = Field(default_factory=datetime.utcnow)