from __future__ import unicode_literals, division, absolute_import, print_function

__license__   = 'GPL v3'
__copyright__ = '2025, Jobobby04'

import socket, re
from threading import Thread

from mechanize import Request
from datetime import datetime

from calibre.ebooks.BeautifulSoup import BeautifulSoup

from calibre.ebooks.metadata.book.base import Metadata

class Worker(Thread): # Get details

    """
    Get book details from Eka's Portal in a separate thread
    """

    def __init__(self, url, match_authors, result_queue, browser, log, relevance, plugin, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url, self.result_queue = url,  result_queue
        self.match_authors = match_authors
        self.log, self.timeout = log, timeout
        self.relevance, self.plugin = relevance, plugin
        self.browser = browser.clone_browser()
        self.cover_url = self.eka_id = self.isbn = None

    def run(self):
        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r'%self.url)

    def get_details(self):
        try:
            self.log.info('Eka url: %r'%self.url)
            self.log.info('Eka relevance: %r'%self.relevance)
            request = self.url
            try:
                import calibre_plugins.ekaportal.config as cfg
                cookie = cfg.get_plugin_pref(cfg.STORE_NAME, cfg.KEY_SID)
            except:
                cookie = None
            if cookie:
                request = Request(self.url, headers={'Cookie': 'phpbb3_rl7a3_sid=%r'%cookie})
            raw = self.browser.open_novisit(request, timeout=self.timeout).read().strip()
        except Exception as e:
            if callable(getattr(e, 'getcode', None)) and \
                    e.getcode() == 404:
                self.log.error('URL malformed: %r'%self.url)
                return
            attr = getattr(e, 'args', [None])
            attr = attr if attr else [None]
            if isinstance(attr[0], socket.timeout):
                msg = 'Eka timed out. Try again later.'
                self.log.error(msg)
            else:
                msg = 'Failed to make details query: %r'%self.url
                self.log.exception(msg)
            return

        #raw = raw.decode('utf-8', errors='replace')
        #raw = raw.replace(" async ", " ")
        #open('E:\\t3.html', 'wb').write(raw)

        try:
            root = BeautifulSoup(raw)
        except:
            msg = 'Failed to parse Eka details page: %r'%self.url
            self.log.exception(msg)
            return

        self.parse_details(root)

    def parse_details(self, root):
        try:
            eka_id = self.parse_eka_id(self.url)
        except:
            self.log.exception('Error parsing eka id for url: %r'%self.url)
            eka_id = None

        try:
            title = self.parse_title(root)
        except:
            self.log.exception('Error parsing title for url: %r'%self.url)
            title = None

        try:
            author = self.parse_author(root)
        except:
            self.log.exception('Error parsing author for url: %r'%self.url)
            author = None

        if not title or not author or not eka_id:
            self.log.error('Could not find title/authors/Eka id for %r'%self.url)
            self.log.error('Eka: %r Title: %r Author: %r'%(eka_id, title,
                author))
            return

        mi = Metadata(title, [author])
        mi.set_identifier('eka', eka_id)
        self.eka_id = eka_id

        try:
            mi.pubdate = self.parse_pubdate(root)
        except:
            self.log.exception('Error parsing publish date for url: %r' % self.url)

        try:
            mi.tags = self.parse_tags(root)
        except:
            self.log.exception('Error parsing tags for url: %r'%self.url)

        try:
            mi.comments = self.parse_summary(root)
        except:
            self.log.exception('Error parsing comments for url: %r' % self.url)

        # There will be no other on Eka's Portal!
        mi.publisher = 'Eka\'s Portal'

        mi.source_relevance = self.relevance

        self.plugin.clean_downloaded_metadata(mi)

        self.result_queue.put(mi)

    def parse_eka_id(self, url):
        from calibre_plugins.ekaportal import Eka # import BASE_URL
        return re.search(Eka.BASE_URL + '/g4/view/(.*)', url).groups(0)[0]

    def parse_title(self, root):
        title_node = root.css.select('div.g-box-header > span.g-box-title') #.xpath('//div[@class="g-box-header"]/span[@class="g-box-title"]') #'div.g-box-header > span.g-box-title')
        if title_node:
            self.log.info("parse_title: title=", title_node[1].text)
            return title_node[1].text
        else:
            self.log.error("parse_title: no title")
        return None

    def parse_author(self, root):
        author_node = root.css.select('div.g-box-header > span > a.user-link') #.xpath('//div[@class="g-box-header"]/span/a[@class="user-link"]') #'div.g-box-header > span > a.user-link')
        if author_node:
            self.log.info("parse_author: author=", author_node[0].text)
            return author_node[0].text
        else:
            self.log.error("parse_author: no author")
        return None

    def parse_tags(self, root):
        tag_nodes = root.css.select('div#taginfo span.taglist > a')
        if tag_nodes:
            tag_list = [ x.text for x in tag_nodes ]
            self.log.info("parse_tags: tags=", tag_list)
            return tag_list
        else:
            self.log.error("parse_tags: no tags")
        return None

    def parse_pubdate(self, root):
        pubdate_node = root.css.select('.pretty-date')
        if pubdate_node:
            pubdate_dirty = pubdate_node[0].attrs.get('title')
            pubdate_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', pubdate_dirty)
            self.log.info("parse_pubdate: pubdate_clean=", pubdate_clean)
            return datetime.strptime(pubdate_clean, "%b %d, %Y %I:%M %p")
        else:
            self.log.error("parse_tags: no pubdate")
        return None

    def parse_summary(self, root):
        summary_node = root.css.select('.g-box-contents .item-main-column p')
        if summary_node:
            self.log.info("parse_summary: summary=", summary_node[0].prettify())
            return summary_node[0].prettify()
        else:
            self.log.error("parse_summary: no summary")
        return None

