// Runs in the browser part of the WebView, not in the page. Page scripts are
// disabled, so this is the only code that touches a book; QML talks to it
// through messages only.

var state = null

// Second line of defence besides the app-wide setting, and for this view
// only: no page scripts, no <meta http-equiv="refresh"> leaving the chapter,
// no embedded frames. Each in its own try, should Gecko drop one of them.
try { docShell.allowJavascript = false } catch (e) { }
try { docShell.allowMetaRedirects = false } catch (e) { }
try { docShell.allowSubframes = false } catch (e) { }

function current() {
    return state && state.doc === content.document ? state : null
}

addEventListener("DOMContentLoaded", function (event) {
    var doc = content.document
    if (event.target !== doc)
        return
    // Without a viewport the page is laid out 980 px wide, like on a desktop;
    // a book's own viewport would break the page width just the same.
    var viewport = doc.querySelector("meta[name=viewport]")
    if (!viewport) {
        viewport = doc.createElement("meta")
        viewport.name = "viewport"
        ;(doc.head || doc.documentElement).appendChild(viewport)
    }
    viewport.content = "width=device-width, initial-scale=1"
    // The WebView gets no touches; this only guards against links leaving
    // the chapter should that ever change.
    doc.addEventListener("click", function (e) { e.preventDefault() }, true)
}, true)

// Wait for "load", not DOMContentLoaded: images change the number of pages.
addEventListener("load", function (event) {
    if (event.target === content.document)
        sendAsyncMessage("anchorman:loaded", { url: content.document.URL })
}, true)

addMessageListener("anchorman:layout", function (message) {
    var o = message.data
    var doc = content.document
    var width = content.innerWidth
    var margin = o.margin
    var style = doc.createElement("style")
    // Everything is !important: the book's CSS must neither break the pages
    // nor override the basic settings. Pages are CSS columns of one screen width
    // each: a column of width - 2 * margin plus a gap of 2 * margin, so every
    // page starts exactly one screen width further right.
    style.textContent = important(
        "html { height: 100%; margin: 0; padding: 0; overflow: hidden; background: " + o.background + "; }" +
        "html body { margin: 0; height: 100vh; box-sizing: border-box; overflow: hidden;" +
        "  padding: " + o.marginTop + "px " + margin + "px " + margin + "px;" +
        "  column-width: " + (width - 2 * margin) + "px; column-gap: " + (2 * margin) + "px; column-fill: auto;" +
        "  color: " + o.color + "; background: " + o.background + ";" +
        "  font-size: " + o.fontSize + "px; line-height: " + o.lineHeight + ";" +
        "  overflow-wrap: break-word; }" +
        // Like the basic settings of FBReader: font size and line spacing
        // come from the app, relative sizes, indents and spacing of the
        // book build on them. A unitless line height scales with each font.
        "body * { line-height: inherit; }" +
        "body img, body svg { display: block; margin: 0 auto; max-width: 100%; max-height: 70vh;" +
        "  break-inside: avoid; }" +
        // Links cannot be followed, so they look like the text around them.
        "body a, body a:link, body a:visited { color: inherit; text-decoration: none; }")
    ;(doc.head || doc.documentElement).appendChild(style)
    unjustify(doc)

    var sentences = []
    for (var i = 0; i < o.ids.length; ++i) {
        // Python does not check that the ids exist in the page.
        var el = doc.getElementById(o.ids[i])
        if (el)
            sentences.push(el)
    }
    state = {
        serial: o.serial,
        doc: doc,
        // The body scrolls, not the root element: Sailfish's Gecko stops
        // scrolling the root four screen widths before its end.
        scroller: doc.body || doc.documentElement,
        width: width,
        sentences: sentences
    }
    go(o.target)
})

function important(css) {
    return css.replace(/;/g, " !important;")
}

// Justified text leaves wide gaps on a narrow screen. CSS cannot override
// only "justify" and keep "center", so look at each element. All reads come
// before all writes: mixing them would recompute the styles every time.
function unjustify(doc) {
    var elements = doc.body ? doc.body.getElementsByTagName("*") : []
    var justified = []
    for (var i = 0; i < elements.length; ++i) {
        if (content.getComputedStyle(elements[i]).textAlign === "justify")
            justified.push(elements[i])
    }
    for (var j = 0; j < justified.length; ++j)
        justified[j].style.setProperty("text-align", "start", "important")
}

addMessageListener("anchorman:goto", function (message) {
    if (current())
        go(message.data.target)
})

addMessageListener("anchorman:turn", function (message) {
    if (!current())
        return
    var page = currentPage() + message.data.delta
    if (page < 0 || page >= pageCount()) {
        sendAsyncMessage("anchorman:edge", { serial: state.serial, delta: message.data.delta })
        return
    }
    showPage(page)
})

function pageCount() {
    return Math.max(1, Math.round(state.scroller.scrollWidth / state.width))
}

function currentPage() {
    return Math.round(state.scroller.scrollLeft / state.width)
}

// target: { id, fraction } (either may be missing) or { end: true }.
function go(target) {
    var el = target.id ? state.doc.getElementById(target.id) : null
    if (el)
        showPage(pageOf(el))
    else if (target.end)
        showPage(pageCount() - 1)
    else
        showPage(Math.round((target.fraction || 0) * (pageCount() - 1)))
}

function showPage(page) {
    var pages = pageCount()
    state.scroller.scrollLeft = Math.max(0, Math.min(pages - 1, page)) * state.width
    // Report where the view really is, should the scroll be clamped.
    page = currentPage()
    sendAsyncMessage("anchorman:page", {
        serial: state.serial,
        page: page,
        pages: pages,
        firstId: firstSentenceStartingOn(page),
        fraction: pages > 1 ? page / (pages - 1) : 0
    })
}

// Trailing whitespace inside a sentence can produce empty boxes on the next
// page; they do not count.
function boxes(el) {
    return Array.prototype.filter.call(el.getClientRects(), function (r) {
        return r.width >= 1 && r.height >= 1
    })
}

function pageOfBox(rect) {
    return Math.floor((rect.left + state.scroller.scrollLeft) / state.width)
}

function pageOf(el) {
    var first = boxes(el)[0] || el.getBoundingClientRect()
    return pageOfBox(first)
}

// The first sentence that starts on the page. It brings back exactly this
// page; a sentence cut off at the top starts on the previous one. "" if no
// sentence starts here, then the fraction of the chapter is used.
function firstSentenceStartingOn(page) {
    for (var i = 0; i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length === 0)
            continue
        var start = pageOfBox(rects[0])
        if (start === page)
            return state.sentences[i].id
        if (start > page)
            return ""
    }
    return ""
}
