#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""
Book content extraction and preparation for the Ask AI plugin.

Uses calibre's own full-text-search text extractor so that any format calibre
can index (EPUB, MOBI, PDF, ...) can be summarized. No code here depends on
the GUI, so it can run in a worker thread.
"""

import os
import re

from calibre.ai import ChatMessage, ChatMessageType
from calibre.ai.utils import StreamedResponseAccumulator
from calibre.library.comments import comments_as_markdown
from calibre.utils.localization import _

# Preferred order of formats to extract text from. Comic formats are image
# collections with no meaningful text and are skipped entirely.
FORMAT_PRIORITY = ('EPUB', 'AZW3', 'AZW', 'MOBI', 'PDF', 'FB2', 'DOCX', 'DOC',
                   'TXT', 'HTML', 'XHTML')
COMIC_FORMATS = frozenset(('CBR', 'CBZ', 'CBT', 'CB7'))


class NoExtractableFormat(Exception):
    """Raised when a book has no format we can pull text from."""


def pick_format(formats):
    """Return the best format (uppercase) to extract text from, or None."""
    if not formats:
        return None
    upper = {f.upper() for f in formats}
    for fmt in FORMAT_PRIORITY:
        if fmt in upper:
            return fmt
    # Fall back to any non-comic format we were not explicitly ranking.
    for f in formats:
        if f.upper() not in COMIC_FORMATS:
            return f.upper()
    return None


def extract_book_text(path):
    """Extract plain text from an e-book file using calibre's FTS extractor."""
    from calibre.db.fts.text import extract_text
    return extract_text(path)


def get_book_text(db, book_id):
    """
    Return ``(text, fmt)`` for the given book.

    ``db`` is the library database (``gui.current_db``). The on-disk path is
    resolved with calibre's own ``new_api.format_abspath`` so that any library
    folder layout (the standard ``<id>/<id>.<fmt>`` or a custom one) works.
    Raises :class:`NoExtractableFormat` when the book has no extractable
    format, the file is missing, or the extraction yields no text.
    """
    # Note: the legacy db.formats() takes a row index, not a book id, so use
    # the new API which is keyed by book id.
    fmt = pick_format(db.new_api.formats(book_id))
    if fmt is None:
        raise NoExtractableFormat('No extractable format found for this book')
    path = db.new_api.format_abspath(book_id, fmt)
    if not path or not os.path.exists(path):
        raise NoExtractableFormat('Book file not found for the %s format' % fmt)
    text = extract_book_text(path)
    if not text or not text.strip():
        raise NoExtractableFormat('No text could be extracted from the %s file' % fmt)
    return text, fmt


# ---------------------------------------------------------------------------
# Content preparation strategies
# ---------------------------------------------------------------------------

def sample_text(text, max_chars, sampling, segments):
    """
    Reduce ``text`` to at most ``max_chars`` characters.

    Returns ``(content, is_excerpt)``. ``sampling == 'beginning'`` takes the
    first ``max_chars`` characters; ``sampling == 'even'`` takes ``segments``
    evenly spaced segments joined by a marker.
    """
    max_chars = max(1000, int(max_chars))
    if len(text) <= max_chars:
        return text, False
    segments = max(1, int(segments))
    if sampling == 'beginning' or segments <= 1:
        return text[:max_chars], True
    seg_len = max_chars // segments
    pieces = []
    for i in range(segments):
        start = int(len(text) * i / segments)
        pieces.append(text[start:start + seg_len])
    return '\n\n[...]\n\n'.join(pieces), True


def split_chunks(text, chunk_chars):
    """
    Split ``text`` into chunks of at most ``chunk_chars``, breaking on
    paragraph boundaries where possible.
    """
    chunk_chars = max(1000, int(chunk_chars))
    if len(text) <= chunk_chars:
        return [text]
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_chars, n)
        if end < n:
            boundary = text.rfind('\n\n', start, end)
            if boundary > start + chunk_chars // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def cap_partials(partials, max_chars):
    """
    Scale the list of partial summaries down so their combined length is at
    most ``max_chars`` (each partial is truncated proportionally).
    """
    max_chars = max(1000, int(max_chars))
    total = sum(len(p) for p in partials)
    if total <= max_chars:
        return partials
    scale = max_chars / total
    return [p[:int(len(p) * scale)] for p in partials]


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def metadata_block(mi, allowed_fields):
    """Build the metadata header for the AI prompt.

    Title and authors are always included. ``allowed_fields`` is the set of
    *additional* field names to include — standard fields (``series``, ``tags``,
    ``publisher``, ...) or custom fields (``#...``). Fields with no value are
    skipped. Comments-type fields are rendered as markdown notes at the end.
    """
    lines = ['Book: %s' % mi.title]
    if mi.authors:
        lines.append('Authors: %s' % mi.format_authors())
    comments = []
    for field in sorted(allowed_fields):
        if field in ('title', 'authors'):
            continue  # always handled above
        if field == 'comments':
            if mi.comments:
                comments.append(comments_as_markdown(mi.comments))
            continue
        m = mi.metadata_for_field(field)
        if m is not None and m.get('datatype') == 'comments':
            val = mi.get(field)
            if not val:
                continue
            ctype = m.get('display', {}).get('interpret_as') or 'html'
            if ctype in ('long-text', 'short-text', 'markdown'):
                comments.append(val)
            else:
                comments.append(comments_as_markdown(val))
            continue
        name, val = mi.format_field(field)
        if val is None or val == '':
            continue
        lines.append('%s: %s' % (name, val))
    if comments:
        lines.append('Notes:')
        lines.extend(comments)
    return '\n'.join(lines)


