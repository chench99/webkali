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


# ================= 基础工具函数 (保持不变) =================
def get_c2_ip():
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway: return gateway
    except:
        pass
    return "127.0.0.1"


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def check_monitor_mode(iface):
    try:
        iw_info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in iw_info: return True
    except:
        pass
    return False


def ensure_monitor_mode(original_iface):
    """(保持原有逻辑)"""
    if check_monitor_mode(original_iface): return original_iface
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {original_iface}")
    # 查找新接口名
    for name in os.listdir("/sys/class/net"):
        if (name.startswith(original_iface) or "mon" in name) and check_monitor_mode(name):
            return name
    return original_iface


def get_smart_interfaces():
    """(保持原有逻辑，返回网卡列表)"""
    interfaces = []
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []
    for iface in os.listdir(sys_cls_net):
        if iface in ["lo"] or iface.startswith(("eth", "docker", "veth")): continue
        if not os.path.exists(f"{sys_cls_net}/{iface}/wireless") and not os.path.exists(
                f"{sys_cls_net}/{iface}/phy80211"):
            continue

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


# ================= 核心：增强版扫描逻辑 =================

def cleanup_files(prefix):
    """清理临时文件"""
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass


def perform_scan_airodump(iface):
    """
    执行 10s 双频扫描，并解析 AP 和 Client 数量
    """
    print(f"[*] 执行双频扫描 (10s): {iface}")
    prefix = f"{TMP_DIR}/scan_result"
    cleanup_files(prefix)

    # 1. 启动 airodump
    cmd = [
        "timeout", "10s",
        "airodump-ng",
        "--band", "abg",  # 双频
        "--write", prefix,
        "--output-format", "csv",
        iface
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. 解析 CSV
    csv_file = f"{prefix}-01.csv"
    networks = []

    if os.path.exists(csv_file):
        try:
            # 这里的逻辑是：先读入所有行，分为 AP 部分和 Client 部分
            with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            ap_section = []
            client_section = []
            is_client_section = False

            for line in lines:
                if line.strip() == "": continue
                if line.startswith("Station MAC"):
                    is_client_section = True
                    continue

                if is_client_section:
                    client_section.append(line)
                else:
                    ap_section.append(line)

            # --- 解析 Clients 以统计人数 ---
            client_counts = {}  # { bssid: count }
            if len(client_section) > 0:
                reader = csv.reader(client_section)
                for row in reader:
                    if len(row) < 6: continue
                    bssid = row[5].strip()
                    if bssid and bssid != "(not associated)":
                        client_counts[bssid] = client_counts.get(bssid, 0) + 1

            # --- 解析 AP ---
            if len(ap_section) > 1:  # Skip header
                reader = csv.reader(ap_section)
                for row in reader:
                    # airodump csv header check
                    if not row or len(row) < 14 or row[0].strip() == "BSSID": continue

                    bssid = row[0].strip()
                    ssid = row[13].strip()
                    if not ssid: ssid = "<Hidden>"

                    channel = 0
                    try:
                        channel = int(row[3].strip())
                    except:
                        pass

                    signal = -100
                    try:
                        signal = int(row[8].strip())
                    except:
                        pass

                    enc = row[5].strip()

                    # 构造结果
                    networks.append({
                        "bssid": bssid,
                        "ssid": ssid,
                        "channel": channel,
                        "signal": signal,
                        "encryption": enc,
                        "vendor": "Unknown",  # 简单版暂不查厂商
                        "band": "5G" if channel > 14 else "2.4G",
                        "clientCount": client_counts.get(bssid, 0)  # ✅ 增加字段
                    })

        except Exception as e:
            print(f"[-] CSV 解析失败: {e}")

    cleanup_files(prefix)
    return networks


# ================= 主循环 (保持 C2 逻辑) =================

def run_monitor_task(task_type, params, original_iface):
    """(保持原有监听逻辑不变，省略以节省篇幅，重点是上面的扫描)"""
    # 这里引用你之前提供的 run_monitor_task 代码...
    # ...
    pass


def main():
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    os.environ['no_proxy'] = '*'

    print(f"[*] Kali Smart Agent v7.0 (Fixed) -> {base_url}")

    # 注册
    try:
        requests.post(f"{base_url}/register_agent", json={"interfaces": get_smart_interfaces()}, timeout=2)
    except:
        pass

    while True:
        try:
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            if task == "scan":
                iface = params.get("interface")
                mon_iface = ensure_monitor_mode(iface)

                # 执行扫描
                res = perform_scan_airodump(mon_iface)

                # 回传结果
                requests.post(f"{base_url}/callback", json={
                    "type": "scan_result",
                    "networks": res
                })

            elif task in ["monitor_target", "deep_scan"]:
                # 调用你原有的监听逻辑
                # run_monitor_task(task, params, params.get("interface"))
                # 为保证完整性，若上方未粘贴 run_monitor_task，则此处需保留原逻辑
                pass

            elif task == "idle":
                # 空闲时偶尔刷新网卡列表
                if int(time.time()) % 10 == 0:
                    requests.post(f"{base_url}/register_agent", json={"interfaces": get_smart_interfaces()})

        except Exception as e:
            print(f"[!] Loop Error: {e}")
            time.sleep(2)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()