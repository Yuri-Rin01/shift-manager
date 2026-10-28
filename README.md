# シフト作成システム（shift-manager）

介護施設向けのシフト作成・管理システムです。FastAPI + SQLite で動作し、インターネット接続なしのローカル運用を前提にしています。

## 主な機能

- シフトカレンダー（期間表示、印刷、労働時間の集計表示）
- シフト自動生成（条件・プレビュー付き）と確定・調整
- 職員管理（フロア・職種・資格・夜勤可否など）
- 日次業務（当直表、AM/PM の役割分担、週次印刷）
- 休み希望ポータル（職員が名前 + PIN で休み希望を提出）
- バックアップ / 復元（設定画面から、または DB ファイルのコピー）

## 起動方法

### Windows EXE（配布用）

`ShiftManager.exe` をダブルクリックするとブラウザが自動で開きます。詳しくは `packaging/README_EXE.txt` を参照してください。

### サーバー起動（Windows）

```
start-server.bat
```

管理画面（main.py）と休み希望ポータル（leave_portal_main.py）の両方が起動します。再起動は `restart-servers.bat`。

### 開発時

```
pip install -r requirements.txt
uvicorn main:app --port 8000
```

## 初回セットアップとログイン

1. 初回は `/setup` で管理者のユーザー名・パスワードを決めます（ソースには書かないでください）
2. 以降は `/login` から入ります。職員管理・設定・生成・バックアップは管理者のみ操作できます
3. 休み希望ポータル用に、職員管理で各職員に 4〜8 桁の PIN を設定します

詳細は `docs/local-auth.md` を参照してください。

## 設定

`.env.example` を `.env` にコピーして編集します。

- `FACILITY_TYPE`: `care` | `hospital` | `all`
- `FACILITY_NAME`: サイドバーに表示する施設名

## データ

- 職員・シフトのデータは SQLite の `shift.db` に保存されます（EXE 版では EXE と同じフォルダ）
- ログイン用の秘密鍵は DB と同じフォルダの `.auth_secret` に自動生成されます（Git 管理外）
- バックアップは設定画面の「データの保存と復元」から、または `shift.db` のコピーで行います

## テスト

```
pip install -r requirements-dev.txt
pytest
```

## ドキュメント

- `docs/local-auth.md` — ローカル運用でのログイン導入手順
- `docs/daily-duties.md` — 日次業務（当直表）の仕様
