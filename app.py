import csv
import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

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
    'debug': False,
    'upload_dir': 'gazou',
    'max_upload_mb': 16,
    'allowed_extensions': ['jpg', 'jpeg', 'png', 'webp', 'gif'],
    'thept_path': r'C:\common\thept.txt',
    'exam_names': ['カメラ'],
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

    @app.get('/settings')
    def settings():
        return jsonify({'exam_names': server_config['exam_names']})

    @app.get('/patient')
    def patient():
        return jsonify(parse_thept(server_config['thept_path']))

    @app.post('/upload')
    def upload():
        image = request.files.get('image')
        if image is None or image.filename == '':
            return jsonify({'error': '画像ファイルが選択されていません。'}), 400

        original_name = secure_filename(image.filename)
        extension = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
        if extension not in allowed_extensions:
            return jsonify({'error': '対応していない画像形式です。'}), 400

        use_rsbase = request.form.get('use_rsbase', 'true').lower() == 'true'
        exam_name = request.form.get('exam_name', '').strip() or server_config['exam_names'][0]
        if exam_name not in server_config['exam_names']:
            return jsonify({'error': '未登録の検査名です。'}), 400

        if use_rsbase:
            patient_info = parse_thept(server_config['thept_path'])
            patient_id = patient_info['id'] if patient_info['available'] else ''
            if not patient_id:
                return jsonify({'error': patient_info['error'] or 'RSBase ID を取得できません。'}), 400
        else:
            patient_id = request.form.get('manual_id', '').strip()
            if not patient_id:
                return jsonify({'error': '手動IDを入力してください。'}), 400

        filename = create_rsbase_filename(upload_dir, patient_id, exam_name, extension)
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