def build_single_shot_messages(mi, content, is_excerpt, allowed_fields,
                               language_instruction=''):
    """Build the system message for a single-shot question about the book."""
    header = []
    meta = metadata_block(mi, allowed_fields)
    if meta:
        header.append(meta)
    if is_excerpt:
        header.append('The text below is an excerpt from the book '
                      '(it is too long to send in full).')
    else:
        header.append('The text below is the full content of the book.')
    header.append('You are helping the reader understand this book. Answer their '
                  'questions using the content provided, staying specific and '
                  'faithful to what the book actually says.')
    header.append('When you answer, use markdown formatting wherever possible.')
    if language_instruction:
        header.append(language_instruction)
    system = '\n'.join(header) + '\n\n--- book content ---\n' + content
    return [ChatMessage(system, type=ChatMessageType.system)]


def build_map_prompt(mi, index, total, chunk, allowed_fields, task_prompt=''):
    """Build the user prompt for one chunk of the map phase.

    When ``task_prompt`` is given, the part summary is steered toward whatever
    is relevant to that request, so the later combine step has material that
    matches what the user actually asked for.
    """
    meta = metadata_block(mi, allowed_fields)
    prefix = (meta + '\n' if meta else '')
    if task_prompt:
        goal = ('The summaries of all parts will later be combined to answer a '
                'specific request about the book. The request is: %s\n'
                'Keep that request in mind and make sure this summary captures '
                'everything relevant to it.\n\n' % task_prompt)
    else:
        goal = ''
    intro = ('You are summarizing part %d of %d of a book, in order. '
             'Write a detailed, self-contained summary of ONLY this part, '
             'preserving plot, characters and important details, so that the '
             'parts can later be combined into a summary of the whole book. '
             'Use markdown.\n' % (index, total))
    tail = '--- part %d of %d ---\n%s' % (index, total, chunk)
    return prefix + intro + goal + tail


def build_reduce_messages(mi, partials, allowed_fields, language_instruction=''):
    """Build the system message for the reduce step of map-reduce."""
    header = []
    meta = metadata_block(mi, allowed_fields)
    if meta:
        header.append(meta)
    header.append('The text below is a series of detailed, in-order summaries '
                  'of consecutive parts of the book.')
    header.append('You are helping the reader understand this book. Answer their '
                  'questions using these part summaries, staying specific and '
                  'faithful to what the book actually says.')
    header.append('When you answer, use markdown formatting wherever possible.')
    if language_instruction:
        header.append(language_instruction)
    body = '\n\n'.join('### Part %d\n%s' % (i + 1, p)
                       for i, p in enumerate(partials))
    system = '\n'.join(header) + '\n\n--- part summaries ---\n' + body
    return [ChatMessage(system, type=ChatMessageType.system)]


# ---------------------------------------------------------------------------
# Map-reduce engine (runs in a worker thread)
# ---------------------------------------------------------------------------

def run_map_reduce(mi, text, chunk_chars, plugin, allowed_fields,
                   task_prompt='', abort=None, log=None, notifications=None):
    """
    Summarize each chunk of ``text`` and return the list of partial summaries.

    ``task_prompt``, when given, steers each part summary toward the request it
    will be combined to answer. Runs in a worker thread. ``abort`` is a
    ``threading.Event``, ``notifications`` a Queue that receives ``(frac, msg)``
    tuples and ``log`` a log callable. Raises on cancellation or AI error.
    """
    chunks = split_chunks(text, chunk_chars)
    total = len(chunks)
    partials = []
    for i, chunk in enumerate(chunks):
        if abort is not None and abort.is_set():
            raise InterruptedError('Summarization was cancelled')
        prompt = build_map_prompt(mi, i + 1, total, chunk, allowed_fields, task_prompt)
        messages = [ChatMessage(prompt, type=ChatMessageType.user)]
        acc = StreamedResponseAccumulator()
        for res in plugin.text_chat(messages):
            if res.exception is not None:
                details = res.error_details or ''
                raise Exception('AI error while summarizing part %d: %s %s'
                                % (i + 1, res.exception, details))
            acc.accumulate(res)
        acc.finalize()
        partials.append(acc.all_content.strip())
        if notifications is not None:
            notifications.put((i + 1) / total,
                              'Summarized part %d of %d' % (i + 1, total))
        if log is not None:
            log('Summarized part %d of %d' % (i + 1, total))
    return partials


