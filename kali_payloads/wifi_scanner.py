import subprocess
import time
import requests
import os
import csv
import glob
import sys
import socket
import re
import shutil

# ================= 配置区域 =================
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 2
TMP_DIR = "/tmp/kali_c2_scan"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 基础工具函数 =================

def get_c2_ip():
    """智能探测 C2 服务器 IP"""
    if FIXED_C2_IP: return FIXED_C2_IP
    try:
        # 探测默认网关
        gateway = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if gateway: return gateway
    except:
        pass
    return "127.0.0.1"


def run_cmd(cmd):
    """执行 Shell 命令并返回输出"""
    try:
        # 使用 check_output 获取输出
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def get_driver_name(iface):
    """获取网卡驱动名称"""
    try:
        driver = subprocess.check_output(f"ethtool -i {iface} | grep driver", shell=True).decode().split(":")[1].strip()
    except:
        driver = "Unknown"
    return driver


def check_monitor_mode(iface):
    """检查指定网卡是否已经是监听模式"""
    try:
        iw_info = run_cmd(f"iw dev {iface} info")
        if "type monitor" in iw_info:
            return True
    except:
        pass
    return False


# ================= 核心：智能网卡管理 =================

def get_smart_interfaces():
    """获取网卡列表"""
    interfaces = []
    sys_cls_net = "/sys/class/net"
    if not os.path.exists(sys_cls_net): return []

    for iface in os.listdir(sys_cls_net):
        if iface == "lo" or iface.startswith("eth") or iface.startswith("docker"):
            continue

        # 简单判断是否为无线 (存在 wireless 目录或 phy80211)
        if not os.path.exists(f"{sys_cls_net}/{iface}/wireless") and not os.path.exists(
                f"{sys_cls_net}/{iface}/phy80211"):
            # 再试一次 iw
            if not run_cmd(f"iw dev {iface} info"):
                continue

        driver = get_driver_name(iface)
        mode = "Monitor" if check_monitor_mode(iface) else "Managed"

        display_name = f"{driver} ({iface})"
        if mode == "Monitor":
            display_name = f"🔥 {driver} ({iface})"

        interfaces.append({
            "name": iface,
            "display": display_name,
            "mode": mode,
            "is_wireless": True
        })

    return interfaces


def ensure_monitor_mode(original_iface):
    """确保进入监听模式，并返回最终的接口名"""
    print(f"[*] 检查网卡模式: {original_iface}")

    # 1. 如果已经是监听模式
    if check_monitor_mode(original_iface):
        return original_iface

    # 2. 尝试开启
    print(f"[*] 正在开启监听模式: {original_iface}")
    run_cmd("airmon-ng check kill")  # 杀掉 NetworkManager 防止干扰
    run_cmd(f"airmon-ng start {original_iface}")

    # 3. 智能寻找新名称 (通常是 wlan0mon)
    # 重新遍历所有网卡，找一个同驱动且是 Monitor 模式的
    current_ifaces = os.listdir("/sys/class/net")
    for name in current_ifaces:
        # 匹配名字规则
        if name.startswith(original_iface) or "mon" in name:
            if check_monitor_mode(name):
                print(f"[+] 监听模式已开启，新接口: {name}")
                return name

    # 兜底：随便找一个 monitor 接口
    for name in current_ifaces:
        if check_monitor_mode(name):
            return name

    return original_iface


# ================= 业务功能函数 =================

