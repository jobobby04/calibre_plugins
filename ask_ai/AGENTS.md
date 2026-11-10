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
  prompt building, and the map-reduce engine (`run_map_reduce`). Everything here
  is safe to run in a `ThreadedJob`.
- `action.py` — toolbar action + quick-action menu; drives the background
  extract / map-reduce jobs and opens the dialog.
- `dialog.py` — `ConverseWidget` subclass (`AskAIPanel`) + settings dialog
  + Save-to-comments.
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

`ConversationHistory.format_llm_note(assistant_name, title)` renders the
conversation as a markdown note. Write it to `mi.comments` (append or replace
per the `save_mode` pref) via `db.new_api.set_metadata(book_id, mi)`, then
`self.gui.library_view.model().refresh_ids((book_id,))`.
