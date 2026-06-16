import queue
import socket
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from werkzeug.serving import make_server

from app import APP_DIR, CONFIG_PATH, DEVICES_PATH, create_app, load_config, save_config
from auth import DeviceAuthManager


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return '127.0.0.1'


def display_host(host: str) -> str:
    return get_lan_ip() if host in {'0.0.0.0', '::', ''} else host


class ScrollableTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=12)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.content.bind('<Configure>', self._on_content_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)

    def _on_content_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event):
        if self.winfo_viewable():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')


class ServerController:
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.server = None
        self.thread = None
        self.config = None
        self.public_url = ''

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, config: dict, auth_manager=None) -> None:
        if self.is_running():
            self.log_callback('Server is already running.')
            return

        self.config = config
        app = create_app(config, on_event=self.log_callback, auth_manager=auth_manager)
        host = app.config['APP_CONFIG']['host']
        port = app.config['APP_CONFIG']['port']
        upload_dir = app.config['APP_CONFIG']['upload_dir']
        self.server = make_server(host, port, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.public_url = f'http://{display_host(host)}:{port}'
        self.log_callback(f'Server started: {self.public_url}')
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
        self.public_url = ''
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
        self.auth_manager = DeviceAuthManager(DEVICES_PATH)
        self.qr_photo = None
        self.registration_qr_photo = None

        self.create_widgets()
        self.load_config_to_form()
        self.update_auth_tab_state()
        self.refresh_devices()
        self.after(100, self.flush_logs)
        self.after(250, self.auto_start_server)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def create_widgets(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=12, pady=12)

        self.server_scroll = ScrollableTab(self.notebook)
        self.auth_scroll = ScrollableTab(self.notebook)
        self.server_tab = self.server_scroll.content
        self.auth_tab = self.auth_scroll.content
        self.notebook.add(self.server_scroll, text='Server')
        self.notebook.add(self.auth_scroll, text='Device Auth')

        self.server_tab.columnconfigure(0, weight=1)
        self.server_tab.rowconfigure(3, weight=0)
        self.auth_tab.columnconfigure(0, weight=1)
        self.auth_tab.rowconfigure(2, weight=0)

        settings = ttk.LabelFrame(self.server_tab, text='Settings', padding=12)
        settings.grid(row=0, column=0, sticky='ew')
        settings.columnconfigure(1, weight=1)

        self.config_vars['port'] = tk.StringVar()
        self.config_vars['upload_dir'] = tk.StringVar()
        self.config_vars['max_upload_mb'] = tk.StringVar()
        self.config_vars['allowed_extensions'] = tk.StringVar()
        self.config_vars['thept_path'] = tk.StringVar()
        self.config_vars['exam_names'] = tk.StringVar()
        self.config_vars['provisional_id'] = tk.StringVar()
        self.config_vars['device_auth_enabled'] = tk.BooleanVar()

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
        self.add_row(settings, 6, 'Provisional ID', ttk.Entry(settings, textvariable=self.config_vars['provisional_id']))

        controls = ttk.Frame(self.server_tab)
        controls.grid(row=1, column=0, sticky='ew', pady=12)
        controls.columnconfigure(3, weight=1)
        ttk.Button(controls, text='Save settings', command=self.save_settings).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(controls, text='Start server', command=self.start_server_from_form).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(controls, text='Stop server', command=self.stop_server).grid(row=0, column=2, padx=(0, 8))
        self.status_var = tk.StringVar(value='Stopped')
        ttk.Label(controls, textvariable=self.status_var, anchor='e').grid(row=0, column=3, sticky='e')

        address_frame = ttk.LabelFrame(self.server_tab, text='Server Address', padding=8)
        address_frame.grid(row=2, column=0, sticky='ew', pady=(0, 12))
        address_frame.columnconfigure(0, weight=1)
        self.server_url_var = tk.StringVar(value='Server is stopped.')
        ttk.Label(address_frame, textvariable=self.server_url_var).grid(row=0, column=0, sticky='ew')
        self.qr_label = ttk.Label(address_frame, text='QR code will appear after startup.', anchor='center')
        self.qr_label.grid(row=1, column=0, sticky='ew', pady=(8, 0))

        log_frame = ttk.LabelFrame(self.server_tab, text='Log', padding=8)
        log_frame.grid(row=3, column=0, sticky='nsew')
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap='word', state='disabled')
        self.log_text.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text.configure(yscrollcommand=scrollbar.set)

        auth_settings = ttk.LabelFrame(self.auth_tab, text='Device Auth', padding=12)
        auth_settings.grid(row=0, column=0, sticky='ew')
        self.auth_enabled_check = ttk.Checkbutton(
            auth_settings,
            text='Device auth enabled',
            variable=self.config_vars['device_auth_enabled'],
            command=self.update_auth_tab_state,
        )
        self.auth_enabled_check.grid(row=0, column=0, sticky='w')
        ttk.Label(auth_settings, text='Save settings and restart server after changing this option.').grid(
            row=1, column=0, sticky='w', pady=(6, 0)
        )

        device_frame = ttk.LabelFrame(self.auth_tab, text='Device Tokens', padding=8)
        device_frame.grid(row=1, column=0, sticky='ew', pady=12)
        device_frame.columnconfigure(0, weight=1)
        device_controls = ttk.Frame(device_frame)
        device_controls.grid(row=0, column=0, sticky='ew')
        self.create_registration_button = ttk.Button(
            device_controls,
            text='Create registration QR',
            command=self.create_registration_qr,
        )
        self.create_registration_button.grid(row=0, column=0, padx=(0, 8))
        self.delete_device_button = ttk.Button(device_controls, text='Delete selected', command=self.delete_selected_device)
        self.delete_device_button.grid(row=0, column=1, padx=(0, 8))
        self.refresh_devices_button = ttk.Button(device_controls, text='Refresh', command=self.refresh_devices)
        self.refresh_devices_button.grid(row=0, column=2)
        self.registration_url_var = tk.StringVar(value='')
        ttk.Label(device_frame, textvariable=self.registration_url_var).grid(row=1, column=0, sticky='ew', pady=(8, 0))
        self.registration_qr_label = ttk.Label(device_frame, text='Registration QR will appear here.', anchor='center')
        self.registration_qr_label.grid(row=2, column=0, sticky='ew', pady=(8, 0))

        list_frame = ttk.LabelFrame(self.auth_tab, text='Registered Devices', padding=8)
        list_frame.grid(row=2, column=0, sticky='nsew')
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.device_tree = ttk.Treeview(list_frame, columns=('name', 'created_at', 'last_seen_at'), show='headings', height=8)
        self.device_tree.heading('name', text='Name')
        self.device_tree.heading('created_at', text='Created')
        self.device_tree.heading('last_seen_at', text='Last seen')
        self.device_tree.column('name', width=180)
        self.device_tree.column('created_at', width=190)
        self.device_tree.column('last_seen_at', width=190)
        self.device_tree.grid(row=0, column=0, sticky='nsew')
        device_scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.device_tree.yview)
        device_scrollbar.grid(row=0, column=1, sticky='ns')
        self.device_tree.configure(yscrollcommand=device_scrollbar.set)

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
        self.config_vars['provisional_id'].set(str(config.get('provisional_id', '999999')))
        self.config_vars['device_auth_enabled'].set(bool(config.get('device_auth_enabled', False)))
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

        provisional_id = self.config_vars['provisional_id'].get().strip()
        if not provisional_id:
            raise ValueError('Provisional ID must not be empty.')

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
            'provisional_id': provisional_id,
            'device_auth_enabled': bool(self.config_vars['device_auth_enabled'].get()),
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
        self.update_auth_tab_state()
        return config

    def start_server_from_form(self) -> None:
        config = self.save_settings()
        if config is None:
            return

        try:
            self.server.start(config, auth_manager=self.auth_manager)
        except Exception as error:
            self.status_var.set('Stopped')
            messagebox.showerror('Server error', str(error))
            self.enqueue_log(f'Server error: {error}')
            return

        self.status_var.set('Running')
        self.update_server_address()

    def auto_start_server(self) -> None:
        self.enqueue_log('Auto starting server...')
        self.start_server_from_form()

    def stop_server(self) -> None:
        self.server.stop()
        self.status_var.set('Stopped')
        self.server_url_var.set('Server is stopped.')
        self.qr_photo = None
        self.qr_label.configure(image='', text='QR code will appear after startup.')

    def update_server_address(self) -> None:
        url = self.server.public_url
        if not url:
            self.server_url_var.set('Server is stopped.')
            return

        self.server_url_var.set(url)
        if self.config_vars['device_auth_enabled'].get():
            self.qr_photo = None
            self.qr_label.configure(
                image='',
                text='Device auth is enabled. Use the registration QR on the Device Auth tab.',
            )
            return

        try:
            import qrcode
            from PIL import ImageTk

            image = qrcode.make(url).resize((180, 180))
            self.qr_photo = ImageTk.PhotoImage(image)
            self.qr_label.configure(image=self.qr_photo, text='')
        except Exception as error:
            self.qr_photo = None
            self.qr_label.configure(image='', text=f'QR unavailable: {error}')
            self.enqueue_log(f'QR unavailable: {error}')

    def create_registration_qr(self) -> None:
        if not self.server.public_url:
            messagebox.showwarning('Server stopped', 'Start server before creating a registration QR.')
            return

        token = self.auth_manager.create_registration_token(ttl_seconds=300)
        url = f'{self.server.public_url}/register?token={token}'
        self.registration_url_var.set(url)
        try:
            import qrcode
            from PIL import ImageTk

            image = qrcode.make(url).resize((180, 180))
            self.registration_qr_photo = ImageTk.PhotoImage(image)
            self.registration_qr_label.configure(image=self.registration_qr_photo, text='')
        except Exception as error:
            self.registration_qr_photo = None
            self.registration_qr_label.configure(image='', text=f'QR unavailable: {error}')
            self.enqueue_log(f'Registration QR unavailable: {error}')
        self.enqueue_log('Registration QR created. It expires in 5 minutes and can be used once.')

    def refresh_devices(self) -> None:
        if not hasattr(self, 'device_tree'):
            return
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        for device in self.auth_manager.list_devices():
            self.device_tree.insert(
                '',
                'end',
                iid=device['id'],
                values=(device.get('name', ''), device.get('created_at', ''), device.get('last_seen_at', '')),
            )

    def delete_selected_device(self) -> None:
        selected = self.device_tree.selection()
        if not selected:
            messagebox.showinfo('Device tokens', 'Select a device first.')
            return
        device_id = selected[0]
        if not messagebox.askyesno('Delete device', 'Delete selected device token?'):
            return
        if self.auth_manager.delete_device(device_id):
            self.enqueue_log(f'Device deleted: {device_id}')
        self.refresh_devices()

    def update_auth_tab_state(self) -> None:
        enabled = bool(self.config_vars['device_auth_enabled'].get())
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'create_registration_button'):
            self.create_registration_button.configure(state=state)
            self.delete_device_button.configure(state=state)
            self.refresh_devices_button.configure(state=state)
        if self.server.public_url:
            self.update_server_address()
        if hasattr(self, 'registration_qr_label') and not enabled:
            self.registration_url_var.set('Device auth is disabled.')
            self.registration_qr_photo = None
            self.registration_qr_label.configure(image='', text='Enable device auth to create registration QR.')

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
