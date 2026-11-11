# AGENTS.md — Ask AI

Plugin-specific notes for Ask AI. General calibre plugin-development
guidance (build, DB API, headless testing, conventions) lives in the repo-root
`AGENTS.md`.

## What it does

Asks the AI about a book **from its content** (not just metadata) using
calibre's built-in AI support. It reuses calibre's own AI conversation widget,
so the provider, model, and API keys all come from calibre's AI settings
(`Preferences -> AI`) — this plugin adds no provider configuration of its own.

## Naming

- The plugin `name` is **`'Ask AI'`** (with a space, intentional), so the zip
  is `Ask AI.zip`. Don't "fix" the space.
- The folder/import path is `ask_ai` (`calibre_plugins.ask_ai`); prefs live
  under `plugins/Ask AI` (with a space, matching the name), gprefs/db keys
  under `ask_ai_*`.
- If the plugin `name` ever changes again, the old plugin must be **removed**
  from `Preferences -> Plugins` before installing the new zip, or both
  coexist.

## calibre AI APIs used

- `calibre.gui2.llm.ConverseWidget` — the chat UI (streaming, quick actions,
  cost display, settings). Subclass it for the panel. Overridable hooks:
  `settings_dialog()`, `create_initial_messages(action_prompt, **kwargs)`,
  `choose_action_message()`, `prompt_text_for_action(action)`,
  `activate_action(action)`, `start_api_call(action_prompt, **kwargs)`,
  `get_language_instruction()`, `quick_actions_as_html(actions)`.
- `calibre.gui2.llm.LLMSettingsDialogBase` + `LLMActionsSettingsWidget` — the
  settings dialog (AI Provider tab + a custom Actions tab). A
  `LLMActionsSettingsWidget` subclass **must** override
  `create_custom_widgets()` (the base raises `NotImplementedError`); yield the
  shared `LocalisedResults` toggle there.
- `calibre.gui2.llm.ActionData` — quick-action base.
  `Action.unserialize(prefs, defaults, include_disabled)` rebuilds the action
  list from `gprefs` (stored under `ask_ai_quick_actions`).
- `calibre.ai` — `ChatMessage`, `ChatMessageType` for building prompts.
  `ChatMessage` is a `NamedTuple` whose text field is **`.query`** (not
  `.text`): `ChatMessage(text, type=ChatMessageType.system)`.
- `calibre.ai.utils.StreamedResponseAccumulator` — accumulate a streamed
  response into `acc.all_content` (call `acc.finalize()` after the loop).
- `calibre.ai.prefs.plugin_for_purpose(AICapabilities.text_to_text)` — the
  configured text provider plugin; check `.is_ready_for_use` before calling.
  `plugin.text_chat(messages)` yields `ChatResponse` items (check
  `res.exception` on each).

## Content extraction

- `calibre.db.fts.text.extract_text(path)` — calibre's full-text-search text
  extractor; works for any format calibre can index (EPUB, MOBI, PDF, ...).
  It is slow — run it in a worker thread, never on the GUI thread.
- Resolve the file path with `db.new_api.format_abspath(book_id, fmt)` (see the
  repo-root DB-API notes) — never hand-build the path.

## Metadata fields

Which metadata is sent to the AI is field-driven, mirroring calibre's own book
AI (`calibre/gui2/dialogs/llm_book.py`):

- **Title and authors are always sent.** The user selects the *additional*
  fields (standard like `series`/`tags`/`publisher`, or custom `#...`) in the
  **Metadata** tab of the AI Settings dialog (`MetadataSettings` in
  `dialog.py`).
- `dialog.get_allowed_fields()` returns the selected set. Standard fields are
  stored globally in `gprefs['ask_ai_allowed_standard_fields']`, custom
  fields per-library in `db.pref('ask_ai_allowed_custom_fields')`. When
  the user has never chosen, it defaults to `{'series', 'tags'}`.
- `content.metadata_block(mi, allowed_fields)` builds the header from that set.
  It uses `mi.format_field(field)` for display values and renders comments-type
  fields (standard `comments` and custom `datatype == 'comments'`) as markdown
  notes via `comments_as_markdown`.
- Compute `get_allowed_fields()` on the GUI thread and pass the set into the
  worker (the map job) — don't call it inside the worker thread.

## Architecture

