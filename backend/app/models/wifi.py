from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime


class WiFiNetwork(SQLModel, table=True):
    """
    [AP表] WiFi 热点信息持久化
    存储扫描到的路由器信息，每次点击“执行扫描”时会清空此表
    """
    __tablename__ = "wifi_networks"

    id: Optional[int] = Field(default=None, primary_key=True)
    bssid: str = Field(unique=True, index=True)  # 物理地址 (MAC)
    ssid: str = Field(default="<Hidden>")  # 热点名称
    channel: int = Field(default=0)  # 信道
    signal_dbm: int = Field(default=-100)  # 信号强度 (dBm)
    encryption: str = Field(default="OPEN")  # 加密方式
    vendor: Optional[str] = Field(default="Unknown")  # 设备厂商
    client_count: int = Field(default=0)  # 在线终端数量
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class TargetedClient(SQLModel, table=True):
    """
    [Station表] 客户端信息持久化
    存储被监听的客户端设备，通过 network_bssid 与 AP 关联
    """
    __tablename__ = "targeted_clients"

    id: Optional[int] = Field(default=None, primary_key=True)
    network_bssid: str = Field(index=True)  # 关联的 AP BSSID (逻辑外键)
    client_mac: str = Field(index=True)  # 客户端 MAC
    signal_dbm: int = Field(default=-100)  # 客户端信号强度
    packet_count: int = Field(default=0)  # 捕获的数据包数量
    last_seen: datetime = Field(default_factory=datetime.utcnow)