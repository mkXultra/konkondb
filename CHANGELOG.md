# CHANGELOG

<!-- version list -->

## v0.3.1 (2026-03-08)

### Bug Fixes

- Init --plugin をテンプレート非生成・config 書き込みのみに変更
  ([`2674a12`](https://github.com/mkXultra/konkondb/commit/2674a12affecbff6288c8fbd6414d7df8fc5196c))

### Chores

- GitHub PR テンプレートを追加
  ([`4f67b91`](https://github.com/mkXultra/konkondb/commit/4f67b916b779cf0b08b2f73930c92d87bf8a69ab))


## v0.3.0 (2026-03-05)

### Documentation

- BuildContext・Tombstone・deleteコマンドの設計ドキュメントを追加・更新
  ([`360d1f0`](https://github.com/mkXultra/konkondb/commit/360d1f0d00c0d831b25dd52ba7bb26178904673a))

- README build() 更新とマルチエージェント実行パターンドキュメント追加
  ([`50e4007`](https://github.com/mkXultra/konkondb/commit/50e40071fa9d1e4a57aa680ef4e66d4c53dee9eb))

- プラグイン環境セットアップガイドを追加
  ([`8c838e1`](https://github.com/mkXultra/konkondb/commit/8c838e15012919fdc56e2c811e4377251d77ef49))

### Features

- Deleteコマンド・BuildContext・Tombstone削除追跡を実装
  ([`5450ed7`](https://github.com/mkXultra/konkondb/commit/5450ed73ad1d99a54d694ed6ec1042974e5fa905))

- Ingest-staged スクリプト追加・削除検知と dry-run 対応
  ([`6c5d749`](https://github.com/mkXultra/konkondb/commit/6c5d74991cc88cfc7b7d2a8de26ef9c8e9ef6aea))


## v0.2.0 (2026-03-02)

### Bug Fixes

- Add fixed file
  ([`d626f24`](https://github.com/mkXultra/konkondb/commit/d626f24d9dbdb1c95d65f20b38ea3b2a199765c0))

- Check logic
  ([`d5968f2`](https://github.com/mkXultra/konkondb/commit/d5968f2640404f549d5be4c330587534ad3c71a9))

- Ci
  ([`5de4e28`](https://github.com/mkXultra/konkondb/commit/5de4e28f90afe9cd49be78ef78c25a7b2088826e))

### Chores

- Fix precommit hook
  ([`1c752c8`](https://github.com/mkXultra/konkondb/commit/1c752c800ed0074d1a04f3e6079db9ce7fa9bffc))

### Documentation

- .gitignoreとプロジェクト構造ドキュメントを実装済み内容に合わせて更新
  ([`6f5370c`](https://github.com/mkXultra/konkondb/commit/6f5370ce2819460fd96e8c7ee3bdc704f6fe4929))

- 04_cli_design.md をCLI共通規約とコマンド個別仕様に分割・再構成
  ([`6dc93ec`](https://github.com/mkXultra/konkondb/commit/6dc93ec6cf8e60c39972c23c62c23230cb7b98a3))

- ADR-20260301 JSONファイルバックエンド導入の設計決定を記録
  ([`31eb152`](https://github.com/mkXultra/konkondb/commit/31eb1529303d64daed42f3b0de1c2aba772abfaf))

- ADR-20260302 migrateコマンド導入の設計決定を記録
  ([`1243aee`](https://github.com/mkXultra/konkondb/commit/1243aee7650e6b3d3142ac44a15daa637a6afaee))

- Application LayerをBC間調停層として導入し、設計ドキュメントを一括更新
  ([`2ebe587`](https://github.com/mkXultra/konkondb/commit/2ebe58754a115d5b341bfa38758ff2ec8a2bc79c))

- Application LayerをBC間調停層として導入し、設計ドキュメントを一括更新
  ([`26813d5`](https://github.com/mkXultra/konkondb/commit/26813d5c72f22d78e801cb5698ff760110dd2bd3))

- Describeおよびmigrateコマンドの設計仕様ドキュメントを追加
  ([`c355ca3`](https://github.com/mkXultra/konkondb/commit/c355ca3c5cec34ba6d74e23640a915504436b4e4))

- Foundation + Command Spec設計モデルをADRとして正式化
  ([`de806f8`](https://github.com/mkXultra/konkondb/commit/de806f839b0864c676fe09e8280b325935c8ec7c))

- Konkon raw をサブコマンドグループとして再構成し、raw get を正式仕様に追加
  ([`7ba6b52`](https://github.com/mkXultra/konkondb/commit/7ba6b52a7a738e5351f3bc28870f1ba1b06d64d7))

- LLMセッション初期化用プロンプトファイルを追加
  ([`a72b508`](https://github.com/mkXultra/konkondb/commit/a72b508cfae154e8a8dc753fcd3dcb922a6667d0))

- 設計ドキュメントにSSOTルールを導入し、重複定義をクロスリファレンスに置換
  ([`e7a90b0`](https://github.com/mkXultra/konkondb/commit/e7a90b0005c29a389d201127bb5c7406d9487a64))

### Features

- Add check context insert
  ([`6e079b5`](https://github.com/mkXultra/konkondb/commit/6e079b58dc7046318cedf2651b19b4fa9df355db))

- Application Layer（ユースケース層）を実装し、CLIとLib Entryの公開APIを整備
  ([`d690e8c`](https://github.com/mkXultra/konkondb/commit/d690e8c8dd10c1f438b0c56944ba2cb949fd6de3))

- JSONファイルバックエンドを実装し、マルチバックエンド対応を導入
  ([`4fd2544`](https://github.com/mkXultra/konkondb/commit/4fd2544d26d747a8bc39d75bb0bca39c8bf12729))

- Konkon describeコマンドを実装し、プラグインのクエリインターフェース表示機能を追加
  ([`a8660f8`](https://github.com/mkXultra/konkondb/commit/a8660f8693e928814a858d250d8bccadd04de1e6))

- Konkon initに--pluginオプションとconfig.toml設定機能を追加
  ([`d5b71af`](https://github.com/mkXultra/konkondb/commit/d5b71af3335a57585392978c12dcc27f04485994))

- Konkon raw getコマンドを実装し、IDによるレコード単件取得機能を追加
  ([`0ef1dfe`](https://github.com/mkXultra/konkondb/commit/0ef1dfe219bc661510e361a3962409e97da8d674))

- Konkon raw listコマンドを実装し、Raw DB一覧表示機能を追加
  ([`5f85a51`](https://github.com/mkXultra/konkondb/commit/5f85a51906fd569f4f4f8399096845d02055e7f9))

- KonkondbサンプルにDesign Viewコンテキストを追加
  ([`e6fa5c0`](https://github.com/mkXultra/konkondb/commit/e6fa5c0958593ed5664231ced60882cddf61da83))

- KonkondbサンプルにPlugin Devビューとdev-fullクエリを追加
  ([`3a4e161`](https://github.com/mkXultra/konkondb/commit/3a4e161f8dd405fb267bb37d0acefd5b2543658e))

- Konkondb自身をインデックスするLLM連携プラグインのサンプルを追加
  ([`f7fc4b6`](https://github.com/mkXultra/konkondb/commit/f7fc4b6007541bc8eb8a0d8faebea406fc761049))

- Migrateコマンドを実装し、Raw DBバックエンド間のデータ移行機能を追加
  ([`a208378`](https://github.com/mkXultra/konkondb/commit/a2083782c700c3f96092350b9ef4332ae6edb88d))

- Pre-commitフックとインストールスクリプトを追加
  ([`3ce8ca0`](https://github.com/mkXultra/konkondb/commit/3ce8ca04614380553d84b4772c510d64ff947a1f))

- Schema()をプラグインコントラクトに必須化し、searchコマンドに-pオプションを追加
  ([`77c997a`](https://github.com/mkXultra/konkondb/commit/77c997ae2cac164de75b6d563a2deea28d196851))

- Updated_atフィールド追加・インクリメンタルビルド・konkon updateコマンドを実装
  ([`8911c53`](https://github.com/mkXultra/konkondb/commit/8911c53c42cc35b63a2ed62ffe460b4935fc2674))

- プロジェクトファイルを差分検知してingestするシェルスクリプトを追加
  ([`cba7743`](https://github.com/mkXultra/konkondb/commit/cba774336020d48d37bff32328e923fd67ffe222))

### Testing

- MigrateコマンドのJSON出力バイト同一性検証テストを追加
  ([`f5a8e22`](https://github.com/mkXultra/konkondb/commit/f5a8e22e40991a09b46963a3958abf8d640e8e6a))


## v0.1.0 (2026-02-27)

- Initial Release
