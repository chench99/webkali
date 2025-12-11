from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from pydantic import BaseModel
import subprocess
import platform
import re
import psutil
import sys
import os
from typing import Optional, List

# 引入攻击模块
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")

# ==========================================
# 1. 厂商数据库 (OUI) - 保持不变
# ==========================================
OUI_DB = {
    "DC:D2:FC": "TP-Link", "50:D4:F7": "TP-Link", "98:48:27": "TP-Link",
    "80:EA:96": "NetGear", "A0:04:60": "NetGear",
    "D8:32:14": "Xiaomi", "64:CC:2E": "Xiaomi", "28:6C:07": "Xiaomi",
    "FC:48:EF": "Huawei", "48:46:C1": "Huawei", "00:E0:FC": "Huawei",
    "BC:54:36": "Tenda", "C8:3A:35": "Tenda",
    "88:66:5A": "Apple", "BC:D1:19": "Apple",
    "B8:27:EB": "Raspberry Pi",
}


def get_vendor(mac_addr):
    try:
        if not mac_addr: return "Unknown"
        prefix = mac_addr.upper().replace("-", ":")[:8]
        for oui, vendor in OUI_DB.items():
            if prefix.startswith(oui): return vendor
        return "Unknown"
    except:
        return "Unknown"


def get_band(channel):
    try:
        ch = int(channel)
        if 1 <= ch <= 14:
            return "2.4GHz"
        elif 36 <= ch <= 173:
            return "5GHz"
        return "Unknown"
    except:
        return "2.4GHz"


# ==========================================
# 2. 网卡获取逻辑 (Kali 专用优化)
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    """
    获取 Kali 下的真实网卡列表
    """
    interfaces = []

    # 使用 psutil 获取网卡状态
    stats = psutil.net_if_stats()

    # 常见的无线网卡前缀
    wifi_prefixes = ["wlan", "mon", "wlp", "wlx", "wi"]

    for iface, stat in stats.items():
        # 判断是否为无线网卡
        is_wireless = any(p in iface.lower() for p in wifi_prefixes)

        # 补充信息：是否处于 Monitor 模式 (简易判断)
        mode = "Managed"
        if "mon" in iface.lower():
            mode = "Monitor"

        interfaces.append({
            "name": iface,
            "is_up": stat.isup,
            "is_wireless": is_wireless,
            "mode": mode,
            "speed": stat.speed
        })

    # 排序：无线网卡在前，Monitor 模式的最前
    interfaces.sort(key=lambda x: (not x['is_wireless'], x['mode'] != "Monitor"))

    return {"interfaces": interfaces}


# ==========================================
# 3. 扫描核心逻辑 (nmcli 深度解析)
# ==========================================
def get_real_scan_results(target_interface: str = None):
    system_type = platform.system()
    networks = []

    print(f"[*] 执行深度扫描 | 系统: {system_type} | 指定网卡: {target_interface or 'Auto'}")

    # --- Windows (保持兼容，防止报错) ---
    if system_type == "Windows":
        # ... (此处省略 Windows 代码，保持原样即可，重点是下面的 Linux) ...
        # 为了节省篇幅，这里复用之前的 Windows 逻辑，或者直接 pass，因为你在 Kali 上
        pass

        # --- Linux / Kali 真实扫描 ---
    else:
        try:
            # 构造 nmcli 命令
            # 字段: SSID, BSSID, 信道, 信号, 安全, 速率
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY,RATE", "dev", "wifi", "list"]

            # 如果指定了网卡，强制使用该网卡
            if target_interface:
                cmd.extend(["ifname", target_interface])

            # 执行命令
            output = subprocess.check_output(cmd).decode('utf-8')

            for line in output.split('\n'):
                line = line.strip()
                if not line: continue

                # nmcli -t 输出是用冒号分隔的，但 BSSID 里面也有冒号
                # 技巧：倒序切割
                parts = line.split(':')

                # 确保至少有足够的字段
                if len(parts) >= 5:
                    # 倒序解析
                    # RATE 是最后一部分 (例如: 270 Mbit/s)
                    # SECURITY 是倒数第二部分 (例如: WPA2)
                    # SIGNAL 是倒数第三部分 (例如: 80)
                    # CHAN 是倒数第四部分 (例如: 11)

                    # 剩下的前面部分是 SSID + BSSID
                    # BSSID 是固定的 6 个字节 (5个冒号)，所以占用 parts[-10] 到 parts[-4]

                    rate = parts[-1]
                    sec = parts[-2]
                    sig = parts[-3]
                    chan = parts[-4]

                    # 提取 BSSID (MAC)
                    # 只有当长度足够时才提取
                    if len(parts) >= 10:
                        bssid = ":".join(parts[-10:-4])
                        # SSID 是剩下的最前面的部分
                        ssid = line.split(bssid)[0].strip(':')
                    else:
                        bssid = "Unknown"
                        ssid = parts[0]

                    if not ssid: ssid = "<Hidden>"

                    # 处理信号
                    try:
                        signal_val = int(sig)
                        dbm = int((signal_val / 2) - 100) if signal_val > 0 else -100
                    except:
                        dbm = -80

                    # 处理信道
                    try:
                        channel = int(chan)
                    except:
                        channel = 1

                    networks.append({
                        "ssid": ssid,
                        "bssid": bssid,
                        "channel": channel,
                        "signal": dbm,
                        "encryption": sec,
                        "vendor": get_vendor(bssid),
                        "band": get_band(channel),
                        "rate": rate,  # 增加速率字段
                        "clients": 0  # 占位符：普通扫描无法获取客户端数量，需 Airodump
                    })

        except subprocess.CalledProcessError as e:
            print(f"[!] Kali 扫描失败: {e}")
            print(f"[!] 尝试执行的命令: {' '.join(cmd)}")
        except Exception as e:
            print(f"[!] 未知错误: {e}")

    return networks


# ==========================================
# 4. 接口定义
# ==========================================
class ScanRequest(BaseModel):
    interface: Optional[str] = None


@router.post("/scan/start")
@router.post("/networks")
async def scan_wifi_manual(req: ScanRequest = Body(default=None)):
    """支持手动选择网卡的扫描接口"""
    target_iface = req.interface if req else None

    # 调用核心扫描
    results = get_real_scan_results(target_interface=target_iface)

    # 排序：信号强的在前
    results.sort(key=lambda x: x['signal'], reverse=True)

    return {
        "code": 200,
        "status": "success",
        "interface": target_iface or "Auto",
        "count": len(results),
        "networks": results
    }


# 兼容 GET
@router.get("/scan/start")
@router.get("/networks")
async def scan_wifi_auto():
    results = get_real_scan_results(None)
    results.sort(key=lambda x: x['signal'], reverse=True)
    return {"code": 200, "networks": results}


# ==========================================
# 5. 攻击接口 (保持不变)
# ==========================================
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_capture(config: AttackConfig, background_tasks: BackgroundTasks):
    if wifi_attacker.is_running:
        raise HTTPException(status_code=409, detail="任务运行中")
    background_tasks.add_task(wifi_attacker.run_attack_cycle, config.bssid, config.channel, config.attack_type)
    return {"status": "started"}


@router.post("/capture/stop")
async def stop_capture():
    wifi_attacker.is_running = False
    return {"status": "stopped"}


@router.get("/capture/status")
async def get_status():
    return {"is_running": wifi_attacker.is_running, "handshake_captured": wifi_attacker.handshake_captured}