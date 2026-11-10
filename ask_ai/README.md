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

1. Select a book in the library.
2. Click the **Ask AI** toolbar button, or open its menu to pick a
   specific quick action (Summary, Detailed summary, Chapter by chapter,
   Logline, Themes & analysis).
3. The book's text is extracted in the background. Depending on the book's
   length and your *content strategy* setting, it is either sent in one prompt
   or split into parts that are summarized individually and then combined
   (map-reduce).
4. A chat dialog opens with the AI's answer. You can ask follow-up questions,
   run other quick actions, copy the result, or **Save to comments** to write
   the summary into the book's `comments` field.

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
| Save to comments | Append to, or replace, the book's `comments` field |

Quick actions can be customized (add, edit, remove, reorder) from the
**Actions** tab of the dialog's settings, and the metadata fields sent to the
AI (title and authors are always sent; series, tags, publisher, custom fields,
...) are chosen from the **Metadata** tab.

## Notes

- v1 summarizes a **single book** at a time (the first selected book if
  several are selected).
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
