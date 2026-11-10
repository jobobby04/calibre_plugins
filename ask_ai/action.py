#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""
Toolbar action for the Ask AI plugin.

Wires the toolbar button and its quick-action menu to the background
extraction / map-reduce jobs and the dialog.
"""

from functools import partial

from qt.core import QTimer

from calibre.gui2 import Dispatcher, error_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob
from calibre.utils.localization import _

from calibre_plugins.ask_ai import content
from calibre_plugins.ask_ai.config import get_prefs


class AskAIAction(InterfaceAction):
    name = 'Ask AI'
    action_spec = (_('Ask AI'), 'ai.png',
                   _("Ask the AI about this book's content"), None)
    action_type = 'current'
    action_add_menu = True
    dont_add_to = frozenset(('context-menu-device', 'toolbar-device',
                             'menubar-device'))

    def genesis(self):
        self.qaction.triggered.connect(self.ask_ai)
        self.ask_ai_menu = self.qaction.menu()
        assert self.ask_ai_menu is not None
        self.ask_ai_menu.aboutToShow.connect(self.about_to_show_menu)

    def about_to_show_menu(self):
        from calibre.utils.icu import primary_sort_key
        from calibre_plugins.ask_ai.dialog import current_actions
        m = self.ask_ai_menu
        m.clear()
        # The general dialog (no preset action). Needed in the submenu because,
        # in the context menu, the parent item only opens this submenu and never
        # fires its own triggered signal.
        general = m.addAction(_('Open dialog'))
        general.triggered.connect(self.ask_ai)
        m.addSeparator()
        for ac in sorted(current_actions(), key=lambda a: primary_sort_key(a.human_name)):
            a = m.addAction(ac.human_name)
            a.triggered.connect(partial(self.ask_ai_with_action, ac))

    def ask_ai_with_action(self, action=None):
        rows = list(self.gui.library_view.selectionModel().selectedRows())
        if not rows:
            d = error_dialog(self.gui, _('Cannot ask AI'), _('No book selected'))
            d.exec()
            return
        # v1 is single-book: use the first selected book.
        book_id = self.gui.library_view.model().id(rows[0])
        self.start(book_id, action)

    def ask_ai(self):
        self.ask_ai_with_action()

    def start(self, book_id, action):
        db = self.gui.current_db
        mi = db.new_api.get_metadata(book_id)
        prefs = get_prefs()

        def do_extract(abort, log, notifications):
            notifications.put((0.0, 'Extracting text…'))
            text, fmt = content.get_book_text(db, book_id)
            notifications.put((1.0, 'Extracted %d characters' % len(text)))
            return text, fmt

        job = ThreadedJob(
            'ask-ai-extract',
            _('Extract text from {}').format(mi.title),
            do_extract,
            (),
            {},
            Dispatcher(partial(self.extraction_done, book_id, action, prefs, mi)),
        )
        self.gui.job_manager.run_threaded_job(job)
        self.gui.status_bar.show_message(_('Extracting text from {}…').format(mi.title), 2000)

    def extraction_done(self, book_id, action, prefs, mi, job):
        if job.failed:
            self.gui.job_exception(job, dialog_title=_('Text extraction failed'))
            return
        text, fmt = job.result
        self.prepare_and_open(book_id, action, prefs, mi, text, fmt)

    def prepare_and_open(self, book_id, action, prefs, mi, text, fmt):
        from calibre_plugins.ask_ai.dialog import BookContext
        strategy = prefs['strategy']
        needs_map = strategy == 'map_reduce' or (
            strategy == 'auto' and len(text) > prefs['max_chars'])
        if needs_map:
            # A long book: open the dialog to pick a task. Summarizing it for
            # that task runs as a background job only after the user confirms,
            # so the part summaries are tailored to the chosen task.
            ctx = BookContext(mi, 'map_reduce', raw_text=text, partials=[], fmt=fmt)
            auto_prompt = action.prompt_text([mi]) if action is not None else None
            self.open_dialog(book_id, ctx, auto_prompt=auto_prompt)
        else:
            content_text, is_excerpt = content.sample_text(
                text, prefs['max_chars'], prefs['sampling'], prefs['sample_segments'])
            ctx = BookContext(mi, 'single', content=content_text,
                              is_excerpt=is_excerpt, fmt=fmt)
            self.open_dialog(book_id, ctx)

    def open_dialog(self, book_id, ctx, auto_prompt=None):
        from calibre_plugins.ask_ai.dialog import AskAIDialog
        d = AskAIDialog(ctx, self.gui, book_id, parent=self.gui)
        # When the user picks a task for a long book and confirms, this starts
        # the background map job.
        d.llm.on_long_book_task = partial(self.start_task_map_job, book_id, ctx)
        if auto_prompt:
            # Fire the chosen task once the dialog's event loop is running.
            QTimer.singleShot(0, partial(d.llm.start_api_call, auto_prompt))
        d.exec()

    def start_task_map_job(self, book_id, ctx, task_prompt):
        from calibre.ai import AICapabilities
        from calibre.ai.prefs import plugin_for_purpose
        from calibre_plugins.ask_ai.dialog import get_allowed_fields
        plugin = plugin_for_purpose(AICapabilities.text_to_text)
        if plugin is None or not plugin.is_ready_for_use:
            error_dialog(self.gui, _('No AI provider'),
                         _('No AI provider is configured. Open the AI settings to '
                           'configure one, then try again.'), show=True)
            return
        prefs = get_prefs()
        allowed = get_allowed_fields()

        def do_map(abort, log, notifications):
            return content.run_map_reduce(ctx.mi, ctx.raw_text, prefs['chunk_chars'],
                                          plugin, allowed,
                                          task_prompt, abort=abort, log=log,
                                          notifications=notifications)

        job = ThreadedJob(
            'ask-ai-map',
            _('Summarizing parts of {}').format(ctx.mi.title),
            do_map, (), {},
            Dispatcher(partial(self.map_done, book_id, ctx, task_prompt)),
        )
        self.gui.job_manager.run_threaded_job(job)
        self.gui.status_bar.show_message(_('Summarizing parts of {}…').format(ctx.mi.title), 2000)

    def map_done(self, book_id, ctx, task_prompt, job):
        if job.failed:
            self.gui.job_exception(job, dialog_title=_('Summarization failed'))
            return
        ctx.partials = job.result
        # Reopen the dialog with the part summaries and run the final combine.
        self.open_dialog(book_id, ctx, auto_prompt=task_prompt)
