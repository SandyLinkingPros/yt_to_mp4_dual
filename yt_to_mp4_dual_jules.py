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

class ContextMenu:
    # ... (ContextMenu class is complete and remains unchanged) ...
    """A factory for creating context menus for different widgets."""
    def __init__(self, widget):
        self.widget = widget
        self.menu = tk.Menu(widget, tearoff=0)
        widget_type = widget.winfo_class()
        if widget_type in ('TEntry', 'Entry', 'ScrolledText'):
            self.add_command("剪下", self.cut, '<<Cut>>', 'Ctrl+X'); self.add_command("複製", self.copy, '<<Copy>>', 'Ctrl+C'); self.add_command("貼上", self.paste, '<<Paste>>', 'Ctrl+V'); self.add_separator(); self.add_command("全選", self.select_all, '<<SelectAll>>', 'Ctrl+A'); self.add_command("清空", self.clear)
        elif widget_type == 'Treview':
            self.add_command("複製選取", self.copy_treeview_selection); self.add_separator(); self.add_command("全選", self.select_all_treeview)
        if widget_type == 'ScrolledText':
            self.add_separator(); self.add_command("複製全部", self.copy_all); self.add_command("另存日誌...", self.save_log)
        widget.bind("<Button-3>", self.show_menu)
    def add_command(self, label, command, event=None, accelerator=None):
        self.menu.add_command(label=label, command=command, accelerator=accelerator)
        if event: self.widget.bind(f"<{accelerator.replace('Ctrl', 'Control')}>", lambda e: self.widget.event_generate(event))
    def add_separator(self): self.menu.add_separator()
    def show_menu(self, event):
        try:
            if self.widget.winfo_class() in ('TEntry', 'Entry', 'ScrolledText'):
                has_selection = bool(self.widget.tag_ranges("sel")); can_paste = bool(self.widget.clipboard_get()); is_editable = self.widget.cget('state') == 'normal'
                self.menu.entryconfig("剪下", state='normal' if has_selection and is_editable else 'disabled'); self.menu.entryconfig("複製", state='normal' if has_selection else 'disabled'); self.menu.entryconfig("貼上", state='normal' if can_paste and is_editable else 'disabled'); self.menu.entryconfig("清空", state='normal' if is_editable else 'disabled')
            self.menu.tk_popup(event.x_root, event.y_root)
        finally: self.menu.grab_release()
    def cut(self): self.widget.event_generate('<<Cut>>')
    def copy(self): self.widget.event_generate('<<Copy>>')
    def paste(self): self.widget.event_generate('<<Paste>>')
    def select_all(self): self.widget.event_generate('<<SelectAll>>')
    def clear(self):
        if self.widget.cget('state') == 'normal': self.widget.delete(0, 'end')
    def copy_treeview_selection(self):
        content = ["\t".join(map(str, self.widget.item(item_id, 'values'))) for item_id in self.widget.selection()]
        if content: self.widget.clipboard_clear(); self.widget.clipboard_append("\n".join(content))
    def select_all_treeview(self): self.widget.selection_set(self.widget.get_children())
    def copy_all(self):
        content = self.widget.get('1.0', 'end-1c'); self.widget.clipboard_clear(); self.widget.clipboard_append(content)
    def save_log(self):
        content = self.widget.get('1.0', 'end-1c')
        filepath = filedialog.asksaveasfilename(title="另存日誌", defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f: f.write(content)
            except Exception as e: messagebox.showerror("錯誤", f"無法儲存檔案: {e}")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube 影片下載器 v1.1")
        self.geometry("900x800")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.worker_queue = queue.Queue(); self.current_info = None; self.download_thread = None; self.stop_requested = threading.Event()
        self.output_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Videos")); self.container_var = tk.StringVar(value="MP4"); self.quality_var = tk.StringVar(value="best"); self.quality_limit = tk.StringVar(value="1080"); self.mode_var = tk.StringVar(value="both"); self.safe_filename_var = tk.BooleanVar(value=True); self.cookies_var = tk.BooleanVar(value=False); self.cookie_file_path = tk.StringVar(value=""); self.proxy_var = tk.BooleanVar(value=False); self.proxy_address = tk.StringVar(value=""); self.concurrent_fragments = tk.StringVar(value="3"); self.rate_limit = tk.StringVar(value="0")
        self.build_ui(); self.setup_context_menus(); self.load_settings(); self.process_worker_queue()

    def build_ui(self):
        main_frame = ttk.Frame(self, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        url_frame = ttk.LabelFrame(main_frame, text="1. 輸入來源"); url_frame.pack(fill=tk.X, padx=5, pady=5); url_frame.columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="URL:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W); self.url_entry = ttk.Entry(url_frame); self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        self.txt_button = ttk.Button(url_frame, text="選TXT清單", command=self.select_txt_file); self.txt_button.grid(row=0, column=2, padx=5, pady=5)
        self.detect_button = ttk.Button(url_frame, text="偵測", command=self.start_task_thread); self.detect_button.grid(row=0, column=3, padx=5, pady=5)
        settings_frame = ttk.LabelFrame(main_frame, text="2. 下載設定"); settings_frame.pack(fill=tk.X, padx=5, pady=5); settings_frame.columnconfigure(1, weight=1)
        ttk.Label(settings_frame, text="輸出資料夾:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W); self.output_entry = ttk.Entry(settings_frame, textvariable=self.output_path); self.output_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        self.select_folder_button = ttk.Button(settings_frame, text="選擇", command=self.select_folder); self.select_folder_button.grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(settings_frame, text="容器:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W); container_frame = ttk.Frame(settings_frame); container_frame.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W); ttk.Radiobutton(container_frame, text="MP4", variable=self.container_var, value="MP4").pack(side=tk.LEFT); ttk.Radiobutton(container_frame, text="MKV", variable=self.container_var, value="MKV").pack(side=tk.LEFT, padx=10)
        ttk.Label(settings_frame, text="畫質:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W); quality_frame = ttk.Frame(settings_frame); quality_frame.grid(row=2, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W); ttk.Radiobutton(quality_frame, text="最高畫質(H.264優先)", variable=self.quality_var, value="best").pack(side=tk.LEFT); ttk.Radiobutton(quality_frame, text="限制至", variable=self.quality_var, value="limit").pack(side=tk.LEFT, padx=10)
        self.quality_limit_entry = ttk.Entry(quality_frame, width=8, textvariable=self.quality_limit); self.quality_limit_entry.pack(side=tk.LEFT); ttk.Label(quality_frame, text="p").pack(side=tk.LEFT)
        ttk.Label(settings_frame, text="輸出模式:").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W); mode_frame = ttk.Frame(settings_frame); mode_frame.grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky=tk.W); ttk.Radiobutton(mode_frame, text="兩支：中文+原音", variable=self.mode_var, value="both").pack(side=tk.LEFT); ttk.Radiobutton(mode_frame, text="只中文", variable=self.mode_var, value="chinese").pack(side=tk.LEFT, padx=10); ttk.Radiobutton(mode_frame, text="只原音", variable=self.mode_var, value="original").pack(side=tk.LEFT, padx=10)
        adv_frame = ttk.LabelFrame(settings_frame, text="進階"); adv_frame.grid(row=4, column=0, columnspan=3, sticky=tk.EW, padx=5, pady=5); adv_frame.columnconfigure(1, weight=1)
        adv_row1 = ttk.Frame(adv_frame); adv_row1.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row1, text="檔名安全化", variable=self.safe_filename_var).pack(side=tk.LEFT); ttk.Label(adv_row1, text="併發數:").pack(side=tk.LEFT, padx=(15, 0)); self.concurrent_entry = ttk.Entry(adv_row1, width=5, textvariable=self.concurrent_fragments); self.concurrent_entry.pack(side=tk.LEFT, padx=5); ttk.Label(adv_row1, text="速率限制:").pack(side=tk.LEFT, padx=(15, 0)); self.rate_limit_entry = ttk.Entry(adv_row1, width=8, textvariable=self.rate_limit); self.rate_limit_entry.pack(side=tk.LEFT, padx=5); ttk.Label(adv_row1, text="KiB/s").pack(side=tk.LEFT)
        adv_row2 = ttk.Frame(adv_frame); adv_row2.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row2, text="Cookies", variable=self.cookies_var, command=self.toggle_adv_options).pack(side=tk.LEFT); self.cookie_entry = ttk.Entry(adv_row2, textvariable=self.cookie_file_path, state='disabled'); self.cookie_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5); self.cookie_button = ttk.Button(adv_row2, text="選擇檔案", state='disabled', command=self.select_cookie_file); self.cookie_button.pack(side=tk.LEFT)
        adv_row3 = ttk.Frame(adv_frame); adv_row3.pack(fill=tk.X, padx=5, pady=2); ttk.Checkbutton(adv_row3, text="Proxy", variable=self.proxy_var, command=self.toggle_adv_options).pack(side=tk.LEFT); self.proxy_entry = ttk.Entry(adv_row3, textvariable=self.proxy_address, state='disabled'); self.proxy_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(22,5))
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, padx=5, pady=10)
        result_frame = ttk.LabelFrame(main_frame, text="3. 偵測結果"); result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); paned_window = ttk.PanedWindow(result_frame, orient=tk.HORIZONTAL); paned_window.pack(fill=tk.BOTH, expand=True); video_frame = ttk.Frame(paned_window); audio_frame = ttk.Frame(paned_window); paned_window.add(video_frame, weight=1); paned_window.add(audio_frame, weight=1)
        ttk.Label(video_frame, text="畫質候選 (單選)").pack(anchor=tk.W, padx=5, pady=2); self.video_tree = ttk.Treeview(video_frame, columns=('ID', 'ext', 'res', 'fps', 'vcodec', 'size'), show='headings', height=5, selectmode='extended'); self.video_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); self.video_tree.heading('ID', text='ID'); self.video_tree.column('ID', width=50); self.video_tree.heading('ext', text='格式'); self.video_tree.column('ext', width=50); self.video_tree.heading('res', text='解析度'); self.video_tree.column('res', width=100); self.video_tree.heading('fps', text='FPS'); self.video_tree.column('fps', width=50); self.video_tree.heading('vcodec', text='編碼'); self.video_tree.column('vcodec', width=100); self.video_tree.heading('size', text='大小(MB)'); self.video_tree.column('size', width=80)
        ttk.Label(audio_frame, text="音軌清單").pack(anchor=tk.W, padx=5, pady=2); self.audio_tree = ttk.Treeview(audio_frame, columns=('ID', 'lang', 'acodec', 'abr', 'note'), show='headings', height=5, selectmode='extended'); self.audio_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); self.audio_tree.heading('ID', text='ID'); self.audio_tree.column('ID', width=50); self.audio_tree.heading('lang', text='語言'); self.audio_tree.column('lang', width=80); self.audio_tree.heading('acodec', text='編碼'); self.audio_tree.column('acodec', width=100); self.audio_tree.heading('abr', text='碼率(kbps)'); self.audio_tree.column('abr', width=80); self.audio_tree.heading('note', text='備註'); self.audio_tree.column('note', width=100)
        download_frame = ttk.Frame(main_frame); download_frame.pack(fill=tk.X, padx=5, pady=5); self.start_button = ttk.Button(download_frame, text="開始下載", command=self.start_download_thread); self.start_button.pack(side=tk.LEFT, padx=5); self.stop_button = ttk.Button(download_frame, text="中止", state=tk.DISABLED, command=self.request_stop); self.stop_button.pack(side=tk.LEFT, padx=5)
        progress_frame = ttk.Frame(main_frame); progress_frame.pack(fill=tk.X, padx=5, pady=5); self.progress_bar = ttk.Progressbar(progress_frame, orient='horizontal', mode='determinate'); self.progress_bar.pack(fill=tk.X, expand=True, padx=5, pady=2); self.progress_label = ttk.Label(progress_frame, text="進度: 0%  剩餘 --:--")
        self.progress_label.pack(fill=tk.X, padx=5, pady=2)
        log_frame = ttk.LabelFrame(main_frame, text="日誌"); log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5); self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10); self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    def setup_context_menus(self): ContextMenu(self.url_entry); ContextMenu(self.output_entry); ContextMenu(self.quality_limit_entry); ContextMenu(self.concurrent_entry); ContextMenu(self.rate_limit_entry); ContextMenu(self.log_text); ContextMenu(self.video_tree); ContextMenu(self.audio_tree); ContextMenu(self.cookie_entry); ContextMenu(self.proxy_entry)
    def on_closing(self): self.save_settings(); self.destroy()
    def save_settings(self):
        settings = {'output_path': self.output_path.get(),'container_var': self.container_var.get(),'quality_var': self.quality_var.get(),'quality_limit': self.quality_limit.get(),'mode_var': self.mode_var.get(),'safe_filename_var': self.safe_filename_var.get(),'cookies_var': self.cookies_var.get(),'cookie_file_path': self.cookie_file_path.get(),'proxy_var': self.proxy_var.get(),'proxy_address': self.proxy_address.get(),'concurrent_fragments': self.concurrent_fragments.get(),'rate_limit': self.rate_limit.get()}
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(settings, f, indent=4)
        except Exception as e: print(f"Error saving settings: {e}")
    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    for key, var in self.get_tk_vars().items(): var.set(settings.get(key, var.get()))
                self.toggle_adv_options()
        except Exception as e: print(f"Error loading settings: {e}")
    def get_tk_vars(self): return {k: v for k, v in self.__dict__.items() if isinstance(v, tk.Variable)}
    def toggle_adv_options(self): self.cookie_entry.config(state='normal' if self.cookies_var.get() else 'disabled'); self.cookie_button.config(state='normal' if self.cookies_var.get() else 'disabled'); self.proxy_entry.config(state='normal' if self.proxy_var.get() else 'disabled')
    def select_folder(self):
        folder_selected = filedialog.askdirectory();
        if folder_selected: self.output_path.set(folder_selected)
    def select_cookie_file(self):
        filepath = filedialog.askopenfilename(title="選擇 Netscape/Cookies.txt 格式的檔案", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]);
        if filepath: self.cookie_file_path.set(filepath)
    def select_txt_file(self):
        filepath = filedialog.askopenfilename(title="選擇包含URL列表的TXT檔案", filetypes=[("Text files", "*.txt")])
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f: urls = [line.strip() for line in f if line.strip()]
                if urls: self.start_task_thread(urls)
                else: messagebox.showwarning("警告", "檔案為空或不包含有效的URL。")
            except Exception as e: messagebox.showerror("錯誤", f"讀取檔案失敗: {e}")
    def get_ydl_opts(self):
        opts = {'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}
        if self.cookies_var.get() and self.cookie_file_path.get(): opts['cookiefile'] = self.cookie_file_path.get()
        if self.proxy_var.get() and self.proxy_address.get(): opts['proxy'] = self.proxy_address.get()
        if self.rate_limit.get().isdigit() and int(self.rate_limit.get()) > 0: opts['ratelimit'] = int(self.rate_limit.get()) * 1024
        if self.concurrent_fragments.get().isdigit() and int(self.concurrent_fragments.get()) > 0: opts['concurrent_fragment_downloads'] = int(self.concurrent_fragments.get())
        return opts
    def log(self, message): self.worker_queue.put({'type': 'log', 'data': message})
    def set_ui_state(self, state):
        self.after(0, lambda: self._set_ui_state_thread_safe(state))
    def _set_ui_state_thread_safe(self, state):
        is_disabled = state == 'disabled'
        for child in self.winfo_children():
            if hasattr(child, 'winfo_children'):
                for widget in child.winfo_children():
                    if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Radiobutton, ttk.Checkbutton)): widget.config(state=state)
        self.start_button.config(state='disabled' if is_disabled else 'normal'); self.stop_button.config(state='normal' if is_disabled else 'disabled')
        if not is_disabled: self.detect_button.config(state='normal'); self.select_folder_button.config(state='normal'); self.txt_button.config(state='normal'); self.toggle_adv_options()
    def request_stop(self): self.log("收到中止請求...完成當前任務後將會停止。"); self.stop_requested.set()
    def start_task_thread(self, urls=None):
        if not urls: urls = [self.url_entry.get()]
        if not urls[0]: return messagebox.showwarning("警告", "請先輸入 URL 或選擇 TXT 檔案")
        self.set_ui_state('disabled'); self.stop_requested.clear()
        threading.Thread(target=self.process_urls, args=(urls,), daemon=True).start()
    def process_urls(self, urls):
        for i, url in enumerate(urls):
            if self.stop_requested.is_set(): self.log("任務已中止。"); break
            self.log(f"開始處理第 {i+1}/{len(urls)} 個 URL: {url}")
            try: self.worker_queue.put({'type': 'clear_results'}); time.sleep(0.1) # Wait for UI to clear
            except queue.Full: pass
            self.detect_and_download_url(url)
        self.worker_queue.put({'type': 'batch_finished'})
    def detect_and_download_url(self, url):
        try:
            ydl_opts = self.get_ydl_opts()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.worker_queue.put({'type': 'detection_result', 'data': info})
            if info.get('_type') == 'playlist':
                self.log(f"偵測到播放清單: '{info.get('title')}'，將處理其中的影片。")
                for entry in info['entries']:
                    if self.stop_requested.is_set(): self.log("任務已中止。"); return
                    self.log(f"處理播放清單中的影片: {entry.get('title')}")
                    self.download_video_with_info(entry)
            else: self.download_video_with_info(info)
        except Exception as e: self.worker_queue.put({'type': 'error', 'data': e, 'url': url})
    def download_video_with_info(self, info):
        self.current_info = info
        selected_video_item = self.find_best_video_format(info)
        if not selected_video_item: self.log(f"錯誤: 找不到適合 {info.get('title')} 的影像格式，已略過。"); return
        video_info = next((f for f in info['formats'] if f['format_id'] == selected_video_item['id']), None)
        if self.container_var.get() == 'MP4' and video_info.get('vcodec', '').startswith(('vp09', 'av01')):
            if not messagebox.askokcancel("相容性警告", f"您選擇的畫質 ({video_info.get('resolution')}, {video_info.get('vcodec')}) 在 MP4 容器中可能會有相容性問題。\n\n建議改用 MKV 容器以獲得最佳效果。\n\n是否仍要繼續使用 MP4 下載？"):
                self.log("使用者因相容性問題取消下載。"); return
        tasks = self.prepare_download_tasks(info)
        if not tasks: self.log(f"警告: 找不到符合 '{info.get('title')}' 的音軌，已略過。"); return
        self.download_and_merge(video_info, tasks, info)
    def find_best_video_format(self, info):
        videos = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
        h264_videos = [v for v in videos if 'avc' in v.get('vcodec', '')]
        target_videos = h264_videos if h264_videos else videos
        if not target_videos: return None
        target_videos.sort(key=lambda x: (int(x.get('height', 0)), x.get('fps', 0)), reverse=True)
        return target_videos[0]
    def prepare_download_tasks(self, info):
        all_audios = [f for f in info['formats'] if f.get('acodec') != 'none']
        audio_id_zh, audio_id_orig = None, None
        hant_audios = [a for a in all_audios if str(a.get('language')).lower().startswith('zh-hant')]; hans_audios = [a for a in all_audios if str(a.get('language')).lower().startswith('zh-hans')]
        if hant_audios: audio_id_zh = max(hant_audios, key=lambda x: x.get('abr', 0))['format_id']
        elif hans_audios: audio_id_zh = max(hans_audios, key=lambda x: x.get('abr', 0))['format_id']
        orig_audios = [a for a in all_audios if a.get('is_original')];
        if orig_audios: audio_id_orig = max(orig_audios, key=lambda x: x.get('abr', 0))['format_id']
        tasks = []
        output_mode = self.mode_var.get()
        if output_mode in ['both', 'chinese']:
            if audio_id_zh: tasks.append({'audio_id': audio_id_zh, 'lang_tag': 'zh-Hant', 'suffix': '(中文)'})
            else: self.log(f"警告: 影片 '{info.get('title')}' 找不到中文音軌。")
        if output_mode in ['both', 'original']:
            if audio_id_orig: tasks.append({'audio_id': audio_id_orig, 'lang_tag': 'en', 'suffix': '(original)'})
            else: self.log(f"警告: 影片 '{info.get('title')}' 找不到原聲音軌。")
        return tasks
    def download_and_merge(self, video_info, tasks, base_info):
        self.log(f"準備下載 '{base_info.get('title')}'...")
        tmp_files = []; video_path = os.path.join(self.output_path.get(), f"__temp_video.{video_info['ext']}")
        try:
            self.log(f"開始下載影像: {video_info['format_id']}"); tmp_files.append(video_path); self._download_stream(video_info['format_id'], video_path, base_info['webpage_url']); self.log("影像下載完成。")
            for task in tasks:
                if self.stop_requested.is_set(): self.log("任務已中止。"); break
                audio_id = task['audio_id']; audio_info = next((f for f in base_info['formats'] if f['format_id'] == audio_id), None); audio_ext = audio_info['ext']; audio_path = os.path.join(self.output_path.get(), f"__temp_audio.{audio_ext}"); tmp_files.append(audio_path)
                self.log(f"開始下載音軌: {audio_id} {task['suffix']}"); self._download_stream(audio_id, audio_path, base_info['webpage_url']); self.log(f"音軌 {audio_id} 下載完成。")
                output_filename = self.get_safe_filename(video_info, task['suffix'], self.container_var.get().lower(), base_info)
                output_filepath = os.path.join(self.output_path.get(), output_filename); self.log(f"開始合併為: {output_filename}")
                command = ['ffmpeg', '-y', '-i', video_path, '-i', audio_path, '-c', 'copy', '-map', '0:v:0', '-map', '1:a:0', '-metadata:s:a:0', f"language={task['lang_tag']}", output_filepath]
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', startupinfo=subprocess.STARTUPINFO(dwFlags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else None)
                for line in process.stdout: self.log(f"[ffmpeg] {line.strip()}")
                process.wait()
                if process.returncode == 0: self.log(f"成功建立: {output_filename}")
                else: self.log(f"錯誤: FFmpeg 合併失敗 (返回碼 {process.returncode})"); self.worker_queue.put({'type': 'log', 'data': f"FFmpeg command: {' '.join(command)}"})
                os.remove(audio_path); tmp_files.remove(audio_path)
        except FileNotFoundError: self.worker_queue.put({'type': 'error', 'data': 'FFmpeg not found. Please install FFmpeg and ensure it is in your system\'s PATH.'})
        except Exception as e: self.worker_queue.put({'type': 'error', 'data': e})
        finally:
            for f in tmp_files:
                if os.path.exists(f): os.remove(f)
    def _download_stream(self, format_id, outpath, url):
        ydl_opts = self.get_ydl_opts()
        ydl_opts.update({'format': format_id, 'outtmpl': outpath, 'progress_hooks': [self.progress_hook], 'overwrites': True})
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
    def progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').replace('%','').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', '--:--').strip()
            self.worker_queue.put({'type': 'progress', 'data': {'percent': float(percent), 'speed': speed, 'eta': eta}})
    def process_worker_queue(self):
        try:
            message = self.worker_queue.get_nowait()
            msg_type, data = message.get('type'), message.get('data')
            if msg_type == 'log':
                timestamp = time.strftime("%H:%M:%S", time.localtime()); self.log_text.insert(tk.END, f"[{timestamp}] {data}\n"); self.log_text.see(tk.END)
            elif msg_type == 'clear_results':
                for i in self.video_tree.get_children(): self.video_tree.delete(i)
                for i in self.audio_tree.get_children(): self.audio_tree.delete(i)
            elif msg_type == 'detection_result':
                self.update_results_ui(data)
            elif msg_type == 'error':
                url = message.get('url', '')
                error_str = str(data)
                self.log(f"處理 '{url}' 時發生錯誤: {error_str}")
                if "unavailable" in error_str.lower() or "private" in error_str.lower(): self.log("提示: 該影片可能為私人影片、已被刪除或有地區限制，請嘗試使用 Cookies/Proxy。")
                self.set_ui_state('normal')
            elif msg_type == 'progress':
                self.progress_bar['value'] = data['percent']; self.progress_label.config(text=f"進度: {data['percent']:.1f}% | 速度: {data['speed']} | 剩餘: {data['eta']}")
            elif msg_type == 'batch_finished':
                self.set_ui_state('normal'); self.progress_bar['value'] = 0; self.progress_label.config(text="進度: 0%  剩餘 --:--")
                self.log("所有任務完成。")
                if messagebox.askyesno("完成", "所有下載任務已完成，是否要開啟輸出資料夾？"):
                    if os.path.exists(self.output_path.get()): os.startfile(self.output_path.get())
                    else: self.log(f"錯誤: 輸出資料夾不存在: {self.output_path.get()}")
        except queue.Empty: pass
        finally: self.after(100, self.process_worker_queue)
    def update_results_ui(self, info):
        self.current_info = info
        self.log(f"偵測到影片: {info.get('title')}")
        for i in self.video_tree.get_children(): self.video_tree.delete(i)
        for i in self.audio_tree.get_children(): self.audio_tree.delete(i)
        video_formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
        audio_formats = [f for f in info.get('formats', []) if f.get('acodec') != 'none']
        video_formats.sort(key=lambda x: (int(x.get('height',0)), x.get('fps',0)), reverse=True)
        for f in video_formats:
            size_mb = f.get('filesize') or f.get('filesize_approx'); self.video_tree.insert('', 'end', values=(f['format_id'], f.get('ext'), f.get('resolution'), f.get('fps'), f.get('vcodec'), f"{round(size_mb / (1024*1024), 2):.2f}" if size_mb else "N/A"), iid=f['format_id'])
        audio_formats.sort(key=lambda x: ((x.get('language') or ''), (x.get('abr') or 0)), reverse=True)
        for f in audio_formats:
            note = 'original' if f.get('is_original') else ('auto-dub' if f.get('asr') else ''); self.audio_tree.insert('', 'end', values=(f['format_id'], f.get('language', 'N/A'), f.get('acodec'), f.get('abr'), note), iid=f['format_id'])
        self.log(f"找到 {len(video_formats)} 個影像格式，{len(audio_formats)} 個音軌。")
    def get_safe_filename(self, video_info, suffix, ext, base_info):
        title = base_info.get('title', 'video'); video_id = base_info.get('id', ''); height = video_info.get('height', 'N/A'); vcodec = video_info.get('vcodec', 'N/A').split('.')[0]
        template = f"{title} [{video_id}]_{height}p_{vcodec} {suffix}"
        if self.safe_filename_var.get():
            sanitized = re.sub(r'[\\/*?:"<>|]', "", template); sanitized = sanitized.translate(str.maketrans("".join(chr(0xff01 + i) for i in range(94)), "".join(chr(0x21 + i) for i in range(94)))); sanitized = sanitized[:150]
            return f"{sanitized}.{ext}"
        return f"{template}.{ext}"

if __name__ == "__main__":
    app = App()
    app.mainloop()
