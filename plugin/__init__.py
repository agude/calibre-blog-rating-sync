from calibre.customize import InterfaceActionBase


class BlogRatingSyncPlugin(InterfaceActionBase):
    name = "Blog Rating Sync"
    description = "Sync book ratings from blog reviews with JSON-LD structured data"
    supported_platforms = ["windows", "osx", "linux"]
    author = "Alex Gude"
    version = (0, 1, 0)
    minimum_calibre_version = (5, 0, 0)

    actual_plugin = "calibre_plugins.blog_rating_sync.ui:BlogRatingSyncAction"

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.blog_rating_sync.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
