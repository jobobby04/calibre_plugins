import json
from qt.core import QMessageBox, QApplication
from calibre.gui2.actions import InterfaceAction
from calibre.ebooks.metadata.book.base import Metadata

class ClipboardMetadataAction(InterfaceAction):
    name = 'Clipboard Metadata Importer'

    action_spec = (
        'Paste Metadata from Clipboard',
        None,  # You can add an icon here, e.g. QIcon('images/icon.png')
        'Replace book metadata with JSON from clipboard',
        None
    )

    def genesis(self):
        # Create menu action
        self.qaction.setText('Paste Metadata from Clipboard')
        self.qaction.triggered.connect(self.apply_metadata_from_clipboard)

    def apply_metadata_from_clipboard(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return QMessageBox.warning(
                self.gui,
                'No selection',
                'Please select a book to apply metadata to.'
            )

        # Read clipboard using Qt
        try:
            clipboard = QApplication.clipboard()
            raw_data = clipboard.text().strip()
            data = json.loads(raw_data)
        except Exception as e:
            return QMessageBox.critical(
                self.gui,
                'Clipboard Error',
                f'Could not read JSON from clipboard:\n{e}'
            )

        db = self.gui.current_db

        for row in rows:
            book_id = self.gui.library_view.model().id(row)
            mi = db.get_metadata(book_id, index_is_id=True)

            # Update metadata fields if they exist in JSON
            if 'title' in data:
                mi.title = data['title']
            if 'authors' in data:
                mi.authors = data['authors'] if isinstance(data['authors'], list) else [data['authors']]
            if 'tags' in data:
                mi.tags = data['tags']
            if 'series' in data:
                mi.series = data['series']
            if 'series_index' in data:
                mi.series_index = float(data['series_index'])
            if 'publisher' in data:
                mi.publisher = data['publisher']
            if 'pubdate' in data:
                from calibre.utils.date import parse_only_date
                mi.pubdate = parse_only_date(data['pubdate'])
            if 'comments' in data:
                mi.comments = data['comments']
            if 'languages' in data:
                mi.languages = data['languages']

            # Write changes back
            db.set_metadata(book_id, mi)

        self.gui.library_view.model().refresh(rows)
        self.gui.status_bar.show_message('Metadata updated from clipboard JSON.', 3000)