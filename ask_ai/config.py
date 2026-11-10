#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__   = 'GPL v3'
__copyright__ = '2026, Jobobby04'
__docformat__ = 'restructuredtext en'

from qt.core import (QComboBox, QFormLayout, QGroupBox,
                     QLineEdit, QVBoxLayout, QWidget)

from calibre.utils.config import JSONConfig
from calibre.utils.localization import _

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/Ask AI')

DEFAULTS = {
    'strategy': 'auto',
    'max_chars': 200000,
    'sampling': 'even',
    'sample_segments': 12,
    'chunk_chars': 100000,
    'save_mode': 'append',
}

plugin_prefs.defaults.update(DEFAULTS)


def get_prefs():
    """Return the current plugin preferences as a plain dict."""
    ans = {}
    for key, default in DEFAULTS.items():
        ans[key] = plugin_prefs.get(key, default)
    return ans


def _to_int(text, default):
    try:
        return int(str(text).strip())
    except (ValueError, TypeError):
        return default


class ConfigWidget(QWidget):
    """Customization dialog shown under Preferences -> Plugins."""

    def __init__(self, parent=None):
        super().__init__(parent)
        c = get_prefs()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox(_('Summarization options'), self)
        form = QFormLayout(box)

        self.strategy = QComboBox(self)
        self.strategy.addItem(_('Automatic (whole book if it fits, else split into parts)'), 'auto')
        self.strategy.addItem(_('One piece (up to the max characters)'), 'single')
        self.strategy.addItem(_('Split into parts (always)'), 'map_reduce')
        self.strategy.setCurrentIndex(max(0, self.strategy.findData(c['strategy'])))
        form.addRow(_('How to send the book:'), self.strategy)

        self.max_chars = QLineEdit(str(c['max_chars']), self)
        self.max_chars.setToolTip(_('The most book content, in characters, to send to the AI at once.'))
        form.addRow(_('Max characters:'), self.max_chars)

        self.sampling = QComboBox(self)
        self.sampling.addItem(_('Pieces spread across the whole book'), 'even')
        self.sampling.addItem(_('The beginning of the book'), 'beginning')
        self.sampling.setCurrentIndex(max(0, self.sampling.findData(c['sampling'])))
        form.addRow(_('If the book is too long, use:'), self.sampling)

        self.sample_segments = QLineEdit(str(c['sample_segments']), self)
        self.sample_segments.setToolTip(_('How many pieces to take from the book when it is too long to send whole.'))
        form.addRow(_('Number of pieces:'), self.sample_segments)

        self.chunk_chars = QLineEdit(str(c['chunk_chars']), self)
        self.chunk_chars.setToolTip(_('When the book is split into parts, how many characters go in each part.'))
        form.addRow(_('Size of each part (characters):'), self.chunk_chars)

        self.save_mode = QComboBox(self)
        self.save_mode.addItem(_('Append to the book comments'), 'append')
        self.save_mode.addItem(_('Replace the book comments'), 'replace')
        self.save_mode.setCurrentIndex(max(0, self.save_mode.findData(c['save_mode'])))
        form.addRow(_('Save to comments:'), self.save_mode)

        outer.addWidget(box)
        outer.addStretch(1)

    def save_settings(self):
        p = get_prefs()
        p['strategy'] = self.strategy.currentData()
        p['max_chars'] = _to_int(self.max_chars.text(), DEFAULTS['max_chars'])
        p['sampling'] = self.sampling.currentData()
        p['sample_segments'] = _to_int(self.sample_segments.text(), DEFAULTS['sample_segments'])
        p['chunk_chars'] = _to_int(self.chunk_chars.text(), DEFAULTS['chunk_chars'])
        p['save_mode'] = self.save_mode.currentData()
        for key, val in p.items():
            plugin_prefs[key] = val