# ---------------------------------------------------------------------------
# Save to comments (idempotent)
# ---------------------------------------------------------------------------

# HTML-comment markers delimiting the AI block inside the book's comments.
# They are invisible in calibre's rendered comments and give a reliable
# boundary: re-running replaces the block between the markers and leaves the
# regular comments (separated by an <hr> rule) untouched.
BEGIN_MARKER = '<!-- AskAI:begin -->'
END_MARKER = '<!-- AskAI:end -->'
SEPARATOR = '<hr>'

# Matches an <hr> rule line, tolerating the variations calibre/Qt may normalize
# it to (<hr>, <hr/>, <hr />).
_HR_RE = re.compile(r'^<hr\s*/?>$', re.IGNORECASE)


def _strip_separator(text, side):
    """Remove a single <hr> rule line at the given edge of text."""
    text = (text or '').strip()
    if not text:
        return ''
    lines = text.split('\n')
    if side == 'end' and _HR_RE.match(lines[-1].strip()):
        lines = lines[:-1]
    elif side == 'start' and _HR_RE.match(lines[0].strip()):
        lines = lines[1:]
    return '\n'.join(lines).strip()


def regular_comments(existing):
    """
    Return the regular (non-AI) part of an existing comments field.

    If the comments contain an AskAI block (between the HTML-comment markers)
    it is removed — along with the <hr> separator next to it — and the
    remaining regular comments are returned. Comments without a block are
    returned unchanged (stripped).
    """
    existing = (existing or '').strip()
    b = existing.find(BEGIN_MARKER)
    e = existing.find(END_MARKER)
    if b == -1 or e == -1 or e < b:
        return existing
    before = _strip_separator(existing[:b], 'end')
    after = _strip_separator(existing[e + len(END_MARKER):], 'start')
    return '\n\n'.join(p for p in (before, after) if p)


def _markdown_to_html(text):
    """Convert markdown to HTML, preserving single line breaks as <br> tags.

    The comments field is HTML, so the AI's markdown must be converted before
    it is stored. calibre's ``markdown()`` keeps single newlines as literal
    ``\\n`` inside a ``<p>`` (which render as a space), so those are turned
    into ``<br>`` afterwards to make the line breaks show.
    """
    from calibre.library.comments import markdown
    html = markdown(text)
    return re.sub(
        r'(<p[^>]*>)(.*?)(</p>)',
        lambda m: m.group(1) + m.group(2).replace('\n', '<br />') + m.group(3),
        html, flags=re.DOTALL)


def apply_summary_to_comments(existing, summary, mode='prepend'):
    """
    Build the new value for the book's comments field with the AI summary
    applied.

    The summary (markdown) is converted to HTML — the comments field is HTML,
    so this is what makes headings and line breaks render — and wrapped in the
    AskAI markers so that re-running replaces the previous AI block while
    leaving the regular comments untouched. ``mode`` is 'prepend' (AI block on
    top, then <hr>, then the regular comments), 'append' (the mirror image) or
    'replace' (the AI block only).
    """
    body = _markdown_to_html(_('## AI Summary') + '\n' + summary.strip())
    block = '%s\n%s\n%s' % (BEGIN_MARKER, body, END_MARKER)
    regular = regular_comments(existing)
    if mode == 'replace' or not regular:
        return block
    if mode == 'append':
        return regular + '\n\n' + SEPARATOR + '\n\n' + block
    return block + '\n\n' + SEPARATOR + '\n\n' + regular


# ---------------------------------------------------------------------------
# Batch summarization (runs in a worker thread)
# ---------------------------------------------------------------------------

class BookResult:
    """The outcome of summarizing one book in a batch."""

    def __init__(self, book_id, title, authors, fmt=None, summary='',
                 status='ok', error='', is_excerpt=False, saved=False):
        self.book_id = book_id
        self.title = title
        self.authors = authors
        self.fmt = fmt
        self.summary = summary
        self.status = status      # 'ok' or 'error'
        self.error = error
        self.is_excerpt = is_excerpt
        self.saved = saved


