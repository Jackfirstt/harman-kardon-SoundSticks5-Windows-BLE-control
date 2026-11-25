# 纯后端
import asyncio
import re
import time
import builtins
from bleak import BleakScanner, BleakClient
from protocol import (
    DeviceState,
    apply_notification,
    build_light_power,
    build_brightness,
    build_theme,
    build_speed,
    build_eq,
    build_eq_reset,
    build_media_action,
    build_volume,
    build_feedback_tone,
    build_color,
    build_color_reset,
    build_auto_off,
    build_rename,
    build_theme_only,
)
from const import (
    CONTROL_SERVICE_UUID,
    COMMAND_UUID,
    NOTIFY_UUID,
    HARMAN_DISCOVERY_UUID,
    FAST_PAIR_UUID,
    QUERY_LIGHT,
    QUERY_AGGREGATE,
    QUERY_FEEDBACK,
    QUERY_AUTO_OFF,
    QUERY_EQ,
    THEMES,
    SPEEDS,
    AUTO_OFF_SECONDS,
    AUDIO_SOURCE_LABELS, AUDIO_SOURCE_UNKNOWN,
)

# ==========================================
# 打印时间戳 (纯后端也可以保留，方便调试)
# ==========================================
_original_print = builtins.print


def print(*args, **kwargs):
    timestamp = time.strftime("[%H:%M:%S]")
    _original_print(timestamp, *args, **kwargs)


_ADDRESS_LIKE_NAME = re.compile(r"^(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}$", re.IGNORECASE)

# 全局状态缓存，UI 可以直接读取
state = DeviceState()


def matches_soundsticks5(name, service_uuids, service_data):
    uuids = {u.lower() for u in (service_uuids or [])}
    data = {k.lower(): bytes(v) for k, v in (service_data or {}).items()}
    if CONTROL_SERVICE_UUID in uuids:
        return True
    has_harman = HARMAN_DISCOVERY_UUID in uuids or HARMAN_DISCOVERY_UUID in data
    if "SoundSticks 5" in (name or "").lower() and has_harman:
        return True
    anonymous = not name or bool(_ADDRESS_LIKE_NAME.fullmatch(name))
    return anonymous and data.get(FAST_PAIR_UUID) == b"\x00\x00"


