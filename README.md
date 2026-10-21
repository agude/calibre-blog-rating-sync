# Calibre Blog Rating Sync

A Calibre plugin that syncs book ratings from blog reviews. It reads the
[schema.org `Review`](https://schema.org/Review) JSON-LD embedded in each
review page and writes the rating into your Calibre library.

## How it works

Each book is linked to a review URL stored in a custom column. Syncing
fetches every linked URL, extracts the `Review` rating from the page's
JSON-LD, and updates Calibre's rating column. Ratings are normalized to
Calibre's five-star scale using `bestRating`/`worstRating` and preserve
half stars (Calibre stores ratings as 0–10 internally).

## Requirements

- Calibre 5.13 or newer. It is the first release with the `qt.core` module
  the plugin imports.
- A blog whose review pages embed JSON-LD like:

  ```html
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Review",
    "reviewRating": {
      "@type": "Rating",
      "ratingValue": "4",
      "bestRating": "5",
      "worstRating": "1"
    },
    "itemReviewed": {
      "@type": "Book",
      "name": "Hyperion",
      "author": {"@type": "Person", "name": "Dan Simmons"}
    }
  }
  </script>
  ```

  Top-level arrays, `@graph` containers, list-valued `@type`, and
  string-valued `author` are all handled. Pages with a `rel="canonical"`
  link pointing elsewhere are treated as outdated reviews and skipped.

- For bulk linking: a `sitemap.xml` at the blog root (sitemap index files
  are followed). Review pages must be direct children of a path prefix,
  `/books/` by default (e.g. `/books/hyperion/`; `/books/authors/...` is
  ignored).

## Installation

```sh
just build
```

Then in Calibre: **Preferences → Plugins → Load plugin from file** →
select `BlogRatingSync.zip` → restart Calibre.

## Setup

1. Create a custom **text** column to hold the review URL:
   **Preferences → Add your own columns**, lookup name `blog_review_url`
   (shown as `#blog_review_url`). Restart Calibre.
2. Configure the plugin (**Preferences → Plugins → Blog Rating Sync →
   Customize plugin**): set your blog's base URL and the custom column
   lookup name.

## Usage

The toolbar button's menu has five actions:

- **Sync linked ratings** (also the default toolbar action) — fetch every
  linked review and update ratings that changed.
- **Update selected books from blog** — fetch only the linked reviews of the
  selected books and update their ratings. Use it after linking a new book.
- **Bulk link from sitemap...** — discover review pages via the sitemap,
  match them to unlinked Calibre books by title/author similarity, and
  review the proposed matches in a table before linking. Each Calibre book
  can be selected by at most one review; conflicting selections are reset
  to Skip for manual resolution.
- **Link URL to selected book...** — paste a review URL for one selected
  book; the plugin fetches the page and shows what it found before linking.
- **Unlink selected books** — clear the review URL for the selected books.

To show the same menu when you right-click a book, add the plugin to that
menu. On first install, Calibre asks where to add the plugin. Later, go to
**Preferences → Toolbars & menus**. Set the location to
"The context menu for the books in the calibre library", and add
"Blog Rating Sync". Right-clicking a book then shows Blog Rating Sync with
the same submenu as the toolbar button.

## Development

```sh
just test        # run the test suite (uv run pytest)
just build       # produce BlogRatingSync.zip
just bump minor  # bump the version (major|minor|patch)
```

The version lives in `plugin/constants.py` (`PLUGIN_VERSION`); the plugin
metadata and user agent derive from it. `just bump` updates it and
`pyproject.toml` together.

Tests run without Calibre or Qt installed; `tests/conftest.py` stubs both
and maps the `calibre_plugins.blog_rating_sync.*` imports to the real
modules in `plugin/`.
