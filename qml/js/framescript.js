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
    var target = o.target
    // Laid out again (new text size): replace our style and stay with the
    // sentence at the top of the page, even if it began on the page before.
    // The first sentence starting on the page would drift forward.
    var style = current() ? state.style : null
    if (style && target.keep) {
        var top = firstSentenceOn(currentPage())
        if (top)
            target = { id: top, fraction: target.fraction }
    }
    if (!style) {
        style = doc.createElement("style")
        ;(doc.head || doc.documentElement).appendChild(style)
    }
    // QML gives the text size and the bar in screen pixels, CSS counts
    // device-independent ones.
    var dpr = content.devicePixelRatio || 1
    var fontSize = o.fontSize / dpr
    var marginBottom = o.marginBottom + o.barHeight / dpr
    // Everything is !important: the book's CSS must neither break the pages
    // nor override the basic settings. Pages are CSS columns of one screen width
    // each: a column of width - 2 * margin plus a gap of 2 * margin, so every
    // page starts exactly one screen width further right.
    style.textContent = important(
        // On html too: sizes in rem refer to it.
        "html { height: 100%; margin: 0; padding: 0; overflow: hidden; background: " + o.background + ";" +
        "  font-size: " + fontSize + "px; }" +
        "html body { margin: 0; height: 100vh; box-sizing: border-box; overflow: hidden;" +
        "  padding: " + o.marginTop + "px " + margin + "px " + marginBottom + "px;" +
        "  column-width: " + (width - 2 * margin) + "px; column-gap: " + (2 * margin) + "px; column-fill: auto;" +
        "  color: " + o.color + "; background: " + o.background + ";" +
        "  font-size: " + fontSize + "px; line-height: " + o.lineHeight + ";" +
        "  overflow-wrap: break-word; }" +
        // Like the basic settings of FBReader: font size and line spacing
        // come from the app, relative sizes, indents and spacing of the
        // book build on them. A unitless line height scales with each font.
        "body * { line-height: inherit; }" +
        // The app's font, not the book's; code stays monospaced.
        "body, body * { font-family: " + o.fontFamily + "; }" +
        "body pre, body code, body kbd, body samp, body tt { font-family: monospace; }" +
        "body img, body svg { display: block; margin: 0 auto; max-width: 100%; max-height: 70vh;" +
        "  break-inside: avoid; }" +
        // Links cannot be followed, so they look like the text around them.
        "body a, body a:link, body a:visited { color: inherit; text-decoration: none; }" +
        // Our own mark for the sentence spoken: the book's style for its
        // active class is made for white pages.
        "body .anchorman-active { background-color: " + o.activeColor + "; }")
    normalize(doc)

    var sentences = []
    var isSentence = {}
    for (var i = 0; i < o.ids.length; ++i) {
        // Python does not check that the ids exist in the page.
        var el = doc.getElementById(o.ids[i])
        if (el) {
            sentences.push(el)
            isSentence[o.ids[i]] = true
        }
    }
    var active = current() ? state.active : null
    state = {
        serial: o.serial,
        doc: doc,
        style: style,
        // The body scrolls, not the root element: Sailfish's Gecko stops
        // scrolling the root four screen widths before its end.
        scroller: doc.body || doc.documentElement,
        width: width,
        sentences: sentences,
        isSentence: isSentence,
        active: active
    }
    go(target)
    if (o.highlight) {
        highlight(o.highlight)
    } else if (state.active) {
        // Playback has stopped.
        state.active.classList.remove("anchorman-active")
        state.active = null
    }
    awaitPaint(o.serial)
})

// The sentence spoken: marked, its page shown. A sentence running onto
// further pages reports them with the share of its text before each, so
// QML can turn the page while the sentence is spoken.
function highlight(id) {
    var el = state.doc.getElementById(id)
    if (state.active && state.active !== el)
        state.active.classList.remove("anchorman-active")
    state.active = el
    var splits = []
    if (el) {
        el.classList.add("anchorman-active")
        var rects = boxes(el)
        var total = 0
        for (var i = 0; i < rects.length; ++i)
            total += rects[i].width
        var first = rects.length ? pageOfBox(rects[0]) : pageOf(el)
        var before = 0
        var page = first
        for (var j = 0; j < rects.length; ++j) {
            var p = pageOfBox(rects[j])
            if (p > page && total > 0) {
                splits.push({ page: p, share: before / total })
                page = p
            }
            before += rects[j].width
        }
        if (first !== currentPage())
            showPage(first)
    }
    sendAsyncMessage("anchorman:highlighted", { serial: state.serial, id: id, splits: splits })
}

