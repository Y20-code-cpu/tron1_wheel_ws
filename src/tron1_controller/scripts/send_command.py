#!/usr/bin/env python3
"""
TRON1 轮足机器人完整控制脚本
符合《TRON1 SDK开发指南》v1.6 规范
"""

import websocket
import json
import time
import sys
import argparse
import threading
import uuid
from enum import IntEnum


class LightEffect(IntEnum):
    STATIC_RED = 1
    STATIC_GREEN = 2
    STATIC_BLUE_Dark = 3
    STATIC_BLUE_Cambridge = 4
    STATIC_PURPLE = 5
    STATIC_YELLOW = 6
    STATIC_WHITE = 7

class TRON1Robot:
    SPEED_LIMIT_X = 3.0
    SPEED_LIMIT_Z = 1.5
    
    STATUS_MAP = {
        'DAMPING': ('🟡', '阻尼模式'),
        'STAND': ('🟢', '站立模式'),
        'WALK': ('🚶', '行走模式'),
        'SIT': ('💺', '蹲下模式'),
        'STAIR': ('🪜', '楼梯模式'),
        'ERROR_FALLOVER': ('🔴', '摔倒错误'),
        'RECOVER': ('🔄', '恢复中'),
        'ERROR_RECOVER': ('❌', '恢复失败')
    }
    
    def __init__(self, robot_ip, accid):
        self.robot_ip = robot_ip
        self.accid = accid
        self.ws = None
        self.running = False
        self.status_printed = False  
        self.latest_status = {}
        self.status_thread = None
        self.response_events = {}
        self.lock = threading.Lock()
        
    def _generate_guid(self):
        return str(uuid.uuid4())
    
    def connect(self):
        ws_url = f"ws://{self.robot_ip}:5000"
        try:
            self.ws = websocket.create_connection(ws_url, timeout=5)
            print(f"✅ 已连接到机器人: {ws_url}")
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def start_listener(self):
        if self.status_thread is None or not self.status_thread.is_alive():
            self.running = True
            self.status_printed = False  # 重置标记
            self.status_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self.status_thread.start()
    
    def stop_listener(self):
        self.running = False
        if self.status_thread:
            self.status_thread.join(timeout=2)
    
    def _listener_loop(self):
        while self.running and self.ws:
            try:
                self.ws.settimeout(0.5)
                response = self.ws.recv()
                if response and isinstance(response, str):
                    self._handle_message(response)
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException:
                break
            except Exception:
                break
    
    def _handle_message(self, message):
        if not message or not message.strip():
            return
        
        try:
            resp_json = json.loads(message)
        except json.JSONDecodeError:
            return
        
        try:
            title = resp_json.get("title", "")
            guid = resp_json.get("guid", "")
            
            with self.lock:
                if title.startswith("response_") and guid in self.response_events:
                    event = self.response_events[guid]
                    event['data'] = resp_json
                    event['flag'].set()
                    return
                
                if title == "notify_robot_info":
                    self.latest_status = resp_json.get("data", {})
                    # 只打印一次状态
                    if not self.status_printed:
                        self._print_status()
                        self.status_printed = True
                elif title == "notify_odom":
                    data = resp_json.get("data", {})
                    pos = data.get('pose_position', [])
                    if len(pos) >= 3:
                        print(f"\n📍 里程计: 位置=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})m")
                elif title == "notify_sitdown":
                    result = resp_json.get("data", {}).get("result", "")
                    print(f"📢 蹲下完成: {result}")
                elif title == "notify_stand_mode":
                    result = resp_json.get("data", {}).get("result", "")
                    print(f"📢 站起完成: {result}")
                elif title == "notify_walk_mode":
                    result = resp_json.get("data", {}).get("result", "")
                    print(f"📢 行走模式切换完成: {result}")
                elif title == "notify_recover":
                    result = resp_json.get("data", {}).get("result", "")
                    print(f"📢 摔倒恢复完成: {result}")
                elif title == "notify_invalid_request":
                    print(f"⚠️ 非法指令: {resp_json.get('data')}")
        except Exception:
            pass
    
    def _print_status(self):
        if not self.latest_status:
            return
        
        status = self.latest_status.get('status', 'UNKNOWN')
        icon, desc = self.STATUS_MAP.get(status, ('❓', '未知状态'))
        
        print("\n" + "=" * 50)
        print("📊 机器人状态")
        print("=" * 50)
        print(f"{icon} 状态: {status} - {desc}")
        print(f"🔋 电量: {self.latest_status.get('battery', '?')}%")
        print(f"📦 软件版本: {self.latest_status.get('sw_version', '?')}")
        print(f"⚙️ IMU: {self.latest_status.get('imu', '?')}")
        print(f"🎥 相机: {self.latest_status.get('camera', '?')}")
        print(f"🔧 电机: {self.latest_status.get('motor', '?')}")
        print("=" * 50)
    
    def send_and_wait(self, title, data=None, timeout=5):
        if not self.ws:
            if not self.connect():
                return None
        
        guid = self._generate_guid()
        msg = {
            "accid": self.accid,
            "title": title,
            "timestamp": int(time.time() * 1000),
            "guid": guid,
            "data": data if data else {}
        }
        
        event = {'flag': threading.Event(), 'data': None}
        with self.lock:
            self.response_events[guid] = event
        
        try:
            self.ws.send(json.dumps(msg))
            print(f"📤 发送: {title}")
            
            if event['flag'].wait(timeout):
                return event['data']
            else:
                print(f"⏱️ 等待响应超时: {title}")
                return None
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return None
        finally:
            with self.lock:
                self.response_events.pop(guid, None)
    
    def send(self, title, data=None):
        if not self.ws:
            if not self.connect():
                return False
        
        msg = {
            "accid": self.accid,
            "title": title,
            "timestamp": int(time.time() * 1000),
            "guid": self._generate_guid(),
            "data": data if data else {}
        }
        
        try:
            self.ws.send(json.dumps(msg))
            print(f"📤 发送: {title}")
            return True
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return False
    
    def stand(self):
        resp = self.send_and_wait("request_stand_mode")
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print("✅ 站起成功")
            else:
                print(f"⚠️ 站起失败: {result}")
        return resp
    
    def walk_mode(self):
        resp = self.send_and_wait("request_walk_mode")
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print("✅ 行走模式切换成功")
            else:
                print(f"⚠️ 切换失败: {result}")
        return resp
    
    def move(self, x, z=0.0):
        x = max(-self.SPEED_LIMIT_X, min(self.SPEED_LIMIT_X, x))
        z = max(-self.SPEED_LIMIT_Z, min(self.SPEED_LIMIT_Z, z))
        data = {"x": x, "y": 0.0, "z": z}
        print(f"🏃 移动: 速度={x:.2f}m/s, 转向={z:.2f}rad/s")
        return self.send("request_twist", data)
    
    def sitdown(self):
        resp = self.send_and_wait("request_sitdown")
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print("✅ 蹲下成功")
            else:
                print(f"⚠️ 蹲下失败: {result}")
        return resp
    
    def emergency_stop(self):
        print("🛑 紧急停止")
        return self.send("request_emgy_stop")
    
    def recover(self):
        resp = self.send_and_wait("request_recover")
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print("✅ 已开始恢复爬起")
            else:
                print(f"⚠️ 恢复失败: {result}")
        return resp
    
    def stair_mode(self, enable):
        mode = "开启" if enable else "关闭"
        resp = self.send_and_wait("request_stair_mode", {"enable": enable})
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print(f"✅ 楼梯模式{mode}成功")
            else:
                print(f"⚠️ 操作失败: {result}")
        return resp
    
    def adjust_height(self, direction):
        action = "升高" if direction == 1 else "降低"
        resp = self.send_and_wait("request_base_height", {"direction": direction})
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print(f"✅ 身高{action}成功")
            else:
                print(f"⚠️ 无法调整身高: {result}")
        return resp
    
    def set_light_effect(self, effect):
        resp = self.send_and_wait("request_light_effect", {"effect": int(effect)})
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print("✅ 灯光设置成功")
            else:
                print(f"⚠️ 灯光设置失败: {result}")
        return resp
    
    def enable_odom(self, enable):
        state = "开启" if enable else "关闭"
        resp = self.send_and_wait("request_enable_odom", {"enable": enable})
        if resp:
            result = resp.get("data", {}).get("result", "")
            if result == "success":
                print(f"✅ 里程计{state}成功")
            else:
                print(f"⚠️ 里程计{state}失败: {result}")
        return resp
    
    def get_status_once(self):
        print("📊 获取机器人状态...")
        self.status_printed = False  # 重置标记
        self.latest_status = {}
        
        for _ in range(10):
            time.sleep(0.5)
            if self.latest_status and not self.status_printed:
                self._print_status()
                self.status_printed = True
                return self.latest_status
        
        print("⚠️ 未收到状态信息")
        return None
    
    def close(self):
        self.running = False
        if self.ws:
            self.ws.close()
            print("🔌 连接已关闭")


