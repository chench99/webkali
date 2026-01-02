from sqlalchemy.orm import Session
from app.models.wifi import WiFiNetwork, TargetedClient
from app.schemas.wifi import WiFiNetworkCreate
from typing import List, Optional

def get_network_by_bssid(db: Session, bssid: str):
    """通过 BSSID 查找 WiFi"""
    return db.query(WiFiNetwork).filter(WiFiNetwork.bssid == bssid).first()

def get_all_networks(db: Session, skip: int = 0, limit: int = 100):
    """获取所有 WiFi 列表"""
    return db.query(WiFiNetwork).offset(skip).limit(limit).all()

def create_or_update_network(db: Session, network_data: WiFiNetworkCreate):
    """
    核心逻辑：
    1. 如果 WiFi 已存在，更新信号/信道等信息。
    2. 如果 WiFi 不存在，创建新记录。
    3. [重点] 更新该 WiFi 下连接的客户端列表 (TargetedClient)。
    """
    # 1. 查找数据库中是否已有该 WiFi
    db_network = get_network_by_bssid(db, network_data.bssid)

    if db_network:
        # === 更新模式 ===
        db_network.ssid = network_data.ssid
        db_network.channel = network_data.channel
        db_network.signal_dbm = network_data.signal_dbm
        db_network.encryption = network_data.encryption
        db_network.vendor = network_data.vendor
        db_network.client_count = network_data.client_count
        if network_data.last_seen:
            db_network.last_seen = network_data.last_seen
        # 注意：这里不需要 commit，最后统一 commit
    else:
        # === 创建模式 ===
        db_network = WiFiNetwork(
            ssid=network_data.ssid,
            bssid=network_data.bssid,
            channel=network_data.channel,
            signal_dbm=network_data.signal_dbm,
            encryption=network_data.encryption,
            vendor=network_data.vendor,
            client_count=network_data.client_count,
            last_seen=network_data.last_seen
        )
        db.add(db_network)
        # 这里必须先 commit 一次，确保 db_network 拿到 ID，否则下面插入 Client 时外键会报错
        db.commit()
        db.refresh(db_network)

    # 2. 处理客户端列表 (Clients)
    # network_data.clients 是一个 MAC 地址字符串列表，例如 ["AA:BB:CC...", "11:22:33..."]
    if network_data.clients is not None:
        # 策略：为了保证数据的实时性，我们先清空该 WiFi 下的旧客户端记录
        # (因为扫描结果代表了当前时刻的最新状态)
        db.query(TargetedClient).filter(TargetedClient.network_bssid == network_data.bssid).delete()
        
        # 重新插入最新发现的客户端
        for client_mac in network_data.clients:
            # 过滤掉非法的 MAC (例如广播地址或与 BSSID 相同的)
            if client_mac and client_mac != network_data.bssid:
                new_client = TargetedClient(
                    client_mac=client_mac,
                    network_bssid=network_data.bssid
                )
                db.add(new_client)
    
    # 3. 提交所有更改
    db.commit()
    db.refresh(db_network)
    return db_network
