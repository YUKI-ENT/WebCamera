import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR))
CONFIG_PATH = APP_DIR / 'config.json'
CONFIG_SAMPLE_PATH = APP_DIR / 'config.json.sample'
BUNDLED_CONFIG_SAMPLE_PATH = RESOURCE_DIR / 'config.json.sample'


DEFAULT_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': True,
    'upload_dir': 'uploads',
    'max_upload_mb': 16,
    'allowed_extensions': ['jpg', 'jpeg', 'png', 'webp', 'gif'],
}


def ensure_config_file() -> None:
    if CONFIG_PATH.exists():
        return

    sample_path = CONFIG_SAMPLE_PATH if CONFIG_SAMPLE_PATH.exists() else BUNDLED_CONFIG_SAMPLE_PATH
    if sample_path.exists():
        shutil.copyfile(sample_path, CONFIG_PATH)
        return

    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + '\n', encoding='utf-8')


def load_config() -> dict:
    ensure_config_file()

    with CONFIG_PATH.open(encoding='utf-8') as config_file:
        loaded_config = json.load(config_file)

    return DEFAULT_CONFIG | loaded_config


def save_config(config: dict) -> None:
    clean_config = DEFAULT_CONFIG | config
    clean_config['port'] = int(clean_config['port'])
    clean_config['debug'] = bool(clean_config['debug'])
    clean_config['max_upload_mb'] = int(clean_config['max_upload_mb'])
    clean_config['upload_dir'] = str(clean_config['upload_dir'])
    clean_config['allowed_extensions'] = [
        extension.lower().lstrip('.') for extension in clean_config['allowed_extensions'] if extension
    ]

    CONFIG_PATH.write_text(
        json.dumps(clean_config, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def normalize_config(config: dict | None = None) -> dict:
    normalized = DEFAULT_CONFIG | (config or load_config())
    normalized['port'] = int(normalized['port'])
    normalized['debug'] = bool(normalized['debug'])
    normalized['max_upload_mb'] = int(normalized['max_upload_mb'])
    normalized['allowed_extensions'] = {
        extension.lower().lstrip('.') for extension in normalized['allowed_extensions'] if extension
    }

    upload_dir = Path(normalized['upload_dir'])
    normalized['upload_dir'] = upload_dir if upload_dir.is_absolute() else APP_DIR / upload_dir

    return normalized


def create_app(config: dict | None = None, on_event=None) -> Flask:
    server_config = normalize_config(config)
    upload_dir = server_config['upload_dir']
    allowed_extensions = server_config['allowed_extensions']

    app = Flask(
        __name__,
        static_folder=RESOURCE_DIR / 'static',
        template_folder=RESOURCE_DIR / 'templates',
    )
    app.config['APP_CONFIG'] = server_config
    app.config['MAX_CONTENT_LENGTH'] = server_config['max_upload_mb'] * 1024 * 1024
    upload_dir.mkdir(parents=True, exist_ok=True)

    def emit(message: str) -> None:
        if on_event is not None:
            on_event(message)

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.post('/upload')
    def upload():
        image = request.files.get('image')
        if image is None or image.filename == '':
            return jsonify({'error': '画像ファイルが選択されていません。'}), 400

        original_name = secure_filename(image.filename)
        extension = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
        if extension not in allowed_extensions:
            return jsonify({'error': '対応していない画像形式です。'}), 400

        filename = f'{uuid4().hex}.{extension}'
        save_path = upload_dir / filename
        image.save(save_path)
        emit(f'Uploaded: {filename}')

        return jsonify(
            {
                'message': 'アップロードしました。',
                'filename': filename,
                'url': f'/uploads/{filename}',
            }
        )

    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename: str):
        return send_from_directory(upload_dir, filename)

    return app


if __name__ == '__main__':
    app = create_app()
    server_config = app.config['APP_CONFIG']
    print(f'Config: {CONFIG_PATH}')
    print(f'Upload directory: {server_config["upload_dir"]}')
    app.run(
        host=server_config['host'],
        port=server_config['port'],
        debug=server_config['debug'],
    )
