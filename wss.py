import re
import time
import gzip
import requests
import websocket
import threading
import logging
from datetime import datetime

from proto import dy_pb2


# ANSI转义码
RESET = "\033[0m" # 重置颜色
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"


class Room:
    def __init__(self, url):
        self.url = url
        self.ttwid = ''
        self.room_id = ''
        self.ws_connect = None

    def connect(self):
        """
        获取ttwid和房间ID，构建WebSocket URL，初始化WebSocket连接
        """
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
            "Cookie": "__ac_nonce=0638733a400869171be51"
        }
        response = requests.get(self.url, headers=headers)
        self.ttwid = response.cookies.get('ttwid')
        body = response.text
        match = re.search(r'roomId\\":\\"(\d+)\\"', body)
        if match:
            self.room_id = match.group(1)
        else:
            logging.error("No match found")
            return

        # 构建WebSocket URL
        ws_url = f"wss://webcast3-ws-web-lq.douyin.com/webcast/im/push/v2/?app_name=douyin_web&version_code=180800&webcast_sdk_version=1.3.0&update_version_code=1.3.0&compress=gzip&internal_ext=internal_src:dim|wss_push_room_id:{self.room_id}|wss_push_did:{self.ttwid}|dim_log_id:202302171547011A160A7BAA76660E13ED|fetch_time:1676620021641|seq:1|wss_info:0-1676620021641-0-0|wrds_kvs:WebcastRoomStatsMessage-1676620020691146024_WebcastRoomRankMessage-1676619972726895075_AudienceGiftSyncData-1676619980834317696_HighlightContainerSyncData-2&cursor=t-1676620021641_r-1_d-1_u-1_h-1&host=https://live.douyin.com&aid=6383&live_id=1&did_rule=3&debug=false&endpoint=live_pc&support_wrds=1&im_path=/webcast/im/fetch/&user_unique_id={self.ttwid}&device_platform=web&cookie_enabled=true&screen_width=1440&screen_height=900&browser_language=zh&browser_platform=MacIntel&browser_name=Mozilla&browser_version=5.0%20(Macintosh;%20Intel%20Mac%20OS%20X%2010_15_7)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/110.0.0.0%20Safari/537.36&browser_online=true&tz_name=Asia/Shanghai&identity=audience&room_id={self.room_id}&heartbeatDuration=0&signature=00000000"

        # 连接WebSocket
        self.ws_connect = websocket.create_connection(ws_url, header={"Cookie": f"ttwid={self.ttwid}"})
        self.read_thread = threading.Thread(target=self.read)
        self.read_thread.start()

        # 启动心跳包发送线程
        self.heartbeat_thread = threading.Thread(target=self.send_heartbeat)
        self.heartbeat_thread.start()

    def read(self):
        """
        负责持续接收消息，解压缩，反序列化
        """
        while True:
            data = self.ws_connect.recv()
            msg_pack = dy_pb2.PushFrame()
            msg_pack.ParseFromString(data)
            decompressed = gzip.decompress(msg_pack.payload)
            payload_package = dy_pb2.Response()
            payload_package.ParseFromString(decompressed)
            if payload_package.needAck:
                self.send_ack(msg_pack.logId, payload_package.internalExt)
            for msg in payload_package.messagesList:
                self.parse_message(msg)

    def send_ack(self, log_id, i_ext):
        """
        发送确认消息回服务器
        """
        ack_pack = dy_pb2.PushFrame(logId=log_id, payloadType=i_ext)
        data = ack_pack.SerializeToString()
        self.ws_connect.send(data, opcode=websocket.ABNF.OPCODE_BINARY)

    def parse_message(self, msg):
        """
        负责根据消息类型调用相应的解析函数
        """
        if msg.method == "WebcastMemberMessage":
            self.parse_member_msg(msg.payload)
        elif msg.method == "WebcastChatMessage":
            self.parse_chat_msg(msg.payload)
        elif msg.method == "WebcastLikeMessage":
            self.parse_like_msg(msg.payload)
        elif msg.method == "WebcastSocialMessage":
            self.parse_social_msg(msg.payload)
        elif msg.method == "WebcastGiftMessage":
            self.parse_gift_msg(msg.payload)
        else:
            # print(msg)
            pass

    def parse_member_msg(self, payload):
        """
        解析入场消息
        """
        try:
            member_msg = dy_pb2.MemberMessage()
            member_msg.ParseFromString(payload)
            user_name = member_msg.user.nickName
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [入场] {user_name} 来了")
        except Exception as e:
            logging.error(f"Error parsing member message: {e}")

    def parse_chat_msg(self, msg_payload):
        """
        解析聊天消息
        """
        try:
            chat_msg = dy_pb2.ChatMessage()
            chat_msg.ParseFromString(msg_payload)
            user_name = chat_msg.user.nickName
            message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [弹幕] {user_name} : {chat_msg.content}"
            print(f"{CYAN}{message}{RESET}")
        except Exception as e:
            logging.error(f"Error parsing chat message: {e}")

    def parse_like_msg(self, msg_payload):
        """
        解析点赞消息
        """
        try:
            like_msg = dy_pb2.LikeMessage()
            like_msg.ParseFromString(msg_payload)
            user_name = like_msg.user.nickName
            message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [点赞] {user_name} 点赞 * {like_msg.count}"
            print(f"{YELLOW}{message}{RESET}")
        except Exception as e:
            logging.error(f"Error parsing like message: {e}")

    def parse_social_msg(self, msg_payload):
        """
        解析关注消息
        """
        try:
            social_msg = dy_pb2.SocialMessage()
            social_msg.ParseFromString(msg_payload)
            user_name = social_msg.user.nickName
            message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [关注] {user_name} 关注了你"
            print(f"{RED}{message}{RESET}")
        except Exception as e:
            logging.error(f"Error parsing social message: {e}")

    def parse_gift_msg(self, msg_payload):
        """
        解析礼物消息
        """
        try:
            gift_msg = dy_pb2.GiftMessage()
            gift_msg.ParseFromString(msg_payload)
            user_name = gift_msg.user.nickName
            message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [礼物] {user_name} : {gift_msg.gift.name} * {gift_msg.comboCount}"
            print(f"{GREEN}{message}{RESET}")
        except Exception as e:
            logging.error(f"Error parsing gift message: {e}")

    def send_heartbeat(self):
        """
        定期发送心跳包以保持连接活跃
        """
        while True:
            try:
                ping_pack = dy_pb2.PushFrame(payloadType="bh")
                data = ping_pack.SerializeToString()
                self.ws_connect.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
                time.sleep(10)
            except Exception as e:
                logging.error(f"Heartbeat error: {e}")
                break  # 发生错误时退出循环

if __name__ == '__main__':
    room = Room("https://live.douyin.com/379931136059")
    room.connect()
