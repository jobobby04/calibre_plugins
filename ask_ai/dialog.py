#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

"""
The Ask AI dialog: a ConverseWidget subclass seeded with the book content,
wrapped in a Dialog. Reuses calibre's built-in AI conversation widget so we get
streaming, quick actions, provider configuration and cost display for free.
"""

from functools import lru_cache

from qt.core import (QAbstractItemView, QDialogButtonBox, QLabel, QListWidget,
                     QListWidgetItem, QSize, Qt, QVBoxLayout, QWidget)

from calibre.ai import ChatMessage
from calibre.gui2 import gprefs
from calibre.gui2.dialogs.confirm_delete import confirm
from calibre.gui2.llm import (ActionData, ConverseWidget,
                              LLMActionsSettingsWidget, LLMSettingsDialogBase,
                              LocalisedResults)
from calibre.gui2.ui import get_gui
from calibre.gui2.widgets2 import Dialog
from calibre.utils.icu import primary_sort_key
from calibre.utils.localization import _
from polyglot.binary import from_hex_unicode

from calibre_plugins.ask_ai import content
from calibre_plugins.ask_ai.config import get_prefs

PREFS_KEY = 'ask_ai_quick_actions'


class BookContext:
    """Carries the prepared book content into the dialog."""

    def __init__(self, mi, mode, content=None, partials=None,
                 is_excerpt=False, fmt=None, raw_text=None):
        self.mi = mi
        self.mode = mode            # 'single' or 'map_reduce'
        self.content = content      # for 'single'
        self.partials = partials    # for 'map_reduce' (filled after the map phase)
        self.is_excerpt = is_excerpt
        self.fmt = fmt
        self.raw_text = raw_text    # for 'map_reduce' (input to the map phase)


class Action(ActionData):
    def prompt_text(self, books):
        pt = self.prompt_template
        return pt.format(
            books_word='book' if len(books) < 2 else 'books',
            is_are='is' if len(books) < 2 else 'are',
            title=books[0].title,
            authors=books[0].format_authors(),
            series=books[0].series or '',
        )


@lru_cache(2)
def default_actions():
    return (
        Action('summary', _('Summarize'),
               'Provide a concise summary of the book.'),
        Action('detailed', _('Detailed summary'),
               'Provide a detailed summary of the book, covering the main plot, '
               'characters, themes and setting.'),
        Action('chapters', _('Chapters'),
               'Provide a chapter by chapter summary of the book.'),
        Action('logline', _('Logline'),
               'Summarize the book in a single sentence logline.'),
        Action('themes', _('Themes & analysis'),
               'Analyze the major themes, motifs and literary devices in the book.'),
        Action('universe', _('Universe'),
               'Describe the fictional universe this book is set in. Outline the '
               'major plots, themes and characters in the universe.'),
        Action('series', _('Series'),
               'Give the series this book is in. List all the books in the series, '
               'in both published and internal chronological order. Also describe '
               'any prominent spin-off series.'),
    )


def current_actions(include_disabled=False):
    p = gprefs.get(PREFS_KEY) or {}
    return Action.unserialize(p, default_actions(), include_disabled)


def get_current_db():
    """The current library's metadata cache (keyed by book id)."""
    gui = get_gui()
    assert gui is not None
    return gui.current_db.new_api


def get_allowed_fields():
    """Return the set of *additional* metadata field names to send to the AI.

    Title and authors are always sent (see ``content.metadata_block``); this
    returns the other fields the user has selected in the Metadata settings.
    Standard fields are stored globally, custom fields per-library. When the
    user has not chosen anything yet, series and tags are included by default.
    """
    default = ('series', 'tags')
    std = gprefs.get('ask_ai_allowed_standard_fields')
    std = set(default) if std is None else set(std)
    cust = get_current_db().pref('ask_ai_allowed_custom_fields')
    cust = set(default) if cust is None else set(cust)
    return std | cust


