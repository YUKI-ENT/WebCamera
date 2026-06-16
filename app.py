import csv
import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from auth import DeviceAuthManager


APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR))
CONFIG_PATH = APP_DIR / 'config.json'
CONFIG_SAMPLE_PATH = APP_DIR / 'config.json.sample'
BUNDLED_CONFIG_SAMPLE_PATH = RESOURCE_DIR / 'config.json.sample'
DEVICES_PATH = APP_DIR / 'devices.json'


DEFAULT_CONFIG = {
    'host': '0.0.0.0',
    'port': 5000,
    'debug': False,
    'upload_dir': 'gazou',
    'max_upload_mb': 200,
    'allowed_extensions': ['jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4', 'mov', 'm4v', 'webm', '3gp', '3gpp', '3g2', 'h264', 'hevc'],
    'thept_path': r'C:\common\thept.txt',
    'exam_names': ['カメラ'],
    'provisional_id': '999999',
    'device_auth_enabled': False,
}


MIME_EXTENSION_MAP = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'video/mp4': 'mp4',
    'video/quicktime': 'mov',
    'video/webm': 'webm',
    'video/3gpp': '3gp',
    'video/3gpp2': '3g2',
    'video/h264': 'h264',
    'video/hevc': 'hevc',
}


def ensure_config_file() -> None:
    if CONFIG_PATH.exists():
        return

    sample_path = CONFIG_SAMPLE_PATH if CONFIG_SAMPLE_PATH.exists() else BUNDLED_CONFIG_SAMPLE_PATH
    if sample_path.exists():
        shutil.copyfile(sample_path, CONFIG_PATH)
        return

    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_config() -> dict:
    ensure_config_file()

    with CONFIG_PATH.open(encoding='utf-8') as config_file:
        loaded_config = json.load(config_file)

    return DEFAULT_CONFIG | loaded_config


def clean_list(values) -> list[str]:
    if isinstance(values, str):
        values = values.split(',')
    return [str(value).strip() for value in values if str(value).strip()]


def save_config(config: dict) -> None:
    clean_config = DEFAULT_CONFIG | config
    clean_config['port'] = int(clean_config['port'])
    clean_config['debug'] = bool(clean_config['debug'])
    clean_config['max_upload_mb'] = int(clean_config['max_upload_mb'])
    clean_config['upload_dir'] = str(clean_config['upload_dir'])
    clean_config['thept_path'] = str(clean_config['thept_path'])
    clean_config['provisional_id'] = str(clean_config['provisional_id']).strip() or DEFAULT_CONFIG['provisional_id']
    clean_config['device_auth_enabled'] = bool(clean_config['device_auth_enabled'])
    clean_config['allowed_extensions'] = [
        extension.lower().lstrip('.') for extension in clean_list(clean_config['allowed_extensions'])
    ]
    clean_config['exam_names'] = clean_list(clean_config['exam_names']) or DEFAULT_CONFIG['exam_names']

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
        extension.lower().lstrip('.') for extension in clean_list(normalized['allowed_extensions'])
    }
    normalized['exam_names'] = clean_list(normalized['exam_names']) or DEFAULT_CONFIG['exam_names']
    normalized['thept_path'] = str(normalized['thept_path'])
    normalized['provisional_id'] = str(normalized['provisional_id']).strip() or DEFAULT_CONFIG['provisional_id']
    normalized['device_auth_enabled'] = bool(normalized['device_auth_enabled'])

    upload_dir = Path(normalized['upload_dir'])
    normalized['upload_dir'] = upload_dir if upload_dir.is_absolute() else APP_DIR / upload_dir

    return normalized


def parse_thept(path: str) -> dict:
    thept_path = Path(path)
    if not thept_path.exists():
        return {'id': '', 'name': '', 'available': False, 'error': 'thept.txt が見つかりません。'}

    last_error = ''
    for encoding in ('cp932', 'utf-8-sig', 'utf-8'):
        try:
            content = thept_path.read_text(encoding=encoding).strip()
            rows = list(csv.reader(io.StringIO(content)))
        except Exception as error:
            last_error = str(error)
            continue

        if not rows or len(rows[0]) < 3:
            return {'id': '', 'name': '', 'available': False, 'error': 'thept.txt の形式を読み取れません。'}

        row = rows[0]
        return {
            'id': row[1].strip(),
            'name': row[2].strip(),
            'available': True,
            'error': '',
        }

    return {'id': '', 'name': '', 'available': False, 'error': last_error or 'thept.txt を読み取れません。'}


def safe_filename_part(value: str, fallback: str = 'unknown') -> str:
    cleaned = re.sub(r'[\\/:*?"<>|~\r\n\t]', '_', str(value).strip())
    cleaned = re.sub(r'\s+', '_', cleaned)
    cleaned = cleaned.strip(' ._')
    return cleaned or fallback


def normalize_output_extension(extension: str) -> str:
    extension = extension.lower().lstrip('.')
    return 'jpg' if extension == 'jpeg' else extension


def extension_from_upload(file_storage, original_name: str, allowed_extensions: set[str]) -> str:
    extension = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    if extension in allowed_extensions:
        return extension

    mimetype = (file_storage.mimetype or '').lower()
    mime_extension = MIME_EXTENSION_MAP.get(mimetype, '')
    if mime_extension in allowed_extensions:
        return mime_extension

    return extension


