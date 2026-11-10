# AGENTS.md

calibre plugin repository (Windows). Three plugins plus a shared library. There is no test suite, linter, or CI — verification is a manual debug build and running the plugin in calibre.

IMPORTANT: When applicable, prefer using intellij-index MCP tools for code navigation and refactoring.

## Layout

- `ekaportal/` — metadata source plugin (scrapes book metadata from aryion.com)
- `clipboard_metadata/` — interface action plugin (applies clipboard JSON to selected books)
- `ask_ai/` — interface action plugin (asks the AI about a book's content via calibre's built-in AI support; has its own `AGENTS.md`)
- `common/` — shared `common_*.py` modules, copied into each plugin folder at build time; `build.py` is the zip builder
- `scripts/` — user-facing helper scripts (doc→docx conversion, Tampermonkey userscript), not build tooling

## Writing a new interface-action plugin

An interface-action plugin is two files:

- `__init__.py` — an `InterfaceActionBase` subclass. Sets `name` (drives the zip filename), `description` (shown in the Plugins list), `version`, `minimum_calibre_version`, and `actual_plugin = 'calibre_plugins.<folder>.action:<ClassName>'`. Implement `is_customizable()` → `True`.
- `action.py` — the `<ClassName>` subclass of `calibre.gui2.actions.InterfaceAction`. `action_spec = (label, icon, tooltip, shortcut)`, `action_type = 'current'`, optional `dont_add_to` frozenset. Connect signals in `genesis()`. Implement `config_widget()` (returns a QWidget) and `save_settings(config_widget)` for the Customize dialog.

Copy the `.build/` folder, `Test.ps1`, `about.txt`, `README.md`, and an empty `plugin-import-name-<folder>.txt` marker from an existing plugin. The toolbar icon goes in `images/icon.png`.

## Build / test (the only workflow)

Build scripts are Windows batch files. Requires `calibre-debug`, `calibre-customize`, and `python` on PATH. Run from inside the plugin's `.build` folder:

