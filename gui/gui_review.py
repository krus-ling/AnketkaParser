import json
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk
from core.memory import DB_PATH, SurveyMemory

# Цветовая палитра Dark Slate (Tailwind-style)
BG_MAIN = "#0b0f19"
BG_PANEL = "#111827"
BG_CARD = "#1e293b"
BG_CARD_HOVER = "#273549"
BG_ACTIVE = "#1e3a8a"
BORDER_COLOR = "#2d3748"
TEXT_MAIN = "#f8fafc"
TEXT_MUTED = "#94a3b8"
TEXT_DIM = "#64748b"
ACCENT_BLUE = "#38bdf8"
ACCENT_GREEN = "#10b981"
ACCENT_AMBER = "#f59e0b"
ACCENT_RED = "#ef4444"
ACCENT_PURPLE = "#a855f7"


class ConflictResolverDialog(tk.Toplevel):
    def __init__(self, parent, existing_rec: dict, new_rec: dict, scale: float = 1.0):
        super().__init__(parent)
        self.title("⚡ Обнаружен дубликат проверенного вопроса")
        self.geometry(f"{int(1050 * scale)}x{int(620 * scale)}")
        self.minsize(800, 500)
        self.configure(bg=BG_MAIN)
        self.scale = scale
        self.result_action = "cancel"
        self.existing_rec = existing_rec
        self.new_rec = new_rec
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self.wait_window(self)

    def _f(self, size: int, weight: str = "normal"):
        return ("Segoe UI", int(size * self.scale), weight)

    def _build_ui(self):
        top_bar = tk.Frame(self, bg=BG_MAIN, padx=16, pady=12)
        top_bar.pack(fill=tk.X)
        tk.Label(top_bar, text="⚠️ В проверенной базе уже существует такой вопрос!", font=self._f(13, "bold"),
                 fg=ACCENT_AMBER, bg=BG_MAIN).pack(anchor="w")
        tk.Label(top_bar, text="Сравните варианты и выберите, какую запись сохранить в базе знаний:", font=self._f(9),
                 fg=TEXT_MUTED, bg=BG_MAIN).pack(anchor="w", pady=(2, 0))

        compare_box = tk.Frame(self, bg=BG_MAIN, padx=16, pady=4)
        compare_box.pack(fill=tk.BOTH, expand=True)

        col_old = tk.Frame(compare_box, bg=BG_PANEL, highlightthickness=1, highlightbackground=ACCENT_GREEN, padx=14,
                           pady=12)
        col_old.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        self._fill_column(col_old, self.existing_rec, "✅ СУЩЕСТВУЮЩАЯ (ПРОВЕРЕННАЯ)", ACCENT_GREEN)

        col_new = tk.Frame(compare_box, bg=BG_PANEL, highlightthickness=1, highlightbackground=ACCENT_BLUE, padx=14,
                           pady=12)
        col_new.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self._fill_column(col_new, self.new_rec, "⏳ НОВАЯ (НА ПОДТВЕРЖДЕНИЕ)", ACCENT_BLUE)

        action_bar = tk.Frame(self, bg=BG_MAIN, padx=16, pady=14)
        action_bar.pack(fill=tk.X)

        tk.Button(action_bar, text="🔄 Заменить старую новой", font=self._f(10, "bold"), bg="#2563eb", fg="#ffffff",
                  activebackground="#1d4ed8", bd=0, padx=14, pady=8, cursor="hand2",
                  command=lambda: self._set_action("replace")).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(action_bar, text="🗑️ Оставить старую (удалить эту)", font=self._f(10, "bold"), bg="#334155",
                  fg="#fca5a5", activebackground=ACCENT_RED, activeforeground="#ffffff", bd=0, padx=14, pady=8,
                  cursor="hand2", command=lambda: self._set_action("keep_old_delete_new")).pack(side=tk.LEFT,
                                                                                                padx=(0, 8))
        tk.Button(action_bar, text="💾 Одобрить обе", font=self._f(10), bg=BG_CARD, fg=TEXT_MAIN,
                  activebackground=BG_CARD_HOVER, bd=0, padx=12, pady=8, cursor="hand2",
                  command=lambda: self._set_action("keep_both")).pack(side=tk.LEFT)
        tk.Button(action_bar, text="Отмена", font=self._f(10), bg=BG_CARD, fg=TEXT_MUTED,
                  activebackground=BG_CARD_HOVER, bd=0, padx=14, pady=8, cursor="hand2", command=self.destroy).pack(
            side=tk.RIGHT)

    def _fill_column(self, parent_frame, rec: dict, badge_text: str, badge_color: str):
        head = tk.Frame(parent_frame, bg=BG_PANEL)
        head.pack(fill=tk.X, pady=(0, 8))
        tk.Label(head, text=f"ID #{rec['id']}", font=self._f(10, "bold"), fg=badge_color, bg=BG_PANEL).pack(
            side=tk.LEFT)
        tk.Label(head, text=badge_text, font=self._f(8, "bold"), fg=badge_color, bg=BG_CARD, padx=6, pady=2).pack(
            side=tk.RIGHT)

        tk.Label(parent_frame, text=rec["full_question"], font=self._f(10, "bold"), fg=TEXT_MAIN, bg=BG_PANEL,
                 wraplength=420, justify=tk.LEFT, anchor="w").pack(fill=tk.X, pady=(0, 8))

        opts_box = tk.LabelFrame(parent_frame, text=" Выбор / Ответ ", font=self._f(9, "bold"), fg=TEXT_MUTED,
                                 bg=BG_PANEL, padx=8, pady=6)
        opts_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        options_json = rec.get("options_json")
        options = json.loads(options_json) if options_json else None
        active_json = rec.get("corrected_json") or rec.get("selected_json")
        active_sel = json.loads(active_json) if active_json else []

        canvas = tk.Canvas(opts_box, bg=BG_PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(opts_box, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        if options and isinstance(options, list):
            for idx, opt in enumerate(options):
                is_picked = (isinstance(active_sel, list) and idx in active_sel)
                card_bg = BG_ACTIVE if is_picked else BG_CARD
                c = tk.Frame(inner, bg=card_bg, padx=6, pady=4)
                c.pack(fill=tk.X, pady=2)
                mark = "☑" if is_picked else "☐"
                tk.Label(c, text=f"{mark} [{idx}] {opt}", font=self._f(9), fg=TEXT_MAIN if is_picked else TEXT_MUTED,
                         bg=card_bg, wraplength=360, justify=tk.LEFT).pack(anchor="w")
        else:
            txt_val = active_sel if isinstance(active_sel, str) else str(rec.get("selected_text", ""))
            tk.Label(inner, text=f"✍️ Ответ: {txt_val}", font=self._f(10, "bold"), fg=ACCENT_BLUE, bg=BG_PANEL,
                     wraplength=380, justify=tk.LEFT).pack(anchor="w", pady=4)

        reason = rec.get("notes") or rec.get("reasoning") or "—"
        tk.Label(parent_frame, text=f"💡 Заметка: {reason}", font=self._f(9), fg=TEXT_MUTED, bg=BG_PANEL, wraplength=420,
                 justify=tk.LEFT, anchor="w").pack(fill=tk.X)

    def _set_action(self, action_name: str):
        self.result_action = action_name
        self.destroy()


class SurveyReviewApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Survey Memory Studio — Dark Edition")
        self.geometry("1300x820")
        self.minsize(1050, 650)
        self.configure(bg=BG_MAIN)

        self.memory = SurveyMemory()
        self.current_record = None
        self.option_check_vars = []
        self.option_cards = []
        self.filter_mode = "unverified"
        self.scale = 1.15

        self._setup_styles()
        self._build_ui()
        self._bind_zoom_and_nav_shortcuts()
        self.load_records()

    def _get_connection(self):
        return sqlite3.connect(DB_PATH)

    def _get_font(self, size: int, weight: str = "normal"):
        return ("Segoe UI", int(size * self.scale), weight)

    def _setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure(".", background=BG_MAIN, foreground=TEXT_MAIN, font=self._get_font(10))
        self.style.configure("Custom.Treeview", background=BG_PANEL, foreground=TEXT_MAIN, fieldbackground=BG_PANEL,
                             font=self._get_font(11), rowheight=int(40 * self.scale), borderwidth=0, relief="flat")
        self.style.configure("Custom.Treeview.Heading", background=BG_CARD, foreground=TEXT_MUTED,
                             font=self._get_font(10, "bold"), borderwidth=0, relief="flat")
        self.style.map("Custom.Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])
        self.style.configure("Dark.Vertical.TScrollbar", background=BG_CARD, troughcolor=BG_PANEL, borderwidth=0,
                             arrowsize=0)

    def _build_ui(self):
        self.header_bar = tk.Frame(self, bg=BG_MAIN, height=52)
        self.header_bar.pack(fill=tk.X, padx=18, pady=(12, 6))

        tk.Label(self.header_bar, text="⚡ SURVEY MEMORY STUDIO", font=self._get_font(14, "bold"), fg=ACCENT_BLUE,
                 bg=BG_MAIN).pack(side=tk.LEFT)
        tk.Label(self.header_bar, text=f"🔍 Масштаб: {int(self.scale * 100)}% (Ctrl + 🖱️)", font=self._get_font(9),
                 fg=TEXT_DIM, bg=BG_MAIN).pack(side=tk.LEFT, padx=(20, 0))
        self.lbl_stats = tk.Label(self.header_bar, text="Загрузка...", font=self._get_font(10, "bold"), fg=TEXT_MUTED,
                                  bg=BG_MAIN)
        self.lbl_stats.pack(side=tk.RIGHT)

        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=BG_MAIN, bd=0, sashwidth=7, sashpad=2,
                                    sashrelief=tk.FLAT, showhandle=False)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 16))

        # ================= ЛЕВАЯ ПАНЕЛЬ =================
        left_frame = tk.Frame(self.paned, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.paned.add(left_frame, minsize=360, width=int(480 * self.scale))

        filter_bar = tk.Frame(left_frame, bg=BG_PANEL)
        filter_bar.pack(fill=tk.X, padx=12, pady=12)

        self.btn_f_unver = tk.Button(filter_bar, text="⏳ На проверке (0)", font=self._get_font(10, "bold"),
                                     bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                                     bd=0, padx=10, pady=7, cursor="hand2",
                                     command=lambda: self.set_filter("unverified"))
        self.btn_f_unver.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_f_ver = tk.Button(filter_bar, text="✅ Проверенные (0)", font=self._get_font(10, "bold"), bg=BG_CARD,
                                   fg=TEXT_MUTED, activebackground=BG_CARD_HOVER, activeforeground=TEXT_MAIN, bd=0,
                                   padx=10, pady=7, cursor="hand2", command=lambda: self.set_filter("verified"))
        self.btn_f_ver.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_f_all = tk.Button(filter_bar, text="📋 Все (0)", font=self._get_font(10, "bold"), bg=BG_CARD,
                                   fg=TEXT_MUTED, activebackground=BG_CARD_HOVER, activeforeground=TEXT_MAIN, bd=0,
                                   padx=10, pady=7, cursor="hand2", command=lambda: self.set_filter("all"))
        self.btn_f_all.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_clean_dups = tk.Button(filter_bar, text="🧹 Дубли", font=self._get_font(9, "bold"), bg=BG_CARD,
                                        fg=ACCENT_AMBER, activebackground=BG_CARD_HOVER, activeforeground="#ffffff",
                                        bd=0, padx=8, pady=7, cursor="hand2", command=self.clean_unverified_duplicates)
        self.btn_clean_dups.pack(side=tk.LEFT)

        self.btn_refresh = tk.Button(filter_bar, text="🔄", font=self._get_font(10, "bold"), bg=BG_CARD, fg=TEXT_MAIN,
                                     activebackground=BG_CARD_HOVER, activeforeground=TEXT_MAIN, bd=0, padx=10, pady=7,
                                     cursor="hand2", command=self.load_records)
        self.btn_refresh.pack(side=tk.RIGHT)

        tree_container = tk.Frame(left_frame, bg=BG_PANEL)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        cols = ("id", "status", "type", "question")
        self.tree = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse",
                                 style="Custom.Treeview")
        self.tree.heading("id", text="#")
        self.tree.heading("status", text="Статус")
        self.tree.heading("type", text="Тип")
        self.tree.heading("question", text="Вопрос")
        self.tree.column("id", width=48, stretch=False, anchor=tk.CENTER)
        self.tree.column("status", width=88, stretch=False, anchor=tk.CENTER)
        self.tree.column("type", width=85, stretch=False, anchor=tk.CENTER)
        self.tree.column("question", width=220, stretch=True)

        scroll_tree = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview,
                                    style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll_tree.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # ================= ПРАВАЯ ПАНЕЛЬ =================
        right_frame = tk.Frame(self.paned, bg=BG_MAIN)
        self.paned.add(right_frame, minsize=500)

        self.meta_card = tk.Frame(right_frame, bg=BG_PANEL, padx=20, pady=16, highlightthickness=1,
                                  highlightbackground=BORDER_COLOR)
        self.meta_card.pack(fill=tk.X, pady=(0, 12))

        top_meta = tk.Frame(self.meta_card, bg=BG_PANEL)
        top_meta.pack(fill=tk.X)
        self.lbl_id = tk.Label(top_meta, text="ID: —", font=self._get_font(11, "bold"), fg=ACCENT_BLUE, bg=BG_PANEL)
        self.lbl_id.pack(side=tk.LEFT)
        self.lbl_status_badge = tk.Label(top_meta, text="НЕТ ВЫБОРА", font=self._get_font(9, "bold"), bg=BG_CARD,
                                         fg=TEXT_MUTED, padx=12, pady=4)
        self.lbl_status_badge.pack(side=tk.LEFT, padx=(12, 0))
        self.lbl_date = tk.Label(top_meta, text="", font=self._get_font(10), fg=TEXT_DIM, bg=BG_PANEL)
        self.lbl_date.pack(side=tk.RIGHT)

        self.lbl_question = tk.Label(self.meta_card,
                                     text="Выберите вопрос из таблицы слева для просмотра и редактирования.",
                                     font=self._get_font(13, "bold"), fg=TEXT_MAIN, bg=BG_PANEL, wraplength=700,
                                     justify=tk.LEFT, anchor="w")
        self.lbl_question.pack(fill=tk.X, pady=(12, 0))

        self.body_card = tk.Frame(right_frame, bg=BG_PANEL, padx=20, pady=16, highlightthickness=1,
                                  highlightbackground=BORDER_COLOR)
        self.body_card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.lbl_body_title = tk.Label(self.body_card, text="Варианты ответа", font=self._get_font(11, "bold"),
                                       fg=TEXT_MUTED, bg=BG_PANEL)
        self.lbl_body_title.pack(anchor="w", pady=(0, 12))

        self.canvas = tk.Canvas(self.body_card, bg=BG_PANEL, highlightthickness=0)
        self.options_scroll = ttk.Scrollbar(self.body_card, orient=tk.VERTICAL, command=self.canvas.yview,
                                            style="Dark.Vertical.TScrollbar")
        self.options_frame = tk.Frame(self.canvas, bg=BG_PANEL)
        self.options_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.options_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.options_scroll.set)
        self.body_card.bind("<Configure>", self._on_body_configure)
        self._bind_mousewheel(self.canvas, self.canvas)
        self._bind_mousewheel(self.options_frame, self.canvas)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.options_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.reason_card = tk.Frame(right_frame, bg=BG_CARD, padx=18, pady=12, highlightthickness=1,
                                    highlightbackground=BORDER_COLOR)
        self.reason_card.pack(fill=tk.X, pady=(0, 14))

        self.lbl_reason_title = tk.Label(self.reason_card, text="💡 Обоснование решения LLM:",
                                         font=self._get_font(10, "bold"), fg=ACCENT_PURPLE, bg=BG_CARD)
        self.lbl_reason_title.pack(anchor="w")
        self.lbl_reasoning = tk.Label(self.reason_card, text="—", font=self._get_font(10), fg=TEXT_MUTED, bg=BG_CARD,
                                      wraplength=700, justify=tk.LEFT, anchor="w")
        self.lbl_reasoning.pack(fill=tk.X, pady=(4, 0))

        action_bar = tk.Frame(right_frame, bg=BG_MAIN)
        action_bar.pack(fill=tk.X)

        self.btn_toggle_verify = tk.Button(action_bar, text="✅ Ответ верен", font=self._get_font(11, "bold"),
                                           bg=ACCENT_GREEN, fg="#ffffff", activebackground="#059669",
                                           activeforeground="#ffffff", bd=0, padx=18, pady=10, cursor="hand2",
                                           command=self.toggle_verification)
        self.btn_toggle_verify.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_save = tk.Button(action_bar, text="💾 Сохранить выбор", font=self._get_font(11, "bold"), bg="#2563eb",
                                  fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff", bd=0, padx=18,
                                  pady=10, cursor="hand2", command=self.save_correction)
        self.btn_save.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_delete = tk.Button(action_bar, text="🗑️ Удалить (Del)", font=self._get_font(11, "bold"), bg="#334155",
                                    fg="#fca5a5", activebackground=ACCENT_RED, activeforeground="#ffffff", bd=0,
                                    padx=18, pady=10, cursor="hand2", command=self.delete_record)
        self.btn_delete.pack(side=tk.LEFT, padx=(0, 14))

        self.btn_prev_nav = tk.Button(action_bar, text="◀ Назад", font=self._get_font(10, "bold"), bg=BG_CARD,
                                      fg=TEXT_MAIN, activebackground=BG_CARD_HOVER, activeforeground=TEXT_MAIN, bd=0,
                                      padx=14, pady=10, cursor="hand2", command=self.select_prev_record)
        self.btn_prev_nav.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_next_nav = tk.Button(action_bar, text="Вперед ▶", font=self._get_font(10, "bold"), bg=BG_CARD,
                                      fg=TEXT_MAIN, activebackground=BG_CARD_HOVER, activeforeground=TEXT_MAIN, bd=0,
                                      padx=14, pady=10, cursor="hand2", command=self.select_next_record)
        self.btn_next_nav.pack(side=tk.LEFT)

        self.btn_export = tk.Button(action_bar, text="📤 Экспорт датасета (.jsonl)", font=self._get_font(11, "bold"),
                                    bg=BG_CARD, fg=TEXT_MAIN, activebackground=BG_CARD_HOVER,
                                    activeforeground=TEXT_MAIN, bd=0, padx=18, pady=10, cursor="hand2",
                                    command=self.export_dataset)
        self.btn_export.pack(side=tk.RIGHT)

    def _bind_zoom_and_nav_shortcuts(self):
        self.bind_all("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.bind_all("<Control-plus>", lambda e: self.change_zoom(0.08))
        self.bind_all("<Control-equal>", lambda e: self.change_zoom(0.08))
        self.bind_all("<Control-minus>", lambda e: self.change_zoom(-0.08))
        self.bind_all("<Control-0>", lambda e: self.reset_zoom())
        self.bind_all("<Alt-Left>", lambda e: self.select_prev_record())
        self.bind_all("<Alt-Right>", lambda e: self.select_next_record())
        self.bind_all("<Delete>", self._on_delete_key)
        self.bind_all("<BackSpace>", self._on_delete_key)

    def _on_delete_key(self, event):
        if isinstance(event.widget, tk.Entry):
            return
        self.delete_record()

    def _on_ctrl_wheel(self, event):
        delta = 0.08 if event.delta > 0 else -0.08
        self.change_zoom(delta)

    def change_zoom(self, delta: float):
        new_scale = round(self.scale + delta, 2)
        if 0.75 <= new_scale <= 2.0:
            self.scale = new_scale
            self._apply_zoom()

    def reset_zoom(self):
        self.scale = 1.0
        self._apply_zoom()

    def _apply_zoom(self):
        self._setup_styles()
        self.title_lbl.config(font=self._get_font(14, "bold"))
        self.lbl_zoom.config(text=f"🔍 Масштаб: {int(self.scale * 100)}% (Ctrl + 🖱️)", font=self._get_font(9))
        self.lbl_stats.config(font=self._get_font(10, "bold"))
        self.btn_f_unver.config(font=self._get_font(10, "bold"), pady=int(7 * self.scale))
        self.btn_f_ver.config(font=self._get_font(10, "bold"), pady=int(7 * self.scale))
        self.btn_f_all.config(font=self._get_font(10, "bold"), pady=int(7 * self.scale))
        self.btn_clean_dups.config(font=self._get_font(9, "bold"), pady=int(7 * self.scale))
        self.btn_refresh.config(font=self._get_font(10, "bold"), pady=int(7 * self.scale))
        self.lbl_id.config(font=self._get_font(11, "bold"))
        self.lbl_status_badge.config(font=self._get_font(9, "bold"))
        self.lbl_date.config(font=self._get_font(10))
        self.lbl_question.config(font=self._get_font(13, "bold"))
        self.lbl_body_title.config(font=self._get_font(11, "bold"))
        self.lbl_reason_title.config(font=self._get_font(10, "bold"))
        self.lbl_reasoning.config(font=self._get_font(10))
        self.btn_toggle_verify.config(font=self._get_font(11, "bold"), pady=int(10 * self.scale))
        self.btn_save.config(font=self._get_font(11, "bold"), pady=int(10 * self.scale))
        self.btn_delete.config(font=self._get_font(11, "bold"), pady=int(10 * self.scale))
        self.btn_prev_nav.config(font=self._get_font(10, "bold"), pady=int(10 * self.scale))
        self.btn_next_nav.config(font=self._get_font(10, "bold"), pady=int(10 * self.scale))
        self.btn_export.config(font=self._get_font(11, "bold"), pady=int(10 * self.scale))
        self._render_details()

    def _bind_mousewheel(self, widget, canvas):
        def _on_wheel(e):
            if not (e.state & 0x0004):
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        widget.bind("<MouseWheel>", _on_wheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child, canvas)

    def _on_body_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width - 24)

    def set_filter(self, mode: str):
        self.filter_mode = mode
        buttons = [
            (self.btn_f_unver, "unverified", "#2563eb"),
            (self.btn_f_ver, "verified", ACCENT_GREEN),
            (self.btn_f_all, "all", "#6366f1")
        ]
        for btn, key, active_color in buttons:
            if self.filter_mode == key:
                btn.config(bg=active_color, fg="#ffffff")
            else:
                btn.config(bg=BG_CARD, fg=TEXT_MUTED)
        self.load_records()

    def clean_unverified_duplicates(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, clean_question, options_json FROM qa_records WHERE is_verified = 0 ORDER BY id ASC")
            rows = cursor.fetchall()
            seen = set()
            to_delete = []
            for rec_id, clean_q, opts in rows:
                key = (clean_q, opts or "")
                if key in seen:
                    to_delete.append(rec_id)
                else:
                    seen.add(key)
            if not to_delete:
                messagebox.showinfo("Дубликаты", "В непроверенных записях дубликатов не найдено!")
                return
            if messagebox.askyesno("Очистка дубликатов",
                                   f"Найдено идентичных дубликатов: {len(to_delete)}.\nУдалить их и оставить только уникальные?",
                                   default=messagebox.YES):
                cursor.executemany("DELETE FROM qa_records WHERE id = ?", [(i,) for i in to_delete])
                conn.commit()
                messagebox.showinfo("Готово", f"Успешно удалено {len(to_delete)} дубликатов!")
                self.load_records()

    def load_records(self, target_id=None, target_index=None):
        if target_id is None and self.current_record:
            target_id = self.current_record["id"]
        for item in self.tree.get_children():
            self.tree.delete(item)

        query = "SELECT id, is_verified, question_type, full_question FROM qa_records"
        params = ()
        if self.filter_mode == "unverified":
            query += " WHERE is_verified = 0"
        elif self.filter_mode == "verified":
            query += " WHERE is_verified = 1"
        query += " ORDER BY id DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_verified = 1 THEN 1 ELSE 0 END) FROM qa_records")
            stat_row = cursor.fetchone()
            total_count = stat_row[0] or 0
            ver_count = stat_row[1] or 0
            unver_count = total_count - ver_count

            self.btn_f_unver.config(text=f"⏳ На проверке ({unver_count})")
            self.btn_f_ver.config(text=f"✅ Проверенные ({ver_count})")
            self.btn_f_all.config(text=f"📋 Все ({total_count})")
            self.lbl_stats.config(
                text=f"📊 Всего: {total_count}   |   ⏳ На проверке: {unver_count}   |   ✅ Проверено: {ver_count}")

            item_keys = []
            selected_tree_item = None
            for row in rows:
                rec_id, is_ver, q_type, q_txt = row
                status_icon = "✅ Да" if is_ver == 1 else "⏳ Нет"
                clean_preview = q_txt.replace("\n", " ").strip()[:50]
                t_item = self.tree.insert("", tk.END, values=(rec_id, status_icon, q_type, clean_preview))
                item_keys.append((t_item, rec_id))
                if target_id and rec_id == target_id:
                    selected_tree_item = t_item

            if selected_tree_item:
                self.tree.selection_set(selected_tree_item)
                self.tree.focus(selected_tree_item)
                self.tree.see(selected_tree_item)
                self._load_record_by_id(target_id)
            elif item_keys:
                idx_to_pick = 0
                if target_index is not None:
                    idx_to_pick = min(max(0, target_index), len(item_keys) - 1)
                t_item, rec_id = item_keys[idx_to_pick]
                self.tree.selection_set(t_item)
                self.tree.focus(t_item)
                self.tree.see(t_item)
                self._load_record_by_id(rec_id)
            else:
                self._clear_details()

    def _load_record_by_id(self, rec_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM qa_records WHERE id = ?", (rec_id,))
            cols = [c[0] for c in cursor.description]
            row = cursor.fetchone()
            if row:
                self.current_record = dict(zip(cols, row))
                self._render_details()

    def _clear_details(self):
        self.current_record = None
        self.lbl_id.config(text="ID: —")
        self.lbl_status_badge.config(text="НЕТ ЗАПИСЕЙ", bg=BG_CARD, fg=TEXT_MUTED)
        self.lbl_date.config(text="")
        self.lbl_question.config(text="Список пуст.")
        self.lbl_reasoning.config(text="—")
        for w in self.options_frame.winfo_children():
            w.destroy()

    def _on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        item = selected_items[0]
        rec_id = int(self.tree.item(item, "values")[0])
        self._load_record_by_id(rec_id)

    def select_prev_record(self):
        children = self.tree.get_children()
        if not children:
            return
        selected = self.tree.selection()
        if not selected:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])
            self._on_tree_select(None)
            return
        curr_idx = children.index(selected[0])
        if curr_idx > 0:
            prev_item = children[curr_idx - 1]
            self.tree.selection_set(prev_item)
            self.tree.focus(prev_item)
            self.tree.see(prev_item)
            self._on_tree_select(None)

    def select_next_record(self):
        children = self.tree.get_children()
        if not children:
            return
        selected = self.tree.selection()
        if not selected:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.see(children[0])
            self._on_tree_select(None)
            return
        curr_idx = children.index(selected[0])
        if curr_idx < len(children) - 1:
            next_item = children[curr_idx + 1]
            self.tree.selection_set(next_item)
            self.tree.focus(next_item)
            self.tree.see(next_item)
            self._on_tree_select(None)

    def _render_details(self):
        if not self.current_record:
            return
        rec = self.current_record
        is_verified = rec["is_verified"] == 1

        self.lbl_id.config(text=f"ID #{rec['id']}  ·  {rec['question_type'].upper()}", font=self._get_font(11, "bold"))
        self.lbl_date.config(text=f"Создано: {rec['created_at'][:19].replace('T', ' ')}", font=self._get_font(10))

        if is_verified:
            self.lbl_status_badge.config(text="● ПРОВЕРЕНО", bg="#064e3b", fg="#6ee7b7", font=self._get_font(9, "bold"))
            self.btn_toggle_verify.config(text="↩️ Вернуть на проверку", bg=ACCENT_AMBER, activebackground="#d97706")
        else:
            self.lbl_status_badge.config(text="● НА ПРОВЕРКЕ", bg="#451a03", fg="#fcd34d",
                                         font=self._get_font(9, "bold"))
            self.btn_toggle_verify.config(text="✅ Ответ верен", bg=ACCENT_GREEN, activebackground="#059669")

        self.lbl_question.config(text=rec["full_question"], font=self._get_font(13, "bold"))
        self.lbl_reasoning.config(text=rec.get("notes") or rec.get("reasoning") or "Обоснование отсутствует",
                                  font=self._get_font(10))

        for widget in self.options_frame.winfo_children():
            widget.destroy()
        self.option_check_vars.clear()
        self.option_cards.clear()

        options_json = rec.get("options_json")
        options = json.loads(options_json) if options_json else None
        active_json = rec.get("corrected_json") or rec.get("selected_json")
        active_selection = json.loads(active_json) if active_json else []

        # === ИСПРАВЛЕНИЕ: Определяем, множественный ли это выбор ===
        q_type = rec.get("question_type", "").lower()
        is_multi = "multi" in q_type or "checkbox" in q_type

        if options and isinstance(options, list):
            self.lbl_body_title.config(
                text=f"Варианты ответа ({'Множественный' if is_multi else 'Одиночный'} выбор, кликните по плашке):",
                font=self._get_font(11, "bold"))
            for idx, opt_text in enumerate(options):
                is_selected = (isinstance(active_selection, list) and idx in active_selection)
                var = tk.BooleanVar(value=is_selected)
                self.option_check_vars.append(var)
                card_bg = BG_ACTIVE if is_selected else BG_CARD

                card = tk.Frame(self.options_frame, bg=card_bg, padx=int(14 * self.scale), pady=int(12 * self.scale),
                                cursor="hand2")
                card.pack(fill=tk.X, pady=4, padx=2)
                self.option_cards.append((card, var))

                check_symbol = "☑" if is_selected else "☐"
                sym_lbl = tk.Label(card, text=check_symbol, font=self._get_font(14, "bold"),
                                   fg=ACCENT_BLUE if is_selected else TEXT_MUTED, bg=card_bg)
                sym_lbl.pack(side=tk.LEFT, padx=(0, 12))

                text_lbl = tk.Label(card, text=f"[{idx}]  {opt_text}", font=self._get_font(11), fg=TEXT_MAIN,
                                    bg=card_bg, anchor="w", justify=tk.LEFT)
                text_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                # Передаем is_multi в функцию переключения
                def _make_toggle(v=var, c=card, sl=sym_lbl, tl=text_lbl, im=is_multi):
                    return lambda e: self._toggle_option_card(v, c, sl, tl, im)

                card.bind("<Button-1>", _make_toggle())
                sym_lbl.bind("<Button-1>", _make_toggle())
                text_lbl.bind("<Button-1>", _make_toggle())
        else:
            self.lbl_body_title.config(text="Текстовый ответ респондента:", font=self._get_font(11, "bold"))
            entry_box = tk.Frame(self.options_frame, bg=BG_PANEL)
            entry_box.pack(fill=tk.X, pady=6)
            self.custom_text_entry = tk.Entry(entry_box, font=self._get_font(12), bg=BG_CARD, fg=TEXT_MAIN,
                                              insertbackground=TEXT_MAIN, relief="flat", bd=int(10 * self.scale))
            self.custom_text_entry.pack(fill=tk.X, ipady=int(8 * self.scale))
            curr_val = active_selection if isinstance(active_selection, str) else str(rec.get("selected_text", ""))
            self.custom_text_entry.insert(0, curr_val.strip('"'))

        self._bind_mousewheel(self.options_frame, self.canvas)

    # === ИСПРАВЛЕНИЕ: Логика сброса других вариантов при одиночном выборе ===
    def _toggle_option_card(self, var, card, sym_lbl, text_lbl, is_multi):
        if not is_multi:
            # Если одиночный выбор, сбрасываем все остальные варианты
            for v, c, s, t in self.option_cards:
                if v != var and v.get():
                    v.set(False)
                    c.config(bg=BG_CARD)
                    t.config(bg=BG_CARD, fg=TEXT_MAIN)
                    s.config(text="☐", bg=BG_CARD, fg=TEXT_MUTED)

        new_val = not var.get()
        var.set(new_val)
        new_bg = BG_ACTIVE if new_val else BG_CARD
        card.config(bg=new_bg)
        text_lbl.config(bg=new_bg)
        sym_lbl.config(
            text="☑" if new_val else "☐",
            bg=new_bg,
            fg=ACCENT_BLUE if new_val else TEXT_MUTED
        )

    def _check_and_resolve_verified_duplicate(self, candidate_record: dict) -> str:
        clean_q = candidate_record["clean_question"]
        current_id = candidate_record["id"]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM qa_records WHERE clean_question = ? AND is_verified = 1 AND id != ? ORDER BY id DESC LIMIT 1",
                (clean_q, current_id))
            row = cursor.fetchone()
            if not row:
                return "proceed"
            cols = [c[0] for c in cursor.description]
            existing_verified = dict(zip(cols, row))

        dialog = ConflictResolverDialog(self, existing_verified, candidate_record, self.scale)
        action = dialog.result_action
        if action == "replace":
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM qa_records WHERE id = ?", (existing_verified["id"],))
                conn.commit()
            return "proceed"
        elif action == "keep_old_delete_new":
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM qa_records WHERE id = ?", (current_id,))
                conn.commit()
            self.load_records()
            return "stop"
        elif action == "keep_both":
            return "proceed"
        else:
            return "stop"

    def toggle_verification(self):
        if not self.current_record:
            return
        rec_id = self.current_record["id"]
        current_status = self.current_record["is_verified"]
        new_status = 0 if current_status == 1 else 1

        if new_status == 1:
            resolution = self._check_and_resolve_verified_duplicate(self.current_record)
            if resolution == "stop":
                return

        children = self.tree.get_children()
        selected = self.tree.selection()
        curr_idx = children.index(selected[0]) if selected and selected[0] in children else 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE qa_records SET is_verified = ? WHERE id = ?", (new_status, rec_id))
            conn.commit()

        self.current_record["is_verified"] = new_status
        self.load_records(target_id=rec_id, target_index=curr_idx)

    def save_correction(self):
        if not self.current_record:
            return
        rec_id = self.current_record["id"]
        options_json = self.current_record.get("options_json")
        options = json.loads(options_json) if options_json else None

        children = self.tree.get_children()
        selected = self.tree.selection()
        curr_idx = children.index(selected[0]) if selected and selected[0] in children else 0

        if options and self.option_check_vars:
            new_indices = [i for i, var in enumerate(self.option_check_vars) if var.get()]

            # Дополнительная страховка для одиночного выбора
            q_type = self.current_record.get("question_type", "").lower()
            is_multi = "multi" in q_type or "checkbox" in q_type
            if not is_multi and len(new_indices) > 1:
                new_indices = [new_indices[-1]]  # Оставляем только последний выбранный

            if not new_indices:
                messagebox.showwarning("Внимание", "Не выбран ни один вариант ответа!")
                return

            corr_json = json.dumps(new_indices)
            corr_text = json.dumps([options[i] for i in new_indices if i < len(options)], ensure_ascii=False)
            note = f"Исправлено пользователем в GUI на {corr_text}"
        else:
            new_txt = self.custom_text_entry.get().strip()
            if not new_txt:
                messagebox.showwarning("Внимание", "Поле ответа не может быть пустым!")
                return
            corr_json = json.dumps(new_txt, ensure_ascii=False)
            corr_text = new_txt
            note = "Исправлено пользователем в GUI (текстовый ответ)"

        mock_cand = dict(self.current_record)
        mock_cand["corrected_json"] = corr_json
        mock_cand["selected_text"] = corr_text
        mock_cand["notes"] = note

        resolution = self._check_and_resolve_verified_duplicate(mock_cand)
        if resolution == "stop":
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE qa_records SET is_verified = 1, corrected_json = ?, selected_text = ?, notes = ? WHERE id = ?",
                (corr_json, corr_text, note, rec_id))
            conn.commit()

        self.load_records(target_id=rec_id, target_index=curr_idx)

    def delete_record(self):
        if not self.current_record:
            return
        rec_id = self.current_record["id"]
        children = self.tree.get_children()
        selected = self.tree.selection()
        curr_idx = children.index(selected[0]) if selected and selected[0] in children else 0

        if messagebox.askyesno("Удаление", f"Удалить запись #{rec_id} из базы памяти?", default=messagebox.YES):
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM qa_records WHERE id = ?", (rec_id,))
                conn.commit()
            self.load_records(target_index=curr_idx)

    def export_dataset(self):
        try:
            self.memory.export_for_finetuning("dataset_finetuning.jsonl")
            messagebox.showinfo("Экспорт", "Датасет успешно экспортирован в dataset_finetuning.jsonl!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать датасет: {e}")


if __name__ == "__main__":
    app = SurveyReviewApp()
    app.mainloop()