class _ScaledNotifications:
    """Remap (frac, msg) progress notifications into a sub-range of 0..1."""

    def __init__(self, queue, base, span):
        self.queue = queue
        self.base = base
        self.span = span

    def put(self, item):
        frac, msg = item
        self.queue.put((min(1.0, self.base + frac * self.span), msg))


def language_instruction():
    """The 'respond in the current language' instruction, if that is enabled."""
    from calibre.ai.prefs import prefs as aiprefs
    if aiprefs()['llm_localized_results'] != 'always':
        return ''
    from calibre.utils.localization import ui_language_as_english
    lang = ui_language_as_english()
    return 'If you can speak in %s, then respond in %s.' % (lang, lang)


def format_prompt(template, mi):
    """Fill the {title}/{authors}/{series} placeholders of a prompt template.

    Falls back to the raw template if it contains a placeholder that cannot be
    filled (e.g. a stray brace), so a typo never aborts the batch.
    """
    try:
        return template.format(
            title=mi.title,
            authors=mi.format_authors(),
            series=mi.series or '',
        )
    except (KeyError, IndexError, ValueError):
        return template


def summarize_text(mi, text, prompt, prefs, plugin, allowed_fields,
                   language_instruction='', abort=None, log=None,
                   notifications=None):
    """
    Summarize ``text`` (the full book text) with ``prompt``.

    Uses the same single-shot / map-reduce strategy as the single-book flow
    (see the ``strategy`` pref). Returns ``(summary, is_excerpt)`` where
    ``is_excerpt`` is True when the book was too long to send whole and was
    sampled. Runs in a worker thread; raises on cancellation or AI error.
    """
    strategy = prefs['strategy']
    needs_map = strategy == 'map_reduce' or (
        strategy == 'auto' and len(text) > prefs['max_chars'])
    is_excerpt = False
    if needs_map:
        partials = run_map_reduce(mi, text, prefs['chunk_chars'], plugin,
                                  allowed_fields, prompt,
                                  abort=abort, log=log,
                                  notifications=notifications)
        partials = cap_partials(partials, prefs['max_chars'])
        messages = list(build_reduce_messages(mi, partials, allowed_fields,
                                              language_instruction))
    else:
        content_text, is_excerpt = sample_text(text, prefs['max_chars'],
                                               prefs['sampling'],
                                               prefs['sample_segments'])
        messages = list(build_single_shot_messages(
            mi, content_text, is_excerpt, allowed_fields,
            language_instruction))
    messages.append(ChatMessage(prompt))
    acc = StreamedResponseAccumulator()
    for res in plugin.text_chat(messages):
        if abort is not None and abort.is_set():
            raise InterruptedError('Summarization was cancelled')
        if res.exception is not None:
            details = res.error_details or ''
            raise Exception('AI error: %s %s' % (res.exception, details))
        acc.accumulate(res)
    acc.finalize()
    return acc.all_content.strip(), is_excerpt


def run_batch(db, books, prompt_template, prefs, plugin, allowed_fields,
              abort=None, log=None, notifications=None):
    """
    Summarize each book in ``books`` (a list of ``(book_id, mi)`` pairs)
    sequentially with ``prompt_template``.

    Returns a list of :class:`BookResult`, one per book, in the same order.
    A failure on one book (no extractable format, AI error, cancellation, ...)
    is recorded on that book's result and does not stop the batch. Runs in a
    worker thread.
    """
    lang = language_instruction()
    results = []
    total = len(books)
    for i, (book_id, mi) in enumerate(books):
        if abort is not None and abort.is_set():
            results.append(BookResult(book_id, mi.title, mi.format_authors(),
                                      status='error', error='Cancelled'))
            continue
        title, authors = mi.title, mi.format_authors()
        # Scale this book's sub-progress (e.g. the map phase) into its slot of
        # the overall 0..1 range.
        base, span = i / total, 1 / total
        notes = (_ScaledNotifications(notifications, base, span)
                 if notifications is not None else None)
        try:
            text, fmt = get_book_text(db, book_id)
            prompt = format_prompt(prompt_template, mi)
            summary, is_excerpt = summarize_text(
                mi, text, prompt, prefs, plugin, allowed_fields, lang,
                abort=abort, log=log, notifications=notes)
            results.append(BookResult(book_id, title, authors, fmt=fmt,
                                      summary=summary, status='ok',
                                      is_excerpt=is_excerpt))
        except InterruptedError:
            results.append(BookResult(book_id, title, authors,
                                      status='error', error='Cancelled'))
        except Exception as e:
            results.append(BookResult(book_id, title, authors,
                                      status='error', error=str(e)))
        if notifications is not None:
            notifications.put((i + 1) / total,
                              'Done %d of %d books' % (i + 1, total))
        if log is not None:
            log('Book %d of %d: %s' % (i + 1, total, title))
    return results