- `ekaportal\.build\debug.cmd` — build zip, install into calibre, launch `calibre-debug -g` (use this)
- `ekaportal\.build\build.cmd` — same, without launching calibre (same pair exists under `clipboard_metadata\.build\`)

`build.cmd` does: compile translations (if a `translations/` folder exists) → copy `common\common_*.py` into the plugin folder → `python ..\common\build.py` (creates an **uncompressed** zip) → delete the copied common files → `calibre-customize -a <zip>`.

There is no test runner. `Test.ps1` files only launch `calibre-debug -g`. Verify changes by exercising the plugin in the debug calibre instance.

## Build gotchas

- The zip filename is derived from `name = '...'` in the plugin's `__init__.py` (e.g. `EkaPortalPlugin.zip`). Bump `version = (x, y, z)` in the same file when releasing.
- Source files in `common/` use bare `from common_x import ...`. `common/build.py` rewrites them to `from calibre_plugins.<plugin>.common_x` at build time, but only for the files listed in `adjustCommonImports()`. Add any new interdependent common file to that list.
- The `common_*.py` copies left in plugin folders during a build are gitignored — never commit them.
- Subfolders starting with `.` (`.build`, `.tutorial`) are excluded from the zip.
- `*.zip` files in plugin folders are untracked build artifacts.
- `common/build.py` globs only `.py`, `.md`, `.html`, `.cmd`, and `plugin-import-name-*.txt` — so `about.txt` is **not** shipped (source-only) and the `description` in `__init__.py` is what shows in the Plugins list. Don't leave helper scripts (icon generators, etc.) in the plugin folder; they'd be zipped — run them and delete.

## calibre DB API (gotchas)

- `gui.current_db` is a `calibre.db.legacy.LibraryDatabase`. Its **legacy** methods (`db.formats`, `db.title`, `db.id`, ...) take a **row index** by default (with an `index_is_id=False` flag). Passing a book id to them resolves the wrong book or raises `IndexError`.
- Prefer the **new API**: `db.new_api` is a `calibre.db.cache.Cache` keyed by **book id** everywhere — `db.new_api.formats(book_id)` (tuple of formats), `db.new_api.all_book_ids()`, `db.new_api.get_metadata(book_id)`, `db.new_api.set_metadata(book_id, mi)`.
- **Never hand-build a book file path** as `<library>/<id>/<id>.<fmt>` — libraries can use custom folder layouts (e.g. author-named folders). Resolve it with `db.new_api.format_abspath(book_id, fmt)` (absolute path, or `None` if missing); `db.new_api.get_book_path(book_id)` gives the book's folder.

## Headless testing (no GUI)

No test runner, but plugin code and calibre APIs can be exercised headless with `calibre-debug -c`:

- Run a script: `& "<path-to-calibre>\calibre-debug.exe" -c "exec(open(r'...test.py').read())"` — this is calibre's Python (correct Qt bindings + `calibre.*` imports).
- To import a plugin's modules, copy its `.py` files + `images/` into a temp dir laid out as `calibre_plugins\<folder>\`, prepend that dir to `sys.path`, and `import calibre_plugins.<folder>.<module>`.
- Any QWidget needs a `QApplication` first: `QApplication.instance() or QApplication(sys.argv)`.
- To open a real library (what `gui.current_db` is): `from calibre.db.legacy import LibraryDatabase; db = LibraryDatabase(r'<path-to-a-library>')` — it exposes `.new_api`. (The backend `calibre.db.backend.DB` does *not*.) Opening an older-schema library prints harmless "Upgrading database to version N..." lines.

## Conventions

- **Qt menu actions:** `QAction.triggered` emits a `bool`. The calibre idiom for a pre-bound menu item is `item.triggered.connect(partial(self.method, 'arg'))` with `def method(self, which)` — Qt passes the extra `bool`, which is ignored (used throughout `calibre/gui2`, e.g. `fts/search.py`).
- **Background work:** `calibre.gui2.threaded_jobs.ThreadedJob(type, description, func, args, kwargs, Dispatcher(partial(self.cb, ...)))`. `func` must accept `abort` (Event), `log` (GUILog), `notifications` (Queue of `(frac, msg)`). Run via `self.gui.job_manager.run_threaded_job(job)`; in the callback check `job.failed` and show `self.gui.job_exception(job, dialog_title=...)`. Reference: `calibre/gui2/actions/llm_cover.py`.
- **Settings:** plugin-specific prefs in `calibre.utils.config.JSONConfig('plugins/<Name>')` (a `.defaults` dict; `__getitem__` falls back to defaults, `__setitem__` commits). Global/shared prefs in `calibre.gui2.gprefs`.
- **sip:** import it as `from qt.core import sip`, never `import sip` (bare `import sip` raises `ModuleNotFoundError` under calibre's Python).

## Environment variables

- `CALIBRE_CONFIG_DIRECTORY` — set to the `Calibre Settings` folder when using portable calibre; otherwise `build.cmd` installs into your main calibre installation.
- `CALIBRE_DIRECTORY` — set to the folder containing `calibre-debug.exe` if calibre is not on PATH.
- A calibre source checkout lives in a sibling `Calibre` folder. Point `PYTHONPATH` at `<calibre-src>/src` to resolve `calibre.*` imports (see CONTRIBUTING.md for the VS Code setup).

## Plugin notes

- `ekaportal` identifies books by the `eka:` identifier, falling back to parsing the filename pattern `Title-<id>-...` (`get_book_url_from_title` in `__init__.py`). Scraping selectors live in `worker.py`; the SID cookie for private books is stored via `JSONConfig('plugins/EkaPortal')` in `config.py`. Covers are intentionally not fetched.
- `clipboard_metadata` reads JSON from the clipboard and applies only the fields it knows (`title`, `authors`, `tags`, `series`, `series_index`, `publisher`, `pubdate`, `comments`, `languages`) — unknown keys are silently ignored.
- `ask_ai` — AI-specific implementation notes (calibre AI APIs, map-reduce, save-to-comments) live in `ask_ai/AGENTS.md`.