class SoundSticksController:
    def __init__(self):
        self.client = None
        self.is_connected = False

        # 供 PySide6 绑定的 UI 更新回调
        self.on_state_changed = None
        self.on_connection_changed = None  # <--- 加这行

        self.on_state_changed_mini = None   # 小窗口专用状态回调（仅用于音量等协议内状态同步）
        self.on_connection_changed_mini = None  # 小窗口用于解锁控件
        self._should_notify_disconnect = False  # 只有真正连上后才允许回调通知 UI
        self._manual_disconnect = False  # 是否是用户手动断开
        self._is_auto_reconnecting = False

    async def connect(self):
        if self.is_connected:
            return True
        # 通知 UI：开始扫描
        if self.on_state_changed:
            state.track_title = "正在扫描音箱..."
            state.artist = None
            self.on_state_changed(state)
        print("🔍 扫描中...")
        found = asyncio.Event()
        target_device = None

        def on_detect(device, adv_data):
            nonlocal target_device
            if target_device is not None:
                return
            if matches_soundsticks5(
                device.name, adv_data.service_uuids, adv_data.service_data
            ):
                target_device = device
                found.set()

        scanner = BleakScanner(detection_callback=on_detect)
        await scanner.start()
        try:
            await asyncio.wait_for(found.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print("❌ 扫描超时")
            await scanner.stop()
            # 通知 UI：扫描失败
            if self.on_state_changed:
                state.track_title = "扫描超时，未找到音箱，请点击左上角手动连接"
                state.artist = None
                self.on_state_changed(state)
            if self.on_connection_changed:
                self.on_connection_changed(False)
            if self.on_connection_changed_mini:
                self.on_connection_changed_mini(False)
            return False
        await scanner.stop()

        print(f"🔗 连接 {target_device.address} ...")
        # 【新增】通知 UI：已经找到音箱，正在连接
        if self.on_state_changed:
            state.track_title = "已发现音箱，正在建立连接..."
            state.artist = None
            self.on_state_changed(state)
        for attempt in range(1, 4):
            if attempt > 1:
                await asyncio.sleep(2)
            if self.client is not None:
                try:
                    if self.client.is_connected:
                        await self.client.disconnect()
                except Exception:
                    pass
                self.client = None  # 彻底清空引用，让底层回收资源
                await asyncio.sleep(2.0)  # 给 Windows 蓝牙栈 2 秒时间释放端口

            self.client = BleakClient(
                target_device.address, timeout=15.0, use_cached=False, pair=False, disconnected_callback=self._on_disconnected
            )
            try:
                await self.client.connect()

                # 关键：加一点延迟，等 Windows 底层发现服务
                await asyncio.sleep(1.5)

                services = {str(s.uuid).lower() for s in self.client.services}
                if CONTROL_SERVICE_UUID.lower() not in services:
                    print(f"  ❌ 第 {attempt} 次尝试：未找到控制服务")
                    await self.client.disconnect()
                    continue
                # 2. 验证通知订阅（核心：如果失败，直接断开）
                try:
                    await self.client.start_notify(NOTIFY_UUID, self._on_notify)
                except Exception as e:
                    print(f"  ❌ 第 {attempt} 次尝试：订阅通知失败 ({e})")
                    await self.client.disconnect()
                    continue  # 直接重试

                # 3. 到这里才算真正连接成功，通知 UI 解锁
                print("  ✅ 连接成功")
                self.is_connected = True
                self._should_notify_disconnect = True  # ← 加这行
                self._is_auto_reconnecting = False  # ← 加这行，防止循环残留
                if self.on_connection_changed:
                    self.on_connection_changed(True)  # <--- 通知 UI 解锁
                if self.on_connection_changed_mini:
                    self.on_connection_changed_mini(True)  # <--- 通知 UI 解锁小窗口

                try:
                    await self.query_all_status()
                except Exception as query_err:
                    print(f"  ⚠️ 查询状态失败: {query_err}")
                return True
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                try:
                    if self.client and self.client.is_connected:
                        await self.client.disconnect()
                except Exception:
                    pass
                self.client = None
                continue  # 明确进入下一轮
            # await asyncio.sleep(2)
        print(f"  ❌ 连接失败")
        # 3次都失败了
        self._should_notify_disconnect = False
        # 3次都失败了，通知 UI
        if self.on_state_changed:
            state.track_title = "连接失败，请点击左上角手动重试"
            state.artist = None
            self.on_state_changed(state)
        # 通知 UI 连接失败，禁用 UI
        if self.on_connection_changed:
            self.on_connection_changed(False)
        if self.on_connection_changed_mini:
            self.on_connection_changed_mini(False)
        return False

    async def disconnect(self):
        self._should_notify_disconnect = False
        if self.client is not None:
            # 不再单独 stop_notify——disconnect 会自动清理订阅，省一个会挂起的调用
            try:
                await asyncio.wait_for(self.client.disconnect(), timeout=5.0)
            except (asyncio.TimeoutError, Exception) as e:
                # 假死时 disconnect 会超时，抓过来照样往下清
                print(f"断开超时/异常，强制清理: {e}")
            finally:
                # 无论成败，都强制复位，保证 UI 不卡、能重连
                self.client = None
                self.is_connected = False
                if self.on_connection_changed:
                    self.on_connection_changed(False)
                if self.on_connection_changed_mini:
                    self.on_connection_changed_mini(False)
                print("已断开（含强制清理）")

    def _on_disconnected(self, client):
        """底层蓝牙主动断开时触发"""
        # 只有在正式连接成功后才处理，防止连接重试过程中误触发
        if not self._should_notify_disconnect:
            return
        if self.is_connected:
            print("🔌 底层蓝牙已断开（被动断开）")
            self._should_notify_disconnect = False
            self.is_connected = False
            self.client = None
            if self.on_connection_changed:
                self.on_connection_changed(False)
            if self.on_connection_changed_mini:
                self.on_connection_changed_mini(False)

            # ✅ 如果是意外断开，自动重连
            if not self._manual_disconnect:
                print("♻️ 检测到意外断开，3 秒后尝试自动重连...")
                asyncio.create_task(self._auto_reconnect())
            else:
                print("🛑 用户手动断开，不自动重连")
                self._manual_disconnect = False  # 重置标志

    async def _auto_reconnect(self):
        if getattr(self, "_is_auto_reconnecting", False):
            return
        self._is_auto_reconnecting = True

        try:
            for attempt in range(1, 6):
                # 如果已经连上了，或者用户手动断开了，立刻停止自动重连
                if self.is_connected or self._manual_disconnect:
                    print("✅ 已连接或用户手动断开，停止自动重连")
                    return
                
                print(f"🔄 自动重连尝试第 {attempt}/5 次...")
                await asyncio.sleep(3.0)  # 每次重连前等 3 秒，给底层清理时间
                
                if self.is_connected or self._manual_disconnect:
                    return
                
                # 重置手动断开标志，防止上一次的断开被误判
                self._manual_disconnect = False
                
                # 调用 connect()，它内部本身还会重试 3 次
                success = await self.connect()
                if success:
                    print("✅ 自动重连成功")
                    return
                
                print(f"❌ 自动重连第 {attempt} 次失败")
            
            # 5 次全部失败
            print("🛑 自动重连 5 次均失败，停止重试")
            if self.on_state_changed:
                state.track_title = "自动重连失败，请点击左上角手动重试"
                state.artist = None
                self.on_state_changed(state)
        finally:
            self._is_auto_reconnecting = False

    def set_manual_disconnect(self, manual: bool):
        """由 UI 层调用，标记是否是用户主动断开"""
        self._manual_disconnect = manual

    def _on_notify(self, sender, data: bytearray):
        """收到通知时，解析并更新状态，然后触发 UI 回调"""
        try:
            # raw_hex = data.hex(' ')
            # cmd = data[1] if len(data) > 1 else 0
            # print(f"\n[⬇️ 收到通知] Cmd:0x{cmd:02X} | 原始数据: {raw_hex}")

            # 更新全局状态
            apply_notification(state, bytes(data))

            # ===== 打印当前所有解析到的状态 =====
            # print("  📊 当前解析状态:")
            # print(f"    - 播放状态: {state.playback} (1=暂停, 2=播放)")
            # print(f"    - 音量: {state.volume}%")
            # print(f"    - 歌名: {state.track_title}")
            # print(f"    - 歌手: {state.artist}")
            # print(f"    - 灯光开关: {state.light_power}")
            # print(f"    - 亮度: {state.brightness}")
            # print(f"    - 主题ID: {state.theme_id}")
            # print(f"    - 颜色: {state.colors}")
            # print(f"    - 速度: {state.speed}")
            # print(f"    - 反馈音: {state.feedback_tone}")
            # print(f"    - 自动关机配置: {state.auto_off_configured}s, 剩余: {state.auto_off_remaining}s")
            # print(f"    - EQ: {state.eq_gains_db}")
            # print(f"    - 36: {state.unknown_36}")
            # print("-" * 40)

            # 通知 UI 刷新界面
            if self.on_state_changed:
                self.on_state_changed(state)
            # ✅ 【核心修复】通知小窗口更新音量和连接状态
            if self.on_state_changed_mini:
                self.on_state_changed_mini(state)

        except Exception as e:
            print(f"\n[通知解析失败] {e}")

    async def _send(self, payload: bytes):
        if not self.is_connected or self.client is None or not self.client.is_connected:
            print("⚠️ 未连接，无法发送指令")
            # ✅ 关键修复：如果 is_connected 还是 True，但底层已断，立刻复位并通知 UI
            if self.is_connected:
                self.is_connected = False
                self.client = None
                if self.on_connection_changed:
                    self.on_connection_changed(False)
                if self.on_connection_changed_mini:
                    self.on_connection_changed_mini(False)
            return
        try:
            await self.client.write_gatt_char(COMMAND_UUID, payload, response=False)
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"❌ 发送指令失败: {e}")
            self.is_connected = False
            self.client = None
            if self.on_connection_changed:
                self.on_connection_changed(False)
            if self.on_connection_changed_mini:
                self.on_connection_changed_mini(False)

    async def query_all_status(self):
        print("📥 查询全量状态...")
        for q in [
            QUERY_LIGHT,
            QUERY_AGGREGATE,
            QUERY_FEEDBACK,
            QUERY_AUTO_OFF,
            QUERY_EQ,
        ]:
            await self._send(q)
            await asyncio.sleep(0.2)

    # ============ 新增：音源标签 ============
    def get_audio_source_label(self) -> str:
        return AUDIO_SOURCE_LABELS.get(state.unknown_36, AUDIO_SOURCE_UNKNOWN)

    # ================= 核心控制功能 =================
    async def set_light_power(self, on: bool):
        await self._send(build_light_power(on))

    async def set_brightness(self, value: int):
        await self._send(build_brightness(value))

    async def set_theme(self, theme_name: str):
        await self._send(build_theme_only(theme_name))

    async def set_speed(self, speed_name: str):
        await self._send(build_speed(speed_name))

    async def set_color(self, value: int):
        if state.theme_id is not None:
            await self._send(build_color(state.theme_id, value))
        else:
            print("⚠️ 尚未获取到主题ID")

    async def reset_color(self):
        if state.theme_id is not None:
            await self._send(build_color_reset(state.theme_id))
        else:
            print("⚠️ 尚未获取到主题ID")

    async def set_volume(self, value: int):
        await self._send(build_volume(value))

    async def set_eq(self, steps: list[int]):
        await self._send(build_eq(steps))

    async def reset_eq(self):
        await self._send(build_eq_reset())

    async def media_action(self, action: str):
        await self._send(build_media_action(action))

    async def toggle_playback(self):
        """根据当前状态切换播放/暂停"""
        # state.playback: 1 是暂停，2 是播放
        if state.playback == 2:
            await self.media_action("pause")
        else:
            await self.media_action("play")

    async def set_feedback_tone(self, on: bool):
        await self._send(build_feedback_tone(on))

    async def set_auto_off(self, duration: str):
        await self._send(build_auto_off(duration))

    async def rename_speaker(self, new_name: str):
        print(f"✏️ 正在重命名为: {new_name}")
        await self._send(build_rename(new_name))
