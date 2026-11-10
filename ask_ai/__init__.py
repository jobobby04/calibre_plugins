#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2026, Jobobby04'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase


class AskAIPlugin(InterfaceActionBase):

    name                = 'Ask AI'  # Name of the plugin (drives the zip filename)
    description         = 'Ask the AI about a book\'s content using calibre\'s built-in AI support'
    supported_platforms = ['windows', 'osx', 'linux']  # Platforms this plugin will run on
    author              = 'Jobobby04'  # The author of this plugin
    version             = (1, 0, 0)   # The version number of this plugin
    minimum_calibre_version = (8, 16, 2)

    actual_plugin = 'calibre_plugins.ask_ai.action:AskAIAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.ask_ai.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        if hasattr(config_widget, 'save_settings'):
            config_widget.save_settings()
        return True
