from fastapi import APIRouter, BackgroundTasks, HTTPException
import subprocess
import platform
import re
import time

# 引入攻击模块 (确保存在)
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")

# ==========================================
# 1. 厂商识别数据库 (OUI Helper)
# ==========================================
# 这里内置了一些常见的 MAC 前缀，实际生产环境通常会加载一个 5MB 的 oui.json 文件
OUI_DB = {
    "DC:D2:fc": "TP-Link", "50:D4:F7": "TP-Link", "98:48:27": "TP-Link",
    "80:EA:96": "NetGear", "A0:04:60": "NetGear",
    "B4:30:52": "NetGear", "14:14:4B": "NetGear",
    "D8:32:14": "Xiaomi", "64:CC:2E": "Xiaomi", "28:6C:07": "Xiaomi",
    "FC:48:EF": "Huawei", "48:46:C1": "Huawei", "00:E0:FC": "Huawei",
    "BC:54:36": "Tenda", "C8:3A:35": "Tenda",
    "AC:F7:F3": "Xiaomi", "5C:02:14": "Xiaomi",
    "00:0C:29": "VMware", "00:50:56": "VMware",
    "88:66:5A": "Apple", "BC:D1:19": "Apple",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "00:11:32": "Synology",
    "00:11:22": "Cisco",
}


def get_vendor(mac_addr):
    """根据 MAC 地址前 3 段判断厂商"""
    try:
        if not mac_addr: return "Unknown"
        # 提取前缀 (例如 88:66:5A)
        prefix = mac_addr.upper().replace("-", ":")[:8]
        # 简单匹配
        for oui, vendor in OUI_DB.items():
            if prefix.startswith(oui):
                return vendor
        # 如果没匹配到，返回 Unknown
        return "Unknown"
    except:
        return "Unknown"


def get_band(channel):
    """根据信道判断频段"""
    try:
        ch = int(channel)
        if 1 <= ch <= 14:
            return "2.4GHz"
        elif 36 <= ch <= 173:
            return "5GHz"
        else:
            return "Unknown"
    except:
        return "2.4GHz"  # 默认


# ==========================================
# 2. 核心扫描逻辑 (Windows/Linux 全解析)
# ==========================================
def get_real_scan_results():
    """获取企业级详细扫描结果"""
    system_type = platform.system()
    networks = []

    print(f"[*] 执行深度扫描... 系统: {system_type}")

    if system_type == "Windows":
        # --- Windows 深度解析 ---
        # 必须使用 mode=bssid 才能看到信道和详细信号
        cmd = "netsh wlan show networks mode=bssid"
        try:
            # 优先尝试 GBK (中文系统)，失败则 UTF-8
            try:
                output = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
            except:
                output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')

            # 状态机解析法
            current_net = {}
            current_ssid = ""

            for line in output.split('\n'):
                line = line.strip()
                if not line: continue

                # 1. 抓取 SSID (新网络的开始)
                if line.startswith("SSID"):
                    # 如果之前已经解析了一个 BSSID 块，先不用管，因为 SSID 下面可能有多个 BSSID
                    parts = line.split(":")
                    if len(parts) > 1:
                        current_ssid = parts[1].strip()
                        if not current_ssid: current_ssid = "<Hidden>"

                # 2. 抓取认证方式
                elif "身份验证" in line or "Authentication" in line:
                    auth = line.split(":")[1].strip()
                    if "WPA" in auth:
                        encryption = "WPA2"
                    elif "WEP" in auth:
                        encryption = "WEP"
                    else:
                        encryption = "OPEN"
                    # 暂存这个 SSID 的加密方式，赋给下面的 BSSID
                    current_net['encryption'] = encryption

                # 3. 抓取 BSSID (这是每个 AP 的实体)
                elif line.startswith("BSSID"):
                    # 发现新物理热点，初始化字典
                    parts = line.split(":")
                    if len(parts) > 1:
                        bssid = ":".join(parts[1:]).strip()
                        current_net = {
                            "ssid": current_ssid,
                            "bssid": bssid,
                            "encryption": current_net.get('encryption', 'WPA2'),
                            "vendor": get_vendor(bssid),  # 新增：厂商
                            "channel": 1,
                            "signal": -80,
                            "band": "2.4GHz"
                        }
                        networks.append(current_net)  # 先加进去引用，后面填补数据

                # 4. 抓取详细数据 (填充最近的一个 BSSID)
                elif line.startswith("信号") or line.startswith("Signal"):
                    # Windows 返回的是百分比 (99%)，我们需要转成 dBm 估算值
                    # 100% ≈ -50dBm, 0% ≈ -100dBm
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
                            networks[-1]['band'] = get_band(ch)  # 新增：频段
                    except:
                        pass

                elif "无线电类型" in line or "Radio type" in line:
                    # e.g. 802.11ax
                    try:
                        rtype = line.split(":")[1].strip()
                        if networks: networks[-1]['radio_type'] = rtype
                    except:
                        pass

    else:
        # --- Linux / Kali 深度解析 (nmcli) ---
        try:
            # nmcli 字段: SSID, BSSID, CHAN, RATE, SIGNAL, SECURITY, DEVICE
            cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY,RATE", "dev", "wifi", "list"]
            output = subprocess.check_output(cmd).decode('utf-8')

            for line in output.split('\n'):
                if not line: continue
                # 复杂的冒号处理...
                parts = line.split(':')
                # 倒序取值最稳
                if len(parts) >= 5:
                    rate = parts[-1]
                    sec = parts[-2]
                    sig = parts[-3]
                    chan = parts[-4]
                    # BSSID 是 -10 到 -4
                    bssid = ":".join(parts[-10:-4]) if len(parts) >= 10 else "Unknown"
                    ssid = line.split(bssid)[0].strip(':')

                    if not ssid: ssid = "<Hidden>"

                    # 处理信号
                    try:
                        signal_strength = int(sig)  # nmcli 有时返回 bar 有时返回 %
                        # 简单转换: 假设是 %
                        dbm = int((signal_strength / 2) - 100) if signal_strength > 0 else -100
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
                        "vendor": get_vendor(bssid),  # 新增
                        "band": get_band(channel)  # 新增
                    })
        except Exception as e:
            print(f"[!] Linux Scan Error: {e}")

    return networks


# ==========================================
# 3. 统一接口 (Universal Endpoint)
# ==========================================
@router.post("/scan/start")
@router.get("/scan/start")
@router.post("/networks")
@router.get("/networks")
async def scan_wifi_universal():
    """
    全能扫描接口：返回包含厂商、频段、信号详情的丰富数据
    """
    results = get_real_scan_results()

    # 按信号强度排序 (强的在前)
    results.sort(key=lambda x: x['signal'], reverse=True)

    return {
        "code": 200,
        "status": "success",
        "message": "深度扫描完成",
        "count": len(results),
        "networks": results
    }


# ==========================================
# 4. 攻击与其他 (保持原样)
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