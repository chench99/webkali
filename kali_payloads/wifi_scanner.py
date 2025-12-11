import sys
import subprocess
import csv
import time
import os
import json

# === 默认配置 ===
INTERFACE = "wlan0"
OUTPUT_PREFIX = "/tmp/scan_results"


def get_current_mode(iface):
    try:
        output = subprocess.getoutput(f"iwconfig {iface} 2>/dev/null")
        if "Mode:Monitor" in output: return "monitor"
        return "managed"
    except:
        return "unknown"


def enable_monitor_mode(iface):
    print(f"[*] Checking interface: {iface}...")
    if not os.path.exists(f"/sys/class/net/{iface}"):
        if os.path.exists(f"/sys/class/net/{iface}mon"): return f"{iface}mon"

    if get_current_mode(iface) == "monitor": return iface

    print(f"[*] Enabling monitor mode on {iface}...")
    os.system("killall wpa_supplicant 2>/dev/null")
    os.system(f"airmon-ng start {iface} > /dev/null 2>&1")

    mon_iface = f"{iface}mon"
    if os.path.exists(f"/sys/class/net/{mon_iface}"): return mon_iface
    return iface


def start_scan():
    target_iface = enable_monitor_mode(INTERFACE)
    os.system("killall airodump-ng 2>/dev/null")
    os.system(f"rm {OUTPUT_PREFIX}* 2>/dev/null")

    # 启动扫描 (全频段)
    print(f"[*] Starting scan on: {target_iface}...")
    cmd = f"airodump-ng {target_iface} --band abg --write {OUTPUT_PREFIX} --output-format csv --write-interval 1 > /dev/null 2>&1 &"
    os.system(cmd)

    print(json.dumps({"status": "started", "interface": target_iface}))
    sys.stdout.flush()


def parse_loop():
    csv_file = f"{OUTPUT_PREFIX}-01.csv"
    for i in range(10):
        if os.path.exists(csv_file): break
        time.sleep(1)

    while True:
        if os.path.exists(csv_file):
            aps = {}
            clients_count = {}

            try:
                with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.readlines()

                section = "AP"  # 标记当前读的是 AP 还是 Client

                for line in content:
                    line = line.strip()
                    if not line: continue

                    if line.startswith("Station MAC"):
                        section = "CLIENT"
                        continue
                    if line.startswith("BSSID"):
                        section = "AP"
                        continue

                    parts = [p.strip() for p in line.split(',')]

                    if section == "AP":
                        if len(parts) < 14: continue
                        bssid = parts[0]
                        # 存储 AP 信息
                        aps[bssid] = {
                            "bssid": bssid,
                            "channel": parts[3],
                            "encryption": parts[5],
                            "signal": parts[8],
                            "ssid": parts[13],
                            "clients": 0,  # 初始化
                            "score": 0  # 抓包成功率评分
                        }

                    elif section == "CLIENT":
                        if len(parts) < 6: continue
                        # parts[0] = Client MAC, parts[5] = BSSID (connected AP)
                        client_mac = parts[0]
                        ap_bssid = parts[5]

                        # 统计连接数 (过滤掉未连接的)
                        if ap_bssid in aps and "not associated" not in ap_bssid:
                            aps[ap_bssid]["clients"] += 1

                # === 转换成列表并计算评分 ===
                result_list = []
                for bssid, info in aps.items():
                    # 计算抓包成功率/推荐度 (0-100)
                    # 逻辑：有人连(权重高) + 信号好(权重中) + 加密是WPA(权重低)
                    score = 0

                    # 1. 在线用户加分 (最重要，没人连抓不到包)
                    if info["clients"] > 0: score += 50
                    if info["clients"] > 3: score += 20

                    # 2. 信号加分
                    try:
                        sig = int(info["signal"])
                        if sig > -60:
                            score += 20
                        elif sig > -75:
                            score += 10
                    except:
                        pass

                    # 3. 活跃度加分 (通过 Power 变动，这里简化处理)

                    info["score"] = min(score, 100)
                    result_list.append(info)

                print(json.dumps({"networks": result_list}))
                sys.stdout.flush()

            except Exception:
                pass
        time.sleep(1.5)


if __name__ == "__main__":
    if len(sys.argv) > 2: INTERFACE = sys.argv[2]
    if len(sys.argv) > 1:
        if sys.argv[1] == "scan":
            start_scan()
            parse_loop()
        elif sys.argv[1] == "kill":
            os.system("killall airodump-ng 2>/dev/null")
            print(json.dumps({"status": "stopped"}))
    else:
        print("Usage: python3 wifi_scanner.py <scan|kill> [interface]")