from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import os
import psutil

# 引入我们刚才写的攻击模块
# 确保你的 attacker.py 位于 backend/app/modules/wifi/attacker.py
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()

# ==========================================
# 全局单例
# ==========================================
# 我们需要在内存中保持这个实例，以便查询状态和停止攻击
# 默认监听接口设为 wlan0mon，可以通过 API 修改
wifi_attacker = WifiAttacker(interface="wlan0mon")


# ==========================================
# Pydantic 数据模型 (用于验证前端请求)
# ==========================================

class InterfaceConfig(BaseModel):
    interface_name: str


class AttackConfig(BaseModel):
    bssid: str  # 目标路由器的 MAC 地址
    channel: int  # 目标信道
    attack_type: str = "deauth"  # 攻击类型: deauth, flood, mdk4
    count: int = 10  # 攻击包数量 (针对 deauth)
    timeout: int = 60  # 攻击持续时间 (秒)


# ==========================================
# API 路由定义
# ==========================================

@router.get("/interfaces")
async def get_network_interfaces():
    """
    获取系统所有网络接口，方便用户选择哪个网卡用于攻击
    """
    interfaces = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    for iface, stat in stats.items():
        # 获取 MAC 地址
        mac = "Unknown"
        if iface in addrs:
            for addr in addrs[iface]:
                if addr.family == psutil.AF_LINK:
                    mac = addr.address

        interfaces.append({
            "name": iface,
            "is_up": stat.isup,
            "mac": mac,
            # 简单的判断是否可能是无线网卡 (通常以 wlan, mon, wlp 开头)
            "is_wireless": any(x in iface for x in ["wlan", "mon", "wlp", "wi"])
        })
    return {"interfaces": interfaces}


@router.post("/config/interface")
async def set_attack_interface(config: InterfaceConfig):
    """
    设置用于攻击的网卡接口 (例如从 wlan0 切换到 wlan0mon)
    """
    if config.interface_name not in psutil.net_if_stats():
        raise HTTPException(status_code=400, detail=f"接口 {config.interface_name} 不存在")

    wifi_attacker.interface = config.interface_name
    return {"status": "success", "current_interface": wifi_attacker.interface}


@router.post("/capture/start")
async def start_handshake_capture(config: AttackConfig, background_tasks: BackgroundTasks):
    """
    [核心功能] 启动握手包捕获攻击
    接收 BSSID 和 信道，并在后台启动监听和攻击线程
    """
    if wifi_attacker.is_running:
        raise HTTPException(status_code=409, detail="当前已有攻击任务正在运行，请先停止")

    # 验证攻击类型
    valid_types = ["deauth", "flood", "mdk4"]  # 对应 attacker.py 里的逻辑
    if config.attack_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"不支持的攻击类型，仅支持: {valid_types}")

    print(f"[*] API 收到攻击指令: 对 {config.bssid} 执行 {config.attack_type}")

    # 使用 FastAPI 的 BackgroundTasks 在后台运行，防止阻塞 API 响应
    # 注意：这里调用的是 run_attack_cycle
    background_tasks.add_task(
        wifi_attacker.run_attack_cycle,
        bssid=config.bssid,
        channel=config.channel,
        attack_type=config.attack_type
    )

    return {
        "status": "started",
        "target": config.bssid,
        "type": config.attack_type,
        "message": "攻击任务已在后台启动，请轮询 /capture/status 查看进度"
    }


@router.post("/capture/stop")
async def stop_capture():
    """
    强制停止当前的攻击和监听任务
    """
    if not wifi_attacker.is_running:
        return {"status": "stopped", "message": "当前没有正在运行的任务"}

    wifi_attacker.is_running = False
    return {"status": "stopping", "message": "正在发送停止信号..."}


@router.get("/capture/status")
async def get_capture_status():
    """
    [轮询接口] 前端定时调用此接口以更新 UI 状态
    返回：是否运行中、是否抓到包、文件路径等
    """
    # 扫描 captures 目录下的最新文件
    capture_files = []
    if os.path.exists(wifi_attacker.save_path):
        capture_files = sorted(
            [f for f in os.listdir(wifi_attacker.save_path) if f.endswith(".pcap")],
            key=lambda x: os.path.getmtime(os.path.join(wifi_attacker.save_path, x)),
            reverse=True
        )

    return {
        "is_running": wifi_attacker.is_running,
        "current_interface": wifi_attacker.interface,
        "target_bssid": wifi_attacker.target_bssid,
        "handshake_captured": wifi_attacker.handshake_captured,
        "latest_capture_file": capture_files[0] if capture_files else None,
        "all_captures": capture_files[:5]  # 只返回最近5个
    }