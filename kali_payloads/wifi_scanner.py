import subprocess
import json
import time
import requests
import shutil
import os
import sys

# ================= 配置 =================
# 如果自动探测失败，请手动修改这里
FIXED_C2_IP = ""
PORT = "8000"
HEARTBEAT_INTERVAL = 2  # 心跳间隔(秒)


# =======================================

def get_kali_interfaces():
    """获取网卡列表 (含驱动名)"""
    interfaces = []
    try:
        # 使用 ip link 获取基础信息
        out = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
        for line in out.split('\n'):
            if ": " in line:
                iface = line.split(": ")[1].split("@")[0]
                if iface == "lo" or "eth" in iface or "docker" in iface: continue

                # 获取驱动
                driver = "Generic"
                try:
                    ethtool = subprocess.check_output(["ethtool", "-i", iface]).decode()
                    for l in ethtool.split("\n"):
                        if l.startswith("driver:"): driver = l.split(":")[1].strip()
                except:
                    pass

                # 获取模式
                mode = "Managed"
                try:
                    iw_info = subprocess.check_output(["iw", "dev", iface, "info"]).decode()
                    if "type monitor" in iw_info: mode = "Monitor"
                except:
                    pass

                interfaces.append({
                    "name": iface,
                    "display": f"{driver} ({iface})",
                    "mode": mode,
                    "is_wireless": True
                })
    except:
        pass
    return interfaces


def perform_scan(interface):
    """执行扫描任务"""
    print(f"[+] 收到扫描任务，使用网卡: {interface}")
    networks = []

    # 尝试使用 nmcli
    try:
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list"]
        if interface: cmd.extend(["ifname", interface])
        output = subprocess.check_output(cmd).decode()
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
    except Exception as e:
        print(f"[-] nmcli 扫描失败: {e}")
        # 如果 nmcli 失败，可能是因为处于 Monitor 模式，这里可以回退到 iw scan (略)

    return networks


def perform_attack(params):
    """执行攻击任务"""
    target = params.get('bssid')
    print(f"[+] 执行攻击 -> {target}")
    # 这里可以使用 aireplay-ng
    # subprocess.Popen(["aireplay-ng", "--deauth", "10", "-a", target, params.get('interface')])
    # 演示：仅打印
    return True


def main():
    print(f"[*] Kali C2 Agent v5.0 (Daemon Mode)")

    # 1. 连接 C2
    c2_ip = FIXED_C2_IP
    if not c2_ip:
        # 尝试获取网关
        try:
            gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        except:
            gateway = "127.0.0.1"
        c2_ip = input(f"[?] 请输入 C2 Server IP (默认 {gateway}): ").strip() or gateway

    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    print(f"[*] C2 Server: {base_url}")

    # 2. 注册上线
    ifaces = get_kali_interfaces()
    try:
        requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces})
        print("[+] 上线成功！进入守护模式...")
    except Exception as e:
        print(f"[-] 连接失败: {e}")
        return

    # 3. 进入死循环监听 (守护进程)
    while True:
        try:
            # 发送心跳，获取任务
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()

            task = data.get("task")

            if task == "scan":
                # 执行扫描
                iface = data.get("params", {}).get("interface")
                # 自动选择网卡逻辑
                if not iface:
                    iface = ifaces[0]['name'] if ifaces else "wlan0"

                results = perform_scan(iface)

                # 回传结果
                requests.post(f"{base_url}/callback", json={
                    "interface": iface,
                    "count": len(results),
                    "networks": results
                })
                print(f"[+] 扫描完成，已回传 {len(results)} 个结果")

            elif task == "attack":
                perform_attack(data.get("params"))

            elif task == "idle":
                # print(".", end="", flush=True) # 心跳显示
                pass

        except Exception as e:
            print(f"\n[-] C2 连接断开: {e}")
            time.sleep(2)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()