def parse_airodump_csv(csv_path):
    """解析 CSV 数据"""
    clients = []
    try:
        if not os.path.exists(csv_path): return []

        # 复制一份读取，防止文件被占用
        tmp_read = csv_path + ".read"
        shutil.copy(csv_path, tmp_read)

        with open(tmp_read, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        start_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("Station MAC"):
                start_idx = i
                break

        if start_idx != -1:
            reader = csv.reader(lines[start_idx + 1:])
            for row in reader:
                if len(row) < 6: continue
                # 过滤掉不完整的行
                mac = row[0].strip()
                if len(mac) != 17: continue

                clients.append({
                    'mac': mac,
                    'power': row[3].strip(),
                    'packets': row[4].strip(),
                    'bssid': row[5].strip(),
                    'probed': row[6].strip() if len(row) > 6 else ""
                })
    except:
        pass
    return clients


def perform_scan_airodump(iface):
    """
    普通扫描 (15秒)
    增加了 --band abg 参数以支持 5GHz
    """
    networks = []
    print(f"[*] 执行双频扫描 (15s): {iface}")

    prefix = f"{TMP_DIR}/scan_result"

    # ⚠️ 关键修改：增加 --band abg，时间延长到 15s
    cmd = [
        "timeout", "15s",
        "airodump-ng",
        "--band", "abg",  # 同时扫描 2.4G 和 5G
        "--write", prefix,
        "--output-format", "csv",
        iface
    ]

    # 运行扫描
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    csv_file = f"{prefix}-01.csv"
    if os.path.exists(csv_file):
        try:
            with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or len(row) < 14: continue
                    if row[0].strip() == "BSSID": continue
                    if row[0].strip() == "Station MAC": break

                    ssid = row[13].strip()
                    if not ssid: ssid = "<Hidden>"

                    networks.append({
                        "ssid": ssid,
                        "bssid": row[0].strip(),
                        "channel": int(row[3].strip()),
                        "signal": int(row[8].strip()),
                        "encryption": row[5].strip(),
                        "vendor": "Unknown",
                        "band": "5G" if int(row[3].strip()) > 14 else "2.4G"  # 简单判断频段
                    })
        except Exception as e:
            print(f"[-] 解析失败: {e}")

    # 清理
    for f in glob.glob(f"{prefix}*"):
        try:
            os.remove(f)
        except:
            pass

    return networks


def run_monitor_task(task_type, params, original_iface):
    """执行持续监听任务 (Deep Scan / Target Monitor)"""

    # 1. 确保监听模式
    mon_iface = ensure_monitor_mode(original_iface)

    # 清理旧文件
    for f in glob.glob(f"{TMP_DIR}/*"):
        try:
            os.remove(f)
        except:
            pass

    prefix = f"{TMP_DIR}/output"

    # 基础命令
    cmd = ["airodump-ng", "--write", prefix, "--output-format", "csv"]

    if task_type == 'monitor_target':
        bssid = params.get('bssid')
        channel = params.get('channel')
        # 先切信道，防止 airodump 还没启动就漏包
        run_cmd(f"iwconfig {mon_iface} channel {channel}")
        cmd.extend(["--bssid", bssid, "--channel", str(channel)])
        print(f"[*] 锁定监听: {bssid} (CH {channel})")

    elif task_type == 'deep_scan':
        print(f"[*] 启动全网深度扫描 (双频)")
        # ⚠️ 关键修改：深度扫描必须加 --band abg 否则可能扫不到 5G
        # 并且不指定频道，让它自动跳频
        cmd.extend(["--band", "abg"])

    cmd.append(mon_iface)

    # 启动子进程
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csv_file = f"{prefix}-01.csv"

    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    try:
        while True:
            # 检查 C2 停止指令
            try:
                r = requests.get(f"{base_url}/agent/heartbeat", timeout=2)
                remote_task = r.json().get("task")
                if remote_task == "idle" or remote_task != task_type:
                    print("[*] 任务结束")
                    break
            except:
                pass

            # 解析并回传
            clients = parse_airodump_csv(csv_file)
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
        # 深度扫描结束后，建议杀掉 airmon-ng 恢复网络 (可选，这里先不恢复以免频繁切换)
        # run_cmd(f"airmon-ng stop {mon_iface}")


def main():
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"
    os.environ['no_proxy'] = '*'

    print(f"[*] Kali Smart Agent v6.1 (Dual-Band) -> {base_url}")

    # 注册上线
    try:
        ifaces = get_smart_interfaces()
        requests.post(f"{base_url}/register_agent", json={"interfaces": ifaces}, timeout=5)
    except:
        pass

    while True:
        try:
            r = requests.get(f"{base_url}/agent/heartbeat", timeout=5)
            data = r.json()
            task = data.get("task")
            params = data.get("params", {})

            # 只有空闲时才刷新网卡状态，防止扫描中被打断
            if task == "idle":
                current_ifaces = get_smart_interfaces()
                if current_ifaces:
                    requests.post(f"{base_url}/register_agent", json={"interfaces": current_ifaces})

            if task == "scan":
                iface = params.get("interface")
                mon_iface = ensure_monitor_mode(iface)
                res = perform_scan_airodump(mon_iface)
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": res})

            elif task in ["monitor_target", "deep_scan"]:
                iface = params.get("interface")
                # 阻塞执行直到任务结束
                run_monitor_task(task, params, iface)

            elif task == "idle":
                pass

        except Exception as e:
            pass

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()