- `content.py` — GUI-free: format picking, text extraction, sampling, chunking,
  prompt building, the map-reduce engine (`run_map_reduce`), the batch engine
  (`run_batch`), the series-context helpers (`build_series_context` /
  `format_series_context` / `extract_ai_block` / `order_books_for_series`), and
  the idempotent save-to-comments helpers (`apply_summary_to_comments` /
  `regular_comments`). Everything here is safe to run in a `ThreadedJob`.
- `action.py` — toolbar action + quick-action menu; drives the background
  extract / map-reduce / batch jobs and opens the dialogs. A single selected
  book opens the chat dialog; two or more go through the batch flow.
- `dialog.py` — `ConverseWidget` subclass (`AskAIPanel`) + settings dialog +
  Save-to-comments, plus `BatchSetupDialog` and `BatchResultsDialog` for the
  multi-book flow.
- `config.py` — `JSONConfig('plugins/Ask AI')` + the Customize widget.

## Large books: the task job flow

A long book (over `max_chars`, per the `strategy` pref) is **not** summarized
when the dialog opens. Instead the part summaries are tailored to the task the
user actually picks, and the (slow) map phase runs as a background job. The
flow, across `action.py` and `dialog.py`:

1. `action.prepare_and_open` builds `BookContext(mi, 'map_reduce',
   raw_text=text, partials=[])` and opens the dialog. The dialog shows the task
   picker (`choose_action_message`) — no AI call yet.
2. The user picks a task (or types a question). `AskAIPanel.start_api_call`
   sees `mode == 'map_reduce' and not ctx.partials` and **intercepts** it:
   `confirm_long_book_job()` warns that it becomes a background job; on OK it
   calls `self.on_long_book_task(action_prompt)` and `self.window().accept()`
   (closes the dialog). `on_long_book_task` is set by the action to
   `partial(self.start_task_map_job, book_id, ctx)`.
3. `action.start_task_map_job` runs the **task-aware** map as a `ThreadedJob`
   (`content.run_map_reduce(..., task_prompt)`). `task_prompt` is folded into
   every part summary (`content.build_map_prompt`) so the partials capture what
   is relevant to the request.
4. `action.map_done` sets `ctx.partials = job.result` and **reopens** the
   dialog with `auto_prompt=task_prompt` for the final combine.
5. `open_dialog` fires `auto_prompt` via `QTimer.singleShot(0, ...)` once the
   dialog's event loop is running. Now `ctx.partials` is set, so
   `start_api_call` no longer intercepts; `create_initial_messages` builds the
   reduce prompt (`content.cap_partials` scales the partials to `max_chars`
   first) and the combine runs in the dialog.

`BookContext` carries `raw_text` (map input) and `partials` (map output);
`mode` is `'single'` (short book, text in `content`) or `'map_reduce'`.

Note: `content.build_map_prompt` builds its prompt by concatenating
separately-formatted `intro`/`goal`/`tail` pieces — keep them formatted
individually (a single `%`-format over the whole string breaks on the `%d`
in the intro).

## Multi-book (batch)

Selecting **two or more** books runs the batch flow instead of the single-book
chat (the chat is kept for a single book, with follow-ups):

1. `action.ask_ai_with_action` collects **all** selected rows. One book →
   `start()` (the chat). Two or more → `start_batch()`.
2. `BatchSetupDialog` shows "N books", a task combo (from `current_actions()`,
   disabled ones filtered, plus a "Custom prompt…" entry) and an editable
   `QPlainTextEdit` prefilled with the chosen action's template
   (`{title}`/`{authors}`/`{series}`). **The text box is the source of truth.**
   It also has a "Save to comments automatically" checkbox (default on) and a
   one-line cost note. `get_result()` returns `(prompt_template, auto_save)`.
3. `action.run_batch_job` runs `content.run_batch(...)` as a `ThreadedJob`
   (type `ask-ai-batch`). It processes the books **sequentially**: per book,
   `get_book_text` → single-shot or map-reduce (the same strategy logic as the
   single-book flow, via `content.summarize_text`) → summarize with the
   per-book-formatted prompt (`content.format_prompt`). A per-book failure
   (no extractable format, AI error, cancellation) is recorded on that book's
   `BookResult` (`status='error'`) and does **not** abort the batch.