def next_sequence(upload_dir: Path, patient_id: str, date_text: str, exam_name: str) -> int:
    prefix = f'{patient_id}~'
    suffix = f'~{date_text}~{exam_name}~RSB'
    max_sequence = 0

    if not upload_dir.exists():
        return 1

    for file_path in upload_dir.iterdir():
        if not file_path.is_file():
            continue
        stem = file_path.stem
        if not stem.startswith(prefix) or not stem.endswith(suffix):
            continue
        parts = stem.split('~')
        if len(parts) != 5:
            continue
        try:
            max_sequence = max(max_sequence, int(parts[1]))
        except ValueError:
            continue

    return max_sequence + 1


def create_rsbase_filename(upload_dir: Path, patient_id: str, exam_name: str, extension: str) -> str:
    safe_id = safe_filename_part(patient_id, 'noid')
    safe_exam = safe_filename_part(exam_name, 'camera')
    date_text = datetime.now().strftime('%Y_%m_%d')
    sequence = next_sequence(upload_dir, safe_id, date_text, safe_exam)
    return f'{safe_id}~{sequence:04d}~{date_text}~{safe_exam}~RSB.{normalize_output_extension(extension)}'


def create_app(config: dict | None = None, on_event=None, auth_manager: DeviceAuthManager | None = None) -> Flask:
    server_config = normalize_config(config)
    upload_dir = server_config['upload_dir']
    allowed_extensions = server_config['allowed_extensions']
    auth_manager = auth_manager or DeviceAuthManager(DEVICES_PATH)

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

    def device_token_from_request() -> str:
        return request.headers.get('X-Device-Token', '') or request.form.get('device_token', '')

    def require_device_auth():
        if not server_config['device_auth_enabled']:
            return None
        if auth_manager.validate_device_token(device_token_from_request()):
            return None
        return jsonify({'error': 'この端末は登録されていません。サーバーGUIで端末登録してください。'}), 403

    @app.errorhandler(RequestEntityTooLarge)
    def request_entity_too_large(error):
        max_mb = server_config['max_upload_mb']
        return jsonify({'error': f'ファイルサイズが大きすぎます。最大 {max_mb}MB までです。'}), 413

    @app.errorhandler(HTTPException)
    def http_exception(error):
        return jsonify({'error': error.description or error.name}), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        emit(f'Error: {error}')
        return jsonify({'error': 'サーバー内部エラーが発生しました。'}), 500

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/settings')
    def settings():
        token = device_token_from_request()
        return jsonify({
            'exam_names': server_config['exam_names'],
            'provisional_id': server_config['provisional_id'],
            'device_auth_enabled': server_config['device_auth_enabled'],
            'device_registered': (not server_config['device_auth_enabled']) or auth_manager.validate_device_token(token),
        })

    @app.get('/patient')
    def patient():
        return jsonify(parse_thept(server_config['thept_path']))

    @app.get('/register')
    def register_page():
        return render_template('register.html')

    @app.post('/api/register-device')
    def register_device():
        payload = request.get_json(silent=True) or {}
        registration_token = str(payload.get('registration_token', '')).strip()
        device_name = str(payload.get('device_name', '')).strip()
        ok, device_token, device = auth_manager.register_device(registration_token, device_name)
        if not ok:
            return jsonify({'error': '登録用QRが無効または期限切れです。'}), 400
        emit(f"Device registered: {device['name']}")
        return jsonify({'device_token': device_token, 'device': device})

    @app.post('/upload')
    def upload():
        auth_error = require_device_auth()
        if auth_error is not None:
            return auth_error
        images = [file for file in request.files.getlist('image') if file and file.filename]
        if not images:
            return jsonify({'error': 'ファイルが選択されていません。'}), 400

        use_rsbase = request.form.get('use_rsbase', 'true').lower() == 'true'
        exam_name = request.form.get('exam_name', '').strip() or server_config['exam_names'][0]
        if exam_name not in server_config['exam_names']:
            return jsonify({'error': '未登録の検査名です。'}), 400

        used_provisional = False
        if use_rsbase:
            patient_info = parse_thept(server_config['thept_path'])
            patient_id = patient_info['id'] if patient_info['available'] else ''
            if not patient_id:
                patient_id = server_config['provisional_id']
                used_provisional = True
        else:
            patient_id = request.form.get('manual_id', '').strip()
            if not patient_id:
                patient_id = server_config['provisional_id']
                used_provisional = True

        saved_files = []
        for image in images:
            original_name = secure_filename(image.filename)
            extension = extension_from_upload(image, original_name, allowed_extensions)
            if extension not in allowed_extensions:
                detail = f"拡張子: {extension or 'なし'}, MIME: {image.mimetype or '不明'}"
                return jsonify({'error': f'{original_name or "ファイル"} は対応していないファイル形式です。{detail}'}), 400

            filename = create_rsbase_filename(upload_dir, patient_id, exam_name, extension)
            save_path = upload_dir / filename
            image.save(save_path)
            emit(f'Uploaded: {filename}')
            saved_files.append({'filename': filename, 'url': f'/uploads/{filename}'})

        return jsonify(
            {
                'message': 'アップロードしました。',
                'filename': saved_files[0]['filename'],
                'url': saved_files[0]['url'],
                'files': saved_files,
                'count': len(saved_files),
                'used_provisional_id': used_provisional,
                'patient_id': patient_id,
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
