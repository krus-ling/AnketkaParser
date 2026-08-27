import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import asyncio
import sys

from brain import SurveyBrain
from engines.router import SurveyRouter
from bot_state import state


class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


class MainBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("E2E Bot - Панель управления")
        self.root.geometry("1100x700")
        self.root.configure(bg="#2b2b2b")

        self.async_loop = None  # Ссылка на асинхронный цикл браузера

        # --- 1. ВЕРХНЯЯ ПАНЕЛЬ: ВВОД URL ---
        url_frame = tk.Frame(root, bg="#2b2b2b")
        url_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        tk.Label(url_frame, text="URL опроса:", fg="#ffffff", bg="#2b2b2b", font=("Arial", 11, "bold")).pack(
            side=tk.LEFT)

        self.url_entry = tk.Entry(url_frame, font=("Arial", 11), bg="#3c3f41", fg="#ffffff", insertbackground="white",
                                  relief="flat")
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        self.btn_start = tk.Button(url_frame, text="▶ Запустить бота", bg="#0d6efd", fg="white",
                                   font=("Arial", 10, "bold"), relief="flat", cursor="hand2", command=self.start_bot)
        self.btn_start.pack(side=tk.RIGHT)

        # --- 2. ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ ---
        ctrl_frame = tk.Frame(root, bg="#2b2b2b")
        ctrl_frame.pack(fill=tk.X, padx=15, pady=5)

        self.btn_pause = tk.Button(ctrl_frame, text="⏸ Пауза", bg="#f0ad4e", fg="white", font=("Arial", 10, "bold"),
                                   relief="flat", cursor="hand2", width=12, state="disabled", command=self.toggle_pause)
        self.btn_pause.pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        self.chk_debug = tk.Checkbutton(ctrl_frame, text="Отладочный режим (Подтверждать нажатие «Далее»)",
                                        variable=self.debug_var, bg="#2b2b2b", fg="#a9b7c6", selectcolor="#3c3f41",
                                        activebackground="#2b2b2b", activeforeground="#ffffff", font=("Arial", 10),
                                        command=self.toggle_debug)
        self.chk_debug.pack(side=tk.LEFT, padx=20)

        self.btn_confirm = tk.Button(ctrl_frame, text="✅ Подтвердить шаг", bg="#198754", fg="white",
                                     font=("Arial", 10, "bold"), relief="flat", cursor="hand2", state="disabled",
                                     command=self.confirm_step)
        self.btn_confirm.pack(side=tk.LEFT)

        # --- 3. ПАНЕЛЬ ЛОГОВ ---
        log_frame = tk.Frame(root, bg="#1e1e1e")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 15))

        top_bar = tk.Frame(log_frame, bg="#1e1e1e")
        top_bar.pack(fill=tk.X, pady=(0, 5))
        tk.Label(top_bar, text="ТЕРМИНАЛ", fg="#a9b7c6", bg="#1e1e1e", font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        tk.Button(top_bar, text="Очистить", bg="#3c3f41", fg="#a9b7c6", font=("Arial", 8), relief="flat", padx=8,
                  pady=2, cursor="hand2", command=self.clear_logs).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_bar, text="📋 Скопировать", bg="#365880", fg="white", font=("Arial", 8, "bold"), relief="flat",
                  padx=10, pady=2, cursor="hand2", command=self.copy_logs).pack(side=tk.RIGHT)

        self.log_area = scrolledtext.ScrolledText(log_frame, bg="#1e1e1e", fg="#a9b7c6", insertbackground="white",
                                                  selectbackground="#214283", selectforeground="#ffffff",
                                                  font=("Consolas", 10), borderwidth=0, undo=False)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.bind("<Key>", self.prevent_manual_typing)

        sys.stdout = StdoutRedirector(self.log_area)
        print("✅ Боевой интерфейс готов. Вставьте ссылку на опрос и нажмите Запуск.")

    # --- ЛОГИКА GUI ---
    def prevent_manual_typing(self, event):
        if event.state & 0x4 and event.keysym.lower() in ('c', 'a'): return None
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Prior', 'Next', 'Home', 'End'): return None
        return "break"

    def copy_logs(self):
        logs = self.log_area.get("1.0", tk.END).strip()
        if logs:
            self.root.clipboard_clear()
            self.root.clipboard_append(logs)
            print("\n[✓] Логи скопированы!")

    def clear_logs(self):
        self.log_area.delete("1.0", tk.END)

    # --- ЛОГИКА УПРАВЛЕНИЯ БОТОМ ---
    def toggle_pause(self):
        state.is_paused = not state.is_paused

        # Безопасно передаем сигнал в асинхронный поток Playwright
        if self.async_loop:
            if state.is_paused:
                self.async_loop.call_soon_threadsafe(state.pause_event.clear)
                self.btn_pause.config(text="▶ Продолжить", bg="#28a745")
                print("\n[⏸] ПАУЗА. Бот замер и ждет команды...")
            else:
                self.async_loop.call_soon_threadsafe(state.pause_event.set)
                self.btn_pause.config(text="⏸ Пауза", bg="#f0ad4e")
                print("\n[▶] СНЯТО С ПАУЗЫ. Бот продолжает работу...")

    def toggle_debug(self):
        state.is_debug = self.debug_var.get()
        if state.is_debug:
            self.btn_confirm.config(state="normal")
            print(
                "\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВКЛЮЧЕН. Бот будет ждать подтверждения перед каждым переходом на новую страницу.")
        else:
            self.btn_confirm.config(state="disabled")
            print("\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВЫКЛЮЧЕН. Бот работает полностью автономно.")
            if self.async_loop and state.step_event and not state.step_event.is_set():
                self.async_loop.call_soon_threadsafe(state.step_event.set)

    def confirm_step(self):
        if self.async_loop and state.step_event:
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    def start_bot(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http"):
            messagebox.showerror("Ошибка", "Введите корректную ссылку (http...)")
            return

        self.clear_logs()
        self.btn_start.config(state="disabled", text="Бот работает...")
        self.url_entry.config(state="disabled")
        self.btn_pause.config(state="normal")

        print("=" * 60)
        print(f"🚀 Запуск боевого бота по ссылке: {url}")
        print("=" * 60)

        threading.Thread(target=self.run_playwright, args=(url,), daemon=True).start()

    def run_playwright(self, url):
        self.async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.async_loop)

        state.init_events()
        state.is_debug = self.debug_var.get()

        brain = SurveyBrain()
        router = SurveyRouter(brain=brain)

        try:
            self.async_loop.run_until_complete(router.run(url))
            print("\n[✅] ЗАВЕРШЕНО: Бот закончил обработку маршрутов.")
        except Exception as e:
            print(f"\n[❌] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        finally:
            self.async_loop.close()
            self.async_loop = None

            # Возвращаем кнопки в исходное состояние
            self.btn_start.config(state="normal", text="▶ Запустить бота")
            self.url_entry.config(state="normal")
            self.btn_pause.config(state="disabled", text="⏸ Пауза", bg="#f0ad4e")


if __name__ == "__main__":
    root = tk.Tk()
    app = MainBotApp(root)
    root.mainloop()