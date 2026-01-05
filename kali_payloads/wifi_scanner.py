import subprocess
import time
import requests
import os
import csv
import glob
import sys
import traceback
import shutil

# ================= 配置区域 =================
FIXED_C2_IP = ""  # 由后端自动注入
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

# 1. 启动标记
if not os.path.exists(TMP_DIR): os.makedirs(TMP_DIR)
os.system(f"touch {TMP_DIR}/agent_started.lock")


# 日志记录 (关键：把错误写下来，否则出了问题不知道)
def log_error(msg):
    with open(f"{TMP_DIR}/agent_error.log", "a") as f:
        f.write(f"[{time.ctime()}] {msg}\n")


# ================= 工具函数 =================
def get_c2_ip():
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        # 尝试获取默认网关作为回连 IP (适用于 NAT 模式)
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
    # 尝试开启监听模式
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")
    if check_monitor_mode(iface): return iface
    # 备用方案
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {iface}")
    return f"{iface}mon" if os.path.exists(f"/sys/class/net/{iface}mon") else iface


def get_driver_name(iface):
    try:
        if shutil.which("ethtool"):
            res = subprocess.check_output(f"ethtool -i {iface}", shell=True, stderr=subprocess.DEVNULL).decode()
            for line in res.splitlines():
                if "driver:" in line: return line.split(":")[1].strip()
    except:
        pass
    return "Generic"


def get_interfaces():
    ifaces = []
    sys_net = "/sys/class/net"
    if not os.path.exists(sys_net): return []
    for i in os.listdir(sys_net):
        if i != "lo" and os.path.exists(f"{sys_net}/{i}/wireless"):
            mode = "Monitor" if check_monitor_mode(i) else "Managed"
            driver = get_driver_name(i)
            ifaces.append({
                "name": i,
                "display": f"{i} : {driver} [{mode}]",
                "mode": mode,
                "driver": driver
            })
    return ifaces


# ================= CSV 解析 =================
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
        is_client = False
        for line in lines:
            line = line.strip()
            if not line: continue
            if "Station MAC" in line: is_client = True; continue
            (client_lines if is_client else ap_lines).append(line)

        if client_lines:
            for row in csv.reader(client_lines):
                if len(row) < 6: continue
                bssid = row[5].strip().upper()
                if bssid and "NOT ASSOCIATED" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1
                clients.append({
                    "mac": row[0].strip().upper(), "bssid": bssid,
                    "signal": int(row[3].strip()) if row[3].strip().lstrip('-').isdigit() else -100,
                    "packets": int(row[4].strip()) if row[4].strip().isdigit() else 0
                })

        start = -1
        for i, l in enumerate(ap_lines):
            if l.startswith("BSSID"): start = i; break
        if start != -1:
            for row in csv.reader(ap_lines[start + 1:]):
                if len(row) < 14: continue
                bssid = row[0].strip().upper()
                networks.append({
                    "bssid": bssid, "ssid": row[13].strip() or "<Hidden>",
                    "channel": int(row[3].strip()) if row[3].strip().isdigit() else 0,
                    "signal": int(row[8].strip()) if row[8].strip().lstrip('-').isdigit() else -100,
                    "encryption": row[5].strip(),
                    "client_count": client_counts.get(bssid, 0)
                })
    except Exception as e:
        log_error(f"CSV Parse Error: {e}")
    return networks, clients


# ================= 任务执行 =================
def run_scan(iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/scan"
    for f in glob.glob(f"{prefix}*"): os.remove(f)
    subprocess.run(["timeout", "10s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv", mon],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nets, _ = parse_airodump_csv(f"{prefix}-01.csv")
    return nets


def run_monitor(params, iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/mon"
    for f in glob.glob(f"{prefix}*"): os.remove(f)
    cmd = ["airodump-ng", "--bssid", params['bssid'], "--channel", str(params['channel']), "--write", prefix,
           "--output-format", "csv", mon]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, prefix


# ================= 主循环 (修复版) =================
if __name__ == "__main__":
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    print(f"[*] Agent Started. C2: {base_url}")

    current_proc = None

    while True:
        try:
            # 1. 注册 (带超时)
            requests.post(f"{base_url}/register_agent", json={"interfaces": get_interfaces()}, timeout=3)

            # 2. 心跳
            res = requests.get(f"{base_url}/agent/heartbeat", timeout=3).json()
            task = res.get("task")

            # 停止旧任务
            if task != "monitor_target" and current_proc:
                current_proc.terminate()
                current_proc = None
                os.system("killall airodump-ng")

            if task == "scan":
                nets = run_scan(res["params"]["interface"])
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets}, timeout=5)

            elif task == "monitor_target":
                if not current_proc:
                    current_proc, prefix = run_monitor(res["params"], res["params"]["interface"])
                else:
                    # 读取监听数据
                    if os.path.exists(f"{prefix}-01.csv"):
                        _, clients = parse_airodump_csv(f"{prefix}-01.csv")
                        target_clients = [c for c in clients if c['bssid'] == res["params"]["bssid"]]
                        if target_clients:
                            requests.post(f"{base_url}/callback",
                                          json={"type": "monitor_update", "data": target_clients}, timeout=2)

        except KeyboardInterrupt:
            break
        except Exception as e:
            # 🔥 核心修复：捕获错误并继续，而不是退出！
            log_error(f"Loop Error: {e}")
            # 如果是连接被拒绝，可能是后端还没起，等待久一点
            time.sleep(2)

        time.sleep(HEARTBEAT_INTERVAL)