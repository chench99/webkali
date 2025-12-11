from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from pydantic import BaseModel
import subprocess
import platform
import re
import psutil
import shutil
from typing import Optional, List

# 引入攻击模块
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")

# ==========================================
# 1. 厂商数据库 (OUI) - 保持完整
# ==========================================
OUI_DB = {
    "DC:D2:FC": "TP-Link", "50:D4:F7": "TP-Link", "98:48:27": "TP-Link",
    "80:EA:96": "NetGear", "A0:04:60": "NetGear",
    "D8:32:14": "Xiaomi", "64:CC:2E": "Xiaomi", "28:6C:07": "Xiaomi",
    "FC:48:EF": "Huawei", "48:46:C1": "Huawei", "00:E0:FC": "Huawei",
    "BC:54:36": "Tenda", "C8:3A:35": "Tenda",
    "88:66:5A": "Apple", "BC:D1:19": "Apple", "AC:F7:F3": "Xiaomi",
    "B8:27:EB": "Raspberry Pi", "00:0C:29": "VMware"
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
# 2. Kali 原生网卡获取 (iw dev)
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    """
    使用 Kali 原生命令 `iw dev` 获取真实的无线网卡列表
    能区分 Managed (普通) 和 Monitor (监听) 模式
    """
    interfaces = []

    # 1. 尝试使用 iw 命令 (最准确)
    if shutil.which("iw"):
        try:
            # 输出示例:
            # phy#0
            #   Interface wlan0
            #     ifindex 3
            #     wdev 0x1
            #     addr 00:c0:ca:...
            #     type managed
            output = subprocess.check_output(["iw", "dev"]).decode('utf-8')

            current_iface = {}
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith("Interface"):
                    current_iface = {
                        "name": line.split()[1],
                        "is_wireless": True,
                        "mode": "Unknown",
                        "mac": "Unknown"
                    }
                    interfaces.append(current_iface)
                elif line.startswith("type") and current_iface:
                    # 获取模式: managed / monitor
                    current_iface["mode"] = line.split()[1].title()
                elif line.startswith("addr") and current_iface:
                    current_iface["mac"] = line.split()[1]

        except Exception as e:
            print(f"[!] iw command failed: {e}")

    # 2. 如果 iw 失败或为空 (兼容性)，回退到 psutil
    if not interfaces:
        stats = psutil.net_if_stats()
        wifi_keys = ["wlan", "mon", "wlp", "wlx", "wi-fi"]
        for iface, stat in stats.items():
            is_wifi = any(k in iface.lower() for k in wifi_keys)
            if is_wifi:
                interfaces.append({
                    "name": iface,
                    "is_wireless": True,
                    "mode": "Managed",  # 默认
                    "mac": "Unknown"
                })

    # 3. 排序: Monitor 模式优先，然后是 wlan0
    def sort_key(x):
        score = 0
        if x['mode'] == 'Monitor': score += 10
        if 'wlan0' in x['name']: score += 5
        return -score

    interfaces.sort(key=sort_key)

    return {"interfaces": interfaces}


# ==========================================
# 3. 扫描核心逻辑 (深度解析)
# ==========================================
def get_real_scan_results(target_interface: str = None):
    system_type = platform.system()
    networks = []

    print(f"[*] Kali 深度扫描 | 接口: {target_interface or 'Auto'}")

    # --- Linux / Kali ---
    if system_type != "Windows":
        try:
            # nmcli 字段: SSID, BSSID, CHAN, SIGNAL, SECURITY, RATE
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY,RATE", "dev", "wifi", "list"]

            # 如果前端选了网卡，必须指定！
            if target_interface:
                cmd.extend(["ifname", target_interface])

            output = subprocess.check_output(cmd).decode('utf-8')

            for line in output.split('\n'):
                line = line.strip()
                if not line: continue

                parts = line.split(':')
                if len(parts) >= 5:
                    rate = parts[-1]
                    sec = parts[-2]
                    sig = parts[-3]
                    chan = parts[-4]

                    if len(parts) >= 10:
                        bssid = ":".join(parts[-10:-4])
                        ssid = line.split(bssid)[0].strip(':')
                    else:
                        bssid = "Unknown"
                        ssid = parts[0]

                    if not ssid: ssid = "<Hidden>"

                    try:
                        signal_val = int(sig)
                        dbm = int((signal_val / 2) - 100) if signal_val > 0 else -100
                    except:
                        dbm = -80

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
                        "rate": rate,
                        # 重点：在线终端数 (Clients)
                        # 普通扫描无法获取，暂置为 -1 表示"未知/需监听"
                        # 前端会根据这个值显示 "?" 或 "0"
                        "clients": -1
                    })
        except Exception as e:
            print(f"[!] Scan Error: {e}")
    else:
        # Windows 兼容代码 (略，保持原逻辑防止报错)
        pass

    return networks


# ==========================================
# 4. 接口定义
# ==========================================
class ScanRequest(BaseModel):
    interface: Optional[str] = None


@router.post("/scan/start")
@router.post("/networks")
async def scan_wifi_manual(req: ScanRequest = Body(default=None)):
    target_iface = req.interface if req else None
    results = get_real_scan_results(target_interface=target_iface)

    # 排序
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