addMessageListener("anchorman:highlight", function (message) {
    if (current())
        highlight(message.data.id)
})

addMessageListener("anchorman:show", function (message) {
    if (current() && message.data.page !== currentPage())
        showPage(message.data.page)
})

// A tap, given as a share of the view's width and height: the sentence
// there, "" if none.
// Not named like the answer: the WebView hands a frame script's own
// messages back to its listeners, which made the answer ask again.
addMessageListener("anchorman:hitTest", function (message) {
    if (!current())
        return
    var el = state.doc.elementFromPoint(message.data.x * content.innerWidth,
                                        message.data.y * content.innerHeight)
    while (el && !(el.id && state.isSentence[el.id]))
        el = el.parentElement
    sendAsyncMessage("anchorman:hit", { serial: state.serial, id: el ? el.id : "" })
})

// Where playback starts on this page: the preferred sentence (the one
// paused at) if it is on the page, else the topmost sentence, also one cut
// off at the top, else the first one after the page. "" if there is none.
addMessageListener("anchorman:startSentence", function (message) {
    if (!current())
        return
    var page = currentPage()
    var id = ""
    var prefer = message.data.prefer ? state.doc.getElementById(message.data.prefer) : null
    if (prefer && boxes(prefer).some(function (r) { return pageOfBox(r) === page }))
        id = prefer.id
    for (var i = 0; !id && i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length && pageOfBox(rects[rects.length - 1]) >= page)
            id = state.sentences[i].id
    }
    sendAsyncMessage("anchorman:start", { serial: state.serial, id: id })
})

function important(css) {
    return css.replace(/;/g, " !important;")
}

// Elements that may stay smaller than the text around them.
var smallTags = { sub: true, sup: true, small: true, rt: true }

// Undo what CSS alone cannot: justified text leaves wide gaps on a narrow
// screen, but "center" must stay; and books shrink their text with relative
// sizes on paragraphs or wrappers (".calibre { font-size: 0.75em }"), which
// would scale the text size chosen in the app, while larger headings must
// stay. So look at each element: one smaller than its parent gets 1em.
// All reads come before all writes: mixing them would recompute the styles
// every time.
function normalize(doc) {
    if (!doc.body)
        return
    var elements = doc.body.getElementsByTagName("*")
    var sizes = new Map([[doc.body, parseFloat(content.getComputedStyle(doc.body).fontSize)]])
    var justified = []
    var shrunk = []
    // Document order: a parent comes before its children.
    for (var i = 0; i < elements.length; ++i) {
        var element = elements[i]
        var style = content.getComputedStyle(element)
        var size = parseFloat(style.fontSize)
        sizes.set(element, size)
        if (style.textAlign === "justify")
            justified.push(element)
        var parentSize = sizes.get(element.parentElement)
        if (parentSize && size < parentSize * 0.9 && !smallTags[element.localName])
            shrunk.push(element)
    }
    for (var j = 0; j < justified.length; ++j)
        justified[j].style.setProperty("text-align", "start", "important")
    for (var k = 0; k < shrunk.length; ++k)
        shrunk[k].style.setProperty("font-size", "1em", "important")
}

// After a layout QML covers the view until Gecko has painted it; the layout
// itself is reported before the paint. A paint of the unstyled page may
// still be under way and report afterwards, so only paints of a later
// transaction than the one current at the layout count.
var paintSerial = -1
var paintAfter = -1
addEventListener("MozAfterPaint", function (event) {
    if (paintSerial < 0)
        return
    if (paintAfter >= 0 && !(event.transactionId > paintAfter))
        return
    sendAsyncMessage("anchorman:painted", { serial: paintSerial })
    paintSerial = -1
}, true)

function awaitPaint(serial) {
    try {
        paintAfter = content.windowUtils.lastTransactionId
    } catch (e) {
        paintAfter = -1
    }
    paintSerial = serial
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

// target: { id, fraction } (either may be missing) or { end: true }; keep
// is only read by the layout.
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

// The topmost sentence visible on the page, also if it is cut off at the top.
function firstSentenceOn(page) {
    for (var i = 0; i < state.sentences.length; ++i) {
        var rects = boxes(state.sentences[i])
        if (rects.length === 0)
            continue
        if (pageOfBox(rects[0]) > page)
            return ""
        if (pageOfBox(rects[rects.length - 1]) >= page)
            return state.sentences[i].id
    }
    return ""
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
