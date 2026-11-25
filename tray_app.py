import sys
import asyncio
import qasync
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSlider,
    QLabel,
    QPushButton,
    QGridLayout,
    QSystemTrayIcon,
    QMenu,
)
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor, QFontMetrics

from controller import SoundSticksController, state
from const import (
    THEMES,
    SPEEDS,
    AUTO_OFF_SECONDS,
    THEME_BY_ID,
    SPEED_BY_ID,
    AUTO_OFF_BY_SECONDS,
    AUDIO_SOURCE_LABELS,
    AUDIO_SOURCE_UNKNOWN,
)
from protocol import gain_db_to_app_eq_step

# ==========================================
# 放在文件顶部，导入库的下面
# ==========================================
ICON_PLAY = "\ue768"
ICON_PAUSE = "\ue769"
ICON_PREV = "\ue892"
ICON_NEXT = "\ue893"
ICON_REFRESH = "\ue895"
ICON_LINK = "\ue71b"
ICON_DISCONNECT = "\ue711"
ICON_SANDGLASS = "\ue72c"

# ============ 暗色主题 ============
QSS_DARK = """
    QWidget { background-color: #2b2b2b; color: #eee; font-family: 'Segoe UI', 'Microsoft YaHei'; border-radius: 12px; }
    QLabel { font-size: 13px; background: transparent; }
    QPushButton { background-color: #3a3a3a; border: none; padding: 8px; border-radius: 6px; color: #eee; }
    QPushButton:hover { background-color: #4a4a4a; }
    QPushButton:pressed { background-color: #2a2a2a; }
    QPushButton:disabled { background-color: #2a2a2a; color: #777; }
    QSlider { min-height: 20px; }
    QSlider::groove:horizontal { height: 6px; background: #444; border-radius: 3px; }
    QSlider::handle:horizontal { background: #00d2ff; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
    QSlider::handle:horizontal:disabled { background: transparent; border: none; }
    QSlider::groove:vertical { width: 6px; background: #444; border-radius: 3px; margin: 0 5px; }
    QSlider::handle:vertical { background: #00d2ff; width: 16px; height: 16px; margin: 0 -5px; border-radius: 8px; }
    QSlider::handle:vertical:disabled { background: transparent; border: none; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical { width: 6px; background: #2b2b2b; border-radius: 3px; }
    QScrollBar::handle:vertical { background: #555; border-radius: 3px; min-height: 20px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QComboBox { background-color: #3a3a3a; border: none; padding: 6px; border-radius: 6px; color: #eee; }
    QComboBox QAbstractItemView { background-color: #3a3a3a; color: #eee; selection-background-color: #00d2ff; }
    QLabel#panelTitle { font-size: 18px; font-weight: bold; background: transparent; color: #fff; }
"""

# ============ 浅色主题 ============
QSS_LIGHT = """
    QWidget { background-color: #f4f4f4; color: #222; font-family: 'Segoe UI', 'Microsoft YaHei'; border-radius: 12px; }
    QLabel { font-size: 13px; background: transparent; color: #222; }
    QPushButton { background-color: #e0e0e0; border: none; padding: 8px; border-radius: 6px; color: #222; }
    QPushButton:hover { background-color: #d0d0d0; }
    QPushButton:pressed { background-color: #c0c0c0; }
    QPushButton:disabled { background-color: #e8e8e8; color: #aaa; }
    QSlider { min-height: 20px; }
    QSlider::groove:horizontal { height: 6px; background: #c8c8c8; border-radius: 3px; }
    QSlider::handle:horizontal { background: #2CA1E6; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
    QSlider::handle:horizontal:disabled { background: transparent; border: none; }
    QSlider::groove:vertical { width: 6px; background: #c8c8c8; border-radius: 3px; margin: 0 5px; }
    QSlider::handle:vertical { background: #2CA1E6; width: 16px; height: 16px; margin: 0 -5px; border-radius: 8px; }
    QSlider::handle:vertical:disabled { background: transparent; border: none; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical { width: 6px; background: #f4f4f4; border-radius: 3px; }
    QScrollBar::handle:vertical { background: #bbb; border-radius: 3px; min-height: 20px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QComboBox { background-color: #e0e0e0; border: none; padding: 6px; border-radius: 6px; color: #222; }
    QComboBox QAbstractItemView { background-color: #f4f4f4; color: #222; selection-background-color: #0098c0; }
    QLabel#panelTitle { font-size: 18px; font-weight: bold; background: transparent; color: #111; }
"""


# 主题覆盖：None=跟随系统, 'dark'=强制深色, 'light'=强制浅色
THEME_OVERRIDE = None


def current_is_dark() -> bool:
    if THEME_OVERRIDE == "dark":
        return True
    if THEME_OVERRIDE == "light":
        return False
    try:
        hints = QApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        pass
    # 退回调色板亮度判断
    try:
        return QApplication.palette().window().color().lightness() < 128
    except Exception:
        return True

def theme_tokens() -> dict:
    """返回当前主题下所有动态内联样式用到的颜色 token。"""
    if current_is_dark():
        return {
            "header_btn": "#aaa", "header_hover_color": "#fff", "header_hover_bg": "#3a3a3a",
            "round_bg": "#3a3a3a", "round_hover": "#4a4a4a", "round_press": "#2a2a2a",
            "round_text": "#eee", "round_disabled_bg": "#2a2a2a", "round_disabled_text": "#555",
            "accent": "#00d2ff", "accent_hover": "#33ddff", "accent_text": "#000",
            "muted_title": "#aaa", "separator": "#444",
            "bar_disabled": "#444", "handle_border": "#2b2b2b",
            "speed_default_bg": "#3a3a3a", "speed_default_text": "#eee", "speed_default_hover": "#4a4a4a",
            "speed_default_press": "#2a2a2a", "speed_default_disabled_text": "#777",
            "theme_disabled_bg": "#3a3a3a", "theme_disabled_text": "#777",
            "theme_sel_border": "#fff",
            "speed_active_bg": "#00d2ff", "speed_active_text": "#000", "speed_active_hover": "#33ddff",
        }
    return {
        "header_btn": "#000", "header_hover_color": "#000", "header_hover_bg": "#e0e0e0",
        "round_bg": "#e6e6e6", "round_hover": "#d4d4d4", "round_press": "#c2c2c2",
        "round_text": "#222", "round_disabled_bg": "#ededed", "round_disabled_text": "#aaa",
        "accent": "#0098c0", "accent_hover": "#0083a6", "accent_text": "#fff",
        "muted_title": "#777", "separator": "#d2d2d2",
        "bar_disabled": "#c8c8c8", "handle_border": "#444",
        "speed_default_bg": "#e0e0e0", "speed_default_text": "#222", "speed_default_hover": "#d0d0d0",
        "speed_default_press": "#c0c0c0", "speed_default_disabled_text": "#aaa",
        "theme_disabled_bg": "#e0e0e0", "theme_disabled_text": "#aaa",
        "theme_sel_border": "#525252",
        "speed_active_bg": "#2CA1E6", "speed_active_text": "#000", "speed_active_hover": "#3BB8FF",
    }


