# 飲食店予約Webアプリ

PythonによるWeb開発を学ぶために、DjangoとMySQLで構築した飲食店予約アプリです。
店舗情報を閲覧し、会員登録・ログイン後に予約を作成できます。

## 主な機能

- 店舗一覧・詳細の閲覧（ログイン不要）
- 会員登録・ログイン・POSTによるログアウト（Django標準User）
- 未来日時・店舗別の予約可能時間と最大人数での予約作成（日本時間）
- 自分の予約一覧と、開始前の予約のキャンセル
- キャンセル済み・過去の予約履歴の保持
- Django管理画面による店舗管理

管理画面リンクはstaffだけに表示します。管理画面自体のアクセス・操作権限はDjango標準機能で制御します。
MVPの機能・データ設計は [設計書](docs/design.md) に記載しています。
モデル間の関係は [ER図](docs/design.md#er図) を参照してください。

## MVPの範囲と制限

このMVPは予約情報の登録を目的とし、席数・予約枠・満席・重複の判定は行いません。
曜日別営業時間、定休日、日をまたぐ営業時間、二部制、滞在時間も対象外です。
実店舗で空席を保証する仕組みではありません。
API / Django REST Framework、JavaScriptによる非同期処理、決済、メール通知、レビュー、
お気に入り、店舗検索、ページネーション、店舗オーナー機能、Reservationの管理画面機能は対象外です。
本格的なデザイン変更、ファビコン、デプロイも含めません。APIは予約ルール改善完了後の別フェーズとします。

## 使用技術

- Python 3.13
- Django 5.2系
- MySQL 8.4
- mysqlclient（DjangoからMySQLへ接続）
- Docker / Docker Compose（ローカル開発環境）

依存関係は系列を指定し、ビルド時に範囲内のバージョンを取得します。
完全固定のロックファイルはまだ導入していません。
対応条件: [DjangoとPython](https://docs.djangoproject.com/en/5.2/faq/install/)、
[DjangoとMySQL](https://docs.djangoproject.com/en/5.2/ref/databases/#mysql-notes)。

### 技術選定理由

| 技術 | 選定理由 |
| --- | --- |
| Python / Django | PythonによるWeb開発の学習を目的に採用。DjangoのORM・標準認証・フォーム・テンプレート・管理画面を利用し、MVPを構築しました。 |
| MySQL | リレーショナルDBとして、User・Restaurant・Reservationの関連と予約履歴を扱うために採用しました。 |
| Docker / Docker Compose | WebアプリとDBをコンテナ化し、ホスト環境への依存を減らして開発環境を再現しやすくするために採用しました。 |
| Codex | 設計確認・実装・テスト・ドキュメント更新を支援する開発ツールとして利用しました。出力は主要コードの確認、自動テスト、ブラウザー操作で検証しています。 |

## 初回セットアップ

DockerとDocker Compose v2が必要です。ホストへのPythonやMySQLのインストールは不要です。
WSLでDockerが見つからない場合は、Docker Desktopを起動して
Settings → Resources → WSL Integrationで使用中のディストリビューションを有効にします。

Gitでリポジトリを取得し、ルートディレクトリへ移動します。
取得済みの場合はcloneを省略してください。

```bash
git clone https://github.com/shimodum/restaurant-reservation-app.git
cd restaurant-reservation-app
```

以降のコマンドはリポジトリのルートで実行します。

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
Restaurantテーブル（`reservations_restaurant`）と予約を保存する
Reservationテーブル（`reservations_reservation`）も作成します。
既存環境を更新する場合も、`docker compose exec web python manage.py migrate`で
最新のMigrationを適用してください。
`0003_restaurant_booking_rules`は既存店舗に開店・最終予約可能・閉店の3時刻をNULL、
最大予約人数を10として追加します。既存の店舗情報・補足案内・予約履歴は保持します。
既存店舗は3時刻を管理画面で設定するまで新規予約を受け付けません。
更新作業中は予約受付を止め、移行後に管理者が正しい時刻と補足案内を確認してください。
`createsuperuser`では管理画面に入るユーザーを作成します。

### 主要URL

- トップページ: http://localhost:8000/
- 店舗一覧: http://localhost:8000/restaurants/
- 店舗詳細: `/restaurants/<id>/`
- 予約作成（ログイン必須）: `/restaurants/<id>/reserve/`
- 会員登録: http://localhost:8000/accounts/signup/
- ログイン: http://localhost:8000/accounts/login/
- 自分の予約（ログイン必須）: http://localhost:8000/reservations/
- 管理画面: http://localhost:8000/admin/
- ログアウト（POST）: `/accounts/logout/`
- 予約キャンセル（POST・本人のみ）: `/reservations/<id>/cancel/`

`<id>`は対象の店舗または予約のIDです。POST操作は画面内のボタンから行います。

### 店舗データの登録

店舗データは自動投入されません。トップページの表示を確認したら、管理者が次の手順で登録してください。

1. 作成した管理者で管理画面にログインします。
2. 「店舗」の「追加」から店名・説明・住所・開店時刻・最終予約可能時刻・閉店時刻・最大予約人数・営業時間の補足案内を入力して保存します。
   例: 開店11:00、最終予約21:00、閉店22:00、最大人数20、補足案内「L.O. 21:30」。
   時刻は日本時間・分単位で、`開店時刻 < 最終予約可能時刻 < 閉店時刻`とします。
   3時刻すべて空欄でも保存できますが、新規予約は停止します。一部だけの設定はできません。
   最大人数の初期値は10で、1〜32767の範囲で設定できます。
   説明と補足案内には改行を入れて2行以上入力し、表示を確認してください。
3. 店舗一覧を開き、登録した店舗が表示されることを確認します。
4. 「詳細を見る」を開き、店名・説明・住所・営業時間・最終予約可能時刻・最大人数が表示され、
   説明と補足案内の2行目以降も改行して表示されることを確認します。

確認後はアプリのヘッダーからログアウトし、一般会員の登録・ログイン・予約を確認してください。
MySQLはコンテナ間だけで接続し、ホストに3306番ポートを公開しません。

## 認証機能の確認

1. 未ログイン状態で、ヘッダーに「会員登録」「ログイン」が表示されることを確認します。
2. 会員登録画面でユーザー名・パスワード・確認用パスワードを入力します。
   登録後は自動ログインせず、ログイン画面に移動します。
3. 登録した情報でログインし、ホームへ移動してヘッダーにユーザー名と
   「自分の予約」「ログアウト」が表示されることを確認します。
4. 店舗一覧・詳細を閲覧できることを確認します。
5. ヘッダーの「ログアウト」を押し、ホームへ戻って未ログイン表示になることを確認します。

ログアウトはCSRF保護付きPOSTで行います。ログイン・ログアウト後は、
`next` の指定にかかわらずホームへ移動します。
入力エラーはフォーム内に表示されます。スマートフォン幅でも表示を確認してください。

## 予約機能の確認

1. ログインして店舗詳細の「予約する」を開きます。
2. 日本時間で未来の予約日時と、その店舗の最大予約人数以下の人数を入力します。
   開店11:00・最終予約21:00・閉店22:00なら、11:00と21:00は予約可能、10:59・21:01・22:00は不可です。
   最大人数20なら1人・20人は可能、21人は不可です。
3. 予約後、「自分の予約」に移動し、受付メッセージ・店舗名・予約日時・人数・状態を確認します。
4. 共通ヘッダーの「自分の予約」からも一覧を開けることを確認します。
5. 未来の予約済み予約で「予約をキャンセルする」を押します。
   確認画面は挟まず、状態が「キャンセル済み」になり、履歴が残ります。
6. 別ユーザーではこの予約が表示されないことを確認します。

過去・現在時刻の日時や範囲外の人数は登録できません。
自分の予約一覧には過去・キャンセル済みも含め、予約日時の降順で表示します。
キャンセルできるのは未来の予約済み予約だけです。作成・キャンセルはCSRF保護付きPOSTで行います。
未ログインで予約画面へ進むとログイン画面に移動しますが、ログイン後はホームに戻るため、
店舗一覧から対象店舗を選び直してください。
予約があるUser・Restaurantはキャンセル済みの場合も削除できません。
予約時刻は`opening_time <= 予約時刻 <= last_reservation_time`で判定します。
閉店時刻は店舗情報と時刻の整合性検証に使います。補足案内のL.O.は予約可否に影響しません。
店舗設定を変更しても成立済みの予約は保持され、未来の予約のキャンセル条件も変わりません。
管理画面での予約管理、満席・重複の判定は提供しません。
スマートフォン幅でもフォーム・一覧・ヘッダーの表示を確認してください。

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

## テスト方法

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

### 実行コマンド

```bash
docker compose exec web python manage.py check --database default
docker compose exec web python manage.py test
```

認証・店舗表示・予約作成・本人限定の操作・境界値・CSRF・履歴保持・削除保護を確認します。
店舗設定の順序・精度、最終予約可能時刻を含む時間境界、店舗別人数上限、L.O.との独立性、
未設定店舗の受付停止、設定変更後の予約保持、旧データからのMigrationも確認します。
Migrationの巻き戻し検証は専用テストDB内だけで行い、開発DBは巻き戻しません。
管理画面リンクについては未ログイン・一般ユーザー・staffの3状態を確認します。

## 検証状況

### これまでの開発で確認済み

- 既存33件の自動テスト成功、`0002_reservation`の適用、DjangoのDBチェック成功。
- ブラウザーで会員登録 → ログイン → 店舗閲覧 → ログアウトの正常系を確認。
- ブラウザーで予約作成 → 自分の予約一覧 → キャンセルと、ヘッダーの予約一覧リンクを確認。

### MVP最終仕上げ

- 環境構築手順はDockerfile・Compose・環境変数サンプル・Django設定との整合性を静的に確認。別環境での初回構築は再実施していません。
- Templateにautoescapeの無効化や不必要なsafeの使用がないことを静的に確認。
- 2026年9月30日に最終仕上げ後の`check --database default`を再実行し、問題なし。全36件の自動テストが成功しました（既存33件＋管理画面リンク1件＋予約フォーム2件）。
- `git diff --check`で空白エラーなし。`git status`で変更対象を確認しました。
- 文字サイズ・管理画面リンク変更後のブラウザー目視確認は未実施です。

### 予約日時の厳密な形式検証

- サーバー側で日本時間・分単位の`YYYY-MM-DDTHH:MM`形式だけを受け付けます。秒・タイムゾーン・前後の空白などはフォームエラーにし、特殊なISO日時による保存時の`OverflowError`を防ぎます。
- 2026年10月1日に全37件の自動テストが成功しました（既存36件＋不正な日時入力16ケースを確認する回帰テスト1件）。正常な予約作成・日本時間での保存・必須入力・現在と過去の拒否も既存テストで確認しています。
- `check --database default`は問題なし、`makemigrations --check --dry-run`は差分なし、`git diff --check`は空白エラーなしでした。

### 店舗別の予約可能時間・最大人数

- 2026年10月2日に全49件の自動テストが成功しました（既存37件を維持し、12件追加）。日時の厳密な形式検証も既存テストで継続確認しています。
- 開店・最終予約・閉店の整合性、最終予約時刻を含む境界、日本時間、店舗別人数、設定の改ざん拒否、未設定時の受付停止、L.O.との独立性、設定変更後の履歴・キャンセルを確認しました。
- 専用テストDBで旧Migration状態からの移行とデータ保持を確認しました。開発DBにも`0003_restaurant_booking_rules`を適用し、移行前後で既存6店舗の従来の全項目・既存3予約の全項目が一致することを確認しました。全6店舗の新設定は3時刻NULL・最大人数10です。店舗の営業時間設定は変更していません。
- `check --database default`は問題なし、`makemigrations --check --dry-run`は差分なし、`git diff --check`は空白エラーなしでした。
- 今回の画面変更のブラウザー目視確認は未実施です。commit・pushは行っていません。

開発者がPC幅・375px・320pxで、主要画面の文字の読みやすさ、見出し・本文・補足文の階層、
長い店舗名・住所・ユーザー名の折り返し、フォームとボタンの操作性、横はみ出しの有無を確認します。
あわせて会員登録・ログイン・予約作成・一覧・キャンセル・ログアウトの流れを確認します。
Codexによるブラウザー操作は今回行っていません。

## AIを利用した開発

Codexを設計確認、実装、テスト作成・実行、ドキュメント更新に利用しました。
AIの出力をそのまま採用するのではなく、開発者が主要処理を読み、自動テストとブラウザーで
動作を確認しながら開発しました。全コードの人手レビューを完了したという意味ではありません。
今回のUI調整後の目視確認は、上記のとおり別途実施します。
