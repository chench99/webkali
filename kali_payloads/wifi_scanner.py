import subprocess
import time
import requests
import os
import csv
import glob
import sys
import shutil

# ================= 配置区域 =================
FIXED_C2_IP = ""  # 部署时会自动注入
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 基础工具函数 =================

def get_c2_ip():
    """智能获取 C2 地址"""
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        # 尝试获取默认网关 IP
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway: return gateway
    except:
        pass
    # 兜底
    return "127.0.0.1"


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def check_monitor_mode(iface):
    """检查网卡是否为监听模式"""
    try:
        iw_info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in iw_info: return True
    except:
        pass
    return False


def ensure_monitor_mode(original_iface):
    """确保进入监听模式，返回实际接口名 (e.g., wlan0 -> wlan0mon)"""
    if check_monitor_mode(original_iface): return original_iface

    print(f"[*] 开启监听模式: {original_iface}")
    run_cmd("airmon-ng check kill")  # 杀掉干扰进程
    run_cmd(f"airmon-ng start {original_iface}")

    # 查找可能变更为 wlan0mon 的新名称
    # 逻辑：遍历所有网卡，找到一个名字相似且处于 monitor 模式的
    for name in os.listdir("/sys/class/net"):
        if (name.startswith(original_iface) or "mon" in name) and check_monitor_mode(name):
            return name

    # 如果找不到新名字，尝试返回原名字兜底
    return original_iface


# ================= 核心修复：网卡识别逻辑 =================

def get_smart_interfaces():
    """
    [修复] 获取网卡列表回传给 C2
    恢复了双重检查机制：既检查 /sys/class/net 目录，也检查 iw 命令输出。
    """
    interfaces = []
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []

    for iface in os.listdir(sys_cls_net):
        # 1. 排除非物理接口
        if iface in ["lo"] or iface.startswith(("eth", "docker", "veth", "br-", "vmnet")):
            continue

        # 2. [关键修复] 双重判定是否为无线网卡
        is_wireless = False

        # 判定 A: 检查系统目录标志 (适用于内置网卡)
        if os.path.exists(f"{sys_cls_net}/{iface}/wireless") or os.path.exists(f"{sys_cls_net}/{iface}/phy80211"):
            is_wireless = True

        # 判定 B: 检查 iw 命令 (适用于 USB 网卡，如 RTL8812AU)
        if not is_wireless:
            iw_output = run_cmd(f"iw dev {iface} info")
            if "wiphy" in iw_output:
                is_wireless = True

        if not is_wireless:
            continue

        # 3. 获取驱动名称
        driver = "Unknown"
        try:
            driver = subprocess.check_output(f"ethtool -i {iface} | grep driver", shell=True).decode().split(":")[
                1].strip()
        except:
            pass

        mode = "Monitor" if check_monitor_mode(iface) else "Managed"

        interfaces.append({
            "name": iface,
            "display": f"{'🔥 ' if mode == 'Monitor' else ''}{driver} ({iface})",
            "mode": mode,
            "is_wireless": True
        })

    return interfaces


def cleanup_files(prefix):
    """清理临时 CSV 文件"""
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass


# ================= 扫描与监听逻辑 (保持 5G 升级) =================

def parse_csv_dual_section(csv_path):
    """
    解析 CSV，同时提取 AP 和 Clients 统计
    (修复了 Station 解析逻辑)
    """
    networks = []
    client_counts = {}  # { bssid: count }
    clients_details = []

    if not os.path.exists(csv_path): return [], []

    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        ap_lines = []
        station_lines = []
        is_station_section = False

        for line in lines:
            line = line.strip()
            if not line: continue

            if line.startswith("Station MAC"):
                is_station_section = True
                continue

            if is_station_section:
                station_lines.append(line)
            else:
                ap_lines.append(line)

        # 1. 解析 Station 部分 (统计在线人数)
        if station_lines:
            reader = csv.reader(station_lines)
            for row in reader:
                if len(row) < 6: continue
                # Station CSV: MAC, First seen, Last seen, Power, # packets, BSSID, Probed ESSIDs
                st_mac = row[0].strip()
                power = row[3].strip()
                packets = row[4].strip()
                bssid = row[5].strip()

                # 排除未关联的 (not associated)
                if bssid and "not associated" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1

                clients_details.append({
                    "mac": st_mac,
                    "power": power,
                    "packets": packets,
                    "bssid": bssid
                })

        # 2. 解析 AP 部分
        if len(ap_lines) > 0:
            header_idx = -1
            for i, l in enumerate(ap_lines):
                if l.startswith("BSSID"):
                    header_idx = i
                    break

            if header_idx != -1 and len(ap_lines) > header_idx + 1:
                reader = csv.reader(ap_lines[header_idx + 1:])
                for row in reader:
                    if len(row) < 14: continue

                    bssid = row[0].strip()
                    channel_str = row[3].strip()
                    encrypt = row[5].strip()
                    signal_str = row[8].strip()
                    ssid = row[13].strip()

                    try:
                        channel = int(channel_str)
                    except:
                        channel = 0

                    try:
                        signal = int(signal_str)
                    except:
                        signal = -100

                    if not ssid: ssid = "<Hidden>"

                    # [5G 支持] 简单判断：信道 > 14 视为 5G
                    band = "5G" if channel > 14 else "2.4G"

                    networks.append({
                        "bssid": bssid,
                        "ssid": ssid,
                        "channel": channel,
                        "signal": signal,
                        "encryption": encrypt,
                        "band": band,
                        "clientCount": client_counts.get(bssid, 0)  # 绑定人数
                    })

    except Exception as e:
        print(f"[-] CSV Parse Error: {e}")

    return networks, clients_details