class MetadataSettings(QWidget):
    """Choose which metadata fields are sent to the AI (like calibre's book AI)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self)
        la = QLabel(_('Select which metadata fields to send to the AI. Note that '
                      'title and authors are always sent.'))
        la.setWordWrap(True)
        l.addWidget(la)
        self.list_widget = lw = QListWidget(self)
        lw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lw.itemClicked.connect(self.toggle_item)
        l.addWidget(lw)
        fm = get_current_db().field_metadata
        allowed = get_allowed_fields()
        for field_name in sorted(fm.displayable_field_keys(),
                                 key=lambda n: primary_sort_key(fm[n]['label'])):
            if field_name in ('title', 'authors', 'author_sort', 'sort', 'id', 'uuid'):
                continue
            fd = fm[field_name]
            item = QListWidgetItem(fd['name'], lw)
            item.setToolTip(field_name)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked if field_name in allowed
                               else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, field_name)
        bb = QDialogButtonBox(self)
        btn_all = bb.addButton(_('Select &all'), QDialogButtonBox.ButtonRole.ActionRole)
        btn_all.clicked.connect(self.select_all)
        btn_none = bb.addButton(_('Select &none'), QDialogButtonBox.ButtonRole.ActionRole)
        btn_none.clicked.connect(self.select_none)
        l.addWidget(bb)

    def __iter__(self):
        lw = self.list_widget
        return (lw.item(r) for r in range(lw.count()))

    def select_all(self):
        for item in self:
            item.setCheckState(Qt.CheckState.Checked)

    def select_none(self):
        for item in self:
            item.setCheckState(Qt.CheckState.Unchecked)

    def toggle_item(self, item):
        item.setCheckState(Qt.CheckState.Unchecked
                           if item.checkState() == Qt.CheckState.Checked
                           else Qt.CheckState.Checked)

    def commit(self):
        allowed_standard = set()
        allowed_custom = set()
        for item in self:
            if item.checkState() == Qt.CheckState.Checked:
                f = item.data(Qt.ItemDataRole.UserRole)
                if f.startswith('#'):
                    allowed_custom.add(f)
                else:
                    allowed_standard.add(f)
        gprefs.set('ask_ai_allowed_standard_fields', sorted(allowed_standard))
        get_current_db().set_pref('ask_ai_allowed_custom_fields',
                                  sorted(allowed_custom))
        return True


class AskAISettingsWidget(LLMActionsSettingsWidget):
    action_edit_help_text = '<p>' + _(
        'The prompt is a template. {title}, {authors} and {series} are replaced '
        'by the title, authors and series of the book.'
    )

    def get_actions_from_prefs(self):
        yield from current_actions(include_disabled=True)

    def set_actions_in_prefs(self, s):
        gprefs.set(PREFS_KEY, s)

    def create_custom_widgets(self):
        # The "respond in the current language" toggle, shared with calibre's
        # other AI features via the global AI prefs.
        yield '', LocalisedResults()


class AskAISettingsDialog(LLMSettingsDialogBase):
    def __init__(self, parent=None):
        super().__init__(title=_('AI Settings'),
                         name='ask-ai-settings-dialog',
                         prefs=gprefs, parent=parent)

    def custom_tabs(self):
        yield 'config.png', _('&Actions'), AskAISettingsWidget(self)
        yield 'metadata.png', _('&Metadata'), MetadataSettings(self)


class AskAIPanel(ConverseWidget):
    NOTE_TITLE = _('Ask AI')

    def __init__(self, context, gui, book_id, parent=None):
        self.context = context
        self.gui = gui
        self.book_id = book_id
        # Set by the action when it opens the dialog. Called with the task prompt
        # when the user picks a task for a long book and confirms the job.
        self.on_long_book_task = None
        super().__init__(parent, add_close_button=True)

    def settings_dialog(self):
        return AskAISettingsDialog(self)

    def handle_chat_link(self, qurl):
        match qurl.host():
            case self.quick_action_hostname:
                name = from_hex_unicode(qurl.path().strip('/'))
                for ac in current_actions():
                    if ac.name == name:
                        self.activate_action(ac)
                        break
                return True
        return False

    def activate_action(self, action):
        self.start_api_call(self.prompt_text_for_action(action))

    def start_api_call(self, action_prompt, **kwargs):
        ctx = self.context
        if ctx.mode == 'map_reduce' and not ctx.partials:
            # A long book that has not been summarized yet: summarizing it for
            # this task runs as a background job. Warn the user, and if they
            # confirm, hand off to the job and close this dialog.
            if self.confirm_long_book_job():
                if self.on_long_book_task:
                    self.on_long_book_task(action_prompt)
                self.window().accept()
            return
        super().start_api_call(action_prompt, **kwargs)

    def confirm_long_book_job(self):
        return confirm(
            _('This is a long book, so summarizing it for this task will take a '
              'while. It will run as a background job; this dialog will close and '
              'reopen when the final result is ready.\n\nContinue?'),
            'ask_ai_long_book_job',
            self,
            title=_('Long book'),
        )

    def choose_action_message(self):
        mi = self.context.mi
        msg = '<p>' + _('Selected book: <i>{}</i>').format(mi.title)
        if self.context.mode == 'map_reduce':
            if self.context.partials:
                msg += '<br>' + _('The book was split into {} part summaries.').format(
                    len(self.context.partials))
            else:
                msg += '<br>' + _('This is a long book. Choose a task below; '
                                  'summarizing it for that task will run as a '
                                  'background job.')
        msg += self.quick_actions_as_html(current_actions())
        msg += '<p>' + _('Or, type any question about the book below, for example:') + '<br>'
        msg += '<i>What are the main themes of this book?</i><br>'
        msg += _('You can ask follow-up questions after the AI answers.')
        return msg

    ready_message = choose_action_message

    def create_initial_messages(self, action_prompt, **kwargs):
        ctx = self.context
        prefs = get_prefs()
        lang = self.get_language_instruction()
        allowed = get_allowed_fields()
        if ctx.mode == 'map_reduce':
            partials = content.cap_partials(ctx.partials, prefs['max_chars'])
            yield from content.build_reduce_messages(
                ctx.mi, partials, allowed, lang)
        else:
            yield from content.build_single_shot_messages(
                ctx.mi, ctx.content, ctx.is_excerpt, allowed, lang)
        yield ChatMessage(action_prompt)

    def prompt_text_for_action(self, action):
        return action.prompt_text([self.context.mi])

    def add_buttons(self):
        super().add_buttons()
        self.add_button('database_save.png', _('Save to comments'),
                        _('Save this summary to the book comments')).clicked.connect(
            self.save_to_comments)

    def save_to_comments(self):
        from calibre.gui2 import error_dialog
        text = self.conversation_history.format_llm_note(
            self.assistant_name, self.NOTE_TITLE)
        if not text:
            error_dialog(self, _('Nothing to save'),
                         _('There is no AI response to save yet.'), show=True)
            return
        prefs = get_prefs()
        db = self.gui.current_db
        mi = db.new_api.get_metadata(self.book_id)
        if prefs['save_mode'] == 'replace':
            mi.comments = text
        else:
            existing = mi.comments or ''
            mi.comments = (existing + '\n\n' + text) if existing else text
        db.new_api.set_metadata(self.book_id, mi)
        self.gui.library_view.model().refresh_ids((self.book_id,))
        self.gui.status_bar.show_message(_('Summary saved to the book comments.'), 3000)


class AskAIDialog(Dialog):
    def __init__(self, context, gui, book_id, parent=None):
        self.context = context
        self.gui = gui
        self.book_id = book_id
        super().__init__(
            name='ask-ai-dialog',
            title=_('Ask AI about {}').format(context.mi.title),
            parent=parent,
            default_buttons=QDialogButtonBox.StandardButton.Close,
        )

    def setup_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        self.llm = AskAIPanel(self.context, self.gui, self.book_id, parent=self)
        self.llm.close_requested.connect(self.accept)
        self.finished.connect(self.llm.cleanup_on_close)
        l.addWidget(self.llm)
        self.bb.setVisible(False)
        self.llm.result_display.input.setFocus(Qt.FocusReason.OtherFocusReason)

    def sizeHint(self):
        return QSize(600, 750)
