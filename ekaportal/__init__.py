#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai


__license__   = 'GPL v3'
__copyright__ = '2025, Jobobby04'
__docformat__ = 'restructuredtext en'

import time, re

from calibre.ebooks.metadata.sources.base import Source


class Eka(Source):

    name                = 'EkaPortalPlugin'  # Name of the plugin
    description         = 'Downloads metadata from Eka\'s Portal'
    supported_platforms = ['windows', 'osx', 'linux']  # Platforms this plugin will run on
    author              = 'Jobobby04'  # The author of this plugin
    version             = (1, 0, 0)   # The version number of this plugin
    minimum_calibre_version = (2, 0, 0)
    capabilities = frozenset(['identify'])
    touched_fields = frozenset(['title', 'authors', 'identifier:eka',
                                'tags'])
    supports_gzip_transfer_encoding = True
    BASE_URL = 'https://aryion.com'

    def get_eka_id(self, identifiers):
        eka_id = identifiers.get('eka', None)
        return eka_id

    def get_book_url(self, identifiers):
        eka_id = self.get_eka_id(identifiers)
        if eka_id:
            return ('Eka', eka_id,
                    '%s/g4/view/%s'%(Eka.BASE_URL, eka_id))
        return None


    def get_book_url_from_title(self, title):
        if title:
            match = re.match("[^-]+-([0-9]+)-.+", title).group(1)
            if match:
                return ('Eka', match,
                    '%s/g4/view/%s'%(Eka.BASE_URL, match))
        return None

    def config_widget(self):
        """
        Overriding the default configuration screen for our own custom configuration
        """
        from calibre_plugins.ekaportal.config import ConfigWidget
        return ConfigWidget(self)

    def identify(self, log, result_queue, abort, title=None, authors=None,
            identifiers={}, timeout=30):
        matches = []

        eka_id = self.get_eka_id(identifiers)
        br = self.browser
        if eka_id:
            (name, eka_id, url) = self.get_book_url(identifiers)
            matches.append(url)
        else:
            (name, eka_id, url) = self.get_book_url_from_title(title)
            matches.append(url)

        if abort.is_set():
            return None

        if not matches:
            log.error('No matches found')
            return None
        from calibre_plugins.ekaportal.worker import Worker
        author_tokens = list(self.get_author_tokens(authors))
        workers = [Worker(url, author_tokens, result_queue, br, log, i+1, self) for i, url in
                enumerate(matches)]

        for w in workers:
            w.start()
            # Don't send all requests at the same time
            time.sleep(0.1)

        while not abort.is_set():
            a_worker_is_alive = False
            for w in workers:
                w.join(0.2)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break

        return None


