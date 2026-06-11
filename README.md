# WebCamera

スマホなどのブラウザからカメラで撮影し、Python サーバーへ画像をアップロードする Flask アプリです。

Windows exe では GUI 管理画面を表示し、設定変更、ログ確認、サーバーの起動と停止ができます。GUI 起動時にはサーバーも自動起動します。

## 開発実行

サーバーだけを起動する場合:

```bash
.venv/bin/python app.py
```

GUI 管理画面付きで起動する場合:

```bash
.venv/bin/python gui.py
```

初回起動時に `config.json` が無ければ、`config.json.sample` から自動作成します。

## GUI で設定できる項目

- `port`: 待ち受けポート
- `upload_dir`: アップロード画像の保存先
- `max_upload_mb`: 最大アップロードサイズ
- `allowed_extensions`: 許可する画像拡張子

`upload_dir` は相対パスならアプリ本体と同じフォルダ基準、絶対パスならその場所を使います。`host` と `debug` は GUI には表示せず、`config.json` の値を保持します。

## config.json

```json
{
  "host": "0.0.0.0",
  "port": 5000,
  "debug": false,
  "upload_dir": "gazou",
  "max_upload_mb": 16,
  "allowed_extensions": ["jpg", "jpeg", "png", "webp", "gif"]
}
```

## Windows exe 作成

Windows 環境で PyInstaller を入れてから実行します。

```powershell
pip install -r requirements-dev.txt
pyinstaller webcamera.spec
```

生成された `dist\WebCamera.exe` を起動すると GUI が開き、exe と同じフォルダに `config.json` が無ければ自動作成します。