4. `action.batch_done` opens `BatchResultsDialog` — a `QTableWidget`
   (Saved · Title · Author · Status · Length) over a read-only `QTextBrowser` detail
   pane in a vertical `QSplitter`, with **Save selected** / **Save all** /
   **Close**. The Saved column shows a ✓ once a book's summary is written.
   **Save selected** saves the selected rows and updates the checkmarks (the
   dialog stays open); **Save all** saves every successful result and closes
   the dialog. If `auto_save` was on, all successful results are saved when the
   dialog opens (the table still opens for review, already checked). Saving uses the same
   idempotent `apply_summary_to_comments` logic as the single-book flow.

`content.BookResult` carries `book_id, title, authors, fmt, summary, status,
error, is_excerpt, saved`. `run_batch` scales each book's sub-progress (e.g.
the map phase) into its slot of the overall 0..1 range via
`_ScaledNotifications`, so the job progress bar is monotonic.

## Series context (prior-book summaries)

When summarizing a book that is part of a **series**, the AI is given the
summaries of the **earlier books** in that series as reference context, so each
summary can keep continuity (characters, plot, setting). Works in **both** the
batch flow and the single-book flow. Prefs (in `config.py`, Customize has a
"Series context" group box): `series_context` (bool, default **True** — the
master switch), `series_context_chars` (int, default 20000 — total budget of
earlier-summary characters), `series_context_max_books` (int, default 0 =
unlimited, capped by the character budget).

Helpers in `content.py` (all GUI-free):

- `extract_ai_block(comments)` — the inverse of `apply_summary_to_comments`:
  returns the AI summary stored in the comments (located by its
  `<h2>AI Summary</h2>` header) as markdown (via `comments_as_markdown`), or
  `None`. This is how saved summaries are read back as context.
- `build_series_context(db, book_id, max_chars, max_books=0)` — builds the
  context for `book_id` from **saved** summaries only. Returns
  `(entries, position)`: `entries` is a list of `(position, title, summary)`
  for the earlier books (chronological, budget-trimmed) and `position` is the
  book's 1-based position in the series (`None` if it has no series). Uses
  `db.books_in_series_of(book_id, index_is_id=True)` (returns `[]` when the
  book has no series; otherwise all series ids sorted by `series_index`).
- `_apply_budget(entries, max_chars, max_books)` — trims to the budget,
  dropping from the **oldest** so the most recent context is kept. Returns a
  new list; it must not mutate its input.
- `format_series_context(series_name, entries, book_position)` — renders the
  block that is prepended to the prompt. Each earlier book is labelled
  `### Book N — <title>` where **N is the book's real series position** (not
  its position within the included context), so the numbers stay accurate even
  when the oldest are dropped for budget. Returns `''` when there are no
  entries.
- `_series_index(mi)` / `order_books_for_series(books)` — reorders a batch
  selection so books in the same series form a contiguous block in
  `series_index` order (series groups appear in first-appearance order;
  non-series books keep their selection position). `_series_index` uses
  `getattr(mi, 'series_index', None)` so a missing attribute never breaks it.

**Batch flow** (`run_batch`): books are reordered with
`order_books_for_series`. Each series' **saved** summaries are precomputed once
into `saved` (series name → `{position: (title, summary)}` for *all* of the
series' books, so a book's context can draw on earlier books not in the
selection). As books are processed, a fresh summary is added to `in_memory`
(series name → `{position: (title, summary)}`). A book at position P gets
context from `in_memory.get(p) or saved.get(p)` for each `p in range(1, P)` —
so an in-memory (this-run) summary **takes precedence** over a saved one for a
book that is in the selection. The block is built with
`format_series_context` and passed to `summarize_text`.

**Single-book flow**: `action.prepare_and_open` loads the context
synchronously (reading a few comments is cheap) via
`content.build_series_context` and stores the `entries` on
`BookContext.series_context`. `AskAIPanel.create_initial_messages` recomputes
the position with `db.books_in_series_of` and formats the block with
`content.format_series_context`, then passes it to the prompt builders.

**Injection point**: the series block is prepended to the **single-shot and
reduce** system messages only (`build_single_shot_messages` /
`build_reduce_messages` each take a `series_context=''` param, threaded through
`summarize_text`). It is **not** added to the per-chunk map prompts — the map
phase summarizes the current book's own text, and continuity belongs to the
final combine.

## Questions (not just summaries)