def perform_scan_airodump(iface):
    """普通扫描 (15s, 双频)"""
    print(f"[*] 执行普通扫描 (15s): {iface} [Band: 2.4/5G]")
    prefix = f"{TMP_DIR}/scan_result"
    cleanup_files(prefix)

    # [5G 支持] 添加 --band abg
    cmd = [
        "timeout", "15s",
        "airodump-ng",
        "--band", "abg",
        "--write", prefix,
        "--output-format", "csv",
        iface
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    csv_file = f"{prefix}-01.csv"
    networks, _ = parse_csv_dual_section(csv_file)

    cleanup_files(prefix)
    return networks


def run_monitor_task(task_type, params, original_iface):
    """持续监听任务"""
    mon_iface = ensure_monitor_mode(original_iface)
    prefix = f"{TMP_DIR}/monitor_output"
    cleanup_files(prefix)

    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]

    if task_type == 'monitor_target':
        bssid = params.get('bssid')
        channel = params.get('channel')
        run_cmd(f"iwconfig {mon_iface} channel {channel}")
        cmd.extend(["--bssid", bssid, "--channel", str(channel)])
        print(f"[*] 锁定监听: {bssid} (CH {channel})")

    elif task_type == 'deep_scan':
        print(f"[*] 启动全网深度扫描")
        cmd.extend(["--band", "abg"])

    cmd.append(mon_iface)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csv_file = f"{prefix}-01.csv"

    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    try:
        while True:
            # 1. 检查停止信号
            try:
                r = requests.get(f"{base_url}/agent/heartbeat", timeout=2)
                if r.json().get("task") != task_type:
                    print("[*] 收到停止指令")
                    break
            except:
                pass

            # 2. 解析数据并回传
            _, clients = parse_csv_dual_section(csv_file)

            if clients:
                update_type = 'monitor_update' if task_type == 'monitor_target' else 'deep_update'
                try:
                    requests.post(f"{base_url}/callback", json={
                        "type": update_type,
                        "data": clients
                    })
                except:
                    pass

            time.sleep(2)
    finally:
        if proc: proc.terminate()
        cleanup_files(prefix)


# ================= 主循环 =================

def main():
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    os.environ['no_proxy'] = '*'

    print(f"[*] Kali Agent v2.2 (Interface Fix) -> {base_url}")

    # [优化] 记录上次上报网卡的时间
    last_iface_report = 0

    while True:
        try:
            # 1. [关键修复] 周期性上报网卡状态 (每5秒)
            # 这样即使服务端重启，Agent 也会自动重新注册网卡，解决 "找不到网卡" 问题
            if time.time() - last_iface_report > 5:
                ifaces = get_smart_interfaces()
                if ifaces:
                    # print(f"[*] 上报网卡: {[i['name'] for i in ifaces]}")
                    requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=3)
                last_iface_report = time.time()

            # 2. 心跳获取任务
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            if task == "scan":
                iface = params.get("interface")
                mon_iface = ensure_monitor_mode(iface)
                nets = perform_scan_airodump(mon_iface)
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets})

            elif task in ["monitor_target", "deep_scan"]:
                iface = params.get("interface")
                run_monitor_task(task, params, iface)

            # task == "idle" 时，继续循环

        except Exception as e:
            print(f"[!] Loop Error: {e}")
            time.sleep(3)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()