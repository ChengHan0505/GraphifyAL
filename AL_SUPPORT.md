# AL / Business Central support

This fork teaches [graphify](https://github.com/safishamsi/graphify) to understand **AL**, the
language of Microsoft Dynamics 365 Business Central. Upstream graphify ignores `.al` files; this
fork parses them with the [`tree-sitter-al`](https://github.com/SShadowS/tree-sitter-al) grammar
and adds a BC-specific semantic layer on top of graphify's generic extractor.

## Install

Clone this fork and install it into its own virtual environment. Use Python 3.12 or newer. The AL parser, `tree-sitter-al`, is a dependency of this package and is installed from PyPI; it is not vendored here.

```bash
git clone <this-repo> graphify-al && cd graphify-al
uv venv && uv pip install -e .
```

Without uv:

```bash
python -m venv .venv
```

```powershell
# Windows
.venv\Scripts\pip install -e .
```

```bash
# macOS/Linux
.venv/bin/pip install -e .
```

> **Do not install upstream Graphify for AL work.** Do not run `uv tool install graphifyy`. That installs upstream Graphify, which does not parse `.al` files. If upstream `graphifyy` is already on your PATH, do not run `graphify update .` on an AL project. That command drops the AL relationships. Use the virtual environment's Python below.

## Build a graph for an AL repo

Extraction is fully local and needs no API key. Run it from the `graphify-al` folder. These commands use the virtual environment's Python directly, so the environment does not need to be activated, and a global Graphify install is left unused.

```powershell
# Windows
.venv\Scripts\python.exe -m graphify update "C:\path\to\your\al\app"
```

```bash
# macOS/Linux
.venv/bin/python -m graphify update /path/to/your/al/app
```

This writes `graphify-out/{graph.json,graph.html,GRAPH_REPORT.md}` next to the AL app. Re-running re-extracts only changed files (SHA cache under `graphify-out/cache/ast/`). The cache key is the file hash plus the package version, so an extractor change at the same version does not rebuild an existing graph. Delete `graphify-out/cache/ast` before the next update, or the graph keeps the previous relationships.

## Query it

Use the same virtual-environment Python as the build command (`.venv\Scripts\python.exe` on Windows, `.venv/bin/python` on macOS and Linux).

```bash
.venv/bin/python -m graphify query   "SomeCodeunit"            --graph /path/to/your/al/app/graphify-out/graph.json
.venv/bin/python -m graphify affected "Some Setup Table"       --graph .../graph.json   # reverse: what depends on it
.venv/bin/python -m graphify path    "CodeunitA" "CodeunitB"   --graph .../graph.json   # shortest path
.venv/bin/python -m graphify explain "SomeCodeunit"            --graph .../graph.json
```

Node labels: AL objects are their name (`MyCodeunit`, `"My Quoted Object"`). Procedures and object triggers are `.ProcName()`, including `.OnAfterGetRecord()`, `.OnInsert()`, and `.OnRun()`. Nested triggers use the label on the node, such as `Resolve.OnAction`, `Start Date.OnValidate`, or `Header.OnAfterGetRecord`. Find those nodes by following `action`, `field_trigger`, or `report_trigger`. The stored id is a long slug.

`examples/` has a tiny synthetic app you can build and query end-to-end.

## How to read the graph

Use `graph.json` as the map, then open the `.al` file at the edge's line when the graph does not store the fact.

- An object outside the scanned folder is `file_type: "concept"` with an id that starts with `al_ext_` and an empty `source_file`. It may be a standard Business Central object, another extension, or a typo. Do not look for `file_type: "external"`.
- A `calls` edge marked `EXTRACTED` found the target procedure. An `INFERRED` call still needs two checks: the target label is a procedure, such as `.EnsureSetup()`, and the source line agrees. A call whose method is not in the folder lands on the codeunit object, such as `No. Series`, and stays `INFERRED`.
- A `checks` edge is one `if` condition, or one `Error`, `TestField`, or `FieldError`, on the procedure or trigger that contains it. The expression and the line are on the edge. `Validate` and `Modify` are not checks and are not calls.
- An `enum_value` edge lists a value declared on that enum or enum extension. `has_type` still points from a field to the enum object.
- A `table_relation` edge keeps the written text in `expression`. A parsed `IF (condition) target ELSE target` arm also has a `branch` value. A property written as `if … then … else`, an empty property, or a broken `."No."` produces no edge, so a missing edge does not prove the property is empty.
- `extends` stays a separate edge. Fields and enum values declared on an extension stay on the extension.

Read the `.al` file for the order of `Validate` and `Modify`, for `RecordRef`, `FieldRef`, `Variant`, `Codeunit.Run()`, `Page.Run()`, `CurrPage`, `actionref`, record methods (`Get`, `SetRange`, `FindSet`, `Modify`), and for the lines inside a permission set.

## What the AL layer extracts

| Relation | Meaning |
|---|---|
| `contains` / `method` | file → object (codeunit, table, page, report, query, xmlport, enum, interface, extensions) → its procedures/triggers |
| `calls` | intra-object procedure calls, type-resolved codeunit calls, and a page action, field trigger, or report trigger → a local procedure or codeunit procedure when that procedure exists. A codeunit call whose procedure exists is `EXTRACTED`. A call that only finds the codeunit object stays `INFERRED`. Record methods, `CurrPage`, `Page.Run`, `actionref`, `Codeunit.Run`, `Error`, `TestField`, and `FieldError` do not get one of these edges. |
| `subscribes` | `[EventSubscriber]` → the publisher object named in the attribute. An object outside the scanned folder is a `concept` node whose id starts with `al_ext_`. |
| `extends` | `tableextension` / `pageextension` / etc. → its base object |
| `source_table` | page `SourceTable`, report or query `dataitem`, or XMLport `tableelement` → the bound table. A dataitem or element name is kept in the edge context. A table outside the folder is a `concept` node whose id starts with `al_ext_`. |
| `field` | table or table extension → a field it declares. The field node id is the parent object's node id plus the field id. |
| `has_type` | a field whose type is `Enum` → that enum object. `Code`, `Text`, and `Integer` do not get this edge. |
| `enum_value` | an enum or enum extension → a value it declares. The value node id is the declaring object's node id plus the value id. An enum extension keeps its own values. |
| `table_relation` | a field → the table or field named by `TableRelation`. One name targets the table only. `Table.Field` targets that field when the table is in the app. Each parsed `IF (condition) target ELSE target` arm keeps its condition in `branch`, and the original expression stays on the edge. A name that parses but is outside the folder is a `concept` node whose id starts with `al_ext_`. |
| `calc_formula` | a FlowField → the field named by `lookup`, `sum`, `average`, `min`, or `max`, or the table named by `count` or `exist`. The formula function and the original expression stay on the edge. The `where` clause stays in the edge context. `FieldClass` is stored on the field node. |
| `action` | a page or page extension → one of its action triggers. The trigger node id is the page id plus the action name plus the trigger name, so two `OnAction` triggers stay separate. |
| `field_trigger` | a field → a trigger declared on that field. The trigger node id is the owning table id plus the field id plus the trigger name. A table extension field keeps its own trigger. |
| `report_trigger` | a report → a report trigger, or a dataitem trigger. A dataitem trigger id is the report id plus the dataitem name plus the trigger name. |
| `checks` | a procedure or trigger → one `if` condition, or one `Error`, `TestField`, or `FieldError` call inside it. The original expression and the check kind stay on the edge. `Validate` and `Modify` do not get this edge. |
| `imports` | `using` namespace directives |

## Honest limitations

- **Cross-object call resolution is partial.** Only direct, statically-typed calls resolve.
  Event-driven flow, interface dispatch, and service-locator patterns can't be followed
  statically — use the `subscribes` edges to see event wiring.
- **The static `GRAPH_REPORT.md` god-nodes / "surprising connections" sections are object-only.**
  graphify's report treats `.foo()` labels as synthetic stubs (a Python/JS assumption), which
  excludes AL procedures *from that report section only*. The `query`/`affected`/`path` engine
  traverses procedures fine — trust queries over that report section for AL.
- **For precise "definition of / all references to one symbol", an AL language server is better.**
  graphify is for the bird's-eye map and multi-hop traversal across many objects/files.

## Implementation

AL extraction lives in:

- `graphify/detect.py` — `.al` added to `CODE_EXTENSIONS`.
- `graphify/extract.py` — `_AL_CONFIG` (drives the generic extractor), `extract_al`,
  `_al_collect_facts` (per-file AL facts), `_resolve_al_facts` (global cross-object resolution),
  and `_import_al`. Wired into `_DISPATCH` and `extract()`.
- `graphify/watch.py` — on update, a freshly extracted edge replaces an older edge with the same source, target, and relation.
