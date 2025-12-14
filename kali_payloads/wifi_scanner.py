import subprocess
import time
import requests
import os
import csv
import glob
import sys
import traceback

# ================= 配置区域 =================
# 此处 IP 会由后端部署脚本自动替换
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

# 1. 启动自检：创建锁文件
if not os.path.exists(TMP_DIR): os.makedirs(TMP_DIR)
os.system(f"touch {TMP_DIR}/agent_started.lock")


# ================= 工具函数 =================
def get_c2_ip():
    if FIXED_C2_IP: return FIXED_C2_IP
    # 尝试获取 Docker/VM 网关
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
    """自动开启监听模式"""
    if check_monitor_mode(iface): return iface

    # 避免 airmon-ng 改变接口名导致混乱，这里用 ip link 方式
    print(f"[*] 开启监听模式: {iface}")
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")

    if check_monitor_mode(iface): return iface

    # 如果上面的方法失败，尝试 airmon-ng
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {iface}")
    # 猜测新名称
    return f"{iface}mon" if os.path.exists(f"/sys/class/net/{iface}mon") else iface


def get_interfaces():
    ifaces = []
    for i in os.listdir("/sys/class/net"):
        if i != "lo" and os.path.exists(f"/sys/class/net/{i}/wireless"):
            mode = "Monitor" if check_monitor_mode(i) else "Managed"
            ifaces.append({"name": i, "display": f"{i} [{mode}]", "mode": mode})
    return ifaces


# ================= 核心：全能 CSV 解析 =================
def parse_airodump_csv(csv_path):
    """同时解析 AP 和 Clients"""
    networks = []
    clients = []
    client_counts = {}  # {BSSID: count}

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
            if line.startswith("Station MAC"):
                is_client_section = True
                continue

            if is_client_section:
                client_lines.append(line)
            else:
                ap_lines.append(line)

        # 1. 解析 Clients 并统计人数
        if client_lines:
            reader = csv.reader(client_lines)
            for row in reader:
                if len(row) < 6: continue
                st_mac = row[0].strip()
                bssid = row[5].strip()
                if bssid and "not associated" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1

                clients.append({
                    "mac": st_mac,
                    "bssid": bssid,
                    "signal": int(row[3].strip()) if row[3].strip().lstrip('-').isdigit() else -100,
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
                bssid = row[0].strip()
                channel = int(row[3].strip()) if row[3].strip().isdigit() else 0
                networks.append({
                    "bssid": bssid,
                    "ssid": row[13].strip() or "<Hidden>",
                    "channel": channel,
                    "signal": int(row[8].strip()) if row[8].strip().lstrip('-').isdigit() else -100,
                    "encryption": row[5].strip(),
                    # 绑定在线人数
                    "client_count": client_counts.get(bssid, 0)
                })

    except Exception as e:
        print(f"[-] CSV Parse Error: {e}")

    return networks, clients


# ================= 任务逻辑 =================
def run_scan(iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/scan"
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    # 关键参数：--band abg (支持5G)
    cmd = ["timeout", "15s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv", mon]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    nets, _ = parse_airodump_csv(f"{prefix}-01.csv")
    return nets


def run_monitor(task_type, params, iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/mon"
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    # 锁定信道
    os.system(f"iwconfig {mon} channel {params['channel']}")

    cmd = [
        "airodump-ng",
        "--bssid", params['bssid'],
        "--channel", str(params['channel']),
        "--write", prefix,
        "--output-format", "csv",
        mon
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"

    try:
        while True:
            # 检查任务是否还在
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=2).json()
                if res.get("task") != "monitor_target": break
            except:
                pass

            # 解析并回传
            if os.path.exists(f"{prefix}-01.csv"):
                _, clients = parse_airodump_csv(f"{prefix}-01.csv")
                # 只保留目标客户端
                target_clients = [c for c in clients if c['bssid'] == params['bssid']]
                if target_clients:
                    requests.post(f"{base_url}/callback", json={"type": "monitor_update", "data": target_clients})

            time.sleep(2)
    finally:
        proc.terminate()


# ================= 主入口 =================
if __name__ == "__main__":
    try:
        base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"
        print(f"[*] Agent Started. C2: {base_url}")

        last_reg = 0
        while True:
            # 注册网卡
            if time.time() - last_reg > 5:
                requests.post(f"{base_url}/register_agent", json={"interfaces": get_interfaces()})
                last_reg = time.time()

            # 心跳
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=5).json()
                task = res.get("task")

                if task == "scan":
                    nets = run_scan(res["params"]["interface"])
                    requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets})

                elif task == "monitor_target":
                    run_monitor(task, res["params"], res["params"]["interface"])

            except Exception as e:
                # print(f"Connect Error: {e}")
                pass

            time.sleep(HEARTBEAT_INTERVAL)

    except Exception as e:
        # 严重错误写入日志
        with open("/tmp/agent_error.log", "w") as f:
            f.write(traceback.format_exc())