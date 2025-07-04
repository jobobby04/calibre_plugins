from __future__ import unicode_literals, division, absolute_import, print_function

__license__ = 'GPL v3'
__copyright__ = '2025, Jobobby04'

from six import text_type as unicode

# Maintain backwards compatibility with older versions of Qt and calibre.
try:
    from qt.core import (QVBoxLayout, Qt, QGroupBox, QTableWidget,
                         QAbstractItemView, QLineEdit, QLabel)
except ImportError:
    from PyQt5.Qt import (QVBoxLayout, Qt, QGroupBox, QTableWidget,
                          QAbstractItemView, QLineEdit, QLabel)

from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.utils.config import JSONConfig

from calibre_plugins.ekaportal.common_compatibility import qSizePolicy_Expanding, \
    qSizePolicy_Minimum
from calibre_plugins.ekaportal.common_icons import get_icon
from calibre_plugins.ekaportal.common_widgets import ReadOnlyTableWidgetItem

STORE_NAME = 'Options'
KEY_SID = 'sid'

DEFAULT_STORE_VALUES = {
    KEY_SID: '',
}

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/EkaPortal')

# Set defaults
plugin_prefs.defaults[STORE_NAME] = DEFAULT_STORE_VALUES


def get_plugin_pref(store_name, option):
    c = plugin_prefs[store_name]
    default_value = plugin_prefs.defaults[store_name][option]
    return c.get(option, default_value)


def get_plugin_prefs(store_name, fill_defaults=False):
    if fill_defaults:
        c = get_prefs(plugin_prefs, store_name)
    else:
        c = plugin_prefs[store_name]
    return c


def get_prefs(prefs_store, store_name):
    store = {}
    if prefs_store and prefs_store[store_name]:
        for key in plugin_prefs.defaults[store_name].keys():
            store[key] = prefs_store[store_name].get(key, plugin_prefs.defaults[store_name][key])
    else:
        store = plugin_prefs.defaults[store_name]
    return store


class GenreTagMappingsTableWidget(QTableWidget):
    def __init__(self, parent, all_tags):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tags_values = all_tags


class ConfigWidget(DefaultConfigWidget):

    def __init__(self, plugin):
        DefaultConfigWidget.__init__(self, plugin)
        c = get_plugin_prefs(STORE_NAME, fill_defaults=True)

        other_group_box = QGroupBox('Eka options', self)
        self.l.addWidget(other_group_box, self.l.rowCount(), 0, 1, 2)
        other_group_box_layout = QVBoxLayout()
        other_group_box.setLayout(other_group_box_layout)

        self.sid_label = QLabel('Your portal SID cookie (get the \'phpbb3_rl7a3_sid\' value):', self)
        other_group_box_layout.addWidget(self.sid_label)

        self.sid_input = QLineEdit(self)
        self.sid_input.setText(c.get(KEY_SID, ''))
        self.sid_input.setToolTip('Enter your SID value for authentication')
        other_group_box_layout.addWidget(self.sid_input)

    def commit(self):
        DefaultConfigWidget.commit(self)
        new_prefs = {}
        new_prefs[KEY_SID] = unicode(self.sid_input.text()).strip()
        plugin_prefs[STORE_NAME] = new_prefs
