import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from werkzeug.serving import make_server

from app import CONFIG_PATH, create_app, load_config, save_config


class ServerController:
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.server = None
        self.thread = None
        self.config = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, config: dict) -> None:
        if self.is_running():
            self.log_callback('Server is already running.')
            return

        self.config = config
        app = create_app(config, on_event=self.log_callback)
        host = app.config['APP_CONFIG']['host']
        port = app.config['APP_CONFIG']['port']
        upload_dir = app.config['APP_CONFIG']['upload_dir']
        self.server = make_server(host, port, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.log_callback(f'Server started: http://{host}:{port}')
        self.log_callback(f'Upload directory: {upload_dir}')

    def stop(self) -> None:
        if not self.is_running() or self.server is None:
            self.log_callback('Server is not running.')
            return

        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.server = None
        self.thread = None
        self.log_callback('Server stopped.')


class WebCameraGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WebCamera Server')
        self.geometry('760x560')
        self.minsize(680, 500)

        self.log_queue = queue.Queue()
        self.server = ServerController(self.enqueue_log)
        self.config_vars = {}

        self.create_widgets()
        self.load_config_to_form()
        self.after(100, self.flush_logs)
        self.after(250, self.auto_start_server)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def create_widgets(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        settings = ttk.LabelFrame(root, text='Settings', padding=12)
        settings.grid(row=0, column=0, sticky='ew')
        settings.columnconfigure(1, weight=1)

        self.config_vars['port'] = tk.StringVar()
        self.config_vars['upload_dir'] = tk.StringVar()
        self.config_vars['max_upload_mb'] = tk.StringVar()
        self.config_vars['allowed_extensions'] = tk.StringVar()
        self.config_vars['thept_path'] = tk.StringVar()
        self.config_vars['exam_names'] = tk.StringVar()

        self.add_row(settings, 0, 'Port', ttk.Entry(settings, textvariable=self.config_vars['port']))

        upload_row = ttk.Frame(settings)
        upload_row.columnconfigure(0, weight=1)
        ttk.Entry(upload_row, textvariable=self.config_vars['upload_dir']).grid(row=0, column=0, sticky='ew')
        ttk.Button(upload_row, text='Browse...', command=self.browse_upload_dir).grid(row=0, column=1, padx=(8, 0))
        self.add_row(settings, 1, 'Upload directory', upload_row)

        self.add_row(settings, 2, 'Max upload MB', ttk.Entry(settings, textvariable=self.config_vars['max_upload_mb']))
        self.add_row(settings, 3, 'Extensions', ttk.Entry(settings, textvariable=self.config_vars['allowed_extensions']))

        thept_row = ttk.Frame(settings)
        thept_row.columnconfigure(0, weight=1)
        ttk.Entry(thept_row, textvariable=self.config_vars['thept_path']).grid(row=0, column=0, sticky='ew')
        ttk.Button(thept_row, text='Browse...', command=self.browse_thept_path).grid(row=0, column=1, padx=(8, 0))
        self.add_row(settings, 4, 'thept.txt path', thept_row)

        self.add_row(settings, 5, 'Exam names', ttk.Entry(settings, textvariable=self.config_vars['exam_names']))

        controls = ttk.Frame(root)
        controls.grid(row=1, column=0, sticky='ew', pady=12)
        controls.columnconfigure(3, weight=1)
        ttk.Button(controls, text='Save settings', command=self.save_settings).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, text='Start server', command=self.start_server_from_form).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(controls, text='Stop server', command=self.stop_server).grid(row=0, column=2, padx=(0, 8))
        self.status_var = tk.StringVar(value='Stopped')
        ttk.Label(controls, textvariable=self.status_var, anchor='e').grid(row=0, column=3, sticky='e')

        log_frame = ttk.LabelFrame(root, text='Log', padding=8)
        log_frame.grid(row=2, column=0, sticky='nsew')
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=14, wrap='word', state='disabled')
        self.log_text.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def add_row(self, parent, row: int, label: str, widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
        widget.grid(row=row, column=1, sticky='ew', pady=4)

    def load_config_to_form(self) -> None:
        config = load_config()
        self.config_vars['port'].set(str(config['port']))
        self.config_vars['upload_dir'].set(str(config['upload_dir']))
        self.config_vars['max_upload_mb'].set(str(config['max_upload_mb']))
        self.config_vars['allowed_extensions'].set(', '.join(config['allowed_extensions']))
        self.config_vars['thept_path'].set(str(config.get('thept_path', r'C:\\common\\thept.txt')))
        self.config_vars['exam_names'].set(', '.join(config.get('exam_names', ['カメラ'])))
        self.enqueue_log(f'Config loaded: {CONFIG_PATH}')

    def config_from_form(self) -> dict:
        extensions = [
            extension.strip().lower().lstrip('.')
            for extension in self.config_vars['allowed_extensions'].get().split(',')
            if extension.strip()
        ]
        if not extensions:
            raise ValueError('Extensions must not be empty.')

        port = int(self.config_vars['port'].get())
        if port < 1 or port > 65535:
            raise ValueError('Port must be between 1 and 65535.')

        max_upload_mb = int(self.config_vars['max_upload_mb'].get())
        if max_upload_mb < 1:
            raise ValueError('Max upload MB must be 1 or greater.')

        upload_dir = self.config_vars['upload_dir'].get().strip()
        if not upload_dir:
            raise ValueError('Upload directory must not be empty.')

        thept_path = self.config_vars['thept_path'].get().strip()
        if not thept_path:
            raise ValueError('thept.txt path must not be empty.')

        exam_names = [
            exam.strip()
            for exam in self.config_vars['exam_names'].get().split(',')
            if exam.strip()
        ]
        if not exam_names:
            raise ValueError('Exam names must not be empty.')

        current_config = load_config()
        return {
            'host': current_config.get('host', '0.0.0.0'),
            'port': port,
            'debug': current_config.get('debug', False),
            'upload_dir': upload_dir,
            'max_upload_mb': max_upload_mb,
            'allowed_extensions': extensions,
            'thept_path': thept_path,
            'exam_names': exam_names,
        }

    def browse_upload_dir(self) -> None:
        current = self.config_vars['upload_dir'].get().strip()
        initial_dir = current if current and Path(current).is_absolute() else str(Path.cwd())
        selected = filedialog.askdirectory(initialdir=initial_dir)
        if selected:
            self.config_vars['upload_dir'].set(selected)

    def browse_thept_path(self) -> None:
        current = self.config_vars['thept_path'].get().strip()
        initial_dir = str(Path(current).parent) if current else str(Path.cwd())
        selected = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[('Text files', '*.txt'), ('All files', '*.*')],
        )
        if selected:
            self.config_vars['thept_path'].set(selected)

    def save_settings(self) -> dict | None:
        try:
            config = self.config_from_form()
            save_config(config)
        except Exception as error:
            messagebox.showerror('Settings error', str(error))
            self.enqueue_log(f'Settings error: {error}')
            return None

        self.enqueue_log(f'Settings saved: {CONFIG_PATH}')
        return config

    def start_server_from_form(self) -> None:
        config = self.save_settings()
        if config is None:
            return

        try:
            self.server.start(config)
        except Exception as error:
            self.status_var.set('Stopped')
            messagebox.showerror('Server error', str(error))
            self.enqueue_log(f'Server error: {error}')
            return

        self.status_var.set('Running')

    def auto_start_server(self) -> None:
        self.enqueue_log('Auto starting server...')
        self.start_server_from_form()

    def stop_server(self) -> None:
        self.server.stop()
        self.status_var.set('Stopped')

    def enqueue_log(self, message: str) -> None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_queue.put(f'[{timestamp}] {message}')

    def flush_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break

            self.log_text.configure(state='normal')
            self.log_text.insert('end', message + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')

        self.after(100, self.flush_logs)

    def on_close(self) -> None:
        if self.server.is_running():
            self.server.stop()
        self.destroy()


if __name__ == '__main__':
    WebCameraGui().mainloop()
