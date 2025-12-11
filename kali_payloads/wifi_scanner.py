import subprocess
import json
import time
import requests
import shutil
import os
import sys
import socket

# ================= 配置区域 =================
# 注意：部署时后端会自动通过 sed 替换这个值
# 如果你手动运行，请手动填入 Windows 后端的 IP，例如 "192.168.1.5"
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2


# ===========================================

def get_c2_ip():
    """
    智能获取 C2 服务器 IP
    1. 优先使用硬编码的 FIXED_C2_IP
    2. 如果为空，尝试通过连接局域网探测宿主机 IP
    """
    if FIXED_C2_IP:
        return FIXED_C2_IP

    # 尝试探测：如果是 NAT 模式，网关通常是宿主机
    try:
        # 获取默认网关
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway:
            return gateway
    except:
        pass

    # 最后的兜底：默认回环（仅用于调试，实际大概率连不上）
    return "127.0.0.1"


def get_kali_interfaces():
    """获取网卡列表"""
    interfaces = []
    try:
        # 获取所有网络接口
        out = subprocess.check_output(["ip", "-o", "link", "show"]).decode()
        for line in out.split('\n'):
            if ": " not in line: continue

            parts = line.split(": ")
            if len(parts) < 2: continue

            iface = parts[1].split("@")[0].strip()
            # 排除非物理网卡
            if iface == "lo" or "docker" in iface or "veth" in iface: continue

            # 判断模式
            mode = "Managed"
            try:
                iw_out = subprocess.check_output(["iw", "dev", iface, "info"], stderr=subprocess.DEVNULL).decode()
                if "type monitor" in iw_out:
                    mode = "Monitor"
            except:
                pass

            interfaces.append({
                "name": iface,
                "display": f"{iface} [{mode}]",
                "mode": mode,
                "is_wireless": True  # 简单假设都是无线，或者你可以加 ethtool 判断
            })
    except Exception as e:
        print(f"[-] 获取网卡失败: {e}")

    return interfaces


def perform_scan(interface):
    """执行扫描"""
    print(f"[+] 正在扫描: {interface}")
    networks = []

    # 优先使用 nmcli (Managed模式)
    try:
        cmd = ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", interface]
        # 注意：subprocess 在后台运行时可能因为缓冲导致卡顿，这里用 check_output
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(errors='ignore')

        for line in out.split('\n'):
            if not line.strip(): continue
            # nmcli -t 输出格式: SSID:BSSID:CHAN:SIGNAL:SECURITY
            # 因为 SSID 可能包含冒号，我们从后面倒着解析
            parts = line.split(':')
            if len(parts) < 5: continue

            sec = parts[-1]
            sig = parts[-2]
            chan = parts[-3]

            # BSSID 是固定的 6段 (MAC地址)
            # 倒数第4到倒数第9个部分组成 BSSID
            # 例如: ...:AA:BB:CC:DD:EE:FF:6:80:WPA2
            if len(parts) >= 9:
                bssid = ":".join(parts[-9:-3])
                # 剩下的前面就是 SSID
                ssid_parts = parts[:-9]
                ssid = ":".join(ssid_parts).strip()
            else:
                continue

            if not ssid: ssid = "<Hidden>"

            # 信号强度处理
            try:
                signal_val = int(sig)
                # nmcli 有时输出 0-100 的质量值，有时是 dBm。简单转换一下
                if signal_val > 0:
                    dbm = (signal_val / 2) - 100
                else:
                    dbm = signal_val
            except:
                dbm = -80

            networks.append({
                "ssid": ssid,
                "bssid": bssid,
                "channel": int(chan) if chan.isdigit() else 1,
                "signal": int(dbm),
                "encryption": sec,
                "vendor": "Unknown"
            })

    except Exception as e:
        print(f"[-] 扫描出错: {e}")

    return networks


def main():
    # 1. 获取 C2 地址
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    # 禁用系统代理 (防止 requests 走代理报错)
    os.environ['no_proxy'] = '*'

    print(f"[*] Kali Agent 启动，C2 Server: {base_url}")

    # 2. 注册上线
    ifaces = get_kali_interfaces()
    try:
        requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=5)
        print("[+] 注册成功，等待任务...")
    except Exception as e:
        print(f"[-] 注册失败 (检查IP {c2_ip} 是否可达): {e}")
        # 这里不要退出，继续尝试连接，也许 C2 还没启动好

    # 3. 守护循环
    while True:
        try:
            # 心跳
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")

            if task == "scan":
                iface = data.get("params", {}).get("interface")
                if not iface and ifaces: iface = ifaces[0]["name"]

                if iface:
                    res = perform_scan(iface)
                    # 回传结果
                    requests.post(f"{base_url}/callback", json={
                        "type": "scan_result",
                        "networks": res
                    })

            elif task == "idle":
                pass

        except Exception as e:
            print(f"[!] 心跳异常: {e}")

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    # 必须去掉所有 input()，否则 nohup 会报错 EOFError
    main()