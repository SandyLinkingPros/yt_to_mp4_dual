import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import yt_dlp
import threading
import queue
import time
import subprocess
import os
import re
import json

CONFIG_FILE = "settings.json"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube 影片下載器 v1.3 (Robust)")
        self.geometry("800x650")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- App State ---
        self.worker_queue = queue.Queue()
        self.stop_requested = threading.Event()
        self.last_downloaded_info = None # To store info from progress hook

        # --- UI Variables ---
        self.output_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Videos"))
        self.container_var = tk.StringVar(value="MP4")
        self.quality_var = tk.StringVar(value="best")
        self.quality_limit = tk.StringVar(value="1080")
        self.mode_var = tk.StringVar(value="both")
        self.safe_filename_var = tk.BooleanVar(value=True)
        self.cookies_var = tk.BooleanVar(value=False)
        self.cookie_file_path = tk.StringVar(value="")
        self.proxy_var = tk.BooleanVar(value=False)
        self.proxy_address = tk.StringVar(value="")
        self.concurrent_fragments = tk.StringVar(value="3")
        self.rate_limit = tk.StringVar(value="0")

        self.build_ui()
        self.setup_context_menus()
        self.load_settings()
        self.process_worker_queue()

    def build_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Section 1: Input ---
        url_frame = ttk.LabelFrame(main_frame, text="1. 輸入來源")
        url_frame.pack(fill=tk.X, padx=5, pady=5)
        url_frame.columnconfigure(1, weight=1)

        ttk.Label(url_frame, text="URL:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        self.txt_button = ttk.Button(url_frame, text="從TXT批次下載", command=self.start_batch_from_file)
        self.txt_button.grid(row=0, column=2, padx=5, pady=5)

        # --- Section 2: Settings ---
        settings_frame = ttk.LabelFrame(main_frame, text="2. 下載設定")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="輸出資料夾:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.output_entry = ttk.Entry(settings_frame, textvariable=self.output_path)
        self.output_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        self.select_folder_button = ttk.Button(settings_frame, text="選擇", command=self.select_folder)
        self.select_folder_button.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(settings_frame, text="容器:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        container_frame = ttk.Frame(settings_frame)
        container_frame.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W)
        ttk.Radiobutton(container_frame, text="MP4", variable=self.container_var, value="MP4").pack(side=tk.LEFT)
        ttk.Radiobutton(container_frame, text="MKV", variable=self.container_var, value="MKV").pack(side=tk.LEFT, padx=10)

        ttk.Label(settings_frame, text="畫質:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        quality_frame = ttk.Frame(settings_frame)
        quality_frame.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W)
        ttk.Radiobutton(quality_frame, text="最高畫質(H.264優先)", variable=self.quality_var, value="best").pack(side=tk.LEFT)
        ttk.Radiobutton(quality_frame, text="限制至", variable=self.quality_var, value="limit").pack(side=tk.LEFT, padx=10)
        self.quality_limit_entry = ttk.Entry(quality_frame, width=8, textvariable=self.quality_limit)
        self.quality_limit_entry.pack(side=tk.LEFT)
        ttk.Label(quality_frame, text="p").pack(side=tk.LEFT)

        ttk.Label(settings_frame, text="輸出模式:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        mode_frame = ttk.Frame(settings_frame)
        mode_frame.grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="兩支：中文+原音", variable=self.mode_var, value="both").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="只中文", variable=self.mode_var, value="chinese").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="只原音", variable=self.mode_var, value="original").pack(side=tk.LEFT, padx=10)

        adv_frame = ttk.LabelFrame(settings_frame, text="進階")
        adv_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        adv_frame.columnconfigure(1, weight=1)
        adv_row1 = ttk.Frame(adv_frame); adv_row1.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row1, text="檔名安全化", variable=self.safe_filename_var).pack(side=tk.LEFT); ttk.Label(adv_row1, text="併發數:").pack(side=tk.LEFT, padx=(15, 0)); self.concurrent_entry = ttk.Entry(adv_row1, width=5, textvariable=self.concurrent_fragments); self.concurrent_entry.pack(side=tk.LEFT, padx=5); ttk.Label(adv_row1, text="速率限制:").pack(side=tk.LEFT, padx=(15, 0)); self.rate_limit_entry = ttk.Entry(adv_row1, width=8, textvariable=self.rate_limit); self.rate_limit_entry.pack(side=tk.LEFT, padx=5); ttk.Label(adv_row1, text="KiB/s").pack(side=tk.LEFT)
        adv_row2 = ttk.Frame(adv_frame); adv_row2.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row2, text="Cookies", variable=self.cookies_var, command=self.toggle_adv_options).pack(side=tk.LEFT); self.cookie_entry = ttk.Entry(adv_row2, textvariable=self.cookie_file_path, state='disabled'); self.cookie_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5); self.cookie_button = ttk.Button(adv_row2, text="選擇檔案", state='disabled', command=self.select_cookie_file); self.cookie_button.pack(side=tk.LEFT)
        adv_row3 = ttk.Frame(adv_frame); adv_row3.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row3, text="Proxy", variable=self.proxy_var, command=self.toggle_adv_options).pack(side=tk.LEFT); self.proxy_entry = ttk.Entry(adv_row3, textvariable=self.proxy_address, state='disabled'); self.proxy_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(22,5))

        download_frame = ttk.Frame(main_frame)
        download_frame.pack(fill=tk.X, padx=5, pady=10)
        self.start_button = ttk.Button(download_frame, text="開始下載", command=self.start_download_thread, style="Accent.TButton")
        self.start_button.pack(side=tk.LEFT, ipady=5, expand=True, fill=tk.X)
        self.stop_button = ttk.Button(download_frame, text="中止", state=tk.DISABLED, command=self.request_stop)
        self.stop_button.pack(side=tk.LEFT, ipady=5, padx=(10,0))

        progress_frame = ttk.Frame(main_frame); progress_frame.pack(fill=tk.X, padx=5, pady=0); self.progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate'); self.progress_bar.pack(fill=tk.X, expand=True, pady=2); self.progress_label = ttk.Label(progress_frame, text="進度: 0%"); self.progress_label.pack(fill=tk.X, padx=5, pady=2)
        log_frame = ttk.LabelFrame(main_frame, text="日誌"); log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10); self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_context_menus(self):
        widgets = [self.url_entry, self.output_entry, self.quality_limit_entry, self.concurrent_entry, self.rate_limit_entry, self.log_text, self.cookie_entry, self.proxy_entry]
        for widget in widgets: self.create_context_menu(widget)

    def create_context_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="剪下", command=lambda: widget.event_generate('<<Cut>>'), accelerator="Ctrl-X")
        menu.add_command(label="複製", command=lambda: widget.event_generate('<<Copy>>'), accelerator="Ctrl-C")
        menu.add_command(label="貼上", command=lambda: widget.event_generate('<<Paste>>'), accelerator="Ctrl-V")
        menu.add_separator(); menu.add_command(label="全選", command=lambda: widget.event_generate('<<SelectAll>>'), accelerator="Ctrl-A")
        if isinstance(widget, scrolledtext.ScrolledText):
            menu.add_separator(); menu.add_command(label="複製全部", command=self.copy_all_from_log); menu.add_command(label="另存日誌...", command=self.save_log)
        widget.bind("<Button-3>", lambda e: self.show_context_menu(e, menu, widget))

    def show_context_menu(self, event, menu, widget):
        has_selection = False
        try: has_selection = bool(widget.selection_get())
        except tk.TclError: pass
        can_paste = bool(self.clipboard_get()); is_editable = widget.cget('state') == 'normal'
        menu.entryconfig("剪下", state='normal' if has_selection and is_editable else 'disabled'); menu.entryconfig("複製", state='normal' if has_selection else 'disabled'); menu.entryconfig("貼上", state='normal' if can_paste and is_editable else 'disabled'); menu.tk_popup(event.x_root, event.y_root)

    def copy_all_from_log(self): self.clipboard_clear(); self.clipboard_append(self.log_text.get('1.0', 'end-1c'))
    def save_log(self):
        content = self.log_text.get('1.0', 'end-1c')
        filepath = filedialog.asksaveasfilename(title="另存日誌", defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f: f.write(content)
            except Exception as e: self.log(f"無法儲存日誌: {e}")

    def on_closing(self): self.save_settings(); self.destroy()
    def save_settings(self):
        settings = {k: v.get() for k, v in self.get_tk_vars().items()}
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(settings, f, indent=4)
        except Exception as e: print(f"Error saving settings: {e}")
    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: settings = json.load(f)
                for key, var in self.get_tk_vars().items():
                    if key in settings: var.set(settings[key])
                self.toggle_adv_options()
        except Exception as e: print(f"Error loading settings: {e}")
    def get_tk_vars(self): return {k: v for k, v in self.__dict__.items() if isinstance(v, tk.Variable)}
    def toggle_adv_options(self): self.cookie_entry.config(state='normal' if self.cookies_var.get() else 'disabled'); self.cookie_button.config(state='normal' if self.cookies_var.get() else 'disabled'); self.proxy_entry.config(state='normal' if self.proxy_var.get() else 'disabled')
    def select_folder(self):
        folder = filedialog.askdirectory();
        if folder: self.output_path.set(folder)
    def select_cookie_file(self):
        fp = filedialog.askopenfilename(title="選擇 Netscape/Cookies.txt 格式的檔案", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]);
        if fp: self.cookie_file_path.set(fp)
    def get_ydl_opts(self):
        opts = {'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}
        if self.cookies_var.get() and self.cookie_file_path.get(): opts['cookiefile'] = self.cookie_file_path.get()
        if self.proxy_var.get() and self.proxy_address.get(): opts['proxy'] = self.proxy_address.get()
        if self.rate_limit.get().isdigit() and int(self.rate_limit.get()) > 0: opts['ratelimit'] = int(self.rate_limit.get()) * 1024
        if self.concurrent_fragments.get().isdigit() and int(self.concurrent_fragments.get()) > 0: opts['concurrent_fragment_downloads'] = int(self.concurrent_fragments.get())
        return opts
    def log(self, message): self.worker_queue.put({'type': 'log', 'data': message})
    def set_ui_state(self, state): self.after(0, lambda: self._set_ui_state_thread_safe(state))
    def _set_ui_state_thread_safe(self, state):
        is_disabled = state == 'disabled'
        self.start_button.config(state='disabled' if is_disabled else 'normal'); self.txt_button.config(state='disabled' if is_disabled else 'normal'); self.stop_button.config(state='normal' if is_disabled else 'disabled')
    def request_stop(self): self.log("收到中止請求...完成當前任務後將會停止。"); self.stop_requested.set()

    def start_download_thread(self):
        urls = [self.url_entry.get()]
        if not urls[0]: return messagebox.showwarning("警告", "請先輸入 URL。")
        self.set_ui_state('disabled'); self.stop_requested.clear()
        threading.Thread(target=self.process_urls, args=(urls,), daemon=True).start()
    def start_batch_from_file(self):
        filepath = filedialog.askopenfilename(title="選擇包含URL列表的TXT檔案", filetypes=[("Text files", "*.txt")])
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f: urls = [line.strip() for line in f if line.strip()]
            if not urls: return messagebox.showwarning("警告", "檔案為空或不包含有效的URL。")
            self.set_ui_state('disabled'); self.stop_requested.clear()
            threading.Thread(target=self.process_urls, args=(urls,), daemon=True).start()
        except Exception as e: messagebox.showerror("錯誤", f"讀取檔案失敗: {e}")

    def process_urls(self, urls):
        for i, url in enumerate(urls):
            if self.stop_requested.is_set(): self.log("任務已中止。"); break
            self.log(f"--- ({i+1}/{len(urls)}) 開始處理 URL: {url} ---")
            try:
                with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                    info = ydl.extract_info(url, download=False, process=False) # Use process=False for playlists
                video_list = info.get('entries', [info])
                if 'entries' in info: self.log(f"偵測到播放清單 '{info.get('title')}'，共 {len(video_list)} 個影片。")
                for video_entry in video_list:
                    if self.stop_requested.is_set(): self.log("任務已中止。"); break
                    self.download_single_video(video_entry)
            except Exception as e:
                self.worker_queue.put({'type': 'error', 'data': e, 'url': url})
        self.worker_queue.put({'type': 'task_finished'})

    def download_single_video(self, video_entry):
        try:
            self.log(f"分析影片: {video_entry.get('title') or video_entry.get('id')}")
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                full_info = ydl.extract_info(video_entry.get('url') or video_entry.get('webpage_url'), download=False)

            tasks = self.prepare_download_tasks(full_info)
            if not tasks: self.log(f"找不到符合設定的音軌，已略過。"); return

            self.download_and_merge(tasks, full_info)
        except Exception as e:
            self.worker_queue.put({'type': 'error', 'data': e, 'url': video_entry.get('webpage_url')})

    def build_video_format_selector(self):
        selector = "bestvideo"
        if self.quality_var.get() == 'limit' and self.quality_limit.get().isdigit():
            limit = int(self.quality_limit.get())
            selector += f"[height<={limit}]"

        # Prioritize H.264, fallback to any best video
        return f"{selector}[vcodec^=avc]/{selector}"

    def prepare_download_tasks(self, info):
        all_audios = [f for f in info.get('formats', []) if f.get('acodec') != 'none']
        audio_id_zh, audio_id_orig = None, None
        hant_audios = [a for a in all_audios if str(a.get('language')).lower().startswith('zh-hant')]
        if hant_audios: audio_id_zh = max(hant_audios, key=lambda x: x.get('abr') or 0).get('format_id')
        if not audio_id_zh:
            hans_audios = [a for a in all_audios if str(a.get('language')).lower().startswith('zh-hans')]
            if hans_audios: audio_id_zh = max(hans_audios, key=lambda x: x.get('abr') or 0).get('format_id')
        orig_audios = [a for a in all_audios if a.get('is_original')];
        if orig_audios: audio_id_orig = max(orig_audios, key=lambda x: x.get('abr') or 0).get('format_id')
        tasks, output_mode = [], self.mode_var.get()
        if output_mode in ['both', 'chinese']:
            if audio_id_zh: tasks.append({'audio_id': audio_id_zh, 'lang_tag': 'zh-Hant', 'suffix': '(中文)'})
            else: self.log(f"警告: 影片 '{info.get('title')}' 找不到中文音軌。")
        if output_mode in ['both', 'original']:
            if audio_id_orig: tasks.append({'audio_id': audio_id_orig, 'lang_tag': 'en', 'suffix': '(original)'})
            else: self.log(f"警告: 影片 '{info.get('title')}' 找不到原聲音軌。")
        return tasks

    def download_and_merge(self, tasks, base_info):
        tmp_files = []
        try:
            video_format_selector = self.build_video_format_selector()
            self.last_downloaded_info = None # Reset before download

            # Download Video using selector
            self.log(f"開始下載最佳影像 for '{base_info.get('title')}'")
            self._download_stream(video_format_selector, "__temp_video", base_info['webpage_url'])

            if not self.last_downloaded_info:
                raise Exception("無法從 yt-dlp progress hook 獲取下載資訊。")

            video_format_info = self.last_downloaded_info
            video_path = video_format_info['filepath']
            tmp_files.append(video_path)
            self.log(f"影像下載完成: {video_format_info.get('format')}")

            # Download and merge audio tracks
            for task in tasks:
                if self.stop_requested.is_set(): self.log("任務已中止。"); break
                audio_id = task['audio_id']
                self.log(f"開始下載音軌: {audio_id} {task['suffix']}")
                self._download_stream(audio_id, "__temp_audio", base_info['webpage_url'])

                audio_path = self.last_downloaded_info['filepath']
                tmp_files.append(audio_path)

                output_filename = self.get_safe_filename(video_format_info, task['suffix'], self.container_var.get().lower(), base_info)
                output_filepath = os.path.join(self.output_path.get(), output_filename)
                self.log(f"開始合併為: {output_filename}")
                command = ['ffmpeg', '-y', '-i', video_path, '-i', audio_path, '-c', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-metadata:s:a:0', f"language={task['lang_tag']}", output_filepath]
                startupinfo = subprocess.STARTUPINFO(dwFlags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else None
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', startupinfo=startupinfo)
                for line in process.stdout: self.log(f"[ffmpeg] {line.strip()}")
                process.wait()
                if process.returncode == 0: self.log(f"成功建立: {output_filename}")
                else: self.log(f"錯誤: FFmpeg 合併失敗 (返回碼 {process.returncode})")
                os.remove(audio_path); tmp_files.remove(audio_path)
        except FileNotFoundError: self.worker_queue.put({'type': 'error', 'data': 'FFmpeg not found. 請安裝 FFmpeg 並將其加入系統 PATH 中。'})
        except Exception as e: self.worker_queue.put({'type': 'error', 'data': e})
        finally:
            for f in tmp_files:
                if os.path.exists(f): os.remove(f)

    def _download_stream(self, format_id_or_selector, out_template, url):
        # Note: out_template is now a template name, not a full path
        ydl_opts = self.get_ydl_opts()
        ydl_opts.update({
            'format': format_id_or_selector,
            'outtmpl': os.path.join(self.output_path.get(), f"{out_template}.%(ext)s"),
            'progress_hooks': [self.progress_hook],
            'overwrites': True
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])

    def progress_hook(self, d):
        if d['status'] == 'finished':
            self.last_downloaded_info = d['info_dict']
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%').replace('%','').strip()
            try: percent = float(percent_str)
            except (ValueError, TypeError): percent = 0
            self.worker_queue.put({'type': 'progress', 'data': {'percent': percent}})

    def process_worker_queue(self):
        try:
            message = self.worker_queue.get_nowait()
            msg_type, data = message.get('type'), message.get('data')
            if msg_type == 'log':
                timestamp = time.strftime("%H:%M:%S", time.localtime()); self.log_text.insert(tk.END, f"[{timestamp}] {data}\n"); self.log_text.see(tk.END)
            elif msg_type == 'error':
                url = message.get('url', ''); error_str = str(data)
                self.log(f"處理 '{url}' 時發生錯誤: {error_str}")
                if "unavailable" in error_str.lower() or "private" in error_str.lower(): self.log("提示: 該影片可能為私人影片、已被刪除或有地區限制，請嘗試使用 Cookies/Proxy。")
            elif msg_type == 'progress':
                self.progress_bar['value'] = data['percent']; self.progress_label.config(text=f"進度: {data['percent']:.1f}%")
            elif msg_type == 'task_finished':
                self.set_ui_state('normal'); self.progress_bar['value'] = 0; self.progress_label.config(text="進度: 0%")
                self.log("所有任務完成。")
                if self.stop_requested.is_set(): self.log("任務已由使用者中止。")
                elif messagebox.askyesno("完成", "所有下載任務已完成，是否要開啟輸出資料夾？"):
                    if os.path.exists(self.output_path.get()): os.startfile(self.output_path.get())
                    else: self.log(f"錯誤: 輸出資料夾不存在: {self.output_path.get()}")
        except queue.Empty: pass
        finally: self.after(100, self.process_worker_queue)

    def get_safe_filename(self, video_info, suffix, ext, base_info):
        title = base_info.get('title', 'video'); video_id = base_info.get('id', ''); height = video_info.get('height', 'N/A'); vcodec = video_info.get('vcodec', 'N/A').split('.')[0]
        template = f"{title} [{video_id}]_{height}p_{vcodec} {suffix}"
        if self.safe_filename_var.get():
            sanitized = re.sub(r'[\\/*?:"<>|]', "", template); sanitized = sanitized.translate(str.maketrans("".join(chr(0xff01 + i) for i in range(94)), "".join(chr(0x21 + i) for i in range(94)))); sanitized = sanitized[:150]
            return f"{sanitized}.{ext}"
        return f"{template}.{ext}"

if __name__ == "__main__":
    app = App()
    style = ttk.Style(app)
    style.configure("Accent.TButton", font=("Helvetica", 10, "bold"), padding=5)
    app.mainloop()
