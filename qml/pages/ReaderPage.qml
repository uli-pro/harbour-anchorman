import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebView 1.0
import "../components"

WebViewPage {
    id: page

    property var book
    // chapter is the one in the WebView; requested the one being prepared.
    property int chapter: -1
    property int requested: -1
    property var sentenceIds: []
    // The clips of the chapter in the view, for starting playback there.
    property var sentenceClips: []
    property var pendingTarget: null
    property string loadingUrl: ""
    // Messages from the frame script carry the serial of their layout, so
    // late messages about a previous chapter are recognised and dropped.
    property int serial: 0
    property bool ready: false
    property bool covered: true
    // The settings of the last layout; another layout follows if they
    // changed while one was under way.
    property string laidOut: ""
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
    // Chosen in the pulley; until then as the ambience.
    readonly property bool lightPage: app.pageColors === "light"
                                      || (app.pageColors === "" && Theme.colorScheme === Theme.DarkOnLight)
    readonly property color pageColor: lightPage ? "white" : "black"

    // Listening. The bar appears with playback and goes when the reader
    // turns pages while paused.
    property bool barShown: false
    // The sentence spoken (or paused at), marked in the chapter's layouts.
    property string highlightId: ""
    // Further pages of the sentence spoken: [{page, share}], see framescript.js.
    property var splits: []
    // The next chapter with audio, read ahead: {after, chapter, clips};
    // chapter -1 at the end of the book.
    property var upcoming: null
    // Sentence heard last before the book was closed; Play resumes there.
    property string resumeId: ""
    readonly property bool listening: player.active && player.chapter === chapter
    readonly property bool playing: player.playing
    readonly property bool hasAudio: book.spine.some(function (item) { return !!item.overlay })
    // For the lock screen and headphone controls.
    readonly property string coverUrl: book.cover ? player.fileUrl(book.cover) : ""
    property double savedAt: 0
    // Left for the library: the page is going, and must neither lay out
    // nor save again (it would save the top of the page over the sentence).
    property bool closed: false

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
            if (pos && pos.spine < book.spine.length) {
                if (pos.heard)
                    resumeId = pos.id
                loadChapter(pos.spine, { id: pos.id, fraction: pos.fraction })
            } else
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
            show(index, [], [], target)
            return
        }
        py.call("anchorman.bridge.read_chapter", [book.root, item.path, item.overlay], function (result) {
            if (typeof page === "undefined" || !page || requested !== index)
                return  // page closed, or another chapter was asked for meanwhile
            if (result.error) {
                // The text can still be read without sentences.
                console.warn("Cannot read overlay", item.overlay, result.error, result.detail)
                show(index, [], [], target)
            } else {
                show(index, result.ids, result.sentences, target)
            }
        })
    }

    function show(index, ids, clips, target) {
        chapter = index
        requested = -1
        sentenceIds = ids
        sentenceClips = clips
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

    function layoutSettings() {
        return [app.fontSize, app.fontFamily, app.lineHeight, app.paragraphSpacing,
                barShown, lightPage].join("|")
    }

    function layout(target) {
        laidOut = layoutSettings()
        // From lightPage itself: the palette and pageColor may still hold
        // the old colours while lightPage changes (seen on the device).
        var light = lightPage
        // While listening the page shows the sentence spoken; paused, it
        // stays where the reader is.
        if (listening && player.playing && highlightId)
            target = { id: highlightId }
        flickable.webView.sendAsyncMessage("anchorman:layout", {
            serial: serial,
            ids: sentenceIds,
            target: target,
            highlight: listening ? highlightId : "",
            // The ambience's colour; the light palette gives the same.
            activeColor: cssColor(Theme.highlightBackgroundColor, 0.3),
            margin: 24,
            marginTop: 4,
            marginBottom: 12,
            // The bar must not cover the text read along.
            barHeight: barShown ? bar.height : 0,
            fontSize: app.fontSize,
            fontFamily: app.fontFamily === "serif" ? "serif" : "sans-serif",
            lineHeight: app.lineHeight,
            paragraphSpacing: app.paragraphSpacing,
            color: light ? "black" : "white",
            background: light ? "white" : "black"
        })
    }

    // Same chapter and sentence, new text size. While a layout is under way
    // the "page" message calls this again if the size has changed meanwhile.
    function relayout() {
        if (!ready || closed)
            return
        serial++
        ready = false
        covered = true
        // The fallback of the layout before must not uncover this one.
        uncoverTimer.stop()
        charsPerPage = 0
        // Page numbers of the old layout no longer fit.
        splits = []
        if (listening)
            player.setMarks([])
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
            if (data.textScale > 0)
                app.setTextScale(data.textScale)
            ready = true
            if (covered && !uncoverTimer.running)
                uncoverTimer.restart()
            pageIndex = data.page
            pageCount = data.pages
            firstId = data.firstId
            fraction = data.fraction
            updateBookPages()
            savePosition()
            if (laidOut !== layoutSettings())
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
        case "anchorman:highlighted":
            if (data.serial !== serial || data.id !== player.currentId || !listening)
                return
            splits = data.splits
            var clip = player.clips[player.index]
            if (player.hasEnd(clip)) {
                player.setMarks(splits.map(function (split) {
                    return clip.begin + split.share * (clip.end - clip.begin)
                }))
            }
            break
        case "anchorman:hit":
            if (data.serial !== serial)
                return
            if (data.id)
                playSentence(data.id)
            else if (!player.playing)
                playFromPage()
            break
        case "anchorman:start":
            if (data.serial !== serial)
                return
            if (data.id) {
                playSentence(data.id)
            } else {
                // Nothing to hear on this page: the next chapter with audio.
                fetchAudioChapter(chapter, function (index, clips) {
                    if (index >= 0)
                        startPlayer(index, clips, 0)
                })
            }
            break
        }
    }

    function nextAudio(from) {
        for (var i = from + 1; i < book.spine.length; ++i) {
            if (book.spine[i].linear && book.spine[i].overlay)
                return i
        }
        return -1
    }

    // Calls back with the next chapter after from that has clips, or -1.
    function fetchAudioChapter(from, callback) {
        var index = nextAudio(from)
        if (index < 0) {
            callback(-1, [])
            return
        }
        var item = book.spine[index]
        py.call("anchorman.bridge.read_chapter", [book.root, item.path, item.overlay], function (result) {
            if (typeof page === "undefined" || !page)
                return
            if (result.error || result.sentences.length === 0)
                fetchAudioChapter(index, callback)
            else
                callback(index, result.sentences)
        })
    }

    // The player first, then the bar: showing the bar lays the chapter out
    // again, around the sentence the player has just begun.
    function stopPlayer() {
        player.stop()
        barShown = false
        highlightId = ""
    }

    function startPlayer(index, clips, i, offset) {
        resumeId = ""
        player.start(index, clips, i, offset)
        barShown = true
    }

    function playSentence(id) {
        if (listening && player.currentId === id && !player.playing) {
            // The sentence paused at: on from where it stopped.
            player.resume()
            barShown = true
            return
        }
        for (var i = 0; i < sentenceClips.length; ++i) {
            if (sentenceClips[i].id === id) {
                startPlayer(chapter, sentenceClips, i)
                return
            }
        }
    }

    function playFromPage() {
        if (!ready || !hasAudio)
            return
        var prefer = player.active ? (listening ? player.currentId : "") : resumeId
        flickable.webView.sendAsyncMessage("anchorman:startSentence", { prefer: prefer })
    }

    function hit(x, y) {
        flickable.webView.sendAsyncMessage("anchorman:hitTest", { x: x, y: y })
    }

    function togglePlay() {
        if (player.playing)
            pause()
        else
            play()
    }

    // Paused while listening: on where it stopped, without a round trip to
    // the page, which nobody looks at on the lock screen. Otherwise from the
    // page shown.
    function play() {
        // Closing: the page stays until its animation ends.
        if (player.playing || closed || !hasAudio)
            return
        if (player.active && barShown)
            player.resume()
        else
            playFromPage()
    }

    function pause() {
        if (!player.playing)
            return
        player.pause()
        savePosition()
    }

    // Only while listening: paused and turned away, a sentence would pull
    // the page back.
    function nextSentence() {
        if (barShown)
            player.next()
    }

    function previousSentence() {
        if (barShown)
            player.previous()
    }

    function followSentence(index, i) {
        highlightId = player.clips[i].id
        splits = []
        if (index !== chapter && index !== requested)
            loadChapter(index, { id: highlightId })
        else if (index === chapter)
            // Also during a layout: the frame script takes messages in order,
            // and ignores this one if a new chapter is still loading.
            flickable.webView.sendAsyncMessage("anchorman:highlight", { id: highlightId })
        // Pages change rarely while listening; save now and then.
        if (Date.now() - savedAt > 20000)
            savePosition()
        if (!upcoming || upcoming.after !== index) {
            upcoming = { after: index, chapter: -2 }
            fetchAudioChapter(index, function (next, clips) {
                if (upcoming && upcoming.after === index)
                    upcoming = { after: index, chapter: next, clips: clips }
                handOver()
            })
        }
    }

    // The player finished a chapter; give it the next one when it is read.
    function handOver() {
        if (!player.waiting || !upcoming || upcoming.after !== player.chapter
                || upcoming.chapter === -2)
            return
        if (upcoming.chapter < 0) {
            savePosition()
            stopPlayer()  // end of the book
        } else {
            player.continueWith(upcoming.chapter, upcoming.clips)
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
        if (!ready)
            return
        // Paused and turning pages: reading, not listening.
        if (player.active && !player.playing)
            barShown = false
        resumeId = ""
        flickable.webView.sendAsyncMessage("anchorman:turn", { delta: delta })
    }

    function savePosition() {
        if (chapter < 0 || closed)
            return
        savedAt = Date.now()
        // The sentence heard, unless the reader paused and turned away; or
        // the one heard before the book was closed, until pages are turned.
        var heardId = listening && (player.playing || barShown) ? player.currentId
                    : !player.active ? resumeId : ""
        py.call("anchorman.bridge.save_position",
                [app.positionsFile, book.key, { spine: chapter, id: heardId || firstId,
                                                fraction: fraction, heard: heardId !== "" }],
                function (result) {
                    if (result !== true)
                        console.warn("Cannot save position", result.error, result.detail)
                })
    }

    Connections {
        target: app
        // Leaving the settings stores several at once: one layout for all.
        onFontSizeChanged: settingsTimer.restart()
        onFontFamilyChanged: settingsTimer.restart()
        onLineHeightChanged: settingsTimer.restart()
        onParagraphSpacingChanged: settingsTimer.restart()
    }

    onBarShownChanged: relayout()
    onLightPageChanged: relayout()

    // Silica items inside take their colours from this palette.
    palette.colorScheme: lightPage ? Theme.DarkOnLight : Theme.LightOnDark

    // Closing the app gives no further chance to save.
    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state !== Qt.ApplicationActive)
                page.savePosition()
        }
    }

    Component.onCompleted: app.reader = page
    Component.onDestruction: {
        if (app.reader === page)
            app.reader = null
    }

    Player {
        id: player

        root: book.root
        rate: app.playbackRate
        onSentence: page.followSentence(chapter, index)
        onFinished: page.handOver()
        onMarked: {
            if (n < page.splits.length)
                flickable.webView.sendAsyncMessage("anchorman:show", { page: page.splits[n].page })
        }
        onFailed: {
            page.stopPlayer()
            app.showError(qsTr("The narration could not be played."))
        }
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
            color: palette.secondaryColor
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
            color: palette.secondaryColor
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
                text: qsTr("Library")
                onClicked: {
                    savePosition()
                    closed = true
                    stopPlayer()
                    pageStack.pop()
                }
            }
            MenuItem {
                text: qsTr("Settings")
                onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
            }
            MenuItem {
                text: qsTr("Contents")
                onClicked: {
                    var toc = pageStack.push(Qt.resolvedUrl("TocPage.qml"),
                                             { toc: book.toc, currentChapter: chapter })
                    toc.selected.connect(function (index, fragment) {
                        resumeId = ""
                        // A jump away from the sentence spoken: listening
                        // would pull the page back at once.
                        if (player.playing) {
                            player.pause()
                            savePosition()
                        }
                        // As when turning pages: reading now, not listening.
                        if (player.active)
                            barShown = false
                        loadChapter(index, fragment ? { id: fragment } : { fraction: 0 })
                    })
                }
            }
            MenuItem {
                text: lightPage ? qsTr("Dark page") : qsTr("Light page")
                // After the pulley has closed: the new layout covers the page.
                onDelayedClick: app.setPageColors(lightPage ? "dark" : "light")
            }
            MenuItem {
                visible: !barShown && hasAudio
                text: qsTr("Play")
                onClicked: playFromPage()
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
            webView.addMessageListener("anchorman:highlighted")
            webView.addMessageListener("anchorman:hit")
            webView.addMessageListener("anchorman:start")
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
                    else if (ready)
                        hit(mouse.x / width, mouse.y / height)
                }
            }
        }
    }

    Rectangle {
        id: bar

        anchors.bottom: parent.bottom
        width: parent.width
        height: Theme.itemSizeMedium
        color: pageColor
        visible: barShown

        // Taps beside the buttons must not reach the page below.
        MouseArea {
            anchors.fill: parent
        }

        Row {
            anchors.centerIn: parent
            spacing: Theme.paddingLarge

            IconButton {
                icon.source: "image://theme/icon-m-previous"
                onClicked: player.previous()
            }
            IconButton {
                icon.source: player.playing ? "image://theme/icon-m-pause" : "image://theme/icon-m-play"
                onClicked: togglePlay()
            }
            IconButton {
                icon.source: "image://theme/icon-m-next"
                onClicked: player.next()
            }
            BackgroundItem {
                width: Theme.itemSizeMedium
                height: Theme.itemSizeSmall
                anchors.verticalCenter: parent.verticalCenter
                onClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))

                Label {
                    anchors.centerIn: parent
                    color: parent.highlighted ? palette.highlightColor : palette.primaryColor
                    //: Playback speed on the button that opens the settings, e.g. "1.25×"
                    text: qsTr("%1×").arg(Number(app.playbackRate).toLocaleString(Qt.locale(), "f", 2))
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
        id: settingsTimer
        interval: 0
        onTriggered: page.relayout()
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
