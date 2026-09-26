# 飲食店予約Webアプリ

Python / Django / MySQLで作る初心者向けの予約アプリです。
現在は開発環境に加え、店舗情報の登録・一覧・詳細表示、会員登録・ログイン・ログアウトを実装しています。
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
- 会員登録: http://localhost:8000/accounts/signup/
- ログイン: http://localhost:8000/accounts/login/
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

### 自動テスト用の初回設定

Djangoの自動テストでは、開発DBの`restaurant_reservation`とは別に、
`test_restaurant_reservation`というテストDBを使用します。
通常はテスト開始時に作成し、終了後に削除します。
開発DBをテストDBとして指定しないでください。開発中のデータが削除されるおそれがあります。

初回環境構築時には、`restaurant`ユーザーにこのテストDBだけを対象とした権限を追加します。
以下は`.env.example`と同じDB名・ユーザー名を使用している場合の手順です。
DB名やユーザー名を変更している場合は、設定に合わせて読み替えてください。

まず、MySQL管理者として接続します。

```bash
docker compose exec db mysql -u root -p
```

パスワードを求められたら、初回セットアップ時に指定した`MYSQL_ROOT_PASSWORD`を入力します。
これはDjango管理画面の管理者パスワードとは別のものです。
表示された`mysql>`の入力欄で、次を実行してください。

```sql
GRANT ALL PRIVILEGES ON `test\_restaurant\_reservation`.* TO 'restaurant'@'%';
SHOW GRANTS FOR 'restaurant'@'%';
```

`SHOW GRANTS`の結果に、開発DBに加えてテストDB限定の権限が表示されることを確認します。
DB名の`\_`は、`_`をワイルドカードではなく文字として扱い、対象を限定するための記述です。
全DBを対象とする`ON *.*`での権限追加や、他ユーザーへ権限を付与できる
`WITH GRANT OPTION`は不要です。

確認後は`exit`でMySQLを終了します。
この権限はテストDBが削除されても残るため、通常はテストのたびに設定する必要はありません。
以降のテストは管理者ではなく、Djangoに設定済みの`restaurant`ユーザーで実行します。

## 認証機能の確認

1. 未ログイン状態で、ヘッダーに「会員登録」「ログイン」が表示されることを確認します。
2. 会員登録画面でユーザー名・パスワード・確認用パスワードを入力します。
   登録後は自動ログインせず、ログイン画面に移動します。
3. 登録した情報でログインし、ホームへ移動してヘッダーにユーザー名と
   「ログアウト」が表示されることを確認します。
4. 店舗一覧・詳細を閲覧できることを確認します。
5. ヘッダーの「ログアウト」を押し、ホームへ戻って未ログイン表示になることを確認します。

ログアウトはCSRF保護付きPOSTで行います。ログイン・ログアウト後は、
`next` の指定にかかわらずホームへ移動します。
入力エラーはフォーム内に表示されます。スマートフォン幅でも表示を確認してください。

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
accounts/        会員登録・認証URL・テスト
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

自動テストは次のコマンドで実行します。

```bash
docker compose exec web python manage.py check --database default
docker compose exec web python manage.py test
```

現在の開発環境では、上記のテストDB限定の権限設定は完了しており、
認証機能と既存の店舗機能を合わせた全19件の自動テストが成功しています。
ブラウザーでも「会員登録 → ログイン → 店舗閲覧 → ログアウト」の正常系を確認済みです。
新しく環境を構築する場合は、「自動テスト用の初回設定」を行ってからテストしてください。
標準Userを利用しており、この機能に伴う追加マイグレーションはありません。
