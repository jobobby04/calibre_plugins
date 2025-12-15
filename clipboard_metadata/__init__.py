#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Jobobby04'
__docformat__ = 'restructuredtext en'

import time, re

from calibre.ebooks.metadata.sources.base import Source
from calibre.customize import InterfaceActionBase
from calibre_plugins.clipboard_metadata.action import ClipboardMetadataAction


class ClipboardMetadataPlugin(InterfaceActionBase):

    name                = 'ClipboardPlugin'  # Name of the plugin
    description         = 'Uses metadata from Clipboard'
    supported_platforms = ['windows', 'osx', 'linux']  # Platforms this plugin will run on
    author              = 'Jobobby04'  # The author of this plugin
    version             = (1, 0, 0)   # The version number of this plugin
    minimum_calibre_version = (2, 0, 0)

    actual_plugin = 'calibre_plugins.clipboard_metadata.action:ClipboardMetadataAction'

    def is_customizable(self):
        return False

    # def load_actual_plugin(self, gui):
    #     return ClipboardMetadataAction(gui, None)


