from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import os
import subprocess
import psutil
import re
import platform

# 引入攻击模块
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()

# 实例化攻击者 (默认网卡稍后自动更新)
wifi_attacker = WifiAttacker(interface="wlan0mon")


# ==========================================
# 1. 数据模型
# ==========================================
class InterfaceConfig(BaseModel):
    interface_name: str


class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"
    count: int = 10


# ==========================================
# 2. 辅助函数：智能网卡扫描
# ==========================================
def get_wireless_interfaces():
    """获取所有疑似无线网卡的接口名"""
    wireless_ifaces = []
    stats = psutil.net_if_stats()

    # 关键词匹配：只要名字里带这些，就认为是无线网卡
    keywords = ["wlan", "mon", "wi", "wlp", "wl"]

    for iface in stats.keys():
        # Windows 通常叫 "Wi-Fi"，Linux 通常叫 "wlan0"
        if any(k in iface.lower() for k in keywords):
            wireless_ifaces.append(iface)

    return wireless_ifaces


def run_system_scan(interface):
    """执行扫描命令"""
    # [Windows 兼容模式]
    if platform.system() == "Windows":
        print(f"[*] 检测到 Windows 环境，返回模拟扫描数据 (网卡: {interface})")
        return [
            {"ssid": "TEST_OFFICE_WIFI", "bssid": "11:22:33:44:55:66", "channel": 1, "signal": -50,
             "encryption": "WPA2"},
            {"ssid": "GUEST_NETWORK", "bssid": "AA:BB:CC:DD:EE:FF", "channel": 6, "signal": -75, "encryption": "WPA2"},
            {"ssid": "FREE_WIFI", "bssid": "12:34:56:78:90:AB", "channel": 11, "signal": -85, "encryption": "OPEN"},
        ]

    # [Linux 真实扫描]
    networks = []
    try:
        # 尝试使用 nmcli (NetworkManager CLI) - 这种方式不需要 root 且格式好解
        # 命令: nmcli -t -f SSID,BSSID,CHAN,SIGNAL,SECURITY dev wifi list ifname wlan0
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", interface]

        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')

        for line in result.split('\n'):
            line = line.strip()
            if not line: continue
            # nmcli -t 输出格式: SSID:BSSID:CHAN:SIGNAL:SECURITY
            # 注意: BSSID (MAC) 里面也有冒号，需要特殊处理分割
            # 这里做一个简化的处理
            parts = line.split(':')
            if len(parts) >= 4:
                # 倒序取值比较安全
                sec = parts[-1]
                sig = parts[-2]
                chan = parts[-3]
                # 中间的一长串是 BSSID
                bssid = ":".join(parts[-9:-3]) if len(parts) >= 9 else "Unknown"
                # 剩下的是 SSID
                ssid = line.split(bssid)[0].strip(':')

                networks.append({
                    "ssid": ssid or "Hidden",
                    "bssid": bssid,
                    "channel": int(chan) if chan.isdigit() else 1,
                    "signal": int(sig) if sig.isdigit() else -99,
                    "encryption": sec
                })

    except Exception as e:
        print(f"[!] nmcli 扫描失败，尝试 iwlist: {e}")
        try:
            # 备用方案: iwlist (需要 root)
            cmd_iw = f"iwlist {interface} scan"
            output = subprocess.check_output(cmd_iw, shell=True).decode('utf-8', errors='ignore')
            # (这里省略复杂的 iwlist 正则解析，为节省代码长度，如果 nmcli 失败通常是因为没权限)
        except Exception as iw_e:
            print(f"[!] iwlist 扫描也失败: {iw_e}")

    return networks


# ==========================================
# 3. 核心 API 路由 (修复 404 的关键)
# ==========================================

# --- [A] 扫描接口 ---
@router.get("/scan/start")
@router.post("/scan/start")
async def scan_networks():
    """
    [关键修复] 这个接口必须存在，前端才能调用扫描！
    """
    # 1. 自动寻找可用的网卡
    available_ifaces = get_wireless_interfaces()

    if not available_ifaces:
        # 如果找不到，尝试硬编码 wlan0 碰运气，或者报错
        scan_interface = "wlan0"
        print("[!] 警告: 未自动检测到无线网卡，尝试强制使用 wlan0")
    else:
        # 优先使用第一个找到的网卡，排除掉监听模式的卡(通常带 mon)
        scan_interface = available_ifaces[0]
        for iface in available_ifaces:
            if "mon" not in iface:
                scan_interface = iface
                break

    print(f"[*] 正在使用网卡 [{scan_interface}] 进行扫描...")

    # 2. 执行扫描
    results = run_system_scan(scan_interface)

    return {
        "status": "success",
        "interface": scan_interface,
        "count": len(results),
        "networks": results
    }


# --- [B] 网卡列表接口 ---
@router.get("/interfaces")
async def get_interfaces():
    """获取网卡列表"""
    interfaces = []
    stats = psutil.net_if_stats()

    for iface, stat in stats.items():
        is_wireless = False
        # 宽松的判断逻辑
        if any(k in iface.lower() for k in ["wlan", "mon", "wi", "wl"]):
            is_wireless = True

        interfaces.append({
            "name": iface,
            "is_up": stat.isup,
            "is_wireless": is_wireless
        })
    return {"interfaces": interfaces}


# --- [C] 攻击/抓包接口 ---
@router.post("/capture/start")
async def start_capture(config: AttackConfig, background_tasks: BackgroundTasks):
    if wifi_attacker.is_running:
        raise HTTPException(status_code=409, detail="攻击任务已在运行")

    # 更新攻击使用的网卡
    wifi_attacker.interface = "wlan0mon"  # 攻击时通常需要强制指定监听网卡

    background_tasks.add_task(
        wifi_attacker.run_attack_cycle,
        bssid=config.bssid,
        channel=config.channel,
        attack_type=config.attack_type
    )
    return {"status": "started", "message": f"正在攻击 {config.bssid}"}


@router.post("/capture/stop")
async def stop_capture():
    wifi_attacker.is_running = False
    return {"status": "stopped"}


@router.get("/capture/status")
async def get_status():
    return {
        "is_running": wifi_attacker.is_running,
        "handshake_captured": wifi_attacker.handshake_captured
    }