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
# 这个变量会被后端自动替换注入，请保持为空字符串
FIXED_C2_IP = ""
PORT = "8001"
HEARTBEAT_INTERVAL = 3
TMP_DIR = "/tmp/kali_c2_scan"

# 1. 启动标记与目录初始化
if not os.path.exists(TMP_DIR): os.makedirs(TMP_DIR)
os.system(f"touch {TMP_DIR}/agent_started.lock")


# ================= 日志函数 =================
def log(msg):
    """同时输出到控制台和日志文件"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    try:
        with open(f"{TMP_DIR}/agent.log", "a") as f:
            f.write(formatted_msg + "\n")
    except:
        pass


# ================= 核心工具函数 =================
def get_c2_ip():
    """获取 C2 服务器 IP"""
    # 1. 如果后端注入了固定 IP，直接使用
    if FIXED_C2_IP:
        return FIXED_C2_IP

    # 2. 备用：尝试获取默认网关 IP (通常是 Host 的 IP)
    try:
        ip = os.popen("ip route show | grep default | awk '{print $3}'").read().strip()
        if ip: return ip
    except:
        pass

    return "127.0.0.1"


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except:
        return ""


def check_monitor_mode(iface):
    """检查网卡是否已处于监听模式"""
    try:
        output = run_cmd(f"iw dev {iface} info")
        return "type monitor" in output
    except:
        return False


def ensure_monitor_mode(iface):
    """强制开启监听模式"""
    if check_monitor_mode(iface): return iface

    log(f"正在将网卡 {iface} 切换为监听模式...")

    # 尝试方法 1: iw 命令
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")

    if check_monitor_mode(iface): return iface

    # 尝试方法 2: airmon-ng (会创建 mon0)
    run_cmd("airmon-ng check kill")
    run_cmd(f"airmon-ng start {iface}")

    # 检查可能的名称变化
    mon_iface = f"{iface}mon"
    if os.path.exists(f"/sys/class/net/{mon_iface}"):
        return mon_iface

    return iface


def get_driver_name(iface):
    """获取网卡驱动名称 (用于前端显示)"""
    try:
        if shutil.which("ethtool"):
            res = run_cmd(f"ethtool -i {iface}")
            for line in res.splitlines():
                if "driver:" in line:
                    return line.split(":")[1].strip()

        # 备用方法: sysfs
        path = f"/sys/class/net/{iface}/device/driver"
        if os.path.exists(path):
            return os.path.basename(os.path.realpath(path))
    except:
        pass
    return "Generic"


def get_interfaces():
    """获取所有无线网卡信息"""
    ifaces = []
    sys_net = "/sys/class/net"
    if not os.path.exists(sys_net): return []

    for i in os.listdir(sys_net):
        # 排除回环和非无线接口
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


# ================= CSV 解析逻辑 =================
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

        # 1. 统计客户端数量
        if client_lines:
            reader = csv.reader(client_lines)
            for row in reader:
                if len(row) < 6: continue
                bssid = row[5].strip().upper()
                if bssid and "NOT ASSOCIATED" not in bssid:
                    client_counts[bssid] = client_counts.get(bssid, 0) + 1

                # 收集客户端详细信息 (用于 Monitor 模式)
                clients.append({
                    "mac": row[0].strip().upper(),
                    "bssid": bssid,
                    "signal": int(row[3].strip()) if row[3].strip().lstrip('-').isdigit() else -100,
                    "packets": int(row[4].strip()) if row[4].strip().isdigit() else 0
                })

        # 2. 解析 AP 信息
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
                    "vendor": "Unknown",
                    "client_count": client_counts.get(bssid, 0)
                })
    except Exception as e:
        log(f"CSV 解析错误: {e}")

    return networks, clients


# ================= 任务执行逻辑 =================
def run_scan(iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/scan"

    # 清理旧文件
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    # 执行扫描 (15秒)
    cmd = ["timeout", "15s", "airodump-ng", "--band", "abg", "--write", prefix, "--output-format", "csv", mon]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 解析结果
    nets, _ = parse_airodump_csv(f"{prefix}-01.csv")
    return nets


def start_monitor_process(params, iface):
    mon = ensure_monitor_mode(iface)
    prefix = f"{TMP_DIR}/mon"

    # 清理旧文件
    for f in glob.glob(f"{prefix}*"): os.remove(f)

    target_bssid = params['bssid']
    target_ch = str(params['channel'])

    # 锁定信道
    os.system(f"iwconfig {mon} channel {target_ch}")

    # 启动后台监听
    cmd = ["airodump-ng", "--bssid", target_bssid, "--channel", target_ch, "--write", prefix, "--output-format", "csv",
           mon]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, prefix


# ================= 主循环 (守护进程) =================
if __name__ == "__main__":
    c2_ip = get_c2_ip()
    base_url = f"http://{c2_ip}:{PORT}/api/v1/wifi"

    log(f"[*] Agent v2.0 启动")
    log(f"[*] C2 服务器目标: {base_url}")

    current_proc = None
    monitor_prefix = ""

    while True:
        try:
            # === 1. 注册网卡 (心跳) ===
            try:
                # 增加 timeout 防止卡死
                requests.post(f"{base_url}/register_agent", json={"interfaces": get_interfaces()}, timeout=3)
            except requests.exceptions.RequestException:
                # 连接失败是常态（如网络断开），记录日志但不退出
                log(f"[!] 无法连接 C2 ({base_url})，正在重试...")
                time.sleep(HEARTBEAT_INTERVAL)
                continue

            # === 2. 获取任务 ===
            try:
                res = requests.get(f"{base_url}/agent/heartbeat", timeout=3)
                if res.status_code != 200:
                    time.sleep(HEARTBEAT_INTERVAL)
                    continue

                data = res.json()
                task = data.get("task")
                params = data.get("params", {})

            except Exception as e:
                log(f"[!] 获取任务失败: {e}")
                time.sleep(HEARTBEAT_INTERVAL)
                continue

            # === 3. 任务处理 ===

            # 如果任务改变，停止之前的后台进程
            if task != "monitor_target" and current_proc:
                log("[*] 停止后台监听任务")
                current_proc.terminate()
                current_proc = None
                os.system("killall airodump-ng")

            # --- 任务 A: 扫描 ---
            if task == "scan":
                log("[*] 执行全频段扫描...")
                nets = run_scan(params.get("interface", "wlan0"))
                log(f"[*] 扫描完成，发现 {len(nets)} 个热点")
                requests.post(f"{base_url}/callback", json={"type": "scan_result", "networks": nets}, timeout=5)

            # --- 任务 B: 监听 (持续运行) ---
            elif task == "monitor_target":
                # 如果没启动，就启动它
                if not current_proc:
                    log(f"[*] 开始监听目标: {params.get('bssid')}")
                    current_proc, monitor_prefix = start_monitor_process(params, params.get("interface", "wlan0"))
                else:
                    # 如果已经在运行，读取实时数据并回传
                    csv_file = f"{monitor_prefix}-01.csv"
                    if os.path.exists(csv_file):
                        _, all_clients = parse_airodump_csv(csv_file)
                        # 只过滤出目标热点的客户端
                        target = params.get('bssid', '').upper()
                        target_clients = [c for c in all_clients if c['bssid'] == target]

                        if target_clients:
                            requests.post(f"{base_url}/callback",
                                          json={"type": "monitor_update", "data": target_clients},
                                          timeout=2)

        except KeyboardInterrupt:
            log("[!] 用户终止脚本")
            if current_proc: current_proc.terminate()
            break

        except Exception as fatal_error:
            # 捕获所有未预料的错误，防止脚本崩溃退出
            log(f"[CRITICAL] 发生严重错误: {fatal_error}")
            traceback.print_exc()
            time.sleep(5)  # 出错后多睡一会

        time.sleep(HEARTBEAT_INTERVAL)