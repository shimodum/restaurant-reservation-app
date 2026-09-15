# 飲食店予約Webアプリ

Python / Django / MySQLで作る初心者向けの予約アプリです。
現在は設計と開発環境の土台まで実装しています。店舗・予約機能は未実装です。
MVPの機能・データ設計・実装順序は [設計書](docs/design.md) に記載しています。

## 使用技術

- Python 3.13
- Django 5.2系
- MySQL 8.4
- mysqlclient（DjangoからMySQLへ接続）
- Docker Compose（ローカル開発環境）

依存関係は系列を指定し、ビルド時に範囲内のバージョンを取得します。
完全固定のロックファイルはまだ導入していません。
対応条件: [DjangoとPython](https://docs.djangoproject.com/en/5.2/faq/install/)、
[DjangoとMySQL](https://docs.djangoproject.com/en/5.2/ref/databases/#mysql-notes)。

## 初回セットアップ

DockerとDocker Compose v2が必要です。ホストへのPythonやMySQLのインストールは不要です。
WSLでDockerが見つからない場合は、Docker Desktopを起動して
Settings → Resources → WSL Integrationで使用中のディストリビューションを有効にします。

リポジトリのルートで実行します。

```bash
docker --version
docker compose version
cp .env.example .env
```

`.env`の`DJANGO_SECRET_KEY`、`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`を任意の値に変更してください。
`.env`はGit管理対象外です。`MYSQL_HOST=db`はCompose内のMySQLサービス名です。
この設定はローカル開発専用です。

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py check --database default
```

`migrate`は標準認証・セッション・管理画面用のテーブルを作成します。
`createsuperuser`では管理画面に入るユーザーを作成します。

- トップページ: http://localhost:8000/
- 管理画面: http://localhost:8000/admin/

トップページが表示され、作成した管理者で管理画面にログインできれば初期確認完了です。
MySQLはコンテナ間だけで接続し、ホストに3306番ポートを公開しません。

## 普段の操作

```bash
# 起動
docker compose up -d
# 状態・ログの確認
docker compose ps
docker compose logs web db
# Djangoの設定・DBチェック
docker compose exec web python manage.py check --database default
# 停止（データは保持）
docker compose down
```

MySQLのデータは`mysql_data`ボリュームに残ります。
MySQLの初期ユーザー・パスワードは初回作成時だけ適用されます。
作成後に`.env`を変更しても既存DBの認証情報は変わりません。
`docker compose down -v`はDBデータも削除するため、通常の停止には使いません。

## ファイル構成

```text
config/          Djangoの設定・URL
reservations/    店舗・予約用アプリ（モデルは今後実装）
templates/       HTMLテンプレート
docs/design.md   MVP設計
manage.py        Djangoの管理コマンド入口
Dockerfile       Python実行環境
compose.yaml     DjangoとMySQLの起動設定
.env.example     環境変数のサンプル
requirements.txt Python依存関係
```

## 検証状況

Docker Composeでコンテナを起動し、MySQLへのマイグレーション、
トップページの表示、管理者ユーザーでの管理画面ログインまで確認済みです。
