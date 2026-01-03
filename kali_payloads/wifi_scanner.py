import subprocess
import time
import requests
import os
import csv
import glob
import sys
import traceback
import shutil  # 必须引入这个库

# ================= 配置区域 =================
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

# 1. 启动标记
if not os.path.exists(TMP_DIR): os.makedirs(TMP_DIR)
os.system(f"touch {TMP_DIR}/agent_started.lock")


# ================= 工具函数 =================
def get_c2_ip():
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        return os.popen("ip route show | grep default | awk '{print $3}'").read().strip() or "127.0.0.1"
    except:
        return "127.0.0.1"


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def check_monitor_mode(iface):
    return "type monitor" in run_cmd(f"iw dev {iface} info")


def ensure_monitor_mode(iface):
    if check_monitor_mode(iface): return iface
    print(f"[*] 开启监听模式: {iface}")
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")
    if check_monitor_mode(iface): return iface
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {iface}")
    return f"{iface}mon" if os.path.exists(f"/sys/class/net/{iface}mon") else iface


# === 🔥 核心新增：获取真实驱动/芯片型号 ===
def get_driver_name(iface):
    """
    获取网卡真实的物理驱动/芯片名称 (如 mt7921u, rtl88xxau)
    """
    # 方法 1: 使用 ethtool (最准确)
    try:
        if shutil.which("ethtool"):
            cmd = f"ethtool -i {iface}"
            res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
            for line in res.splitlines():
                if "driver:" in line:
                    return line.split(":")[1].strip()
    except:
        pass

    # 方法 2: 读取 sysfs (备用，无需工具)
    try:
        path = f"/sys/class/net/{iface}/device/driver"
        if os.path.exists(path):
            return os.path.basename(os.path.realpath(path))
    except:
        pass

    return "Generic"


def get_interfaces():
    ifaces = []
    sys_net = "/sys/class/net"
    if not os.path.exists(sys_net): return []

    for i in os.listdir(sys_net):
        # 排除 lo 和非无线网卡
        if i != "lo" and os.path.exists(f"{sys_net}/{i}/wireless"):
            mode = "Monitor" if check_monitor_mode(i) else "Managed"
            driver = get_driver_name(i)

            # 🔥 重点：在这里直接组装好前端要显示的字符串
            # 格式示例: wlan0 : mt7921u [Monitor]
            display_str = f"{i} : {driver} [{mode}]"

            ifaces.append({
                "name": i,
                "display": display_str,
                "mode": mode,
                "driver": driver
            })
    return ifaces


# ================= 核心：CSV 解析 =================
def parse_airodump_csv(csv_path):
    networks = []
    clients = []
    client_counts = {}

    if not os.path.exists(csv_path): return [], []

    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        ap_lines = []
        client_lines = []
        is_client_section = False

        for line in lines:
            line = line.strip()
            if not line: continue
            if "Station MAC" in line:
                is_client_section = True
                continue
            (client_lines if is_client_section else ap_lines).append(line)

        # 1. 解析 Clients
        if client_lines:
            reader = csv.reader(client_lines)
            for row in reader:
                if len(row) < 6: continue
                st_mac = row[0].strip().upper()
                bssid = row[5].strip().upper()
                if bssid and "NOT ASSOCIATED" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1
                pwr = row[3].strip()
                clients.append({
                    "mac": st_mac, "bssid": bssid,
                    "signal": int(pwr) if pwr.lstrip('-').isdigit() else -100,
                    "packets": int(row[4].strip()) if row[4].strip().isdigit() else 0
                })

        # 2. 解析 APs
        start = -1
        for i, l in enumerate(ap_lines):
            if l.startswith("BSSID"): start = i; break
        if start != -1:
            reader = csv.reader(ap_lines[start + 1:])
            for row in reader:
                if len(row) < 14: continue
                bssid = row[0].strip().upper()
                networks.append({
                    "bssid": bssid, "ssid": row[13].strip() or "<Hidden>",
                    "channel": int(row[3].strip()) if row[3].strip().isdigit() else 0,
                    "signal": int(row[8].strip()) if row[8].strip().lstrip('-').isdigit() else -100,
                    "encryption": row[5].strip(), "vendor": "Unknown",
                    "client_count": client_counts.get(bssid, 0)
                })
    except:
        pass
    return networks, clients


# ================= 任务逻辑 =================
def run_scan(iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/scan"
    for f in glob.glob(f"{prefix}*"): os.remove(f)
    cmd = ["timeout", "15s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv", mon]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nets, _ = parse_airodump_csv(f"{prefix}-01.csv")
    return nets


def run_monitor(params, iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/mon"
    for f in glob.glob(f"{prefix}*"): os.remove(f)
    target_bssid = params['bssid'].upper()
    target_ch = str(params['channel'])
    os.system(f"iwconfig {mon} channel {target_ch}")

    cmd = ["airodump-ng", "--bssid", target_bssid, "--channel", target_ch, "--write", prefix, "--output-format", "csv",
           mon]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"

    try:
        while True:
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=2).json()
                if res.get("task") != "monitor_target": break
            except:
                pass

            if os.path.exists(f"{prefix}-01.csv"):
                _, all_clients = parse_airodump_csv(f"{prefix}-01.csv")
                target_clients = [c for c in all_clients if c['bssid'] == target_bssid]
                if target_clients: requests.post(f"{base_url}/callback",
                                                 json={"type": "monitor_update", "data": target_clients})
            time.sleep(2)
    finally:
        if proc: proc.terminate()
        os.system("killall airodump-ng")


# ================= 主循环 =================
if __name__ == "__main__":
    try:
        base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"
        while True:
            requests.post(f"{base_url}/register_agent", json={"interfaces": get_interfaces()})
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=5).json()
                if res.get("task") == "scan":
                    nets = run_scan(res["params"]["interface"])
                    requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets})
                elif res.get("task") == "monitor_target":
                    run_monitor(res["params"], res["params"]["interface"])
            except:
                pass
            time.sleep(HEARTBEAT_INTERVAL)
    except:
        pass