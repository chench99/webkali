import sys
import time
import subprocess
import os
import csv
import json
import glob

# ================= 配置 =================
TMP_PREFIX = "/tmp/wifi_scan"
CSV_FILE = f"{TMP_PREFIX}-01.csv"
SCAN_DURATION = 10  # 扫描持续时间(秒)，越长发现设备越多
# =======================================

def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    except:
        pass

def get_actual_iface_name():
    """动态获取网卡名"""
    if os.path.exists("/sys/class/net/wlan0mon"): return "wlan0mon"
    ifaces = os.listdir('/sys/class/net')
    for iface in ifaces:
        if iface.startswith("eth") or iface.startswith("ens") or iface == "lo": continue
        return iface
    return "wlan0"

def parse_airodump_csv():
    """解析 CSV，提取 AP 和 Client 的关系"""
    networks = {} # Key: BSSID, Value: NetworkDict
    clients = []  # List of tuples (ClientMAC, BSSID)

    if not os.path.exists(CSV_FILE):
        return []

    with open(CSV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    # 分割 AP 部分和 Station 部分
    station_start_index = -1
    for i, line in enumerate(lines):
        if "Station MAC" in line:
            station_start_index = i
            break
    
    # 1. 解析 AP (路由器)
    # AP 数据通常在 header 和 Station 之间
    ap_lines = lines[1:station_start_index] if station_start_index != -1 else lines[1:]
    
    for line in ap_lines:
        parts = line.split(',')
        if len(parts) < 14: continue
        
        bssid = parts[0].strip()
        channel = parts[3].strip()
        signal = parts[8].strip() # Power
        ssid = parts[13].strip()
        privacy = parts[5].strip()
        
        # 过滤掉无效数据
        if not bssid or len(bssid) != 17: continue
        
        networks[bssid] = {
            "ssid": ssid if ssid else "(Hidden)",
            "bssid": bssid,
            "channel": int(channel) if channel.isdigit() else 1,
            "signal": int(signal) if signal.lstrip('-').isdigit() else -100,
            "encryption": privacy.strip(),
            "clients": [] # 初始化客户端列表
        }

    # 2. 解析 Clients (连接的设备)
    if station_start_index != -1:
        client_lines = lines[station_start_index+1:]
        for line in client_lines:
            parts = line.split(',')
            if len(parts) < 6: continue
            
            client_mac = parts[0].strip()
            bssid = parts[5].strip() # 客户端连接的 BSSID
            
            # 如果这个 BSSID 在我们要找的 AP 列表里
            if bssid in networks:
                # 去重添加
                if client_mac not in networks[bssid]["clients"]:
                    networks[bssid]["clients"].append(client_mac)

    return list(networks.values())

def main():
    # 1. 准备环境
    iface = get_actual_iface_name()
    
    # 保护 SSH
    os.system(f"nmcli device set {iface} managed no 2>/dev/null")
    os.system("killall wpa_supplicant 2>/dev/null")
    
    # 开启监听
    run_cmd(f"airmon-ng start {iface}")
    mon_iface = get_actual_iface_name()
    
    # 2. 开始扫描
    os.system(f"rm -f {TMP_PREFIX}*")
    
    # 启动 airodump 后台运行
    # --output-format csv 生成我们需要的文件
    cmd = [
        "airodump-ng",
        "--output-format", "csv",
        "-w", TMP_PREFIX,
        mon_iface
    ]
    
    with open(os.devnull, 'w') as devnull:
        proc = subprocess.Popen(cmd, stdout=devnull, stderr=devnull)
        
    # 等待扫描 (这是必须的，否则抓不到客户端)
    time.sleep(SCAN_DURATION)
    
    # 停止扫描
    proc.terminate()
    try: proc.wait(timeout=1)
    except: proc.kill()
    os.system("killall -9 airodump-ng 2>/dev/null")
    
    # 3. 解析结果并输出 JSON
    results = parse_airodump_csv()
    
    # 打印 JSON 给后端读取
    print(json.dumps(results))

if __name__ == "__main__":
    main()