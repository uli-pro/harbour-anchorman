import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebView 1.0

WebViewPage {
    id: page

    property var book
    // chapter is the one in the WebView; requested the one being prepared.
    property int chapter: -1
    property int requested: -1
    property var sentenceIds: []
    property var pendingTarget: null
    property string loadingUrl: ""
    // Messages from the frame script carry the serial of their layout, so
    // late messages about a previous chapter are recognised and dropped.
    property int serial: 0
    property bool ready: false
    property bool covered: true
    property int laidOutFontSize: 0
    property int pageIndex: 0
    property int pageCount: 0
    property string firstId: ""
    // Page numbers across the book are estimated: only the current chapter
    // is laid out, the others are counted by their characters. Python counts
    // them once the first chapter is shown, so opening is not delayed.
    property var chapterChars: []
    property bool countingChars: false
    property real charsPerPage: 0
    property int bookPage: 0
    property int bookPages: 0
    property real fraction: 0
    readonly property color pageColor: Theme.colorScheme === Theme.LightOnDark ? "black" : "white"

    // Turning pages needs the horizontal swipe; the library is in the pulley.
    backNavigation: false
    allowedOrientations: Orientation.Portrait

    function cssColor(c, alpha) {
        return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + ","
                + Math.round(c.b * 255) + "," + alpha + ")"
    }

    function fileUrl(path) {
        return "file://" + path.split("/").map(encodeURIComponent).join("/")
    }

    function start() {
        py.call("anchorman.bridge.load_position", [app.positionsFile, book.key], function (pos) {
            if (typeof page === "undefined" || !page)
                return  // the page was closed meanwhile
            if (pos && pos.spine < book.spine.length)
                loadChapter(pos.spine, { id: pos.id, fraction: pos.fraction })
            else
                loadChapter(Math.max(0, nextLinear(-1, 1)), { fraction: 0 })
        })
    }

    // target: { id, fraction } or { end: true }, see framescript.js
    function loadChapter(index, target) {
        if (index === chapter && ready) {
            flickable.webView.sendAsyncMessage("anchorman:goto", { target: target })
            return
        }
        var item = book.spine[index]
        requested = index
        serial++
        ready = false
        covered = true
        if (!item.overlay) {
            show(index, [], target)
            return
        }
        py.call("anchorman.bridge.read_chapter", [book.root, item.path, item.overlay], function (result) {
            if (typeof page === "undefined" || !page || requested !== index)
                return  // page closed, or another chapter was asked for meanwhile
            if (result.error) {
                // The text can still be read without sentences.
                console.warn("Cannot read overlay", item.overlay, result.error, result.detail)
                show(index, [], target)
            } else {
                show(index, result.ids, target)
            }
        })
    }

    function show(index, ids, target) {
        chapter = index
        requested = -1
        sentenceIds = ids
        pendingTarget = target
        var view = flickable.webView
        var url = fileUrl(book.root + "/" + book.spine[index].path)
        if (view.url.toString() === url) {
            // Still loading: that load will be laid out with the new target.
            if (loadingUrl === url)
                return
            // Setting the same URL again would not load anything.
            loadingUrl = url
            view.reload()
        } else {
            loadingUrl = url
            view.url = url
        }
    }

    function layout(target) {
        laidOutFontSize = app.fontSize
        flickable.webView.sendAsyncMessage("anchorman:layout", {
            serial: serial,
            ids: sentenceIds,
            target: target,
            margin: 24,
            marginTop: 4,
            marginBottom: 12,
            fontSize: app.fontSize,
            lineHeight: 1.3,
            color: cssColor(Theme.primaryColor, 1),
            background: cssColor(pageColor, 1)
        })
    }

    // Same chapter and sentence, new text size. While a layout is under way
    // the "page" message calls this again if the size has changed meanwhile.
    function relayout() {
        if (!ready)
            return
        serial++
        ready = false
        covered = true
        charsPerPage = 0
        layout({ keep: true, id: firstId, fraction: fraction })
    }

    function estimatedPages(index) {
        var perPage = charsPerPage
        if (perPage <= 0) {
            // Nothing laid out yet: assume half a text size per character
            // and 1.3 per line on the screen area.
            perPage = ((flickable.width - 2 * Theme.horizontalPageMargin) / (0.5 * app.fontSize))
                    * (flickable.height / (1.3 * app.fontSize))
        }
        return Math.max(1, Math.round(chapterChars[index] / perPage))
    }

    function updateBookPages() {
        if (chapterChars.length !== book.spine.length) {
            if (!countingChars) {
                countingChars = true
                var paths = book.spine.map(function (item) { return item.path })
                py.call("anchorman.bridge.chapter_lengths", [book.root, paths], function (lengths) {
                    if (typeof page === "undefined" || !page)
                        return
                    chapterChars = lengths
                    updateBookPages()
                })
            }
            return
        }
        var spine = book.spine
        // Short chapters (titles, pictures) say little about a full page.
        if (chapterChars[chapter] >= 1000 && pageCount > 1)
            charsPerPage = chapterChars[chapter] / pageCount
        var before = 0
        var after = 0
        for (var i = 0; i < spine.length; ++i) {
            // Chapters outside the reading order are never paged through.
            if (i === chapter || !spine[i].linear)
                continue
            if (i < chapter)
                before += estimatedPages(i)
            else
                after += estimatedPages(i)
        }
        bookPage = before + pageIndex + 1
        bookPages = before + pageCount + after
    }

    function sameUrl(a, b) {
        try {
            return decodeURIComponent(a) === decodeURIComponent(b)
        } catch (e) {
            return a === b
        }
    }

    function handleMessage(message, data) {
        switch (message) {
        case "anchorman:loaded":
            // A load that was replaced by another one may still report.
            if (loadingUrl === "" || !sameUrl(data.url, loadingUrl))
                return
            loadingUrl = ""
            layout(pendingTarget)
            pendingTarget = null
            break
        case "anchorman:page":
            if (data.serial !== serial)
                return
            ready = true
            if (covered && !uncoverTimer.running)
                uncoverTimer.restart()
            pageIndex = data.page
            pageCount = data.pages
            firstId = data.firstId
            fraction = data.fraction
            updateBookPages()
            savePosition()
            if (laidOutFontSize !== app.fontSize)
                relayout()
            break
        case "anchorman:painted":
            if (data.serial !== serial || !covered)
                return
            uncoverTimer.stop()
            paintedTimer.restart()
            break
        case "anchorman:edge":
            // Only the first of several quick turns past the end counts.
            if (data.serial !== serial || !ready)
                return
            var next = nextLinear(chapter, data.delta)
            if (next >= 0)
                loadChapter(next, data.delta > 0 ? { fraction: 0 } : { end: true })
            break
        }
    }

    function nextLinear(from, delta) {
        for (var i = from + delta; i >= 0 && i < book.spine.length; i += delta) {
            if (book.spine[i].linear)
                return i
        }
        return -1
    }

    function turn(delta) {
        if (ready)
            flickable.webView.sendAsyncMessage("anchorman:turn", { delta: delta })
    }

    function savePosition() {
        py.call("anchorman.bridge.save_position",
                [app.positionsFile, book.key, { spine: chapter, id: firstId, fraction: fraction }],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot save position", result.error, result.detail)
                })
    }

    Connections {
        target: app
        onFontSizeChanged: page.relayout()
    }

    Rectangle {
        anchors.fill: parent
        color: pageColor
    }

    // Chapter and page beside the notch, so the text can use the screen
    // down to its bottom edge.
    Item {
        id: statusLine

        // Only a notch in the middle leaves room on both sides.
        readonly property bool notch: Screen.hasCutouts === true && Screen.topCutout.width > 0
                                      && Screen.topCutout.x > width / 5
                                      && Screen.topCutout.x + Screen.topCutout.width < width * 4 / 5
        readonly property real gap: Theme.paddingMedium

        width: parent.width
        height: Math.max(notch ? Screen.topCutout.y + Screen.topCutout.height : 0,
                         Theme.fontSizeExtraSmall + 2 * Theme.paddingSmall)
        visible: ready

        Label {
            x: Theme.paddingLarge
            width: (statusLine.notch ? Screen.topCutout.x : parent.width / 2) - x - statusLine.gap
            anchors.verticalCenter: parent.verticalCenter
            // Beside a notch there is little room; shrink rather than cut.
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.fontSizeTiny / 2
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            //: Chapter in the book, e.g. "Chapter 3/12"
            text: qsTr("Chapter %1/%2").arg(chapter + 1).arg(book.spine.length)
        }

        Label {
            readonly property real start: statusLine.notch ? Screen.topCutout.x + Screen.topCutout.width
                                                      : parent.width / 2
            x: start + statusLine.gap
            width: parent.width - Theme.paddingLarge - x
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignRight
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.fontSizeTiny / 2
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            visible: bookPages > 0
            //: Estimated page in the whole book, e.g. "Page 30/295"
            text: qsTr("Page %1/%2").arg(bookPage).arg(bookPages)
        }
    }

    WebViewFlickable {
        id: flickable

        anchors {
            top: statusLine.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        // The pulley sits above the flickable; unclipped it would cover the
        // status line.
        clip: true

        PullDownMenu {
            // No highlight strip between the status line and the text; the
            // chosen item is still shown by its text colour.
            highlightColor: "transparent"
            backgroundColor: pageColor

            MenuItem {
                text: qsTr("Text size")
                onClicked: pageStack.push(Qt.resolvedUrl("TextSizePage.qml"))
            }
            MenuItem {
                text: qsTr("Library")
                onClicked: pageStack.pop()
            }
            MenuItem {
                text: qsTr("Contents")
                onClicked: {
                    var toc = pageStack.push(Qt.resolvedUrl("TocPage.qml"),
                                             { toc: book.toc, currentChapter: chapter })
                    toc.selected.connect(function (index, fragment) {
                        loadChapter(index, fragment ? { id: fragment } : { fraction: 0 })
                    })
                }
            }
        }

        webView.active: true
        // WebViewFlickable assumes the page fills the screen; below the
        // header, 100vh would reach past the bottom edge.
        webView.viewportHeight: flickable.height

        webView.onViewInitialized: {
            webView.loadFrameScript(Qt.resolvedUrl("../js/framescript.js"))
            webView.addMessageListener("anchorman:loaded")
            webView.addMessageListener("anchorman:page")
            webView.addMessageListener("anchorman:edge")
            webView.addMessageListener("anchorman:painted")
            page.start()
        }

        webView.onRecvAsyncMessage: page.handleMessage(message, data)


        // The WebView itself gets no touches: no links, no zooming, no text
        // selection. Swipes and taps are handled here.
        MouseArea {
            parent: flickable.webView
            anchors.fill: parent

            property real startX
            property real startY

            onPressed: {
                startX = mouse.x
                startY = mouse.y
                preventStealing = false
            }
            onPositionChanged: {
                // Claim a clearly horizontal swipe before Silica takes it;
                // vertical drags stay with the pulley.
                var dx = Math.abs(mouse.x - startX)
                if (!preventStealing && dx > Theme.startDragDistance / 3
                        && dx > Math.abs(mouse.y - startY)) {
                    preventStealing = true
                }
            }
            onReleased: {
                var dx = mouse.x - startX
                var dy = mouse.y - startY
                if (Math.abs(dx) > width / 8 && Math.abs(dx) > Math.abs(dy)) {
                    turn(dx < 0 ? 1 : -1)
                } else if (Math.abs(dx) < Theme.startDragDistance
                           && Math.abs(dy) < Theme.startDragDistance) {
                    if (mouse.x < width / 4)
                        turn(-1)
                    else if (mouse.x > width * 3 / 4)
                        turn(1)
                }
            }
        }
    }

    // Until a chapter is laid out and painted the WebView shows the book's
    // own white page; cover it. Gecko reports the paint (framescript.js);
    // measured 2 to 400 ms after the layout, so no fixed delay fits.
    Rectangle {
        anchors.fill: flickable
        color: pageColor
        visible: covered
    }

    Timer {
        id: uncoverTimer
        // Fallback should the paint never be reported.
        interval: 1000
        onTriggered: covered = false
    }

    Timer {
        id: paintedTimer
        // The paint reaches the screen a frame or two after Gecko reports it.
        interval: 50
        onTriggered: covered = false
    }
}
