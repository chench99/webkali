import subprocess
import time
import requests
import os
import csv
import glob

# ================= 配置区域 =================
FIXED_C2_IP = ""  # 部署时会自动注入
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"
if not os.path.exists(TMP_DIR): os.makedirs(TMP_DIR)


# ================= 工具函数 =================
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
        if "type monitor" in run_cmd(f"iw dev {iface} info"): return True
    except:
        pass
    return False


def ensure_monitor_mode(iface):
    if check_monitor_mode(iface): return iface
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {iface}")
    # 查找新接口名
    for name in os.listdir("/sys/class/net"):
        if (name.startswith(iface) or "mon" in name) and check_monitor_mode(name):
            return name
    return iface


def cleanup_files(prefix):
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass


# ================= 核心：网卡识别 (修复版) =================
def get_smart_interfaces():
    interfaces = []
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []

    for iface in os.listdir(sys_cls_net):
        if iface in ["lo"] or iface.startswith(("eth", "docker", "veth", "br-")): continue

        # [双重检查] 1. 文件系统检查 2. iw 命令兜底
        is_wireless = os.path.exists(f"{sys_cls_net}/{iface}/wireless") or os.path.exists(
            f"{sys_cls_net}/{iface}/phy80211")
        if not is_wireless:
            if "wiphy" in run_cmd(f"iw dev {iface} info"): is_wireless = True

        if not is_wireless: continue

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


# ================= 解析逻辑 (双频 + 客户端) =================
def parse_csv_dual(csv_path):
    networks = []
    clients = []
    client_counts = {}

    if not os.path.exists(csv_path): return [], []
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        is_station = False
        ap_lines, station_lines = [], []

        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith("Station MAC"):
                is_station = True;
                continue
            (station_lines if is_station else ap_lines).append(line)

        # 解析 Clients
        if station_lines:
            reader = csv.reader(station_lines)
            for row in reader:
                if len(row) < 6: continue
                bssid = row[5].strip()
                if bssid and "not associated" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1
                clients.append(
                    {"mac": row[0].strip(), "power": row[3].strip(), "packets": row[4].strip(), "bssid": bssid})

        # 解析 APs
        if len(ap_lines) > 0:
            start_idx = -1
            for i, l in enumerate(ap_lines):
                if l.startswith("BSSID"): start_idx = i; break

            if start_idx != -1:
                reader = csv.reader(ap_lines[start_idx + 1:])
                for row in reader:
                    if len(row) < 14: continue
                    ch = int(row[3].strip()) if row[3].strip().isdigit() else 0
                    networks.append({
                        "bssid": row[0].strip(),
                        "ssid": row[13].strip() or "<Hidden>",
                        "channel": ch,
                        "signal": int(row[8].strip()) if row[8].strip().lstrip('-').isdigit() else -100,
                        "encryption": row[5].strip(),
                        "band": "5G" if ch > 14 else "2.4G",
                        "clientCount": client_counts.get(row[0].strip(), 0)
                    })
    except Exception as e:
        print(f"[-] CSV Error: {e}")
    return networks, clients


# ================= 任务执行 =================
def perform_scan(iface):
    print(f"[*] 扫描: {iface}")
    prefix = f"{TMP_DIR}/scan"
    cleanup_files(prefix)
    subprocess.run(
        ["timeout", "15s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv", iface],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nets, _ = parse_csv_dual(f"{prefix}-01.csv")
    cleanup_files(prefix)
    return nets


def run_monitor(task_type, params, iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/mon"
    cleanup_files(prefix)

    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]
    if task_type == 'monitor_target':
        cmd.extend(["--bssid", params['bssid'], "--channel", str(params['channel'])])
    else:
        cmd.extend(["--band", "abg"])  # deep scan
    cmd.append(mon)

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"

    try:
        while True:
            # Check Stop
            try:
                if requests.get(f"{base_url}/agent/heartbeat", timeout=2).json().get("task") != task_type: break
            except:
                pass

            # Update
            _, clients = parse_csv_dual(f"{prefix}-01.csv")
            if clients:
                try:
                    requests.post(f"{base_url}/callback", json={"type": "monitor_update", "data": clients})
                except:
                    pass
            time.sleep(2)
    finally:
        if proc: proc.terminate()
        cleanup_files(prefix)


# ================= 主程序 =================
def main():
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"
    print(f"[*] Agent Started -> {base_url}")

    last_reg = 0
    while True:
        try:
            # [关键] 定期注册网卡，防止后端重启后丢失状态
            if time.time() - last_reg > 5:
                ifaces = get_smart_interfaces()
                if ifaces:
                    requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=3)
                last_reg = time.time()

            # 心跳
            res = requests.get(f"{base_url}/agent/heartbeat", timeout=5).json()
            task = res.get("task")

            if task == "scan":
                nets = perform_scan(ensure_monitor_mode(res["params"]["interface"]))
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets})
            elif task in ["monitor_target", "deep_scan"]:
                run_monitor(task, res["params"], res["params"]["interface"])

        except Exception:
            time.sleep(2)
        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()