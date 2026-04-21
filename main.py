# -*- coding: utf-8 -*-
"""
A股分钟波动监控 - Kivy版 (Android APP)
功能：
1. 交易时间(9:15-15:01)每分钟监测涨跌幅变幅
2. 分钟变幅>0.5%发送邮件预警
3. 支持持仓量、持仓金额显示
4. 生成Android APK安装包
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.properties import StringProperty, NumericProperty, ListProperty, ObjectProperty
from kivy.clock import Clock
from kivy.metrics import dp

import requests
import re
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, time as dt_time
import socket
import os

# ========== 配置 ==========
CONFIG_FILE = "stock_monitor_config.json"
SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465
SENDER_EMAIL = "yinnxin0@163.com"
SENDER_PASSWORD = "DKxM76ygJByqkh6t"
RECEIVER_EMAIL = "1501965916@qq.com"
CHANGE_THRESHOLD = 0.5

# 修复主机名
socket.getfqdn = lambda: "localhost"


def get_market(code):
    """判断市场"""
    if code.startswith(("60", "68", "51", "52", "58", "50", "56")):
        return "sh"
    elif code.startswith(("00", "30", "15", "16", "11", "12")):
        return "sz"
    return None


class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior,
                                  RecycleBoxLayout):
    ''' 可选择的列表布局 '''
    pass


class StockListItem(BoxLayout):
    ''' 单行股票数据 '''
    index_text = StringProperty("")
    code = StringProperty("")
    name = StringProperty("")
    price = StringProperty("")
    change_pct = StringProperty("")
    minute_change = StringProperty("")
    volume = StringProperty("0")
    amount = StringProperty("0.00")
    
    def on_volume(self, instance, value):
        ''' 持仓量变化时更新金额 '''
        try:
            price = float(self.price) if self.price else 0
            vol = int(value) if value else 0
            self.amount = f"{vol * price:,.2f}"
        except:
            self.amount = "0.00"


class StockMonitorUI(BoxLayout):
    ''' 主界面 '''
    stock_data = ListProperty([])
    selected_index = NumericProperty(-1)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        
        self.stock_list = []  # [{'code': '000001', 'volume': 1000}, ...]
        self.price_cache = {}  # {code: {'prev': 10.0, 'current': 10.1}}
        self.is_monitoring = False
        self.monitor_event = None
        
        self.load_config()
        self.build_ui()
        Clock.schedule_once(self.ask_modify_list, 0.5)
        
    def load_config(self):
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.stock_list = data.get("stocks", [])
            except:
                pass
                
    def save_config(self):
        config_path = self.get_config_path()
        data = {"stocks": self.stock_list}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.log("配置已保存")
            
    def get_config_path(self):
        # Android: /data/data/org.test.stockmonitor/files/
        # Windows: 当前目录
        if hasattr(App, 'get_running_app'):
            app = App.get_running_app()
            if app and hasattr(app, 'user_data_dir'):
                return os.path.join(app.user_data_dir, CONFIG_FILE)
        return os.path.join(os.path.dirname(__file__), CONFIG_FILE)
        
    def build_ui(self):
        ''' 构建界面 '''
        # 顶部控制按钮
        top_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5), padding=dp(5))
        
        self.btn_start = Button(text="开始监控", font_size='16sp')
        self.btn_start.bind(on_press=self.start_monitoring)
        top_bar.add_widget(self.btn_start)
        
        self.btn_stop = Button(text="停止监控", font_size='16sp', disabled=True)
        self.btn_stop.bind(on_press=self.stop_monitoring)
        top_bar.add_widget(self.btn_stop)
        
        btn_refresh = Button(text="刷新价格", font_size='16sp')
        btn_refresh.bind(on_press=lambda x: self.refresh_prices())
        top_bar.add_widget(btn_refresh)
        
        self.add_widget(top_bar)
        
        # 状态栏
        self.status_label = Label(text="状态: 未启动", size_hint_y=None, height=dp(30),
                                   font_size='14sp', halign='left', valign='middle')
        self.status_label.bind(size=self.status_label.setter('text_size'))
        self.add_widget(self.status_label)
        
        # 表头
        header = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(2))
        headers = ["序号", "代码", "名称", "当前价", "涨跌幅%", "分钟变幅%", "持仓量", "持仓金额"]
        widths = [0.06, 0.12, 0.18, 0.12, 0.12, 0.13, 0.12, 0.15]
        for h, w in zip(headers, widths):
            lbl = Label(text=h, font_size='13sp', bold=True,
                       size_hint_x=w, color=(0.9, 0.9, 0.9, 1))
            with lbl.canvas.before:
                from kivy.graphics import Color, Rectangle
                Color(0.2, 0.4, 0.6, 1)
                lbl.rect = Rectangle(pos=lbl.pos, size=lbl.size)
                lbl.bind(pos=lambda i, v, r=lbl.rect: setattr(r, 'pos', v),
                        size=lambda i, v, r=lbl.rect: setattr(r, 'size', v))
            header.add_widget(lbl)
        self.add_widget(header)
        
        # 股票列表 (使用 ScrollView + GridLayout)
        self.list_container = BoxLayout(orientation='vertical')
        self.scroll = ScrollView()
        self.scroll.add_widget(self.list_container)
        self.add_widget(self.scroll)
        
        # 管理按钮
        btn_bar = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(3), padding=dp(3))
        
        btn_add = Button(text="添加股票", font_size='14sp')
        btn_add.bind(on_press=self.add_stock)
        btn_bar.add_widget(btn_add)
        
        btn_del = Button(text="删除选中", font_size='14sp')
        btn_del.bind(on_press=self.delete_stock)
        btn_bar.add_widget(btn_del)
        
        btn_up = Button(text="↑上移", font_size='14sp')
        btn_up.bind(on_press=lambda x: self.move_stock(-1))
        btn_bar.add_widget(btn_up)
        
        btn_down = Button(text="↓下移", font_size='14sp')
        btn_down.bind(on_press=lambda x: self.move_stock(1))
        btn_bar.add_widget(btn_down)
        
        btn_edit = Button(text="修改持仓", font_size='14sp')
        btn_edit.bind(on_press=self.edit_volume)
        btn_bar.add_widget(btn_edit)
        
        btn_save = Button(text="保存列表", font_size='14sp')
        btn_save.bind(on_press=lambda x: self.save_config())
        btn_bar.add_widget(btn_save)
        
        self.add_widget(btn_bar)
        
        # 日志区
        log_box = BoxLayout(size_hint_y=None, height=dp(100), orientation='vertical')
        log_label = Label(text="日志:", size_hint_y=None, height=dp(20), font_size='12sp', halign='left')
        log_box.add_widget(log_label)
        
        self.log_text = TextInput(text="", readonly=True, font_size='11sp',
                                  background_color=(0.95, 0.95, 0.95, 1))
        log_box.add_widget(self.log_text)
        self.add_widget(log_box)
        
        # 刷新列表
        self.refresh_list()
        
    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.text += f"[{timestamp}] {msg}\n"
        self.log_text.cursor = (0, len(self.log_text.text.split('\n')))
        
    def ask_modify_list(self, dt):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text="是否修改监控股票列表？\n\n选择【是】可添加/删除股票\n选择【否】使用已有列表",
                                font_size='16sp'))
        
        popup = Popup(title="监控列表", content=content, size_hint=(0.8, 0.5))
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        btn_yes = Button(text="是")
        btn_no = Button(text="否")
        btn_box.add_widget(btn_yes)
        btn_box.add_widget(btn_no)
        content.add_widget(btn_box)
        
        btn_yes.bind(on_press=lambda x: setattr(popup, 'dismiss', True) or popup.dismiss())
        btn_no.bind(on_press=lambda x: setattr(popup, 'dismiss', True) or popup.dismiss())
        
        popup.open()
        
    def fetch_stock_data(self, code):
        market = get_market(code)
        if market:
            return self._fetch_by_market(code, market)
        for m in ["sh", "sz"]:
            result = self._fetch_by_market(code, m)
            if result:
                return result
        return None
        
    def _fetch_by_market(self, code, market):
        try:
            url = f"https://web.sqt.gtimg.cn/q={market}{code}"
            headers = {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            resp.encoding = "gbk"
            
            match = re.search(r'v_\w+="([^"]+)"', resp.text)
            if match:
                parts = match.group(1).split("~")
                if len(parts) >= 5:
                    name = parts[1]
                    current = float(parts[3]) if parts[3] else None
                    prev_close = float(parts[4]) if parts[4] else None
                    if name and current:
                        return {"name": name, "current": current, "prev_close": prev_close}
        except Exception as e:
            self.log(f"获取 {code} 失败: {e}")
        return None
        
    def refresh_list(self):
        ''' 刷新列表显示 '''
        self.list_container.clear_widgets()
        
        for i, stock in enumerate(self.stock_list):
            code = stock.get("code", "")
            volume = stock.get("volume", 0)
            
            # 获取价格数据
            data = self.fetch_stock_data(code)
            if data:
                name = data["name"]
                price = f"{data['current']:.3f}"
                change = ((data['current'] - data['prev_close']) / data['prev_close'] * 100) if data['prev_close'] else 0
                change_pct = f"{change:+.2f}"
                
                # 计算分钟变幅
                cache = self.price_cache.get(code, {})
                if 'current' in cache and cache['current']:
                    minute_change = ((data['current'] - cache['current']) / cache['current'] * 100)
                else:
                    minute_change = 0
                minute_str = f"{minute_change:+.3f}"
                
                # 更新缓存
                self.price_cache[code] = {'current': data['current'], 'prev': data['prev_close']}
                
                # 持仓金额
                amount = f"{volume * data['current']:,.2f}"
            else:
                name = "--"
                price = "--"
                change_pct = "--"
                minute_str = "--"
                amount = "0.00"
            
            # 创建行
            row = BoxLayout(size_hint_y=None, height=dp(35), spacing=dp(2))
            row_data = [
                (str(i + 1), 0.06),
                (code, 0.12),
                (name, 0.18),
                (price, 0.12),
                (change_pct, 0.12),
                (minute_str, 0.13),
                (str(volume), 0.12),
                (amount, 0.15)
            ]
            
            # 根据涨跌设置颜色
            if change_pct.startswith('+'):
                color = (1, 0.3, 0.3, 1)  # 红
            elif change_pct.startswith('-'):
                color = (0.3, 0.7, 0.3, 1)  # 绿
            else:
                color = (0.2, 0.2, 0.2, 1)
            
            for text, width in row_data:
                lbl = Label(text=text, font_size='13sp', size_hint_x=width, color=color)
                row.add_widget(lbl)
            
            # 绑定点击事件
            row.bind(on_touch_down=self.make_select_handler(i))
            self.list_container.add_widget(row)
            
    def make_select_handler(self, index):
        def handler(instance, touch):
            if instance.collide_point(*touch.pos):
                self.selected_index = index
                self.log(f"选中第 {index + 1} 行")
        return handler
        
    def add_stock(self, instance):
        ''' 添加股票 '''
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        content.add_widget(Label(text="请输入6位股票代码:", font_size='14sp'))
        entry_code = TextInput(hint_text="例如: 000001", font_size='16sp', multiline=False)
        content.add_widget(entry_code)
        
        content.add_widget(Label(text="持仓量(股):", font_size='14sp'))
        entry_vol = TextInput(hint_text="例如: 1000", font_size='16sp', multiline=False, text="0")
        content.add_widget(entry_vol)
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        btn_ok = Button(text="确定")
        btn_cancel = Button(text="取消")
        btn_box.add_widget(btn_ok)
        btn_box.add_widget(btn_cancel)
        content.add_widget(btn_box)
        
        popup = Popup(title="添加股票", content=content, size_hint=(0.85, 0.6))
        
        def do_add(instance):
            code = entry_code.text.strip()
            vol_text = entry_vol.text.strip()
            
            if len(code) != 6 or not code.isdigit():
                self.show_popup("提示", "请输入正确的6位股票代码")
                return
            
            if any(s["code"] == code for s in self.stock_list):
                self.show_popup("提示", f"代码 {code} 已在列表中")
                return
            
            try:
                volume = int(vol_text) if vol_text else 0
            except:
                volume = 0
            
            self.log(f"正在获取 {code} 数据...")
            data = self.fetch_stock_data(code)
            
            if data:
                self.stock_list.append({"code": code, "volume": volume})
                self.save_config()
                self.refresh_list()
                self.log(f"已添加 {code} {data['name']}")
                popup.dismiss()
            else:
                self.show_popup("错误", f"无法获取 {code} 的数据")
                
        btn_ok.bind(on_press=do_add)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()
        
    def delete_stock(self, instance):
        ''' 删除选中股票 '''
        if self.selected_index < 0 or self.selected_index >= len(self.stock_list):
            self.show_popup("提示", "请先选择要删除的股票")
            return
        
        stock = self.stock_list[self.selected_index]
        code = stock.get("code", "")
        
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=f"确定删除 {code} ？", font_size='16sp'))
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        btn_yes = Button(text="确定")
        btn_no = Button(text="取消")
        btn_box.add_widget(btn_yes)
        btn_box.add_widget(btn_no)
        content.add_widget(btn_box)
        
        popup = Popup(title="确认删除", content=content, size_hint=(0.7, 0.4))
        
        def do_delete(instance):
            del self.stock_list[self.selected_index]
            self.selected_index = -1
            self.save_config()
            self.refresh_list()
            self.log(f"已删除 {code}")
            popup.dismiss()
            
        btn_yes.bind(on_press=do_delete)
        btn_no.bind(on_press=popup.dismiss)
        popup.open()
        
    def move_stock(self, direction):
        ''' 移动股票顺序 '''
        if self.selected_index < 0:
            self.show_popup("提示", "请先选择要移动的股票")
            return
        
        new_index = self.selected_index + direction
        if new_index < 0 or new_index >= len(self.stock_list):
            return
            
        self.stock_list[self.selected_index], self.stock_list[new_index] = \
            self.stock_list[new_index], self.stock_list[self.selected_index]
        self.selected_index = new_index
        self.refresh_list()
        self.log(f"移动到第 {new_index + 1} 位")
        
    def edit_volume(self, instance):
        ''' 修改持仓量 '''
        if self.selected_index < 0 or self.selected_index >= len(self.stock_list):
            self.show_popup("提示", "请先选择要修改的股票")
            return
        
        stock = self.stock_list[self.selected_index]
        code = stock.get("code", "")
        current_vol = stock.get("volume", 0)
        
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=f"修改 {code} 的持仓量:", font_size='14sp'))
        entry = TextInput(text=str(current_vol), font_size='16sp', multiline=False, 
                         input_filter='int', hint_text="持仓股数")
        content.add_widget(entry)
        
        btn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
        btn_ok = Button(text="确定")
        btn_cancel = Button(text="取消")
        btn_box.add_widget(btn_ok)
        btn_cancel = Button(text="取消")
        btn_box.add_widget(btn_ok)
        btn_box.add_widget(btn_cancel)
        content.add_widget(btn_box)
        
        popup = Popup(title="修改持仓量", content=content, size_hint=(0.8, 0.45))
        
        def do_edit(instance):
            try:
                volume = int(entry.text) if entry.text else 0
            except:
                volume = 0
            self.stock_list[self.selected_index]["volume"] = volume
            self.save_config()
            self.refresh_list()
            self.log(f"{code} 持仓量改为 {volume}")
            popup.dismiss()
            
        btn_ok.bind(on_press=do_edit)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()
        
    def show_popup(self, title, message):
        content = BoxLayout(orientation='vertical', padding=dp(20))
        content.add_widget(Label(text=message, font_size='16sp'))
        btn = Button(text="确定", size_hint_y=None, height=dp(50))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.7, 0.4))
        btn.bind(on_press=popup.dismiss)
        popup.open()
        
    def start_monitoring(self, instance):
        ''' 开始监控 '''
        if not self.stock_list:
            self.show_popup("提示", "监控列表为空，请先添加股票")
            return
        
        self.is_monitoring = True
        self.btn_start.disabled = True
        self.btn_stop.disabled = False
        self.status_label.text = "状态: 监控中..."
        self.status_label.color = (0, 0.7, 0, 1)
        self.log("开始监控")
        
        # 每分钟刷新
        self.monitor_event = Clock.schedule_interval(self.monitor_tick, 60)
        
        # 立即刷新一次
        self.monitor_tick(0)
        
    def stop_monitoring(self, instance):
        ''' 停止监控 '''
        self.is_monitoring = False
        self.btn_start.disabled = False
        self.btn_stop.disabled = True
        self.status_label.text = "状态: 已停止"
        self.status_label.color = (0.5, 0.5, 0.5, 1)
        self.log("停止监控")
        
        if self.monitor_event:
            self.monitor_event.cancel()
            self.monitor_event = None
            
    def monitor_tick(self, dt):
        ''' 监控周期 '''
        now = datetime.now()
        current_time = now.time()
        
        # 检查是否交易时间
        market_open = dt_time(9, 15)
        market_close = dt_time(15, 1)
        
        if current_time < market_open or current_time > market_close:
            self.log("非交易时间，跳过检测")
            return
        
        self.refresh_prices(check_alert=True)
        
    def refresh_prices(self, check_alert=False):
        ''' 刷新价格 '''
        self.log("刷新价格...")
        
        for stock in self.stock_list:
            code = stock.get("code", "")
            data = self.fetch_stock_data(code)
            
            if data:
                cache = self.price_cache.get(code, {})
                prev_cache_price = cache.get('current')
                
                # 计算分钟变幅
                if prev_cache_price and prev_cache_price > 0:
                    minute_change = ((data['current'] - prev_cache_price) / prev_cache_price * 100)
                    
                    # 预警检测
                    if check_alert and abs(minute_change) >= CHANGE_THRESHOLD:
                        self.send_alert(code, data['name'], minute_change)
                
                # 更新缓存
                self.price_cache[code] = {'current': data['current'], 'prev': data['prev_close']}
        
        self.refresh_list()
        
    def send_alert(self, code, name, change):
        ''' 发送预警邮件 '''
        try:
            subject = f"【A股预警】{code} {name} 分钟变幅 {change:+.2f}%"
            body = f"""
A股分钟波动预警

股票代码: {code}
股票名称: {name}
分钟变幅: {change:+.2f}%
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

阈值: {CHANGE_THRESHOLD}%
            """
            
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = SENDER_EMAIL
            msg["To"] = RECEIVER_EMAIL
            
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            
            self.log(f"已发送预警邮件: {code} {change:+.2f}%")
        except Exception as e:
            self.log(f"发送邮件失败: {e}")


class StockMonitorApp(App):
    def build(self):
        self.title = "A股分钟波动监控"
        return StockMonitorUI()
    
    def get_application_config(self):
        return super().get_application_config()


if __name__ == "__main__":
    StockMonitorApp().run()
