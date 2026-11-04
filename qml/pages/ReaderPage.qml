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
    property int pageIndex: 0
    property int pageCount: 0
    property string firstId: ""
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
            flickable.webView.sendAsyncMessage("anchorman:layout", {
                serial: serial,
                ids: sentenceIds,
                target: pendingTarget,
                margin: 24,
                marginTop: 40,
                fontSize: 18,
                lineHeight: 1.3,
                color: cssColor(Theme.primaryColor, 1),
                background: cssColor(pageColor, 1)
            })
            pendingTarget = null
            break
        case "anchorman:page":
            if (data.serial !== serial)
                return
            ready = true
            if (covered)
                uncoverTimer.restart()
            pageIndex = data.page
            pageCount = data.pages
            firstId = data.firstId
            fraction = data.fraction
            savePosition()
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

    WebViewFlickable {
        id: flickable

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: bar.top
        }

        PullDownMenu {
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
        // WebViewFlickable assumes the page fills the screen; with the bar
        // below, 100vh would reach under it.
        webView.viewportHeight: flickable.height

        webView.onViewInitialized: {
            webView.loadFrameScript(Qt.resolvedUrl("../js/framescript.js"))
            webView.addMessageListener("anchorman:loaded")
            webView.addMessageListener("anchorman:page")
            webView.addMessageListener("anchorman:edge")
            page.start()
        }

        webView.onRecvAsyncMessage: page.handleMessage(message, data)

        // Until a chapter is laid out and painted the WebView shows a white
        // page; cover it. The layout is reported a moment before the paint.
        Rectangle {
            parent: flickable.webView
            anchors.fill: parent
            color: pageColor
            visible: covered
        }

        Timer {
            id: uncoverTimer
            interval: 150
            onTriggered: covered = false
        }

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

    Item {
        id: bar

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }
        height: Theme.itemSizeExtraSmall

        Label {
            anchors.centerIn: parent
            width: parent.width - 2 * Theme.horizontalPageMargin
            horizontalAlignment: Text.AlignHCenter
            truncationMode: TruncationMode.Fade
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            visible: ready
            //: Position in the book, e.g. "Chapter 3/12 · Page 4/26"
            text: qsTr("Chapter %1/%2 · Page %3/%4").arg(chapter + 1).arg(book.spine.length)
                  .arg(pageIndex + 1).arg(pageCount)
        }
    }
}
