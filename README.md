# WebCamera
<img width="320" height="540" alt="Screenshot_20260611-152627~2" src="https://github.com/user-attachments/assets/dcadec46-50f4-4f9b-9ed3-62fd4108eff6" />

スマホなどのブラウザからカメラで撮影し、Python サーバーへ画像をアップロードする Flask アプリです。

Windows exe では GUI 管理画面を表示し、設定変更、ログ確認、サーバーの起動と停止ができます。GUI 起動時にはサーバーも自動起動し、スマホアクセス用URLとQRコードを表示します。

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
- `thept_path`: RSBase の `thept.txt` の場所
- `exam_names`: クライアント画面に表示する検査名リスト。カンマ区切り
- `provisional_id`: ID未取得時に使う仮ID

`upload_dir` は相対パスならアプリ本体と同じフォルダ基準、絶対パスならその場所を使います。`host` と `debug` は GUI には表示せず、`config.json` の値を保持します。

## RSBase 連携

`thept.txt` は通常 `C:\common\thept.txt` を指定します。内容が `0,34503,"氏名"` のような形式の場合、2列目をID、3列目を患者名として読み取ります。

本ツールを起動するPCにRSBaseがある場合は、基本情報の`(52)  c:\common\thept.txt (&& c:\ID_temp.txt)にIDを出力` をyes としていただくと、RSBaseに連動してIDが設定されます。

クライアント画面では `RSBase ID連動` がオンなら `thept.txt` のIDを使い、オフなら手動ID入力欄の値を使います。`thept.txt` が読めない場合や手動IDが空欄の場合は、設定された仮IDを使って保存します。

保存ファイル名は以下の形式です。

```text
ID~連番~yyyy_mm_dd~検査名~RSB.jpg
```

例:

```text
34503~0001~2026_06_11~カメラ~RSB.jpg
```

## config.json

```json
{
  "host": "0.0.0.0",
  "port": 5000,
  "debug": false,
  "upload_dir": "gazou",
  "max_upload_mb": 16,
  "allowed_extensions": ["jpg", "jpeg", "png", "webp", "gif"],
  "thept_path": "C:\\common\\thept.txt",
  "exam_names": ["カメラ"],
  "provisional_id": "999999"
}
```

## Windows exe 作成

Windows 環境で PyInstaller を入れてから実行します。

```powershell
pip install -r requirements-dev.txt
pyinstaller webcamera.spec
```

生成された `dist\WebCamera.exe` を起動すると GUI が開き、exe と同じフォルダに `config.json` が無ければ自動作成します。

## ファイヤーウォール設定

Windowsで実行するときはTCP 5000が外部からアクセスできるようにファイヤーウォールの設定を行ってください。

