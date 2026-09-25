# 飲食店予約Webアプリ

Python / Django / MySQLで作る初心者向けの予約アプリです。
現在は開発環境に加え、店舗情報の登録・一覧・詳細表示まで実装しています。
予約機能は未実装です。
MVPの機能・データ設計・実装順序は [設計書](docs/design.md) に記載しています。
モデル間の関係は [ER図](docs/design.md#er図) を参照してください。

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

`migrate`は標準認証・セッション・管理画面用のテーブルに加え、
店舗情報を保存するRestaurantテーブル（`reservations_restaurant`）も作成します。
`createsuperuser`では管理画面に入るユーザーを作成します。

- トップページ: http://localhost:8000/
- 店舗一覧: http://localhost:8000/restaurants/
- 管理画面: http://localhost:8000/admin/

トップページが表示されることを確認したら、次の手順で店舗の登録・表示を確認します。

1. 作成した管理者で管理画面にログインします。
2. 「店舗」の「追加」から店名・説明・住所・営業時間を入力し、保存します。
   説明と営業時間には、それぞれ改行を入れて2行以上入力してください。
3. 店舗一覧を開き、登録した店舗が表示されることを確認します。
4. 「詳細を見る」を開き、店名・説明・住所・営業時間が表示され、
   説明と営業時間の2行目以降も改行して表示されることを確認します。

ここまで確認できれば初期確認完了です。
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
reservations/    店舗・予約用アプリ
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
トップページと店舗画面の表示、管理者ユーザーでの管理画面ログインを確認します。
