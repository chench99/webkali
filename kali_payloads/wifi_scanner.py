# backend/kali_payloads/wifi_scanner.py
import subprocess
import json
import time
import requests
import shutil
import re
import os
import socket

# ================= 配置 =================
# 默认 C2 地址 (稍后会动态获取)
DEFAULT_HOST = "192.168.x.x"
PORT = "8000"


# =======================================

def get_driver_name(iface):
    """获取网卡驱动/真实名称"""
    try:
        # 方法1: 通过 ethtool
        if shutil.which("ethtool"):
            out = subprocess.check_output(["ethtool", "-i", iface]).decode()
            for line in out.split("\n"):
                if line.startswith("driver:"):
                    return line.split(":")[1].strip()

        # 方法2: 读取系统文件
        path = f"/sys/class/net/{iface}/device/uevent"
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
                if "DRIVER=" in content:
                    return content.split("DRIVER=")[1].split("\n")[0]
    except:
        pass
    return "Generic"


def get_kali_interfaces():
    """获取网卡并格式化名称"""
    interfaces = []
    # 优先使用 ip link (比 iw 更通用)
    try:
        output = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
        for line in output.split('\n'):
            if ": " in line:
                parts = line.split(": ")
                if len(parts) >= 2:
                    iface_name = parts[1].split("@")[0]  # 处理 wlan0@phy0 这种情况

                    # 过滤掉非无线 (简单的过滤，lo, eth)
                    if iface_name == "lo" or "eth" in iface_name or "docker" in iface_name:
                        continue

                    driver = get_driver_name(iface_name)
                    # 格式化名称: 驱动名 (接口名)
                    display_name = f"{driver} ({iface_name})"

                    # 判断模式
                    mode = "Managed"
                    if "NO-CARRIER" not in line and "UP" in line:  # 粗略判断
                        pass
                    # 尝试用 iw 确认模式
                    try:
                        iw_out = subprocess.check_output(["iw", "dev", iface_name, "info"]).decode()
                        if "type monitor" in iw_out:
                            mode = "Monitor"
                    except:
                        pass

                    interfaces.append({
                        "name": iface_name,
                        "display": display_name,  # 前端要显示的格式
                        "mode": mode,
                        "driver": driver
                    })
    except Exception as e:
        print(f"[!] 获取网卡失败: {e}")
    return interfaces


def scan_with_iw(iface):
    """使用 iw scan (支持 Monitor 模式)"""
    networks = []
    try:
        # trigger scan
        subprocess.run(["iw", "dev", iface, "scan", "trigger"], stderr=subprocess.DEVNULL)
        time.sleep(2)  # 等待扫描
        output = subprocess.check_output(["iw", "dev", iface, "scan", "dump"]).decode('utf-8', errors='ignore')

        current_net = {}
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("BSS "):
                if current_net: networks.append(current_net)
                bssid = line.split("(")[0].strip()
                current_net = {"bssid": bssid, "clients": -1, "vendor": "Unknown"}
            elif line.startswith("SSID:"):
                current_net["ssid"] = line.split("SSID:")[1].strip()
            elif line.startswith("signal:"):
                sig = line.split("signal:")[1].split(".")[0].strip()
                current_net["signal"] = int(float(sig))
            elif line.startswith("DS Parameter set: channel"):
                current_net["channel"] = int(line.split("channel")[1].strip())
            elif line.startswith("RSN:"):
                current_net["encryption"] = "WPA2"
            elif "WPA:" in line:
                current_net["encryption"] = "WPA"

        if current_net: networks.append(current_net)
    except:
        pass
    return networks


def scan_networks(interface=None):
    """智能扫描分流"""
    print(f"[*] 正在扫描接口: {interface}...")

    # 1. 尝试 nmcli (Managed 模式最佳)
    networks = []
    try:
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", interface]
        output = subprocess.check_output(cmd).decode('utf-8')
        for line in output.split('\n'):
            if not line: continue
            parts = line.split(':')
            if len(parts) >= 4:
                bssid = ":".join(parts[-9:-3]) if len(parts) >= 9 else "Unknown"
                ssid = line.split(bssid)[0].strip(':')
                if not ssid: ssid = "<Hidden>"
                networks.append({
                    "ssid": ssid, "bssid": bssid, "channel": int(parts[-3]),
                    "signal": int((int(parts[-2]) / 2) - 100), "encryption": parts[-1],
                    "clients": -1, "vendor": "Unknown"
                })
    except:
        print("[!] nmcli 失败，切换到 iw 模式 (可能是监听模式)...")
        networks = scan_with_iw(interface)

    return networks


def main():
    print("\n" + "=" * 40)
    print("    Kali C2 Wifi Payload v4.0")
    print("=" * 40)

    # 1. 自动探测或询问 C2 地址
    # 获取网关作为默认 C2 地址猜测
    try:
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
    except:
        gateway = "192.168.1.x"

    c2_ip = input(f"[?] 请输入 Windows 后端 IP (默认 {gateway}): ").strip()
    if not c2_ip: c2_ip = gateway

    C2_URL = f"http://{c2_ip}:{PORT}/api/v1/wifi/callback"
    print(f"[*] C2 Server Target: {C2_URL}")

    # 2. 上报网卡列表
    ifaces = get_kali_interfaces()
    print(f"[*] 发现网卡: {[i['display'] for i in ifaces]}")

    # 发送上线包 (Update Interfaces)
    try:
        requests.post(f"http://{c2_ip}:{PORT}/api/v1/wifi/register_agent", json={"interfaces": ifaces})
        print("[+] Agent 上线成功！网卡信息已同步到前端。")
    except Exception as e:
        print(f"[-] 连接 C2 失败: {e}")
        print("    请检查: 1. Windows 防火墙是否关闭 2. IP 是否正确")
        return

    # 3. 循环等待指令或执行一次性扫描
    # 这里演示一次性执行
    target_iface = ifaces[0]['name']
    for i in ifaces:
        if i['mode'] == 'Monitor':
            target_iface = i['name']
            break

    results = scan_networks(target_iface)
    print(f"[*] 扫描到 {len(results)} 个 AP")

    # 4. 回传结果
    payload = {
        "interface": target_iface,
        "count": len(results),
        "networks": results,
        "timestamp": time.time()
    }
    try:
        requests.post(C2_URL, json=payload)
        print("[+] 数据回传成功！请在 Web 界面查看。")
    except:
        print("[-] 数据回传失败")


if __name__ == "__main__":
    main()