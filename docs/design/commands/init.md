# konkon init — プロジェクト初期化

## 概要

プロジェクトの初期化を行う。デフォルトでは `.konkon/` ディレクトリと `konkon.py` テンプレートを生成する。`--plugin` 指定時はテンプレートを生成せず、`.konkon/config.toml` にプラグインパスを登録するのみ。

## Bounded Context

**呼び出すコンテキスト:** なし（システムレベル）
**レイヤー:** L1-L3 外（ファイルシステム操作のみ）

ファイルシステム操作（テンプレート生成または config 書き込み）のみを行う。Raw DB の作成はこの時点では行わない（初回 `insert` 時に遅延作成）。

## シグネチャ

```
konkon init [OPTIONS] [DIRECTORY]
```

## 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `DIRECTORY` | No | `.` (カレントディレクトリ) | プロジェクトを初期化するディレクトリ |

## オプション

| オプション | 型 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `--force` | flag | `false` | 既存の `konkon.py` テンプレートを上書きする（`--plugin` 指定時は無視される） |
| `--plugin` | string | なし | プラグインパスを `.konkon/config.toml` に登録する（DIRECTORY からの相対パス）。テンプレートは生成しない |
| `--raw-backend` | string | `sqlite` | Raw DB バックエンド (`sqlite` または `json`) |

## 生成されるファイル

### `--plugin` なし（デフォルト）

```
<DIRECTORY>/
├── konkon.py          # Plugin テンプレート（build() と query() のスケルトン）
└── .konkon/           # Raw DB 格納ディレクトリ（空）
```

### `--plugin path/to/my.py` 指定時

```
<DIRECTORY>/
└── .konkon/
    └── config.toml    # plugin = 'path/to/my.py'
```

テンプレートファイルは生成しない。デフォルトの `konkon.py` も生成しない。

## `konkon.py` テンプレートの内容

`02_interface_contracts.md` の Plugin Contract に準拠したスケルトンコードを生成する。

```python
"""konkon db plugin — build() と query() を実装してください。"""

from konkon.types import RawDataAccessor, BuildContext, QueryRequest, QueryResult


def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    """
    Raw Data から Context Store を構築します。

    context.mode:
        "full"        — raw_data は全レコードです。Context Store を全再構築してください。
        "incremental" — raw_data は前回ビルド以降の変更分のみです。
                        あわせて、context.deleted_records に含まれるレコード（id/meta）を
                        Context Store から除去してください。
    """
    for record in raw_data:
        # record.id, record.content, record.created_at, record.meta 等が利用可能
        pass


def query(request: QueryRequest) -> str | QueryResult:
    """
    検索リクエストを受け取り、Context Store から結果を返します。
    request.query に検索文字列、request.params に追加パラメータが入ります。
    """
    return ""
```

## 振る舞い

### `--plugin` なし（デフォルト）

1. `DIRECTORY` が存在しない場合、ディレクトリを作成する
2. `konkon.py` が既に存在し `--force` がない場合、終了コード `2` でエラー（`--force` を付けずに既存プロジェクトで実行した操作ミス）
3. `.konkon/` が既に存在する場合、そのまま維持（冪等）
4. `konkon.py` テンプレートを生成する
5. 成功時、stderr に初期化完了メッセージを出力。stdout には何も出力しない

### `--plugin path` 指定時

1. `DIRECTORY` が存在しない場合、ディレクトリを作成する
2. `.konkon/` が既に存在する場合、そのまま維持（冪等）
3. `.konkon/config.toml` に `plugin = '<path>'` を書き込む（既存キーはマージ保持）
4. テンプレートファイルは一切生成しない。`--force` フラグは無視される
5. 成功時、stderr に初期化完了メッセージを出力。stdout には何も出力しない

### `--plugin` バリデーション

- 空文字 → エラー（終了コード `2`）
- 絶対パス → エラー（終了コード `2`）
- `..` を含むパス → エラー（終了コード `2`）
- シングルクォートを含むパス → エラー（終了コード `2`）

## 終了コード

共通終了コードは [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。本コマンド固有の終了コードはない。
