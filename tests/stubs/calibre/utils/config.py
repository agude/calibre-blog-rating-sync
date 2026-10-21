class JSONConfig(dict):
    """A dict that answers missing keys from `defaults`, as calibre's JSONConfig does."""

    def __init__(self, rel_path_to_cf_file):
        super().__init__()
        self.rel_path_to_cf_file = rel_path_to_cf_file
        self.defaults = {}

    def __missing__(self, key):
        return self.defaults[key]
