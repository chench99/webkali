# backend/kali_payloads/wifi_scanner.py

import subprocess
import json
import sys
import time
import requests
import shutil
import re

# =================配置区域=================
# C2 服务器地址 (Kali 运行此脚本时回传数据的地址)
C2_SERVER = "http://127.0.0.1:8000"  # 请根据实际情况修改为宿主机 IP
CALLBACK_URL = f"{C2_SERVER}/api/v1/wifi/callback"
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


def get_kali_interfaces():
    """获取 Kali 真实网卡 (iw dev)"""
    interfaces = []
    if shutil.which("iw"):
        try:
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
                    current_iface["mode"] = line.split()[1].title()
                elif line.startswith("addr") and current_iface:
                    current_iface["mac"] = line.split()[1]
    return interfaces


def scan_networks(interface=None):
    """执行深度扫描"""
    networks = []
    print(f"[*] Starting scan on interface: {interface or 'Auto'}...")

    try:
        # nmcli 命令
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY,RATE", "dev", "wifi", "list"]
        if interface:
            cmd.extend(["ifname", interface])

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
                    "clients": -1  # 预留给 Airodump
                })
    except Exception as e:
        print(f"[!] Scan Error: {e}")
        return []

    return networks


def main():
    # 1. 获取网卡
    ifaces = get_kali_interfaces()
    print(f"[*] Detected Interfaces: {ifaces}")

    # 2. 自动选择最佳网卡 (Monitor 优先 -> wlan0)
    target_iface = None
    for i in ifaces:
        if i['mode'] == 'Monitor':
            target_iface = i['name']
            break
    if not target_iface and ifaces:
        target_iface = ifaces[0]['name']

    # 3. 执行扫描
    results = scan_networks(target_iface)

    # 4. 回传数据给 C2 后端
    payload = {
        "interface": target_iface,
        "count": len(results),
        "networks": results,
        "timestamp": time.time()
    }

    print(f"[*] Sending {len(results)} networks to C2 Server...")
    try:
        # 这里的 endpoint 要对应后端新写的接收接口
        r = requests.post(CALLBACK_URL, json=payload)
        print(f"[+] Server Response: {r.status_code}")
    except Exception as e:
        print(f"[-] Failed to send data: {e}")


if __name__ == "__main__":
    main()