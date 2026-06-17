# WebCamera
<img width="319" height="535" alt="39611~0004~2026_06_17~デジカメ~RSB" src="https://github.com/user-attachments/assets/9f479f02-e57f-4776-85b8-146439126c3d" />

スマホなどのブラウザからカメラで撮影し、Python サーバーへ画像や動画をアップロードする Flask アプリです。

Windows exe では GUI 管理画面を表示し、設定変更、ログ確認、サーバーの起動と停止ができます。GUI 起動時にはサーバーも自動起動し、スマホアクセス用URLとQRコードを表示します。クライアント画面では写真撮影、ギャラリー画像選択、動画撮影/選択ができます。

## 開発実行
- Windows exe版はGUI 管理画面付きで、実行するとすぐにサーバーとして機能します。

  このような画面が起動しますので、設定を適宜変更後、Stop→Startで再起動して、表示されるQRコードのアドレスにスマートフォン等からアクセスしてください。

  アドレスは、`http://192.168.100.10:5000` 等になります。

  <img width="762" height="746" alt="スクリーンショット 2026-06-16 231523" src="https://github.com/user-attachments/assets/22d98c01-fddf-4ec2-b687-04433fddba68" />
  
- Python環境がある場合はスクリプト実行が可能です。

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

本ツールを起動するPCにRSBaseがある場合は、基本情報の`(52)  c:\common\thept.txt (&& c:\ID_temp.txt)にIDを出力` をyes としていただくと、RSBaseに連動してIDが設定されます。

`thept.txt` は通常 `C:\common\thept.txt` を指定します。これによりRSBaseの患者遷移に連動して、本ツールのID,患者名も変わります。

クライアント画面では `RSBase ID連動` がオンなら `thept.txt` のIDを使い、オフなら手動ID入力欄の値を使います。`thept.txt` が読めない場合や手動IDが空欄の場合は、設定された仮IDを使って保存します。

保存作のgazouフォルダを、RSAutoの監視フォルダを指定したり、RSBaseで読み込みボタン（QRcodeの部分）クリックで自動ファイリングされます。


## config.json

WebCamera.exeと同じフォルダの設定ファイル：config.jsonを読み込みますが、初回起動時や存在しない場合は自動で生成されます。

適宜設定を書き換えてください。

```json
{
  "host": "0.0.0.0",
  "port": 5000,
  "debug": false,
  "upload_dir": "gazou",
  "max_upload_mb": 200,
  "allowed_extensions": ["jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "m4v", "webm"],
  "thept_path": "C:\\common\\thept.txt",
  "exam_names": ["カメラ"],
  "provisional_id": "999999"
}
```

## 端末認証

GUI の `端末認証` を有効にすると、登録済み端末だけからアップロードできるようになります。`登録用QR作成` で5分間・1回限りの登録QRを発行し、スマホで読み取って端末登録します。登録済み端末は 一覧から削除できます。端末トークンは `devices.json` にハッシュ保存されます。

1. `サーバー`ページで、`端末認証を有効にする` にチェックを入れ、設定を保存後、サーバーを再起動します。
  <img width="738" height="572" alt="Screenshot 2026-06-17 112457" src="https://github.com/user-attachments/assets/3fb6d14d-84e0-47ca-850e-ccc390edddf0" />

2. `端末認証` ページで、`登録用QRを作成` を押すと、QRコードが表示されます。5分以内にスマートフォンで読みとり、端末名を入力します。
  <img width="762" height="746" alt="スクリーンショット 2026-06-16 231624" src="https://github.com/user-attachments/assets/4c591d79-cc97-4f0a-ba7b-a8f1cea740c5" />

  <img width="320" height="599" alt="39611~0002~2026_06_17~デジカメ~RSB" src="https://github.com/user-attachments/assets/5b6544e4-d801-4d35-bdbd-9e946394bc51" />

3. 登録が完了すると、`登録済み端末`一覧に表示されます。端末を削除したいときは、選択後削除ボタンを押してください。
   <img width="693" height="123" alt="Screenshot 2026-06-17 114409" src="https://github.com/user-attachments/assets/72e349d8-ea52-43a0-b54d-91539c3ac3b5" />

4. 登録済み端末からは、`サーバー`ページのQRコードのアドレスからアップロード可能になります。

## Windows exe 作成

Windows 環境で PyInstaller を入れてから実行することで、Windows exeを作ることもできます。

```powershell
pip install -r requirements-dev.txt
pyinstaller webcamera.spec
```

生成された `dist\WebCamera.exe` を起動すると GUI が開き、exe と同じフォルダに `config.json` が無ければ自動作成します。

## ファイヤーウォール設定

Windowsで実行するときはTCP 5000が外部からアクセスできるようにファイヤーウォールの設定を行ってください。

<img width="435" height="555" alt="Screenshot 2026-06-11 153830" src="https://github.com/user-attachments/assets/0e1cd412-b1c3-4233-b731-e62dbe570760" />


