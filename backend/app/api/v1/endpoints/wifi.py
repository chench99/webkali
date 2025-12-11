from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from pydantic import BaseModel
import subprocess
import platform
import re
import psutil
from typing import Optional, List

# 引入攻击模块 (确保 app/modules/wifi/attacker.py 存在)
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")

# ==========================================
# 1. 厂商数据库 (OUI)
# ==========================================
OUI_DB = {
    "DC:D2:FC": "TP-Link", "50:D4:F7": "TP-Link", "98:48:27": "TP-Link",
    "80:EA:96": "NetGear", "A0:04:60": "NetGear",
    "D8:32:14": "Xiaomi", "64:CC:2E": "Xiaomi", "28:6C:07": "Xiaomi",
    "FC:48:EF": "Huawei", "48:46:C1": "Huawei", "00:E0:FC": "Huawei",
    "BC:54:36": "Tenda", "C8:3A:35": "Tenda",
    "00:0C:29": "VMware", "00:50:56": "VMware",
    "88:66:5A": "Apple", "BC:D1:19": "Apple",
}


def get_vendor(mac_addr):
    try:
        if not mac_addr: return "Unknown"
        prefix = mac_addr.upper().replace("-", ":")[:8]
        for oui, vendor in OUI_DB.items():
            if prefix.startswith(oui):
                return vendor
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
# 2. 扫描核心逻辑 (修复了 SyntaxError)
# ==========================================
def get_real_scan_results(target_interface: str = None):
    system_type = platform.system()
    networks = []

    print(f"[*] 执行扫描 | 系统: {system_type} | 网卡: {target_interface or 'Auto'}")

    # --- Windows 扫描 ---
    if system_type == "Windows":
        cmd = "netsh wlan show networks mode=bssid"
        try:
            # 尝试解码
            try:
                output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
            except:
                output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')

            current_net = {}
            current_ssid = ""

            for line in output.split('\n'):
                line = line.strip()
                if not line: continue

                if line.startswith("SSID"):
                    parts = line.split(":")
                    if len(parts) > 1:
                        current_ssid = parts[1].strip()
                        if not current_ssid: current_ssid = "<Hidden>"

                elif "身份验证" in line or "Authentication" in line:
                    auth = line.split(":")[1].strip()
                    if "WPA" in auth:
                        encryption = "WPA2"
                    elif "WEP" in auth:
                        encryption = "WEP"
                    else:
                        encryption = "OPEN"
                    current_net['encryption'] = encryption

                elif line.startswith("BSSID"):
                    parts = line.split(":")
                    if len(parts) > 1:
                        bssid = ":".join(parts[1:]).strip()
                        # 初始化新网络对象
                        current_net = {
                            "ssid": current_ssid,
                            "bssid": bssid,
                            "encryption": current_net.get('encryption', 'WPA2'),
                            "vendor": get_vendor(bssid),
                            "channel": 1,
                            "signal": -80,
                            "band": "2.4GHz"
                        }
                        networks.append(current_net)

                elif line.startswith("信号") or line.startswith("Signal"):
                    try:
                        percent = int(re.search(r'(\d+)%', line).group(1))
                        dbm = int((percent / 2) - 100)
                        if networks: networks[-1]['signal'] = dbm
                    except:
                        pass

                elif line.startswith("信道") or line.startswith("Channel"):
                    try:
                        ch = int(line.split(":")[1].strip())
                        if networks:
                            networks[-1]['channel'] = ch
                            networks[-1]['band'] = get_band(ch)
                    except:
                        pass

        except Exception as e:
            print(f"[!] Windows 扫描异常: {e}")

    # --- Linux / Kali 扫描 ---
    else:
        # 这里解决了你之前的 SyntaxError 问题
        # 之前的代码可能在这里的 try/except 缩进不对
        try:
            # 如果指定了网卡，使用该网卡扫描
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY,RATE", "dev", "wifi", "list"]
            if target_interface:
                cmd.extend(["ifname", target_interface])

            output = subprocess.check_output(cmd).decode('utf-8')

            for line in output.split('\n'):
                if not line: continue
                parts = line.split(':')
                if len(parts) >= 5:
                    sec = parts[-2]
                    sig = parts[-3]
                    chan = parts[-4]
                    bssid = ":".join(parts[-10:-4]) if len(parts) >= 10 else "Unknown"
                    ssid = line.split(bssid)[0].strip(':')
                    if not ssid: ssid = "<Hidden>"

                    # 处理信号
                    try:
                        signal_val = int(sig)
                        # nmcli 有时返回 bar，有时返回 %，简单处理
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
                        "band": get_band(channel)
                    })
        except Exception as e:
            print(f"[!] Linux Scan Error: {e}")

    return networks


# ==========================================
# 3. 接口定义
# ==========================================

# 新增：定义扫描请求的数据结构
class ScanRequest(BaseModel):
    interface: Optional[str] = None  # 允许为空，为空则自动


@router.get("/interfaces")
async def get_interfaces():
    """获取所有网卡接口供前端选择"""
    interfaces = []
    stats = psutil.net_if_stats()
    keywords = ["wlan", "mon", "wi", "wl", "wireless"]

    for iface, stat in stats.items():
        is_wireless = any(k in iface.lower() for k in keywords)
        interfaces.append({
            "name": iface,
            "is_up": stat.isup,
            "is_wireless": is_wireless
        })
    # 把无线网卡排前面
    interfaces.sort(key=lambda x: x['is_wireless'], reverse=True)
    return {"interfaces": interfaces}


# 兼容 GET 和 POST，POST 支持手动传参
@router.post("/scan/start")
@router.post("/networks")
async def scan_wifi_manual(req: ScanRequest = Body(default=None)):
    """支持手动选择网卡的扫描接口"""
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


# GET 接口保留用于快速测试，使用默认网卡
@router.get("/scan/start")
@router.get("/networks")
async def scan_wifi_auto():
    results = get_real_scan_results(None)
    results.sort(key=lambda x: x['signal'], reverse=True)
    return {
        "code": 200,
        "networks": results
    }


# ==========================================
# 4. 攻击接口 (保持不变)
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