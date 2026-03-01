"""ビュー別ターゲット定義.

BUILDS: ストアに何を入れるかの宣言（build用）
QUERIES: ストアからどう組み立てるかの宣言（query用）
両者は store_path だけで接続される。
"""

# ---------------------------------------------------------------------------
# Shared: L0 ターゲット定義
# ---------------------------------------------------------------------------

L0_TARGETS = {
    # --- プロジェクト概要 ---
    "concept.md": {
        "label": "コンセプト・設計原則",
        "prompt": (
            "Compute on Writeの核心コンセプト、"
            "解決する課題（3つ）、設計原則を簡潔に抽出"
        ),
    },
    "prd.md": {
        "label": "機能要件・コマンド体系",
        "prompt": (
            "CLIコマンド体系、機能要件の一覧、"
            "開発体験の目標を抽出。"
            "思考プロセスや作業手順は含めず、抽出結果のみを返すこと"
        ),
    },
    # --- アーキテクチャ ---
    "docs/design/01_conceptual_architecture.md": {
        "label": "アーキテクチャ境界ルール",
        "prompt": (
            "Bounded Contexts の境界ルール、ACL制約、依存方向、"
            "レイヤー構成を抽出。設計哲学は省略し、"
            "実装時に守るべきルールに絞る"
        ),
    },
    "docs/design/02_interface_contracts.md": {
        "label": "インターフェース契約・型定義",
        "prompt": (
            "Plugin Contract の関数シグネチャ、"
            "全データ型定義（RawRecord, QueryRequest, QueryResult等）、"
            "例外階層を抽出。コード例をそのまま含める。"
            "思考プロセスや作業手順は含めず、抽出結果のみを返すこと"
        ),
    },
    # --- データ・規約 ---
    "docs/design/03_data_model.md": {
        "label": "データモデル・物理スキーマ",
        "prompt": (
            "Raw DB の物理スキーマ（DDL）、"
            "RawDataAccessor の SQL マッピング、"
            "日時フォーマット規約、ID生成戦略を抽出。"
            "思考プロセスや作業手順は含めず、抽出結果のみを返すこと"
        ),
    },
    "docs/design/04_cli_conventions.md": {
        "label": "CLI共通規約",
        "prompt": (
            "stdout/stderr分離ルール、終了コード一覧、"
            "出力フォーマット規約、Plugin Host の共通振る舞い、"
            "例外翻訳表を抽出"
        ),
    },
    "docs/design/05_project_structure.md": {
        "label": "プロジェクト構成・技術スタック",
        "prompt": (
            "ディレクトリレイアウト、技術スタック（確定済み）、"
            "モジュール境界とACL担保方法、エントリポイント定義を抽出"
        ),
    },
    # --- 実践 ---
    "docs/implementation_guide.md": {
        "label": "実装ガイド",
        "raw": True,
    },
    "tach.toml": {
        "label": "モジュール境界定義",
        "raw": True,
    },
}

# ---------------------------------------------------------------------------
# Build declarations — ストアに何を入れるか
# ---------------------------------------------------------------------------

BUILDS = [
    {
        "type": "condensed",
        "store_path": "views.implementation.l0",
        "targets": L0_TARGETS,
    },
    {
        "type": "file_map",
        "store_path": "tables.file_map",
        "fields": {
            "summary": {
                "prompt": "このファイルの役割を1行（80文字以内）で日本語で要約してください。コードの内容だけに基づいて。",
            },
            "detail": {
                "prompt": (
                    "このファイルの主要な関数・クラス名、公開インターフェース、"
                    "依存関係を箇条書きで抽出してください。"
                ),
            },
        },
        "computed_fields": {
            "status": lambda content: "WIP"
            if ("raise NotImplementedError" in content or "# TODO: Implement" in content)
            else "",
        },
    },
]

# ---------------------------------------------------------------------------
# Query declarations — ストアからどう組み立てるか
# ---------------------------------------------------------------------------

QUERIES = {
    "implementation": {
        "title": "実装用コンテキスト",
        "sections": [
            {
                "type": "condensed",
                "label": "プロジェクト基盤",
                "store_path": "views.implementation.l0",
                "targets": L0_TARGETS,
            },
            {
                "type": "table_filter",
                "label": "実装ファイルマップ",
                "store_path": "tables.file_map",
                "filter": lambda r: r["file_path"].startswith(("src/", "tests/")),
                "format": "{file_path}: {status} {summary}",
            },
        ],
    },
}
