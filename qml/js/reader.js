// Injected into the chapter via runJavaScript. Paging, highlighting, page lookup.
// QML replaces the options placeholder at the end with a JSON object.

(function (options) {
    var doc = document
    var activeClass = "-epub-media-overlay-active"
    var margin = options.margin
    var pageWidth = window.innerWidth

    var style = doc.createElement("style")
    style.textContent =
        "html { height: 100%; margin: 0; padding: 0; overflow: hidden; background: " + options.background + "; }" +
        "body { margin: 0; height: 100vh; box-sizing: border-box;" +
        "  padding: " + options.marginTop + "px " + margin + "px " + margin + "px;" +
        "  column-width: " + (pageWidth - 2 * margin) + "px; column-gap: " + (2 * margin) + "px; column-fill: auto;" +
        "  color: " + options.color + "; background: " + options.background + "; font-size: " + options.fontSize + "px; }" +
        "img { display: block; margin: 0 auto; max-width: 100%; max-height: 70vh; break-inside: avoid; }" +
        "a { color: inherit; }" +
        "." + activeClass + " { background: " + options.highlight + "; color: inherit; }"
    doc.head.appendChild(style)

    var sentences = Array.prototype.filter.call(doc.querySelectorAll("[id]"), function (el) {
        return /-s\d+$/.test(el.id)
    })
    var scroller = doc.scrollingElement || doc.documentElement
    var current = null

    function pageCount() {
        return Math.max(1, Math.round(scroller.scrollWidth / pageWidth))
    }

    function currentPage() {
        return Math.round(scroller.scrollLeft / pageWidth)
    }

    function showPage(page) {
        page = Math.max(0, Math.min(pageCount() - 1, page))
        scroller.scrollLeft = page * pageWidth
        return page
    }

    // Trailing whitespace inside a sentence can produce empty boxes on the next page; ignore them.
    function boxes(el) {
        return Array.prototype.filter.call(el.getClientRects(), function (r) {
            return r.width >= 1 && r.height >= 1
        })
    }

    function pageOfBox(rect) {
        return Math.floor((rect.left + scroller.scrollLeft) / pageWidth)
    }

    function pageOf(el) {
        var first = boxes(el)[0] || el.getBoundingClientRect()
        return pageOfBox(first)
    }

    window.anchorman = {
        info: function () {
            return { pages: pageCount(), page: currentPage(),
                     sentences: sentences.map(function (el) { return el.id }) }
        },
        page: function (delta) {
            return { page: showPage(currentPage() + delta), pages: pageCount() }
        },
        highlight: function (id) {
            var start = performance.now()
            var el = doc.getElementById(id)
            if (!el)
                return { error: "unknown id " + id }
            if (current)
                current.classList.remove(activeClass)
            el.classList.add(activeClass)
            current = el
            var page = pageOf(el)
            if (page !== currentPage())
                showPage(page)
            return { page: currentPage(), pages: pageCount(), ms: performance.now() - start }
        },
        // The topmost sentence visible on this page. If it is cut off at the top,
        // playback should start at its beginning on the previous page.
        firstSentenceOnPage: function () {
            var page = currentPage()
            for (var i = 0; i < sentences.length; ++i) {
                var rects = boxes(sentences[i])
                for (var j = 0; j < rects.length; ++j) {
                    if (pageOfBox(rects[j]) === page)
                        return sentences[i].id
                }
            }
            return ""
        }
    }
    return window.anchorman.info()
})(__OPTIONS__)
