#!/usr/bin/env python3
"""
Cosmic Scrapper — простой кликер на Tkinter.
Функции:
- Клик по кораблю дает "Scrap" (металлолом)
- Магазин улучшений (увеличивает Scrap за клик или добавляет автосборщик)
- Задачи (чек-лист с целями и наградами)
- Прогресс: строительство станции (бар прогресса)
- Сохранение/загрузка в JSON

Запуск: python3 cosmic_scrapper_clicker.py
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import json
import os
import time
import threading

SAVEFILE = "cosmic_scrapper_save.json"

class GameState:
    def __init__(self):
        self.scrap = 0.0
        self.scrap_per_click = 1.0
        self.scrap_per_second = 0.0
        self.upgrades = {}
        self.tasks = {}
        self.station_progress = 0.0  # 0..100
        self.last_tick = time.time()

    def to_dict(self):
        return {
            'scrap': self.scrap,
            'scrap_per_click': self.scrap_per_click,
            'scrap_per_second': self.scrap_per_second,
            'upgrades': self.upgrades,
            'tasks': self.tasks,
            'station_progress': self.station_progress,
        }

    @classmethod
    def from_dict(cls, d):
        g = cls()
        g.scrap = d.get('scrap', 0.0)
        g.scrap_per_click = d.get('scrap_per_click', 1.0)
        g.scrap_per_second = d.get('scrap_per_second', 0.0)
        g.upgrades = d.get('upgrades', {})
        g.tasks = d.get('tasks', {})
        g.station_progress = d.get('station_progress', 0.0)
        return g


class Upgrade:
    def __init__(self, id, name, base_cost, effect_type, effect_value, description):
        self.id = id
        self.name = name
        self.base_cost = base_cost
        self.effect_type = effect_type  # 'click' or 'aps' (auto per second)
        self.effect_value = effect_value
        self.description = description

    def cost(self, owned):
        # cost grows multiplicatively
        return int(self.base_cost * (1.6 ** owned))


UPGRADE_DEFS = [
    Upgrade('laser_tools', 'Лазерные клещи', 10, 'click', 1.0, 'Увеличивает Scrap за клик.'),
    Upgrade('magnet_drones', 'Магнитные дроны', 50, 'aps', 0.5, 'Добавляет автосборщик (Scrap в секунду).'),
    Upgrade('scrap_refinery', 'Переработчик', 200, 'aps', 2.0, 'Ускоряет переработку мусора — больше APS.'),
    Upgrade('reinforced_hull', 'Усиленный корпус', 150, 'click', 5.0, 'Увеличивает прибыль с клика.'),
    Upgrade('station_module', 'Модуль станции', 1000, 'progress', 10.0, 'Добавляет прогресс к строительству станции при покупке.'),
]

TASK_DEFS = [
    # id, description, target (type, value), reward (scrap)
    ('collect_100', 'Собрать 100 Scrap', ('scrap_total', 100), 50),
    ('click_50', 'Сделать 50 кликов', ('clicks', 50), 30),
    ('build_25', 'Достичь 25% прогресса станции', ('station_progress', 25), 100),
]

class CosmicScrapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Cosmic Scrapper')
        self.geometry('720x480')
        self.resizable(False, False)

        self.state = GameState()
        self.total_clicks = 0
        self.total_scrap_earned = 0.0

        # load save if exists
        if os.path.exists(SAVEFILE):
            try:
                with open(SAVEFILE, 'r') as f:
                    data = json.load(f)
                    self.state = GameState.from_dict(data.get('state', {}))
                    self.total_clicks = data.get('total_clicks', 0)
                    self.total_scrap_earned = data.get('total_scrap_earned', 0.0)
            except Exception as e:
                print('Не удалось загрузить сохранение:', e)

        self.create_widgets()
        self.update_ui()
        self.running = True
        self.after(1000, self.game_tick)

    def create_widgets(self):
        left = tk.Frame(self, width=360, height=480)
        left.pack(side='left', fill='y')
        right = tk.Frame(self, width=360, height=480)
        right.pack(side='right', fill='y')

        # Ship button (big clickable)
        self.ship_btn = tk.Button(left, text='🚀Кликни корабль', font=('Arial', 20), command=self.click_ship)
        self.ship_btn.place(x=30, y=20, width=300, height=180)

        # Scrap display
        self.scrap_var = tk.StringVar()
        self.scrap_label = tk.Label(left, textvariable=self.scrap_var, font=('Consolas', 18))
        self.scrap_label.place(x=30, y=210)

        self.spc_label = tk.Label(left, text='', font=('Consolas', 10))
        self.spc_label.place(x=30, y=250)

        # Station progress
        tk.Label(left, text='Прогресс станции').place(x=30, y=280)
        self.progress = ttk.Progressbar(left, orient='horizontal', length=300, mode='determinate')
        self.progress.place(x=30, y=300)
        self.progress['maximum'] = 100

        # Buttons right side: store, tasks, save
        tk.Label(right, text='Магазин', font=('Arial', 14)).place(x=20, y=10)
        self.store_frame = tk.Frame(right)
        self.store_frame.place(x=20, y=40, width=320, height=200)
        self.populate_store()

        tk.Label(right, text='Задачи', font=('Arial', 14)).place(x=20, y=250)
        self.tasks_frame = tk.Frame(right)
        self.tasks_frame.place(x=20, y=280, width=320, height=120)
        self.populate_tasks()

        btn_frame = tk.Frame(right)
        btn_frame.place(x=20, y=410)
        tk.Button(btn_frame, text='Сохранить', command=self.save_game).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Загрузить', command=self.load_game).pack(side='left', padx=5)
        tk.Button(btn_frame, text='Сброс', command=self.reset_game).pack(side='left', padx=5)

    def populate_store(self):
        for widget in self.store_frame.winfo_children():
            widget.destroy()
        y = 0
        for u in UPGRADE_DEFS:
            owned = self.state.upgrades.get(u.id, 0)
            cost = u.cost(owned)
            b = tk.Button(self.store_frame, text=f"{u.name} (x{owned}) - {cost} Scrap\n{u.description}",
                          anchor='w', justify='left', command=lambda u=u: self.buy_upgrade(u))
            b.place(x=0, y=y, width=310, height=40)
            y += 44

    def populate_tasks(self):
        for widget in self.tasks_frame.winfo_children():
            widget.destroy()
        y = 0
        for tid, desc, target, reward in TASK_DEFS:
            status = self.state.tasks.get(tid, 'incomplete')
            txt = f"{desc} - {'Выполнено' if status=='done' else 'Ожидает'}"
            lbl = tk.Label(self.tasks_frame, text=txt, anchor='w')
            lbl.place(x=0, y=y, width=240, height=20)
            if status != 'done':
                btn = tk.Button(self.tasks_frame, text='Проверить', command=lambda tid=tid: self.check_task(tid))
                btn.place(x=250, y=y, width=60, height=20)
            y += 26

    def click_ship(self):
        self.state.scrap += self.state.scrap_per_click
        self.total_clicks += 1
        self.total_scrap_earned += self.state.scrap_per_click
        # small animation: shrink and grow
        self.ship_btn.config(font=('Arial', 18))
        self.after(100, lambda: self.ship_btn.config(font=('Arial', 20)))
        self.check_auto_tasks()
        self.update_ui()

    def buy_upgrade(self, upgrade: Upgrade):
        owned = self.state.upgrades.get(upgrade.id, 0)
        cost = upgrade.cost(owned)
        if self.state.scrap < cost:
            messagebox.showinfo('Недостаточно Scrap', f'Нужно {cost} Scrap, у вас {int(self.state.scrap)}')
            return
        self.state.scrap -= cost
        self.state.upgrades[upgrade.id] = owned + 1
        # apply effect
        if upgrade.effect_type == 'click':
            self.state.scrap_per_click += upgrade.effect_value
        elif upgrade.effect_type == 'aps':
            self.state.scrap_per_second += upgrade.effect_value
        elif upgrade.effect_type == 'progress':
            self.state.station_progress = min(100.0, self.state.station_progress + upgrade.effect_value)
        self.populate_store()
        self.update_ui()

    def check_task(self, tid):
        # find task def
        tdef = next((t for t in TASK_DEFS if t[0]==tid), None)
        if not tdef:
            return
        _, desc, target, reward = tdef
        ttype, tval = target
        complete = False
        if ttype == 'scrap_total':
            if self.total_scrap_earned >= tval or self.state.scrap >= tval:
                complete = True
        elif ttype == 'clicks':
            if self.total_clicks >= tval:
                complete = True
        elif ttype == 'station_progress':
            if self.state.station_progress >= tval:
                complete = True
        if complete:
            self.state.tasks[tid] = 'done'
            self.state.scrap += reward
            messagebox.showinfo('Задача выполнена', f'Вы получили {reward} Scrap!')
            self.populate_tasks()
            self.update_ui()
        else:
            messagebox.showinfo('Еще не готово', 'Условия задачи ещё не выполнены.')

    def check_auto_tasks(self):
        # simple check: if scrap >=100 and task not done, mark available (user still must press Check)
        for tid, desc, target, reward in TASK_DEFS:
            if self.state.tasks.get(tid) == 'done':
                continue
            ttype, tval = target
            if ttype == 'scrap_total' and self.total_scrap_earned >= tval:
                # mark as available — we'll leave it for user to press Check
                pass

    def update_ui(self):
        self.scrap_var.set(f"Scrap: {int(self.state.scrap)}")
        self.spc_label.config(text=f"За клик: {self.state.scrap_per_click:.1f} | Автосбор: {self.state.scrap_per_second:.1f}/с")
        self.progress['value'] = self.state.station_progress

    def game_tick(self):
        if not self.running:
            return
        now = time.time()
        elapsed = now - self.state.last_tick
        self.state.last_tick = now
        # add auto scrap
        gain = self.state.scrap_per_second * elapsed
        if gain:
            self.state.scrap += gain
            self.total_scrap_earned += gain
        # passive station progress from scrap: every 500 scrap = 1% station
        progress_gain = (gain / 500.0) * 1.0
        if progress_gain:
            self.state.station_progress = min(100.0, self.state.station_progress + progress_gain)
        # if station reaches 100, reward and reset progress
        if self.state.station_progress >= 100.0:
            messagebox.showinfo('Станция готова!', 'Вы завершили строительство станции — награда 1000 Scrap!')
            self.state.scrap += 1000
            self.state.station_progress = 0.0
        self.update_ui()
        self.after(1000, self.game_tick)

    def save_game(self):
        data = {
            'state': self.state.to_dict(),
            'total_clicks': self.total_clicks,
            'total_scrap_earned': self.total_scrap_earned,
            'saved_at': time.time()
        }
        try:
            with open(SAVEFILE, 'w') as f:
                json.dump(data, f)
            messagebox.showinfo('Сохранено', 'Прогресс сохранён.')
        except Exception as e:
            messagebox.showerror('Ошибка', f'Не удалось сохранить: {e}')

    def load_game(self):
        if not os.path.exists(SAVEFILE):
            messagebox.showinfo('Нет сохранения', 'Файл сохранения не найден.')
            return
        try:
            with open(SAVEFILE, 'r') as f:
                data = json.load(f)
                self.state = GameState.from_dict(data.get('state', {}))
                self.total_clicks = data.get('total_clicks', 0)
                self.total_scrap_earned = data.get('total_scrap_earned', 0.0)
            self.populate_store()
            self.populate_tasks()
            self.update_ui()
            messagebox.showinfo('Загружено', 'Сохранение загружено.')
        except Exception as e:
            messagebox.showerror('Ошибка', f'Не удалось загрузить: {e}')

    def reset_game(self):
        if messagebox.askyesno('Сброс', 'Вы уверены, что хотите начать сначала?'):
            try:
                if os.path.exists(SAVEFILE):
                    os.remove(SAVEFILE)
            except:
                pass
            self.state = GameState()
            self.total_clicks = 0
            self.total_scrap_earned = 0.0
            self.populate_store()
            self.populate_tasks()
            self.update_ui()

    def on_close(self):
        self.running = False
        self.save_game()
        self.destroy()


if __name__ == '__main__':
    app = CosmicScrapperApp()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()
