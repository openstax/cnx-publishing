## Baking the books

### Rationale

In order to implement some book-wide features (consistent numbering, provide
end-of-chapter and end-of-book collated resources) we have implemented a system
to transform a published book into a different format. We describe this as
"baking" a "raw" book into its "baked", finished state. This baking process is
guided by a "recipe", written in a superset of CSS - CSS Transforms, or CSSt.
This language is defined by and implemented in the cnx-easybake module.

### Publishing and Baking

From the publishing perspective, baking is a post-publication conversion of the
provided raw HTML files and table-of-contents tree that constitute a book, into
a more useful completed state. In fact, a book is not completed until it has
been baked. If there is no recipe, currently the baked version is identical to
the raw version. Since baking can be a time-consuming and potentially error
inducing process, successfully publishing does _not_ require successful baking:
storing and making public the (valid) raw form of the book is all that is
required.

#### Technical details

Baking triggers a post-publication processing system, built using Celery and an
AMQP broker (RabbitMQ) for task management. The steps involved in baking are:

  1. create a single-file version of the book - export-epub
  2. acquire the appropriate recipe
  3. apply the recipe to the book - "bake" it.
  4. make public the baked book as the current version of that book

#### Who's got the recipe?

There are 3 possible sources for a recipe for a given book:
  1. A recipe associated with the `print_style` that has been set on the book
  2. A custom recipe attached to the book, named to match the `print_style` set
  on that book
  3. A custom recipe attached to the book, name "ruleset.css"
  (for historical reasons).

These three paths allow for flexible association of recipes with books. The
`print_style` based lookup serves as a recipe-box, so that more than one book
can share a well tested and robust recipe. This sharing allows the recipe to be
updated across multiple books simultaneously, when an error is found.
Conversely, if a specific book needs its own recipe for some reason, it can be
provided either via a completely custom `print_style` setting, or the magic
filename.

#### When do you need to bake? What are the results?

There are two possibilities for when a book needs to be baked: when its content
has changed, or when its recipe has been changed. If the book's content has
changed, there is a new version of the book available - it will have a new
version number. This content will be submitted for baking. On successful
completion, the new version will be recognized as the "latest" for that book (by
uuid), and the book's state is `current`.

#### What about problems?
This is a change in the definition for latest - now it is the most recently
published that has successfully baked, rather than just the most recently
published. As a consequence, if a new version of a book is published, but it
fails to bake for some reason, the content served as `latest` will not change -
instead, the existing baked content remains in place, and that book enters a
`stale content` state. The raw content of the newer version is available, but
will not be redirected to as the latest.

Because of the indirection through `print_style`, the recipe associated with a
book might change without there being a new version - the raw book content of
the book does not change. While it is likely to  be rare, it is _possible_ that
the book will then fail to bake with the new recipe. In that case, the existing
baked content is left in place, and the book enters a `stale recipe` state.

The `stale` states are both formally error states, but not equally serious.
`Stale content` is more serious, since new content has been published, but is
not available to the reader. Conversely, `stale recipe`, for the most part, will
be missing styling or labeling of content, rather than whole sale absence
absence (though in principle the recipe changes could be anything). In order to
help mitigate the seriousness of `stale content`, if content fails to build with
its primary recipe (discovered as described above), then, if this book has been
baked before (in this or an earlier version), the previous recipe will be
used as a fallback. The state of the content is then `fallback recipe` or simply
`fallback`.
