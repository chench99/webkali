import subprocess
import time
import requests
import os
import csv
import glob
import sys
import traceback

# ================= 配置区域 =================
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

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
    print(f"[*] 启用监听模式: {iface}")
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")
    if check_monitor_mode(iface): return iface
    run_cmd("airmon-ng check kill; airmon-ng start " + iface)
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
            if "Station MAC" in line and "First time seen" in line:
                is_client_section = True;
                continue
            (client_lines if is_client_section else ap_lines).append(line)

        # 1. 解析客户端
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
                    "mac": st_mac,
                    "bssid": bssid,
                    "signal": int(pwr) if pwr.lstrip('-').isdigit() else -100,
                    "packets": int(row[4].strip()) if row[4].strip().isdigit() else 0
                })

        # 2. 解析 AP
        start = -1
        for i, l in enumerate(ap_lines):
            if l.startswith("BSSID"): start = i; break

        if start != -1:
            reader = csv.reader(ap_lines[start + 1:])
            for row in reader:
                if len(row) < 14: continue
                bssid = row[0].strip().upper()
                networks.append({
                    "bssid": bssid,
                    "ssid": row[13].strip() or "<Hidden>",
                    "channel": int(row[3].strip()) if row[3].strip().isdigit() else 0,
                    "signal": int(row[8].strip()) if row[8].strip().lstrip('-').isdigit() else -100,
                    "encryption": row[5].strip(),
                    "vendor": "Unknown",  # 预留字段
                    "client_count": client_counts.get(bssid, 0)
                })
    except Exception as e:
        print(f"[-] Parse Error: {e}")

    return networks, clients


# ================= 主循环 =================
def main():
    base_url = f"http://{get_c2_ip()}:{PORT}/api/v1/wifi"
    print(f"[*] Agent Started. C2: {base_url}")

    last_reg = 0
    while True:
        try:
            if time.time() - last_reg > 5:
                requests.post(f"{base_url}/register_agent", json={"interfaces": get_interfaces()})
                last_reg = time.time()

            res = requests.get(f"{base_url}/agent/heartbeat", timeout=5).json()
            task = res.get("task")

            if task == "scan":
                iface = ensure_monitor_mode(res["params"]["interface"])
                prefix = f"{TMP_DIR}/scan"
                for f in glob.glob(f"{prefix}*"): os.remove(f)

                # 5G Support
                cmd = ["timeout", "15s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv",
                       iface]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                nets, _ = parse_airodump_csv(f"{prefix}-01.csv")
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets})

            elif task == "monitor_target":
                iface = ensure_monitor_mode(res["params"]["interface"])
                bssid = res["params"]["bssid"].upper()
                ch = str(res["params"]["channel"])
                prefix = f"{TMP_DIR}/mon"
                for f in glob.glob(f"{prefix}*"): os.remove(f)

                os.system(f"iwconfig {iface} channel {ch}")
                proc = subprocess.Popen(
                    ["airodump-ng", "--bssid", bssid, "--channel", ch, "--write", prefix, "--output-format", "csv",
                     iface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                try:
                    while True:
                        if requests.get(f"{base_url}/agent/heartbeat", timeout=2).json().get(
                            "task") != "monitor_target": break
                        if os.path.exists(f"{prefix}-01.csv"):
                            _, clients = parse_airodump_csv(f"{prefix}-01.csv")
                            target_clients = [c for c in clients if c['bssid'] == bssid]
                            if target_clients:
                                requests.post(f"{base_url}/callback",
                                              json={"type": "monitor_update", "data": target_clients})
                        time.sleep(2)
                finally:
                    proc.terminate()
                    os.system("killall airodump-ng")

        except Exception:
            pass
        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()