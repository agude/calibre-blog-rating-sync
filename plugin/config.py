from calibre.utils.config import JSONConfig
from qt.core import QLabel, QLineEdit, QVBoxLayout, QWidget

prefs = JSONConfig("plugins/blog_rating_sync")
prefs.defaults["blog_base_url"] = "https://alexgude.com"
prefs.defaults["custom_column"] = "#blog_review_url"


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QLabel("Blog base URL:"))
        self.blog_url_edit = QLineEdit(prefs["blog_base_url"])
        layout.addWidget(self.blog_url_edit)

        layout.addWidget(QLabel("Custom column lookup name (e.g. #blog_review_url):"))
        self.column_edit = QLineEdit(prefs["custom_column"])
        layout.addWidget(self.column_edit)

    def save_settings(self):
        prefs["blog_base_url"] = self.blog_url_edit.text().strip().rstrip("/")
        prefs["custom_column"] = self.column_edit.text().strip()
