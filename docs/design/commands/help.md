# konkon help — ヘルプ表示

## 概要

コマンド一覧または個別コマンドの詳細ヘルプを表示する。`konkon --help` と同等。

## Bounded Context

**呼び出すコンテキスト:** なし（システムレベル）
**レイヤー:** L1-L3 外（ヘルプ表示のみ）

## シグネチャ

```
konkon help [COMMAND]
```

## 引数

| 引数 | 必須 | デフォルト | 説明 |
| :--- | :--- | :--- | :--- |
| `COMMAND` | No | — | ヘルプを表示するコマンド名（`init`, `insert`, `update`, `build`, `search`, `raw`, `serve`） |

## 振る舞い

1. `COMMAND` 未指定時: 全コマンドの概要一覧を stdout に出力する
2. `COMMAND` 指定時: 該当コマンドの詳細ヘルプ（シグネチャ、オプション、説明）を stdout に出力する
3. 不明な `COMMAND` が指定された場合: stderr にエラーメッセージを出力し、終了コード `2`

## stdout 出力

- ヘルプ本文は **stdout** に出力する（`konkon help | less` 等のパイプ利用を可能にするため）
- エラーメッセージは stderr に出力する

## `--help` との関係

- `konkon --help` は `konkon help` と同等
- `konkon <command> --help` は `konkon help <command>` と同等
- `--help` はグローバルオプション（[04_cli_conventions.md §2.5](../04_cli_conventions.md)）として全コマンドで利用可能

## 終了コード

共通終了コードは [04_cli_conventions.md §2.3](../04_cli_conventions.md) 参照。

| コード | 条件 |
| :--- | :--- |
| `0` | 正常にヘルプを表示 |
| `2` | 不明なコマンド名が指定された |
