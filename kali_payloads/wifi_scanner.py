import subprocess
import json
import time
import requests
import os
import csv
import glob
import sys
import shutil

# 配置 (自动注入 IP)
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

# 确保临时目录存在
if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


def get_c2_url():
    """获取 C2 地址"""
    c2_ip = FIXED_C2_IP
    if not c2_ip:
        # 简单获取网关 IP 逻辑
        try:
            c2_ip = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        except:
            c2_ip = "127.0.0.1"
    return f"http://{c2_ip}:{PORT}/api/v1/wifi"


BASE_URL = get_c2_url()


def clean_tmp_files():
    for f in glob.glob(f"{TMP_DIR}/*"):
        try:
            os.remove(f)
        except:
            pass


def parse_airodump_csv(csv_path):
    """解析 airodump CSV 中的 Station 部分"""
    clients = []
    try:
        if not os.path.exists(csv_path): return []

        # 为了不锁定文件，复制一份读
        tmp_read = csv_path + ".read"
        shutil.copy(csv_path, tmp_read)

        with open(tmp_read, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # 找到 Station MAC 开始的行
        start_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("Station MAC"):
                start_idx = i
                break

        if start_idx != -1:
            reader = csv.reader(lines[start_idx + 1:])
            for row in reader:
                if len(row) < 6: continue
                # CSV 格式: MAC, First, Last, Power, # packets, BSSID, Probed ESSIDs
                clients.append({
                    'mac': row[0].strip(),
                    'power': row[3].strip(),
                    'packets': row[4].strip(),
                    'bssid': row[5].strip(),
                    'probed': row[6].strip() if len(row) > 6 else ""
                })
    except Exception as e:
        pass
    return clients


def run_monitor_task(task_type, params, iface="wlan0"):
    """执行监听任务 (Targeted 或 Deep)"""
    clean_tmp_files()

    # 1. 准备命令
    prefix = f"{TMP_DIR}/output"
    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]

    if task_type == 'monitor_target':
        bssid = params.get('bssid')
        channel = params.get('channel')
        cmd.extend(["--bssid", bssid, "--channel", str(channel)])
        print(f"[*] 启动定向监听: {bssid} on CH {channel}")

    elif task_type == 'deep_scan':
        print(f"[*] 启动深度全网扫描 (自动跳频)")
        # 深度扫描不加 bssid 限制
        # 可以写个脚本控制 channel hopping，或者依赖 airodump 默认跳频

    cmd.append(iface)

    # 2. 启动进程
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. 循环回传数据
    csv_file = f"{prefix}-01.csv"
    try:
        while True:
            # 检查 C2 是否叫停
            try:
                r = requests.get(f"{BASE_URL}/agent/heartbeat", timeout=2)
                if r.json().get("task") == "idle":
                    print("[*] 收到停止指令")
                    break
                # 如果任务类型变了，也退出，让主循环重启新任务
                if r.json().get("task") != task_type:
                    break
            except:
                pass

            # 解析数据
            clients = parse_airodump_csv(csv_file)
            if clients:
                # 回传
                update_type = 'monitor_update' if task_type == 'monitor_target' else 'deep_update'
                # 对于 deep scan，我们要补上当前信道信息（airodump csv里可能不准，简单处理）

                requests.post(f"{BASE_URL}/callback", json={
                    "type": update_type,
                    "data": clients
                })
                # print(f"[+] 回传 {len(clients)} 条客户端数据")

            time.sleep(2)

    finally:
        proc.terminate()
        proc.wait()
        clean_tmp_files()
        print("[*] 监听进程已结束")


def main():
    print(f"[*] Kali Agent v5.1 (Deep Scan Enabled) connecting to {BASE_URL}")

    # 注册上线 (略，沿用旧代码)

    current_proc = None

    while True:
        try:
            r = requests.get(f"{BASE_URL}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            if task == "scan":
                # ... (原有的普通扫描逻辑) ...
                pass

            elif task == "monitor_target":
                # 阻塞式运行，直到后端发指令停止
                run_monitor_task("monitor_target", params)

            elif task == "deep_scan":
                # 阻塞式运行
                run_monitor_task("deep_scan", params)

            elif task == "idle":
                pass

        except Exception as e:
            print(f"[!] Error: {e}")
            time.sleep(2)

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()