The plugin answers **any** free-form question about the book, not only the
preset quick actions:

- Both system prompts (`content.build_single_shot_messages` and
  `content.build_reduce_messages`) carry a role statement: *"You are helping
  the reader understand this book. Answer their questions … staying specific
  and faithful to what the book actually says."* Keep it in both.
- `choose_action_message` (aliased as `ready_message`) invites *any* question
  and mentions follow-ups.
- **Follow-ups work for free**: `ConverseWidget.start_api_call` appends to the
  conversation history, which keeps the book-content system message in context,
  so later questions in the same dialog still see the book.

## Token limit

There is **no max-tokens setting** (it was dropped). The ~1536-token
completion cap seen in testing is model/server-side, not a calibre limit — the
OpenAI-compatible provider backend sends no `max_tokens` at all. Don't add a
max-tokens pref to "fix" it.

## Save to comments

Saving writes the AI output into the book's `comments` field, headed with an
`<h2>AI Summary</h2>` marker so it is **idempotent** and stays separate from the
regular comments:

```
<h2>AI Summary</h2>
<p>…the AI summary, converted to HTML…</p>

<hr>

<existing regular comments>
```

The block is delimited by its `<h2>AI Summary</h2>` header and the `<hr>` rule
that follows it. **Do not use HTML-comment markers** (`<!-- … -->`) to delimit
the block: calibre strips comments from the comments field, so they are never
persisted and cannot be relied on.

- `content.apply_summary_to_comments(existing, summary, mode)` builds the new
  value. The summary (markdown) is converted to HTML by
  `content._markdown_to_html` so headings and line breaks render (the comments
  field is HTML). `mode` is the `save_mode` pref: `prepend` (default, AI block
  on top), `append` (mirror image), or `replace` (the block only). Re-running
  replaces the previous block and leaves the regular comments (after the `<hr>`)
  untouched — `content.regular_comments(existing)` strips a previous block (and
  its adjacent `<hr>`) to recover them. The block is located by
  `content._ai_block_bounds` (header = `content._ai_header_html()`, end = the
  next `<hr>` from `content._ANY_HR_RE`, or the end of the text). The `<hr>` is
  matched by `content._HR_RE`, which tolerates the `<hr>`/`<hr/>`/`<hr />`
  variations that calibre/Qt may normalize it to, so re-runs clean the rule up
  reliably. `content._strip_div_edges` drops the bare `<div>`/`</div>` edge
  calibre's outer wrapper leaves behind.
- **`content._markdown_to_html` and the `nl2br` gotcha.** It uses calibre's own
  `calibre.library.comments.markdown()` (the same converter the calibre GUI uses
  for the comments field) and then rewrites single newlines inside `<p>` blocks
  into `<br />`. **Do not "simplify" this to the `nl2br` markdown extension**:
  `Markdown(extensions=['nl2br'])` raises `ModuleNotFoundError: No module named
  'nl2br'` in the frozen calibre build (the extension module is not bundled),
  which is exactly why the post-processing approach exists. The plain converter
  alone keeps single newlines as literal `\n` inside `<p>`, which render as a
  space — the original "no line breaks" bug.
- The single-book flow saves the conversation via
  `ConversationHistory.format_llm_note(assistant_name, title)` and then runs it
  through `apply_summary_to_comments` too, so both flows share the same
  idempotent logic and honour the `save_mode` pref.
- After writing, `db.new_api.set_metadata(book_id, mi)` then
  `self.gui.library_view.model().refresh_ids((book_id,))`.

## Debugging

- **Stale plugin load is the first suspect.** When a change "doesn't take
  effect" in the running GUI (a button does nothing, a new column is missing, a
  pref is ignored), calibre is usually still running the previously-loaded copy
  of the plugin — the rebuilt zip has not been picked up. Reinstall the zip
  (`build.cmd`) and **restart calibre** (or relaunch `calibre-debug -g`) before
  assuming there is a code bug. The batch auto-save "did nothing" for exactly
  this reason: the code was correct and a reload fixed it.
- The `ThreadedJob`/`Dispatcher` callback path (e.g. `action.batch_done`) only
  runs in the live GUI event loop, so it cannot be exercised headlessly. To
  trace a value through it, add temporary `print(...)` lines at each hand-off
  and read them in the `calibre-debug -g` console.