def main():
    parser = argparse.ArgumentParser(description='TRON1轮足机器人完整控制')
    parser.add_argument('robot_ip', help='机器人IP地址')
    parser.add_argument('accid', help='机器人序列号')
    
    subparsers = parser.add_subparsers(dest='command', help='控制命令')
    
    subparsers.add_parser('stand', help='站立')
    subparsers.add_parser('walk', help='行走模式')
    subparsers.add_parser('sit', help='蹲下')
    subparsers.add_parser('stop', help='紧急停止')
    subparsers.add_parser('recover', help='摔倒恢复')
    subparsers.add_parser('status', help='获取一次状态')
    subparsers.add_parser('enable_odom', help='开启里程计推送')
    
    move_parser = subparsers.add_parser('move', help='移动')
    move_parser.add_argument('--x', type=float, default=0.5)
    move_parser.add_argument('--z', type=float, default=0.0)
    move_parser.add_argument('--duration', type=float, default=None)
    
    stair_parser = subparsers.add_parser('stair', help='楼梯模式')
    stair_parser.add_argument('--enable', type=lambda x: x.lower() == 'true', default=True)
    
    height_parser = subparsers.add_parser('height', help='调整身高')
    height_parser.add_argument('--dir', choices=['up', 'down'], required=True)
    
    light_parser = subparsers.add_parser('light', help='设置灯光')
    light_parser.add_argument('--effect', type=int, default=1)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    robot = TRON1Robot(args.robot_ip, args.accid)
    
    print("=" * 50)
    print("🤖 TRON1 轮足机器人控制")
    print(f"📍 IP: {args.robot_ip}")
    print(f"🏷️ ACCID: {args.accid}")
    print(f"🎮 命令: {args.command}")
    print("=" * 50)
    
    try:
        if not robot.connect():
            sys.exit(1)
        robot.start_listener()
        
        if args.command == 'stand':
            robot.stand()
        elif args.command == 'walk':
            robot.walk_mode()
        elif args.command == 'move':
            robot.move(args.x, args.z)
            if args.duration:
                time.sleep(args.duration)
                robot.emergency_stop()
        elif args.command == 'sit':
            robot.sitdown()
        elif args.command == 'stop':
            robot.emergency_stop()
        elif args.command == 'recover':
            robot.recover()
        elif args.command == 'stair':
            robot.stair_mode(args.enable)
        elif args.command == 'height':
            robot.adjust_height(1 if args.dir == 'up' else -1)
        elif args.command == 'light':
            robot.set_light_effect(args.effect)
        elif args.command == 'status':
            robot.get_status_once()
        elif args.command == 'enable_odom':
            robot.enable_odom(True)
            time.sleep(2)
        
        time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n🛑 用户中断")
    finally:
        robot.close()


if __name__ == "__main__":
    main()