GLOBAL_PANEL_POS = None

# ==========================================
# 迷你音量面板
# ==========================================
class MiniPanel(QWidget):
    """迷你音量面板：单击托盘图标时显示"""

    # 自定义信号：通知外部要打开完整面板
    open_full_panel = Signal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

        # 窗口属性：无边框 + 置顶 + 失焦自动隐藏
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setFixedSize(360, 90)

        # 垂直布局：上方品牌名 + 下方滑块
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        brand_label = QLabel("harman/kardon")
        brand_label.setObjectName("brand")
        main_layout.addWidget(brand_label)

        slider_container = QWidget()
        slider_layout = QHBoxLayout(slider_container)
        slider_layout.setContentsMargins(12, 0, 12, 8)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(1, 99)
        self.vol_slider.setSingleStep(3)
        self.vol_slider.setPageStep(3)

        # ✅ 1. 默认锁定：初始化时直接禁用并隐藏，等待 controller 解锁
        self.vol_slider.setEnabled(False)

        slider_layout.addWidget(self.vol_slider)
        main_layout.addWidget(slider_container)

        # —— 修复核心：值变更即锁，定时释放；不用 isSliderDown ——
        self._local_locked = False
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.setInterval(2000)  # 2 秒内忽略回传
        self._lock_timer.timeout.connect(self._release_lock)

        # 防抖发送
        self._send_timer = QTimer(self)
        self._send_timer.setSingleShot(True)
        self._send_timer.timeout.connect(self._send_volume)

        # valueChanged 是唯一的真相来源（滚轮/拖拽/点击滑轨/键盘都会触发）
        self.vol_slider.valueChanged.connect(self._on_value_changed)

        # ✅ 安装事件过滤器，拦截所有子控件的鼠标双击
        self.installEventFilter(self)
        # 让小窗口任意位置(含音量滑块本身)的滚轮都走统一的调音量逻辑
        self.vol_slider.installEventFilter(self)

        # ✅ 绑定独立连接状态回调（与大窗口逻辑一致）
        self.controller.on_connection_changed_mini = self._on_connection_changed
        # ✅ 绑定状态回调仅用于音量同步
        self.controller.on_state_changed_mini = self._on_state_changed
        self.apply_color_scheme()

    # —— 值变更：锁定 + 防抖发送 ——
    def _on_value_changed(self, value):
        self._local_locked = True
        self._lock_timer.start()      # 每次变更都重置锁定窗口
        self._send_timer.start(50)    # 50ms 防抖后发出去

    def _release_lock(self):
        # 解锁后不主动改滑块值；下次音箱回传若与当前值差 >3 才同步
        self._local_locked = False

    def _on_connection_changed(self, connected: bool):
        """连接状态变化：启用/禁用滑块"""
        self.vol_slider.setEnabled(connected)
        if not connected:
            self._local_locked = False
            self._lock_timer.stop()
            self._send_timer.stop()

    def _on_state_changed(self, s):
        """收到蓝牙通知：仅在用户没有操作时同步音量"""
        if self._local_locked:
            return
        if s.volume is None:
            return
        rounded = (s.volume // 3) * 3
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(rounded)
        self.vol_slider.blockSignals(False)

    def _send_volume(self):
        value = (self.vol_slider.value() // 3) * 3
        asyncio.create_task(self.controller.set_volume(value))

    def eventFilter(self, obj: QObject, event):
        """统一拦截滚轮(任意位置调音量)与鼠标双击"""
        if event.type() == QEvent.Wheel:
            self._handle_wheel(event)
            return True  # 滚轮统一在此消费，避免再冒泡/被滑块重复处理
        if event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                # 双击音量滑块 → 忽略，不打开大窗口
                if obj is self.vol_slider:
                    return False  # 让滑块正常处理自己的双击
                # 双击窗口内其他任意位置（包括空白区）→ 打开大窗口
                self.open_full_panel.emit()
                self.hide()
                return True  # 事件已消费，不再传递
        return super().eventFilter(obj, event)

    def _handle_wheel(self, event):
        """小窗口任意位置滚轮调音量：按 3 对齐步进，复用滑块 valueChanged 的锁定+防抖发送。"""
        if not self.vol_slider.isEnabled():
            return  # 未连接：滑块禁用，忽略滚轮
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 3
        direction = 1 if delta > 0 else -1
        cur = self.vol_slider.value()
        new_val = ((cur + step * direction) // 3) * 3
        new_val = max(self.vol_slider.minimum(), min(self.vol_slider.maximum(), new_val))
        if new_val != cur:
            self.vol_slider.setValue(new_val)  # 触发 _on_value_changed：锁定 + 防抖发送
        event.accept()

    def show_near_tray(self):
        """在托盘图标附近弹出"""
        global GLOBAL_PANEL_POS
        pos = QCursor.pos()
        screen_geometry = QApplication.primaryScreen().availableGeometry()

        x = pos.x() - self.width() + 20
        y = pos.y() - self.height() - 10

        if x + self.width() > screen_geometry.width():
            x = screen_geometry.width() - self.width() - 10
        if y + self.height() > screen_geometry.height():
            y = screen_geometry.height() - self.height() - 10
        if x < 0:
            x = 10
        if y < 0:
            y = 10
        self.move(x, y)
        GLOBAL_PANEL_POS = (x, y)  # ← 记住这个位置
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_color_scheme(self):
        base = QSS_DARK if current_is_dark() else QSS_LIGHT
        # MiniPanel 品牌文字在暗色下白色、浅色下深色
        brand_color = "#fff" if current_is_dark() else "#222"
        self.setStyleSheet(base + f"""
            QLabel#brand {{ font-size: 16px; color: {brand_color}; padding: 7px 0 0 12px; background: transparent; }}
        """)


# ==========================================
# 歌曲信息跑马灯滚动
# ==========================================
class MarqueeLabel(QLabel):
    # ===== 滚动速度可调参数 =====
    TIMER_INTERVAL_MS = 15        # 每帧间隔(ms)
    SCROLL_STEP_MIN = 0.3           # 最短文本每帧步进(慢)
    SCROLL_STEP_MAX = 1.5           # 最长文本每帧步进(快)
    LENGTH_TIER_PIXELS = 400      # 逻辑宽度达到此值即封顶为 MAX 步进
    # ============================
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text_pixmap = None
        self._offset = 0.0
        self._direction = -1
        self._pause_counter = 0
        self._step = self.SCROLL_STEP_MIN
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_scroll)
        self._is_scrolling = False
        self._text_color = "#aaa"
        self.setStyleSheet(f"font-size: 14px; color: {self._text_color}; font-style: italic;")

    def set_text_color(self, color: str):
        """主题切换时刷新歌曲信息颜色：样式表 + 跑马灯画笔同步更新。"""
        if getattr(self, "_text_color", None) == color:
            return
        self._text_color = color
        self.setStyleSheet(f"font-size: 14px; color: {color}; font-style: italic;")
        # 重新生成文字 pixmap，让滚动状态下也用新颜色
        self._update_pixmap()
        self.update()

    def setText(self, text):
        if super().text() == text:
            return
        super().setText(text)
        self._offset = 0.0
        self._direction = -1
        self._pause_counter = 30
        self._update_pixmap()
        self._check_scroll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._check_scroll()

    def _update_pixmap(self):
        fm = QFontMetrics(self.font())
        text = self.text()
        if not text:
            self._text_pixmap = None
            return

        # 1. 获取设备 DPI 缩放比例（例如 1.25, 1.5, 2.0）
        dpr = self.devicePixelRatioF()

        # 2. 根据逻辑尺寸计算物理像素尺寸
        logical_width = fm.horizontalAdvance(text)
        logical_height = fm.height()
        self._text_pixmap = QPixmap(int(logical_width * dpr), int(logical_height * dpr))
        self._text_pixmap.setDevicePixelRatio(dpr)  # 关键：告诉 Qt 这是一个高分屏图像
        self._text_pixmap.fill(Qt.transparent)

        painter = QPainter(self._text_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(QColor(self._text_color))
        painter.setFont(self.font())

        # 4. 直接使用逻辑坐标绘制，Qt 会自动根据 dpr 放大渲染，避免错位
        painter.drawText(0, fm.ascent(), text)
        painter.end()

    def _compute_step(self):
        """根据文本逻辑宽度计算步进像素：越长越快。"""
        if not self._text_pixmap:
            return self.SCROLL_STEP_MIN
        text_width = self._text_pixmap.width() / self._text_pixmap.devicePixelRatio()
        # 只考虑"超出部分"：超得越多越快
        overflow = max(0.0, text_width - self.width())
        if overflow <= 0:
            return self.SCROLL_STEP_MIN
        tier = self.LENGTH_TIER_PIXELS
        ratio = min(1.0, overflow / tier)       # 0.0~1.0
        step = self.SCROLL_STEP_MIN + ratio * (self.SCROLL_STEP_MAX - self.SCROLL_STEP_MIN)
        return step

    def _check_scroll(self):
        if not self._text_pixmap:
            return

        # 计算文字宽度（因为设置了 DPI，Pixmap 的 width() 是物理宽度，除以 dpr 得到逻辑宽度）
        text_width = self._text_pixmap.width() / self._text_pixmap.devicePixelRatio()
        if text_width > self.width():
            if not self._is_scrolling:
                self._is_scrolling = True
                self._offset = 0.0
                self._direction = -1
                self._pause_counter = 60
                self._step = self._compute_step()
                self._timer.start(self.TIMER_INTERVAL_MS)
            else:
                # 尺寸变化时更新一次步进
                self._step = self._compute_step()
        else:
            if self._is_scrolling:
                self._is_scrolling = False
                self._timer.stop()
            self.update()

    def _update_scroll(self):
        if not self._text_pixmap:
            return
        text_width = self._text_pixmap.width() / self._text_pixmap.devicePixelRatio()
        max_offset = text_width - self.width() + 5
        if max_offset <= 0:
            return
        if self._pause_counter > 0:
            self._pause_counter -= 1
            return
        self._offset += self._direction * self._step
        if self._direction == -1 and self._offset <= -max_offset:
            self._offset = -max_offset
            self._direction = 1
            self._pause_counter = 60
        elif self._direction == 1 and self._offset >= 0:
            self._offset = 0.0
            self._direction = -1
            self._pause_counter = 60
        self.update()

    def paintEvent(self, event):
        if self._is_scrolling and self._text_pixmap:
            painter = QPainter(self)
            # 开启平滑缩放
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setRenderHint(QPainter.Antialiasing, True)
            # 核心修正：因为设置了 DevicePixelRatio，Qt 的 drawPixmap 会自动处理缩放。
            # 这里我们直接按逻辑坐标画，偏移量也是逻辑像素
            painter.drawPixmap(int(self._offset), 0, self._text_pixmap)
        else:
            super().paintEvent(event)


# ==========================================
# 弹出控制面板 UI
# ==========================================
class ControlPanel(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.controller.on_state_changed = self.update_ui
        self.controller.on_connection_changed = self.on_connection_changed

        # 窗口设置
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setFixedSize(360, 710)

        # 主题重绘收集容器（切换浅色/深色时统一重建）
        self._header_btns = []
        self._muted_titles = []
        self._separators = []

        # 主布局：无滚动，直接铺满窗口
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # ================= 标题栏（带连接/断开 + 居中标题 + 刷新） =================
        header_layout = QHBoxLayout()

        # 1. 左侧连接按钮
        self.btn_conn = QPushButton(ICON_LINK)  # 默认显示连接图标
        self.btn_conn.setFixedSize(35, 35)
        self.btn_conn.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; font-size: 16px; color: #aaa; }
            QPushButton:hover { color: #fff; background-color: #3a3a3a; border-radius: 4px; }
        """)
        self.btn_conn.setToolTip("连接")
        self.btn_conn.clicked.connect(self.toggle_connection)
        header_layout.addWidget(self.btn_conn)

        # 2. 中间标题
        title = QLabel("harman/kardon")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title, 1)

        # 3. 右侧刷新按钮
        self.btn_refresh = QPushButton(ICON_REFRESH)
        self.btn_refresh.setFixedSize(35, 35)
        self.btn_refresh.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; font-size: 16px; color: #aaa; }
            QPushButton:hover { color: #fff; background-color: #3a3a3a; border-radius: 4px; }
        """)
        self.btn_refresh.setToolTip("刷新")
        self.btn_refresh.clicked.connect(self.refresh_state)
        self._header_btns += [self.btn_conn, self.btn_refresh]
        header_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(header_layout)

        # ================= 下方控制区（断开时会被禁用） =================
        self.content_widget = QWidget()
        main_layout.addWidget(self.content_widget)

        # 所有功能控件加到 self.layout 中
        self.layout = QVBoxLayout(self.content_widget)
        self.layout.setContentsMargins(0, 10, 0, 0)  # 顶部留点间距
        self.layout.setSpacing(15)

        # 歌曲信息（使用跑马灯，固定宽度 320）
        self.song_label = MarqueeLabel("暂无歌曲信息")
        self.song_label.setFixedWidth(320)
        self.song_label.setFixedHeight(24)  # 固定高度确保不抖动
        self.song_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.song_label)

        # ================= 播放控制 =================
        play_layout = QHBoxLayout()
        # play_layout.setContentsMargins(0, 10, 0, 10) # 上下各留出 10 像素的空间
        # 1. 上一首
        self.btn_prev = QPushButton(ICON_PREV)
        self.btn_prev.setFixedSize(46, 46)  # 加大到 46
        self.btn_prev.setStyleSheet("""
            QPushButton { font-family: 'Segoe MDL2 Assets'; font-size: 18px; border: none; background-color: #3a3a3a; color: #eee; border-radius: 23px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
        """)
        self.btn_prev.clicked.connect(
            lambda: self.spawn(self.controller.media_action("previous"))
        )

        # 2. 播放/暂停 (最大)
        self.btn_play = QPushButton(ICON_PAUSE)
        self.btn_play.setFixedSize(60, 60)
        self.btn_play.setStyleSheet("""
            QPushButton { font-family: 'Segoe MDL2 Assets'; font-size: 24px; border: none; background-color: #3a3a3a; color: #eee; border-radius: 30px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
        """)
        self.btn_play.clicked.connect(self.on_play_click)

        # 3. 下一首
        self.btn_next = QPushButton(ICON_NEXT)
        self.btn_next.setFixedSize(46, 46)  # 加大到 46
        self.btn_next.setStyleSheet("""
            QPushButton { font-family: 'Segoe MDL2 Assets'; font-size: 18px; border: none; background-color: #3a3a3a; color: #eee; border-radius: 23px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
        """)
        self.btn_next.clicked.connect(
            lambda: self.spawn(self.controller.media_action("next"))
        )

        # === 核心布局调整 ===
        # 使用弹簧+固定间距，让按钮完全均匀、分开
        play_layout.addStretch(1)
        play_layout.addWidget(self.btn_prev)
        play_layout.addSpacing(30)  # 按钮之间留出 30 像素间距
        play_layout.addWidget(self.btn_play)
        play_layout.addSpacing(30)  # 按钮之间留出 30 像素间距
        play_layout.addWidget(self.btn_next)
        play_layout.addStretch(1)

        self.layout.addLayout(play_layout)

        # ================= 音量 =================
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("音量:"))

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(1, 99)
        self.vol_slider.setSingleStep(3)  # 每次加 3
        self.vol_slider.setPageStep(3)  # 点击滑轨每次加 3

        self.vol_timer = QTimer()
        self.vol_timer.setSingleShot(True)
        self.vol_timer.timeout.connect(self.send_volume)
        self.vol_slider.valueChanged.connect(self.on_vol_change)
        vol_layout.addWidget(self.vol_slider)
        self.layout.addLayout(vol_layout)

        # ================= 灯光 =================
        self._add_separator()

        # 创建一个垂直外壳，专门控制灯光控制与主题网格的间距
        light_section = QVBoxLayout()
        light_section.setContentsMargins(0, 0, 0, 0)
        light_section.setSpacing(10)  # <--- 在这里调节距离！数字越小靠得越近

        # 1. 灯光标题和开关
        light_title_layout = QHBoxLayout()
        light_title_layout.setContentsMargins(0, 0, 0, 0)

        light_title = QLabel("灯光控制")
        light_title.setStyleSheet("font-weight: bold; color: #aaa; padding: 0px; margin: 0px;")
        self._muted_titles.append(light_title)

        self.light_btn = QPushButton("-")
        self.light_btn.setFixedSize(175, 28)
        self.light_btn.clicked.connect(self.toggle_light)

        light_title_layout.addWidget(light_title)
        light_title_layout.addStretch()
        light_title_layout.addWidget(self.light_btn)

        # 2. 主题网格
        theme_grid = QGridLayout()
        theme_grid.setContentsMargins(0, 0, 0, 0)
        theme_grid.setHorizontalSpacing(8)
        theme_grid.setVerticalSpacing(10)

        self.theme_buttons = {}
        theme_items = [
            ("ocean", "碧波荡漾", ["#06DFBE", "#37ACFF", "#5B32FF"]),
            ("aurora", "极光幻境", ["#42EA66", "#0E8ED9"]),
            ("blossom", "落英缤纷", ["#D786C5", "#8C53E8"]),
            ("sunrise", "旭日东升", ["#FF5359", "#F7A86B", "#EBCC6C", "#E1ED6E"]),
            ("fireplace", "雪夜炉火", ["#E7BA5A", "#F64302"]),
            ("static", "静谧时光", ["#FFE9C9", "#F5C96A", "#8FEA7F", "#66B9F2", "#D36BE5", "#F075A2"],),
        ]

        for i, (key, name, colors) in enumerate(theme_items):
            btn = QPushButton(name)
            btn.setFixedHeight(42)

            # 动态生成按钮的渐变色字符串
            gradient_stops = ""
            for idx, color in enumerate(colors):
                stop_pos = idx / (len(colors) - 1)
                gradient_stops += f"stop:{stop_pos:.2f} {color}, "
            gradient_stops = gradient_stops.rstrip(", ")

            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient_stops});
                    border: 2px solid transparent;
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: bold;
                    color: #222;
                }}
                QPushButton:hover {{ border: 2px solid #fff; }}
                QPushButton:disabled {{ background: #3a3a3a; border: none; color: #777; }}
            """)
            btn.clicked.connect(lambda checked, k=key: self.on_theme_change(k))
            self.theme_buttons[key] = btn
            theme_grid.addWidget(btn, i // 3, i % 3)

        # 3. 把标题和网格装进外壳
        light_section.addLayout(light_title_layout)
        light_section.addLayout(theme_grid)

        # 4. 把外壳加进主布局
        self.layout.addLayout(light_section)

        # === 新增：颜色调节 ===
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("颜色:"))
        self.color_slider = QSlider(Qt.Horizontal)
        self.color_slider.setRange(0, 100)
        self.color_slider.setObjectName(
            "colorSlider"
        )  # <--- 加这一行，用于独立设置 CSS
        self.color_timer = QTimer()
        self.color_timer.setSingleShot(True)
        self.color_timer.timeout.connect(self.send_color)
        self.color_slider.valueChanged.connect(self.on_color_change)

        self.btn_color_reset = QPushButton("重置")
        self.btn_color_reset.setFixedSize(56, 28)
        self.btn_color_reset.clicked.connect(self.reset_color)

        color_layout.addWidget(self.color_slider)
        color_layout.addWidget(self.btn_color_reset)
        self.layout.addLayout(color_layout)
        self.update_color_slider_gradient("ocean")  # 给个初始默认渐变

        # 亮度
        bright_layout = QHBoxLayout()
        bright_layout.addWidget(QLabel("亮度:"))
        self.bright_slider = QSlider(Qt.Horizontal)
        self.bright_slider.setRange(0, 100)
        self.bright_slider.setObjectName("brightnessSlider")
        self.bright_timer = QTimer()
        self.bright_timer.setSingleShot(True)
        self.bright_timer.timeout.connect(self.send_brightness)
        self.bright_slider.valueChanged.connect(self.on_bright_change)
        bright_layout.addWidget(self.bright_slider)
        self.layout.addLayout(bright_layout)
        # 亮度条专属样式（深灰到纯白）
        bright_qss = """
            QSlider#brightnessSlider::groove:horizontal {
                height: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #505050, 
                    stop:1 #ffffff);
                border-radius: 6px;
            }
            QSlider#brightnessSlider::groove:horizontal:disabled {
                height: 12px;
                background: #444;
                border-radius: 6px;
            }
            QSlider#brightnessSlider::handle:horizontal {
                background: #fff;
                border: 2px solid #2b2b2b;
                width: 16px;
                height: 16px;
                margin: -3px 0;
                border-radius: 9px;
            }
            QSlider#brightnessSlider::handle:horizontal:disabled {
                background: transparent;
                border: none;
            }
        """
        self._apply_brightness_qss()

        # === 速度调节 ===
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("速度:"))

        self.btn_speed_low = QPushButton("低")
        self.btn_speed_med = QPushButton("中")
        self.btn_speed_high = QPushButton("高")

        self.btn_speed_low.clicked.connect(lambda: self.set_speed("low"))
        self.btn_speed_med.clicked.connect(lambda: self.set_speed("medium"))
        self.btn_speed_high.clicked.connect(lambda: self.set_speed("high"))

        # 把三个按钮均匀地铺满后面的空间
        speed_layout.addWidget(self.btn_speed_low, 1)  # 这里的 1 表示拉伸比例为 1
        speed_layout.addWidget(self.btn_speed_med, 1)
        speed_layout.addWidget(self.btn_speed_high, 1)

        # 给三个速度按钮一个初始的默认样式（和全局普通按钮一致）
        initial_speed_style = """
            QPushButton { background-color: #3a3a3a; color: #eee; border: none; padding: 8px; border-radius: 6px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { background-color: #2a2a2a; color: #777; }
        """
        self.btn_speed_low.setStyleSheet(initial_speed_style)
        self.btn_speed_med.setStyleSheet(initial_speed_style)
        self.btn_speed_high.setStyleSheet(initial_speed_style)
        self.layout.addLayout(speed_layout)

        # ================= EQ =================
        self._add_separator()
        eq_title_layout = QHBoxLayout()
        eq_title = QLabel("EQ 调节")
        eq_title.setStyleSheet("font-weight: bold; color: #aaa;")
        self._muted_titles.append(eq_title)
        self.btn_eq_reset = QPushButton("重置")
        self.btn_eq_reset.setFixedSize(56, 28)
        self.btn_eq_reset.clicked.connect(self.reset_eq)

        eq_title_layout.addWidget(eq_title)
        eq_title_layout.addStretch()
        eq_title_layout.addWidget(self.btn_eq_reset)
        self.layout.addLayout(eq_title_layout)

        eq_layout = QGridLayout()
        eq_layout.setContentsMargins(0, 0, 0, 0)
        eq_layout.setHorizontalSpacing(2)
        eq_layout.setVerticalSpacing(5)

        # 关键修复：先在循环外创建空列表
        self.eq_sliders = []
        self.eq_labels = []
        self.eq_timers = []

        freqs = ["125Hz", "250Hz", "500Hz", "1kHz", "2kHz", "4kHz", "8kHz"]

        from functools import partial

        for i, freq in enumerate(freqs):
            # 标签
            lbl = QLabel(freq)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 10px; color: #888;")
            lbl.setFixedWidth(40)

            # 滑块
            slider = QSlider(Qt.Vertical)
            slider.setRange(-12, 12)
            slider.setValue(0)
            slider.setFixedHeight(100)
            slider.setFixedWidth(32)
            # 关键修复：使用 partial 绑定索引，避免 lambda 陷阱
            slider.valueChanged.connect(partial(self.on_eq_change, i))

            # 数值
            val_lbl = QLabel("0")
            val_lbl.setAlignment(Qt.AlignCenter)
            val_lbl.setStyleSheet("font-size: 10px; color: #00d2ff;")
            val_lbl.setFixedWidth(40)

            # 关键修复：先把定时器创建好并塞进列表，再连接信号
            eq_timer = QTimer()
            eq_timer.setSingleShot(True)
            eq_timer.timeout.connect(partial(self.send_eq, i))

            # 把滑块、标签、定时器按顺序添加到列表里
            self.eq_sliders.append(slider)
            self.eq_labels.append(val_lbl)
            self.eq_timers.append(eq_timer)

            eq_layout.addWidget(lbl, 0, i)
            eq_layout.addWidget(slider, 1, i, Qt.AlignHCenter)
            eq_layout.addWidget(val_lbl, 2, i)

        self.layout.addLayout(eq_layout)

        # 底部留白
        self.layout.addStretch()

        self.last_sent_volume = -1
        self.last_sent_brightness = -1
        # 初始化时默认禁用控制区（因为还没连上）
        self.content_widget.setEnabled(False)
        self.ignore_playback_update = False

        # 通用 UI 保护机制（防止拖动后底层回传旧数据导致滑块回弹）
        self.ignore_ui_update = {
            "volume": False,
            "brightness": False,
            "color": False,
            "eq": False,
        }

        # 统一管理解除保护的定时器
        self.ui_unlock_timer = QTimer(self)
        self.ui_unlock_timer.setSingleShot(True)
        self.ui_unlock_timer.timeout.connect(self.unlock_all_ui_updates)

        # ✅ 心跳检测：每 30 秒检查一次底层连接状态
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.check_heartbeat)
        self.heartbeat_timer.start(30000)  # 30 秒
        self.apply_color_scheme()

    def _add_separator(self):
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #444; margin: 10px 0;")
        self._separators.append(line)
        self.layout.addWidget(line)

    def show_near_tray(self):
        global GLOBAL_PANEL_POS
        x, y = GLOBAL_PANEL_POS
        screen = QApplication.primaryScreen().availableGeometry()
        # 边界保护
        x = max(10, min(x, screen.width() - self.width() - 10))
        y = max(10, min(y, screen.height() - self.height() - 10))

        self.move(x, y)

        self.on_connection_changed(self.controller.is_connected)  # 启动大窗口时更新ui


        self.show()
        self.raise_()
        self.activateWindow()
        if self.controller.is_connected:
            asyncio.create_task(self.controller.query_all_status())

    def apply_color_scheme(self):
        """切换/跟随主题时，重建全局样式 + 所有动态内联样式。"""
        self.setStyleSheet(QSS_DARK if current_is_dark() else QSS_LIGHT)
        # 歌曲信息：深色保持 #aaa，浅色改为 #969696
        self.song_label.set_text_color("#aaa" if current_is_dark() else "#7D7D7D")
        self._apply_header_btns()
        self._apply_media_btns()
        self._apply_speed_style()
        self._apply_theme_style()
        self._apply_brightness_qss()
        self._apply_titles()
        self._apply_separators()

    # ===== 主题相关：样式重建（自动跟随系统，无手动切换） =====
    def _header_btn_qss(self):
        t = theme_tokens()
        normal = ("QPushButton { background-color: transparent; border: none; "
                  "font-size: 15px; color: " + t["header_btn"] + "; }")
        hover = ("QPushButton:hover { color: " + t["header_hover_color"]
                 + "; background-color: " + t["header_hover_bg"] + "; border-radius: 4px; }")
        return normal + "\n" + hover

    def _apply_header_btns(self):
        qss = self._header_btn_qss()
        for b in self._header_btns:
            b.setStyleSheet(qss)

    def _media_btn_qss(self, size, font_px):
        t = theme_tokens()
        r = size // 2
        s1 = "QPushButton { font-family: 'Segoe MDL2 Assets'; font-size: " + str(font_px) + "px; border: none; background-color: " + t["round_bg"] + "; color: " + t["round_text"] + "; border-radius: " + str(r) + "px; }"
        s2 = "QPushButton:hover { background-color: " + t["round_hover"] + "; }"
        s3 = "QPushButton:pressed { background-color: " + t["round_press"] + "; }"
        s4 = "QPushButton:disabled { background-color: " + t["round_disabled_bg"] + "; color: " + t["round_disabled_text"] + "; }"
        return "\n".join([s1, s2, s3, s4])

    def _apply_media_btns(self):
        self.btn_prev.setStyleSheet(self._media_btn_qss(46, 18))
        self.btn_next.setStyleSheet(self._media_btn_qss(46, 18))
        self.update_play_style(self.btn_play.text() == ICON_PAUSE)

    def _apply_speed_style(self):
        sid = state.speed if state.speed in (1, 2, 3) else 0
        self._update_speed_ui(sid)

    def _apply_theme_style(self):
        theme_key = THEME_BY_ID.get(state.theme_id)
        if theme_key:
            self.update_theme_ui(theme_key)
            self.update_color_slider_gradient(theme_key)
        else:
            # 关键修复：未连接(无主题)时也要重建六个主题按钮样式，
            # 否则按钮会停留在构造时硬编码的深色禁用背景，浅色模式首启禁用态错误。
            self.update_theme_ui(None)
            self.update_color_slider_gradient("ocean")

    def _apply_brightness_qss(self):
        t = theme_tokens()
        qss = f"""
            QSlider#brightnessSlider::groove:horizontal {{
                height: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #505050, stop:1 #ffffff);
                border-radius: 6px;
            }}
            QSlider#brightnessSlider::groove:horizontal:disabled {{
                height: 12px;
                background: {t['bar_disabled']};
                border-radius: 6px;
            }}
            QSlider#brightnessSlider::handle:horizontal {{
                background: #fff;
                border: 2px solid {t['handle_border']};
                width: 16px; height: 16px; margin: -3px 0; border-radius: 9px;
            }}
            QSlider#brightnessSlider::handle:horizontal:disabled {{
                background: transparent; border: none;
            }}
        """
        self.bright_slider.setStyleSheet(qss)

    def _apply_titles(self):
        t = theme_tokens()
        for lbl in self._muted_titles:
            lbl.setStyleSheet(f"font-weight: bold; color: {t['muted_title']};")

    def _apply_separators(self):
        t = theme_tokens()
        for line in self._separators:
            line.setStyleSheet(f"background-color: {t['separator']}; margin: 10px 0;")

    # ================= 连接/断开 =================
    def toggle_connection(self):
        self.btn_conn.setEnabled(False)
        self.btn_conn.setText(ICON_SANDGLASS)
        if self.controller.is_connected:
            self.controller.set_manual_disconnect(True)
            self.spawn(self.disconnect_device())
        else:
            self.controller.set_manual_disconnect(False)
            self.spawn(self.connect_device())

    async def disconnect_device(self):
        await self.controller.disconnect()
        # 断开连接时，controller 会触发 on_connection_changed(False)
        # 所以我们不需要在这里写任何 ui 逻辑了

    async def connect_device(self):
        self.song_label.setText("正在扫描连接...")
        await self.controller.connect()
        # 连接成功后，controller 会触发 on_connection_changed(True)
        # 失败的话 controller 触发 on_connection_changed(False)

    def on_connection_changed(self, connected: bool):
        """底层蓝牙状态改变时，由 controller 自动触发"""
        self.btn_conn.setEnabled(True)

        if connected:
            # 1. 启用所有控件
            self.content_widget.setEnabled(True)
            # 2.
            self.btn_conn.setText(ICON_DISCONNECT)
            # self.btn_conn.setText(ICON_LINK)
            self.btn_conn.setStyleSheet(self._header_btn_qss())
            self.btn_conn.setToolTip("断开")
        else:
            # 1. 禁用所有控件
            self.content_widget.setEnabled(False)
            # 2.
            # self.btn_conn.setText(ICON_DISCONNECT)
            self.btn_conn.setText(ICON_LINK)
            self.btn_conn.setStyleSheet(self._header_btn_qss())
            self.song_label.setText("设备已断开，点击左上角连接")
            self.btn_conn.setToolTip("连接")

    def check_heartbeat(self):
        """每 10 秒主动发一次心跳查询，底层如果死了会触发 _send 的断开逻辑"""
        # 只有 UI 认为在连接时，才去发心跳
        if self.controller.is_connected and not self.controller._manual_disconnect:
            asyncio.create_task(self.controller.query_all_status())

    # ================= 音量防抖 =================
    def on_vol_change(self, value):
        self.vol_timer.start(50)

    def send_volume(self):
        value = self.vol_slider.value()
        # 如果值不对齐 3 的倍数，强行取最接近的 3 的倍数
        value = (value // 3) * 3
        if value != self.last_sent_volume:
            self.last_sent_volume = value
            self.lock_ui_update("volume")
            self.spawn(self.controller.set_volume(value))
            QTimer.singleShot(
                800, lambda: self.spawn(self.controller.query_all_status())
            )

    # ================= 播放函数 =================
    def on_play_click(self):
        # 当前如果是播放图标，说明用户想要播放
        if self.btn_play.text() == ICON_PLAY:
            self.update_play_style(True)
            self.spawn(self.controller.media_action("play"))
        else:
            self.update_play_style(False)  # 立刻变成灰色的播放图标
            self.spawn(self.controller.media_action("pause"))

        # 核心：开启 5 秒非阻塞保护
        self.ignore_playback_update = True
        QTimer.singleShot(5000, self.unlock_playback_update)

    def unlock_playback_update(self):
        """5秒后解除保护，恢复自动同步"""
        self.ignore_playback_update = False

    def update_play_style(self, is_playing):
        """根据播放状态更新按钮样式和图标"""
        if is_playing:
            self.btn_play.setText(ICON_PAUSE)
        else:
            self.btn_play.setText(ICON_PLAY)
        self.btn_play.setStyleSheet(self._media_btn_qss(60, 24))

    def lock_ui_update(self, key):
        """锁定某个滑动条，防止音箱回传旧状态覆盖"""
        self.ignore_ui_update[key] = True
        # 每次拖动都重置定时器，2 秒后统一解锁
        self.ui_unlock_timer.start(2000)

    def unlock_all_ui_updates(self):
        """5 秒后解除所有锁定，并主动同步一次最新状态"""
        for key in self.ignore_ui_update:
            self.ignore_ui_update[key] = False

    def refresh_state(self):
        """发送全量查询指令，重新拉取音箱所有状态"""
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText(ICON_SANDGLASS)  # 变个图标表示正在刷新
        self.spawn(self.controller.query_all_status())

        # 1 秒后恢复按钮，期间通知回包会自动更新 UI
        QTimer.singleShot(1000, self.unlock_refresh_button)

    def unlock_refresh_button(self):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText(ICON_REFRESH)

    # ================= 灯光控制 =================
    def toggle_light(self):
        # 根据当前状态直接发送相反的指令
        target_state = not (state.light_power or False)
        self.spawn(self.controller.set_light_power(target_state))

        # 乐观更新 UI 文字，让它瞬间切换
        if target_state:
            self.light_btn.setText("开")
            state.light_power = True
        else:
            self.light_btn.setText("关")
            state.light_power = False

    def on_theme_change(self, theme_key: str):
        """主题按钮点击：立即切换UI，后台发送指令"""
        if not theme_key:
            return

        # 1. 【立即切换】先更新本地状态和UI，无需等待蓝牙
        state.theme_id = THEME_BY_ID.get(
            theme_key
        )  # 假设 THEME_BY_ID 是 id->key 的反向映射，需根据实际情况调整
        self.update_theme_ui(theme_key)
        self.update_color_slider_gradient(theme_key)

        # 2. 【后台发送】异步发送指令，不阻塞主线程
        async def _send_and_sync():
            try:
                await self.controller.set_theme(theme_key)
                QTimer.singleShot(
                    500, lambda: asyncio.create_task(self.controller.query_all_status())
                )
                # 3. 【反馈后同步】指令成功后，controller 的 on_state_changed 会自动触发 update_ui
                # 这里不需要手动再调 update_theme_ui，避免重复刷新
            except Exception as e:
                print(f"主题切换失败: {e}")
                # 失败时回滚到真实状态（由 controller 的状态回调自动处理）

        self.spawn(_send_and_sync())

    def update_theme_ui(self, current_theme_key: str):
        """根据当前主题高亮对应按钮（安全重绘，不再使用 str.replace）"""
        # 预定义每个主题的渐变色（和初始化时保持一致）
        theme_gradients = {
            "ocean": "stop:0.00 #06DFBE, stop:0.50 #37ACFF, stop:1.00 #5B32FF",
            "aurora": "stop:0.00 #42EA66, stop:1.00 #0E8ED9",
            "blossom": "stop:0.00 #D786C5, stop:1.00 #8C53E8",
            "sunrise": "stop:0.00 #FF5359, stop:0.33 #F7A86B, stop:0.67 #EBCC6C, stop:1.00 #E1ED6E",
            "fireplace": "stop:0.00 #E7BA5A, stop:1.00 #F64302",
            "static": "stop:0.00 #FFE9C9, stop:0.20 #F5C96A, stop:0.40 #8FEA7F, stop:0.60 #66B9F2, stop:0.80 #D36BE5, stop:1.00 #F075A2",
        }

        for key, btn in self.theme_buttons.items():
            gradient = theme_gradients.get(key, "stop:0 #444, stop:1 #444")
            is_selected = key == current_theme_key

            # 根据选中状态生成完整样式，彻底避免 str.replace
            t = theme_tokens()
            border = f"3px solid {t['theme_sel_border']}" if is_selected else "2px solid transparent"
            color = "#fff; font-weight: bold" if is_selected else "#222"

            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {gradient});
                    border: {border};
                    border-radius: 8px;
                    font-size: 12px;
                    font-weight: bold;
                    color: {color};
                }}
                QPushButton:hover {{ border: 2px solid {t['theme_sel_border']}; }}
                QPushButton:disabled {{ background: {t['theme_disabled_bg']}; border: none; color: {t['theme_disabled_text']}; }}
            """)

    def update_color_slider_gradient(self, theme_key):
        """根据不同主题，动态生成颜色条渐变背景"""
        theme_colors = {
            "ocean": ["#06DFBE", "#37ACFF", "#5B32FF"],
            "aurora": ["#42EA66", "#0E8ED9"],
            "blossom": ["#D786C5", "#8C53E8"],
            "sunrise": ["#FF5359", "#F7A86B", "#EBCC6C", "#E1ED6E"],
            "fireplace": ["#E7BA5A", "#F64302"],
            "static": [
                "#FFE9C9",
                "#F5C96A",
                "#8FEA7F",
                "#66B9F2",
                "#D36BE5",
                "#F075A2",
            ],
        }

        colors = theme_colors.get(theme_key, ["#444", "#444"])

        # 动态生成 QSS 的渐变色 stop
        gradient_stops = ""
        for idx, color in enumerate(colors):
            stop_pos = idx / (len(colors) - 1)
            gradient_stops += f"stop:{stop_pos:.2f} {color}, "
        gradient_stops = gradient_stops.rstrip(", ")

        gradient_qss = f"""
            QSlider#colorSlider::groove:horizontal {{
                height: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {gradient_stops});
                border-radius: 6px;
            }}
            QSlider#colorSlider::groove:horizontal:disabled {{
                height: 12px;
                background: {theme_tokens()['bar_disabled']};
                border-radius: 6px;
            }}
            QSlider#colorSlider::handle:horizontal {{
                background: #fff;
                border: 2px solid {theme_tokens()['handle_border']};
                width: 16px;
                height: 16px;
                margin: -3px 0;
                border-radius: 9px;
            }}
            QSlider#colorSlider::handle:horizontal:disabled {{
                background: transparent;
                border: none;
            }}
        """
        self.color_slider.setStyleSheet(gradient_qss)

    def on_bright_change(self, value):
        self.bright_timer.start(50)

    def send_brightness(self):
        value = self.bright_slider.value()
        if value != self.last_sent_brightness:
            self.last_sent_brightness = value
            self.lock_ui_update("brightness")
            self.spawn(self.controller.set_brightness(value))
            QTimer.singleShot(
                800, lambda: self.spawn(self.controller.query_all_status())
            )

    # ================= 颜色与速度 =================
    def on_color_change(self, value):
        self.color_timer.start(50)

    def send_color(self):
        value = self.color_slider.value()
        self.lock_ui_update("color")
        self.spawn(self.controller.set_color(value))
        QTimer.singleShot(800, lambda: self.spawn(self.controller.query_all_status()))

    def reset_color(self):
        self.spawn(self.controller.reset_color())
        QTimer.singleShot(800, lambda: self.spawn(self.controller.query_all_status()))

    def set_speed(self, speed_str):
        """速度按钮点击：立即切换UI，后台发送指令"""
        # 1. 【立即切换】根据 speed_str 映射到数字 id（low=1, medium=2, high=3）
        speed_map = {"low": 1, "medium": 2, "high": 3}
        speed_id = speed_map.get(speed_str)
        if speed_id is None:
            return

        # 直接更新本地状态并刷新UI
        state.speed = speed_id
        self._update_speed_ui(speed_id)

        # 2. 【后台发送】
        async def _send_and_sync():
            try:
                await self.controller.set_speed(speed_str)
                QTimer.singleShot(
                    800, lambda: asyncio.create_task(self.controller.query_all_status())
                )
                # 成功后 controller 的 on_state_changed 会自动同步真实状态
            except Exception as e:
                print(f"速度切换失败: {e}")

        self.spawn(_send_and_sync())

    def _update_speed_ui(self, speed_id: int):
        """根据速度 id 更新三个按钮的样式"""
        t = theme_tokens()
        default_style = f"""
            QPushButton {{ background-color: {t['speed_default_bg']}; color: {t['speed_default_text']}; border: none; padding: 8px; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {t['speed_default_hover']}; }}
            QPushButton:pressed {{ background-color: {t['speed_default_press']}; }}
            QPushButton:disabled {{ background-color: {t['speed_default_bg']}; color: {t['speed_default_disabled_text']}; }}
        """
        active_style = f"""
            QPushButton {{ background-color: {t['speed_active_bg']}; color: {t['speed_active_text']}; font-weight: bold; border: none; padding: 8px; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {t['speed_active_hover']}; }}
            QPushButton:disabled {{ background-color: {t['speed_default_bg']}; color: {t['speed_default_disabled_text']}; }}
        """

        # 先全部重置为默认
        self.btn_speed_low.setStyleSheet(default_style)
        self.btn_speed_med.setStyleSheet(default_style)
        self.btn_speed_high.setStyleSheet(default_style)

        # 再高亮选中的
        if speed_id == 1:
            self.btn_speed_low.setStyleSheet(active_style)
        elif speed_id == 2:
            self.btn_speed_med.setStyleSheet(active_style)
        elif speed_id == 3:
            self.btn_speed_high.setStyleSheet(active_style)

    # ================= EQ 防抖 =================
    def on_eq_change(self, index, value):
        self.eq_labels[index].setText(str(value))
        self.eq_timers[index].start(50)

    def send_eq(self, index):
        steps = [slider.value() for slider in self.eq_sliders]
        self.lock_ui_update("eq")
        self.spawn(self.controller.set_eq(steps))

    def reset_eq(self):
        self.spawn(self.controller.reset_eq())
        QTimer.singleShot(800, lambda: self.spawn(self.controller.query_all_status()))

    # 类里加一个方法，把所有 create_task 换成它
    def spawn(self, coro, on_fail=None):
        task = asyncio.create_task(coro)

        def _done(t):
            exc = t.exception()
            if exc:
                print(f"指令执行失败: {exc}")
                if on_fail:
                    on_fail(exc)

        task.add_done_callback(_done)

    # ================= 状态刷新 =================
    def update_ui(self, s):
        # 音量
        if (
            s.volume is not None
            and not self.vol_slider.isSliderDown()
            and not self.ignore_ui_update["volume"]
        ):
            self.vol_slider.blockSignals(True)
            # 只有当音箱返回的值是对齐的 3 的倍数时才更新滑块（防止底层返回奇怪的数字导致滑块乱跳）
            rounded_vol = (s.volume // 3) * 3
            self.vol_slider.setValue(rounded_vol)
            self.vol_slider.blockSignals(False)
            self.last_sent_volume = rounded_vol

        # 灯光开关
        if s.light_power is not None:
            self.light_btn.setText("开" if s.light_power else "关")

        # 颜色
        if s.theme_id is not None and s.colors and not self.ignore_ui_update["color"]:
            current_color = s.colors.get(s.theme_id)
            if current_color is not None and not self.color_slider.isSliderDown():
                self.color_slider.blockSignals(True)
                self.color_slider.setValue(current_color)
                self.color_slider.blockSignals(False)

        # 亮度
        if (
            s.brightness is not None
            and not self.bright_slider.isSliderDown()
            and not self.ignore_ui_update["brightness"]
        ):
            self.bright_slider.blockSignals(True)
            self.bright_slider.setValue(s.brightness)
            self.bright_slider.blockSignals(False)
            self.last_sent_brightness = s.brightness

        # 速度
        if s.speed is not None:
            self._update_speed_ui(s.speed)

        # 主题 (平铺按钮版)
        if s.theme_id is not None:
            theme_key = THEME_BY_ID.get(s.theme_id)
            if theme_key:
                self.update_theme_ui(theme_key)
                self.update_color_slider_gradient(
                    theme_key
                )  # <--- 加这一行，同步颜色条渐变

        # === 音源输入 + 歌曲信息 ===
        source_label = AUDIO_SOURCE_LABELS.get(s.unknown_36, AUDIO_SOURCE_UNKNOWN)
        if s.unknown_36 in (1, None):
            # 蓝牙或未知：正常显示歌曲信息
            if s.track_title:
                self.song_label.setText(f"{s.track_title} - {s.artist}" if s.artist else s.track_title)
            else:
                self.song_label.setText("暂无歌曲信息")
        else:
            # AUX / HDMI：显示音源标识
            self.song_label.setText(source_label)

        # EQ
        if s.eq_gains_db is not None and not self.ignore_ui_update["eq"]:
            for i, slider in enumerate(self.eq_sliders):
                if not slider.isSliderDown():
                    val = int(s.eq_gains_db[i] * 2)
                    val = max(-12, min(12, val))
                    slider.blockSignals(True)
                    slider.setValue(val)
                    self.eq_labels[i].setText(str(val))
                    slider.blockSignals(False)

        # 播放状态自动同步
        if not self.ignore_playback_update:
            if s.playback == 2:
                self.update_play_style(True)
            elif s.playback == 1:
                self.update_play_style(False)


# ==========================================
# 主程序
# ==========================================
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    controller = SoundSticksController()
    panel = ControlPanel(controller)

    mini_panel = MiniPanel(controller)  # ← 新增

    # 迷你面板双击 → 打开完整面板
    mini_panel.open_full_panel.connect(panel.show_near_tray)

    loop.create_task(controller.connect())

    # 托盘图标：扬声器正面图，颜色跟随系统主题（深色=白，浅色=黑）
    def make_speaker_icon():
        icon_pixmap = QPixmap(64, 64)
        icon_pixmap.fill(Qt.transparent)
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(255, 255, 255) if current_is_dark() else QColor(0, 0, 0)

        # 1. 外圈圆环 (粗线，代表外围胶圈)
        pen_outer = painter.pen()
        pen_outer.setColor(color)
        pen_outer.setWidth(3)
        painter.setPen(pen_outer)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(4, 4, 56, 56)

        # 2. 内圈圆环 (细线，代表内部分割线)
        pen_inner = painter.pen()
        pen_inner.setColor(color)
        pen_inner.setWidth(1.5)
        painter.setPen(pen_inner)
        painter.drawEllipse(10, 10, 44, 44)

        # 3. 中心圆饼 (实心，代表扬声器纸盆)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(23, 23, 18, 18)

        painter.end()
        return QIcon(icon_pixmap)

    tray_icon = QSystemTrayIcon(make_speaker_icon(), app)
    tray_icon.setToolTip("SoundSticks 5 控制台")

    tray_menu = QMenu()
    exit_action = tray_menu.addAction("退出")
    exit_action.triggered.connect(app.quit)
    tray_icon.setContextMenu(tray_menu)

    # 系统深浅色实时切换：刷新大窗口、迷你面板与托盘图标
    def on_scheme_changed(*args):
        panel.apply_color_scheme()
        mini_panel.apply_color_scheme()
        tray_icon.setIcon(make_speaker_icon())

    try:
        QApplication.styleHints().colorSchemeChanged.connect(on_scheme_changed)
    except Exception:
        pass  # 老版本 PySide6 无此信号，仅启动时应用一次

    # 不再需要 _click_timer、_pending_single_click 等变量

    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.Trigger:
            if mini_panel.isVisible():
                mini_panel.hide()
            else:
                mini_panel.show_near_tray()

    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
