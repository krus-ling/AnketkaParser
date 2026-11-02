import os
import shutil
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import asyncio
import sys
import subprocess
from core import config

from core.brain import SurveyBrain
from engines.router import SurveyRouter
from core.bot_state import state


class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        if not string:
            return
        try:
            # Потокобезопасная отправка в GUI через after
            self.text_widget.after(0, self._append_text, string)
        except Exception:
            pass

    def _append_text(self, string):
        try:
            self.text_widget.insert(tk.END, string)
            self.text_widget.see(tk.END)
        except Exception:
            pass

    def flush(self):
        pass


class MainBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("E2E Bot - Панель управления")
        self.root.geometry("1150x700")
        self.root.configure(bg="#2b2b2b")

        self.async_loop = None
        self.history_file = "data/url_history.txt"
        self.url_history = self.load_history()

        # --- 1. ВЕРХНЯЯ ПАНЕЛЬ: ВВОД URL ---
        url_frame = tk.Frame(root, bg="#2b2b2b")
        url_frame.pack(fill=tk.X, padx=15, pady=(15, 5))

        tk.Label(url_frame, text="URL опроса:", fg="#ffffff", bg="#2b2b2b", font=("Arial", 11, "bold")).pack(
            side=tk.LEFT)

        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure("Dark.TCombobox",
                        fieldbackground="#3c3f41",
                        background="#2b2b2b",
                        foreground="#ffffff",
                        arrowcolor="#ffffff",
                        insertcolor="white")

        self.url_entry = ttk.Combobox(url_frame, values=self.url_history, font=("Arial", 11), style="Dark.TCombobox")
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        if self.url_history:
            self.url_entry.set(self.url_history[0])

        self.btn_restart = tk.Button(url_frame, text="🔄 Перезагрузить", bg="#6c757d", fg="white",
                                     font=("Arial", 10, "bold"), relief="flat", cursor="hand2",
                                     command=self.restart_app)
        self.btn_restart.pack(side=tk.RIGHT, padx=(10, 0))

        self.btn_start = tk.Button(url_frame, text="▶ Запустить бота", bg="#0d6efd", fg="white",
                                   font=("Arial", 10, "bold"), relief="flat", cursor="hand2", command=self.start_bot)
        self.btn_start.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_hub = tk.Button(url_frame, text="🌐 Центр Опросов (Все сайты)", bg="#6f42c1", fg="white",
                                 font=("Arial", 10, "bold"), relief="flat", cursor="hand2", command=self.start_multi_hub)
        self.btn_hub.pack(side=tk.RIGHT)

        # --- 2. ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ ---
        ctrl_frame = tk.Frame(root, bg="#2b2b2b")
        ctrl_frame.pack(fill=tk.X, padx=15, pady=5)

        self.btn_pause = tk.Button(ctrl_frame, text="⏸ Пауза", bg="#f0ad4e", fg="white", font=("Arial", 10, "bold"),
                                   relief="flat", cursor="hand2", width=12, state="disabled", command=self.toggle_pause)
        self.btn_pause.pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        self.chk_debug = tk.Checkbutton(ctrl_frame, text="Отладочный режим",
                                        variable=self.debug_var, bg="#2b2b2b", fg="#a9b7c6", selectcolor="#3c3f41",
                                        activebackground="#2b2b2b", activeforeground="#ffffff", font=("Arial", 10),
                                        command=self.toggle_debug)
        self.chk_debug.pack(side=tk.LEFT, padx=15)

        self.btn_confirm = tk.Button(ctrl_frame, text="✅ Подтвердить шаг", bg="#198754", fg="white",
                                     font=("Arial", 10, "bold"), relief="flat", cursor="hand2", state="disabled",
                                     command=self.confirm_step)
        self.btn_confirm.pack(side=tk.LEFT)

        # Кнопка активна ТОЛЬКО при включенной отладке
        self.btn_alt = tk.Button(ctrl_frame, text="🔄 Ответить иначе", bg="#17a2b8", fg="white",
                                 font=("Arial", 10, "bold"), relief="flat", cursor="hand2", state="disabled",
                                 command=self.answer_differently)
        self.btn_alt.pack(side=tk.LEFT, padx=(15, 0))

        self.btn_snapshot = tk.Button(ctrl_frame, text="📸 Снимок", bg="#6f42c1", fg="white",
                                      font=("Arial", 10, "bold"), relief="flat", cursor="hand2", state="disabled",
                                      command=self.take_manual_snapshot)
        self.btn_snapshot.pack(side=tk.LEFT, padx=15)

        self.human_var = tk.BooleanVar(value=getattr(config, "HUMAN_LIKE_DELAYS", True))
        self.chk_human = tk.Checkbutton(ctrl_frame, text="🛡 Антифрод (паузы)",
                                        variable=self.human_var, bg="#2b2b2b", fg="#a9b7c6", selectcolor="#3c3f41",
                                        activebackground="#2b2b2b", activeforeground="#ffffff", font=("Arial", 10),
                                        command=self.toggle_human)
        self.chk_human.pack(side=tk.LEFT, padx=5)

        self.farm_var = tk.BooleanVar(value=True)
        self.chk_farm = tk.Checkbutton(ctrl_frame, text="🔄 Авто-поиск",
                                       variable=self.farm_var, bg="#2b2b2b", fg="#a9b7c6", selectcolor="#3c3f41",
                                       activebackground="#2b2b2b", activeforeground="#ffffff", font=("Arial", 10))
        self.chk_farm.pack(side=tk.LEFT, padx=5)

        # --- 3. ПАНЕЛЬ ЛОГОВ ---
        log_frame = tk.Frame(root, bg="#1e1e1e")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(10, 15))

        top_bar = tk.Frame(log_frame, bg="#1e1e1e")
        top_bar.pack(fill=tk.X, pady=(0, 5))
        tk.Label(top_bar, text="ТЕРМИНАЛ", fg="#a9b7c6", bg="#1e1e1e", font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        tk.Button(top_bar, text="Очистить лог", bg="#3c3f41", fg="#a9b7c6", font=("Arial", 8), relief="flat", padx=8,
                  pady=2, cursor="hand2", command=self.clear_logs).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_bar, text="📋 Скопировать", bg="#365880", fg="white", font=("Arial", 8, "bold"), relief="flat",
                  padx=10, pady=2, cursor="hand2", command=self.copy_logs).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_bar, text="🗑 Удалить снапшоты", bg="#dc3545", fg="white", font=("Arial", 8, "bold"),
                  relief="flat",
                  padx=10, pady=2, cursor="hand2", command=self.clear_error_folders).pack(side=tk.RIGHT, padx=5)
        tk.Button(top_bar, text="📊 Студия ответов", bg="#5a379e", fg="white", font=("Arial", 8, "bold"),
                  relief="flat",
                  padx=10, pady=2, cursor="hand2", command=self.open_review_studio).pack(side=tk.RIGHT, padx=5)

        self.log_area = scrolledtext.ScrolledText(log_frame, bg="#1e1e1e", fg="#a9b7c6", insertbackground="white",
                                                  selectbackground="#214283", selectforeground="#ffffff",
                                                  font=("Consolas", 10), borderwidth=0, undo=False)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.bind("<Key>", self.prevent_manual_typing)

        sys.stdout = StdoutRedirector(self.log_area)
        print("✅ Боевой интерфейс готов. Вставьте ссылку на опрос и нажмите Запуск.")

    def open_review_studio(self):
        review_script = os.path.join(os.path.dirname(__file__), "gui_review.py")
        subprocess.Popen([sys.executable, review_script])
        print("\n[📊] Открыта Студия ревизии и верификации ответов.")

    def toggle_human(self):
        config.HUMAN_LIKE_DELAYS = self.human_var.get()
        status_txt = "ВКЛЮЧЕН" if config.HUMAN_LIKE_DELAYS else "ВЫКЛЮЧЕН"
        print(f"\n[🛡] Режим антифрода (человеческие паузы): {status_txt}")

    def load_history(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        return []

    def save_url_to_history(self, url):
        if url in self.url_history:
            self.url_history.remove(url)
        self.url_history.insert(0, url)
        self.url_history = self.url_history[:15]
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                for u in self.url_history:
                    f.write(u + "\n")
        except Exception:
            pass
        self.url_entry['values'] = self.url_history

    def update_url_from_thread(self, new_url):
        self.root.after(0, self._set_new_url, new_url)

    def _set_new_url(self, new_url):
        if self.url_entry.get() != new_url:
            self.save_url_to_history(new_url)
            self.url_entry.set(new_url)

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
        try:
            self.log_area.delete("1.0", tk.END)
            print("Лог терминала очищен.")
        except Exception:
            pass

    def clear_error_folders(self):
        import stat
        def remove_readonly(func, path, excinfo):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        error_dirs = [
            os.path.join(config.BASE_DIR, "data", "error_questions"),
            os.path.join(os.getcwd(), "data", "error_questions"),
        ]
        deleted_count = 0
        seen_dirs = set()
        for ed in error_dirs:
            norm_ed = os.path.normpath(os.path.abspath(ed))
            if norm_ed in seen_dirs:
                continue
            seen_dirs.add(norm_ed)
            if os.path.exists(norm_ed):
                for item in os.listdir(norm_ed):
                    item_path = os.path.join(norm_ed, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path, onerror=remove_readonly)
                            deleted_count += 1
                        elif os.path.isfile(item_path):
                            os.chmod(item_path, stat.S_IWRITE)
                            os.remove(item_path)
                            deleted_count += 1
                    except Exception as item_err:
                        print(f"[!] Ошибка при удалении {item_path}: {item_err}")
        print(f"\n[🗑] Папки со снапшотами ошибок очищены (удалено папок/файлов: {deleted_count})!")

    def restart_app(self):
        if self.async_loop:
            if not messagebox.askyesno("Перезагрузка", "Вы уверены, что хотите прервать работу?"): return
        current_url = self.url_entry.get().strip()
        if current_url.startswith("http"): self.save_url_to_history(current_url)
        print("\n[🔄] Перезагрузка программы...")
        os.execl(sys.executable, sys.executable, *sys.argv)

    def toggle_pause(self):
        state.is_paused = not state.is_paused
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
        is_running = self.async_loop is not None

        if state.is_debug:
            if is_running:
                self.btn_confirm.config(state="normal")
                self.btn_alt.config(state="normal")
            print("\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВКЛЮЧЕН.")
        else:
            self.btn_confirm.config(state="disabled")
            self.btn_alt.config(state="disabled")
            print("\n[!] ОТЛАДОЧНЫЙ РЕЖИМ ВЫКЛЮЧЕН.")
            if self.async_loop and state.step_event and not state.step_event.is_set():
                state.step_decision = "CONFIRM"
                self.async_loop.call_soon_threadsafe(state.step_event.set)

    def confirm_step(self):
        if self.async_loop and state.step_event:
            state.step_decision = "CONFIRM"
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    def answer_differently(self):
        if not self.async_loop or not state.is_debug:
            return
        print("\n[🔄] КОМАНДА: Ответить иначе. Перевыбираю варианты...")
        state.step_decision = "RETRY"
        state.force_alternative = True
        if state.step_event:
            self.async_loop.call_soon_threadsafe(state.step_event.set)

    def take_manual_snapshot(self):
        if not self.async_loop:
            print("\n[!] Бот не запущен. Снимок можно сделать только во время работы браузера.")
            return
        page = getattr(state, "active_page", None)
        engine = getattr(state, "active_engine", None)
        if page and not page.is_closed():
            print("\n[⏳] Выполняется ручной снимок экрана...")
            target_engine = engine or getattr(self, "router", None) or getattr(self, "cloud_engine", None)
            if target_engine and hasattr(target_engine, "save_error_snapshot"):
                asyncio.run_coroutine_threadsafe(target_engine.save_error_snapshot(page, "MANUAL_SNAPSHOT"), self.async_loop)
            else:
                async def _snap():
                    try:
                        from datetime import datetime
                        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        fp = os.path.join(config.BASE_DIR, "data", "error_questions", f"error_{ts}")
                        os.makedirs(fp, exist_ok=True)
                        await page.screenshot(path=os.path.join(fp, "screenshot.png"), full_page=True)
                        with open(os.path.join(fp, "page.html"), "w", encoding="utf-8") as f:
                            f.write(await page.content())
                        with open(os.path.join(fp, "debug_log.txt"), "w", encoding="utf-8") as f:
                            f.write(f"MANUAL_SNAPSHOT\nURL: {page.url}\n")
                        print(f"\n[📸] Снимок сохранен: {fp}")
                    except Exception as e:
                        print(f"[!] Ошибка сохранения снимка: {e}")
                asyncio.run_coroutine_threadsafe(_snap(), self.async_loop)
        else:
            print("\n[!] Нет активной страницы браузера для создания снимка.")

    def start_bot(self):
        url = self.url_entry.get().strip()
        if not url.startswith("http"):
            messagebox.showerror("Ошибка", "Введите ссылку (http...)")
            return

        self.save_url_to_history(url)
        self.clear_logs()
        self.btn_start.config(state="disabled", text="Бот работает...")
        self.url_entry.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_snapshot.config(state="normal")

        self.btn_confirm.config(state="normal" if self.debug_var.get() else "disabled")
        self.btn_alt.config(state="normal" if self.debug_var.get() else "disabled")

        print("=" * 60)
        print(f"🚀 Запуск боевого бота по ссылке: {url}")
        print("=" * 60)

        threading.Thread(target=self.run_playwright, args=(url,), daemon=True).start()

    def start_multi_hub(self):
        hub_file = os.path.abspath(os.path.join(config.BASE_DIR, "data", "hub.html"))
        if not os.path.exists(hub_file):
            hub_file = os.path.abspath(os.path.join(os.getcwd(), "data", "hub.html"))
        hub_url = f"file:///{hub_file.replace(os.sep, '/')}"

        self.clear_logs()
        self.btn_start.config(state="disabled")
        self.btn_hub.config(state="disabled", text="Мульти-фарм...")
        self.url_entry.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_snapshot.config(state="normal")

        self.btn_confirm.config(state="normal" if self.debug_var.get() else "disabled")
        self.btn_alt.config(state="normal" if self.debug_var.get() else "disabled")

        print("=" * 60)
        print("🌐 Запуск Центра Опросов: Мульти-Фарминг по всем опросникам!")
        print("=" * 60)

        threading.Thread(target=self.run_playwright_multi, args=(hub_url,), daemon=True).start()

    def _on_bot_stopped(self):
        """Безопасное обновление элементов интерфейса в главном потоке."""
        self.btn_start.config(state="normal", text="▶ Запустить бота")
        self.btn_hub.config(state="normal", text="🌐 Центр Опросов (Все сайты)")
        self.url_entry.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ Пауза", bg="#f0ad4e")
        self.btn_snapshot.config(state="disabled")
        self.btn_confirm.config(state="disabled")
        self.btn_alt.config(state="disabled")

    def run_playwright(self, url):
        self.async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.async_loop)
        state.init_events()
        state.is_debug = self.debug_var.get()
        brain = SurveyBrain()
        router = SurveyRouter(brain=brain)

        try:
            self.async_loop.run_until_complete(router.run(url, self.update_url_from_thread, auto_farm=self.farm_var.get()))
            print("\n[✅] ЗАВЕРШЕНО: Бот закончил работу.")
        except Exception as e:
            print(f"\n[❌] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        finally:
            if self.async_loop:
                self.async_loop.close()
                self.async_loop = None
            self.root.after(0, self._on_bot_stopped)

    def run_playwright_multi(self, hub_url):
        self.async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.async_loop)
        state.init_events()
        state.is_debug = self.debug_var.get()
        brain = SurveyBrain()
        router = SurveyRouter(brain=brain)

        try:
            self.async_loop.run_until_complete(router.run(hub_url, self.update_url_from_thread, auto_farm=True, multi_site=True))
            print("\n[✅] ЗАВЕРШЕНО: Бот закончил работу.")
        except Exception as e:
            print(f"\n[❌] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        finally:
            if self.async_loop:
                self.async_loop.close()
                self.async_loop = None
            self.root.after(0, self._on_bot_stopped)


if __name__ == "__main__":
    root = tk.Tk()
    app = MainBotApp(root)
    root.mainloop()
