# Ask AI

A calibre plugin that asks the AI about a book's **content** using calibre's
built-in AI support.

Where calibre's own "Discuss book with AI" action only sends a book's
*metadata* to the model, this plugin extracts the book's actual text and feeds
it to the AI, so the answer reflects what the book really says.

## Requirements

- calibre **8.16.2** or newer (the version where calibre's AI conversation
  widget became reusable)
- An AI provider configured in calibre's own AI settings
  (`Preferences -> AI`), e.g. OpenAI, Google, Ollama, LM Studio, ...

## How to use

1. Select one or more books in the library.
2. Click the **Ask AI** toolbar button, or open its menu to pick a
   specific quick action (Summary, Detailed summary, Chapter by chapter,
   Logline, Themes & analysis).
3. **Single book:** the book's text is extracted in the background. Depending
   on the book's length and your *content strategy* setting, it is either sent
   in one prompt or split into parts that are summarized individually and then
   combined (map-reduce). A chat dialog opens with the AI's answer. You can ask
   follow-up questions, run other quick actions, copy the result, or
   **Save to comments** to write the summary into the book's `comments` field.
4. **Several books:** a setup dialog lets you pick the task (a quick action or
   a custom prompt, applied to every book) and choose whether to save the
   results to the comments automatically. The books are then summarized one by
   one in a background job, and a results table shows each book's summary with
   **Save selected** / **Save all** buttons. A book that fails (e.g. no
   extractable format) is marked as an error and the rest of the batch
   continues.

If no AI provider is configured, the dialog shows a link to configure one.

## Settings

`Preferences -> Plugins -> AskAI -> Customize plugin`:

| Setting | Meaning |
|---|---|
| Content strategy | `Automatic` (single-shot if it fits, else map-reduce), `Single-shot`, or `Map-reduce` |
| Max characters | Cap on how much content is sent in a single prompt |
| Sampling | How a too-large book is reduced for single-shot: evenly spaced segments, or from the beginning |
| Sample segments | Number of evenly spaced segments to sample |
| Map-reduce chunk size | Size of each chunk when using map-reduce |
| Save to comments | How the AI summary is combined with the existing `comments`: at the top (default), at the bottom, or replace. Re-saving replaces the previous AI summary and leaves the rest untouched |

Quick actions can be customized (add, edit, remove, reorder) from the
**Actions** tab of the dialog's settings, and the metadata fields sent to the
AI (title and authors are always sent; series, tags, publisher, custom fields,
...) are chosen from the **Metadata** tab.

## Notes

- A **single** selected book opens the chat dialog (with follow-up questions);
  **two or more** go through the batch flow (setup dialog → background job →
  results table). Batch books are processed sequentially.
- Saved summaries are wrapped in markers inside the `comments` field, so
  re-saving replaces the previous AI summary and leaves your other notes
  intact.
- Text is extracted with calibre's own full-text-search extractor, so any
  format calibre can index works (EPUB, MOBI, PDF, ...). Comic formats are
  skipped.
- The AI provider, model and API keys are calibre's own — this plugin adds no
  separate configuration for them.

## Development

See the repository `AGENTS.md` and `CONTRIBUTING.md`. Build and test with:

```
ask_ai\.build\debug.cmd
```

which builds the zip, installs it into calibre and launches `calibre-debug -g`.
