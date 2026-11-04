import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebView 1.0

// Prototype: measures what the WebView can do for Anchorman. Not for merging.
WebViewPage {
    id: page

    property string chapterUrl: "file://" + StandardPaths.data + "/proto/7505960986668825248_902-h-1.htm.xhtml"
    property var sentences: []
    property int sentenceIndex: -1
    property double loadStart: 0
    property var highlightTimes: []
    property string status: ""

    function cssColor(c, alpha) {
        return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + ","
                + Math.round(c.b * 255) + "," + (alpha === undefined ? c.a : alpha) + ")"
    }

    function readFile(url) {
        var xhr = new XMLHttpRequest()
        xhr.open("GET", url, false)
        xhr.send()
        return xhr.responseText
    }

    function injectReader() {
        var options = {
            color: cssColor(Theme.primaryColor),
            background: Theme.colorScheme === Theme.LightOnDark ? "black" : "white",
            highlight: cssColor(Theme.highlightBackgroundColor, 0.5),
            margin: 24,
            marginTop: 48,
            fontSize: 18
        }
        var source = readFile(Qt.resolvedUrl("../js/reader.js"))
                .split("__OPTIONS__").join(JSON.stringify(options))
        var start = Date.now()
        webView.runJavaScript("return (" + source + ")", function (result) {
            sentences = result.sentences
            status = "Loaded " + (start - loadStart) + " ms, inject " + (Date.now() - start)
                    + " ms. Page " + (result.page + 1) + "/" + result.pages
                    + ", " + sentences.length + " sentences"
        }, function (error) {
            status = "Inject failed: " + error
        })
    }

    function run(script, onResult) {
        var start = Date.now()
        webView.runJavaScript("return " + script, function (result) {
            onResult(result, Date.now() - start)
        }, function (error) {
            status = "Error: " + error
        })
    }

    function nextSentence() {
        if (sentenceIndex + 1 >= sentences.length) {
            autoTimer.stop()
            return
        }
        sentenceIndex++
        run("anchorman.highlight(" + JSON.stringify(sentences[sentenceIndex]) + ")", function (r, ms) {
            highlightTimes.push(ms)
            status = sentences[sentenceIndex] + ": round trip " + ms + " ms, in page "
                    + r.ms.toFixed(1) + " ms. Page " + (r.page + 1) + "/" + r.pages
        })
    }

    function timeSummary() {
        if (highlightTimes.length === 0)
            return ""
        var sum = 0, max = 0
        for (var i = 0; i < highlightTimes.length; ++i) {
            sum += highlightTimes[i]
            max = Math.max(max, highlightTimes[i])
        }
        return highlightTimes.length + " highlights: mean " + (sum / highlightTimes.length).toFixed(1)
                + " ms, max " + max + " ms"
    }

    WebView {
        id: webView
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            bottom: toolbar.top
        }
        active: true

        Component.onCompleted: {
            loadStart = Date.now()
            url = chapterUrl
        }

        onViewInitialized: {
            loadFrameScript(Qt.resolvedUrl("../js/framescript.js"))
            addMessageListener("anchorman:tap")
        }

        onLoadedChanged: {
            if (loaded)
                injectReader()
        }

        onRecvAsyncMessage: {
            if (message !== "anchorman:tap")
                return
            var tapTime = data.time
            if (!data.id) {
                status = "Tap outside a sentence, " + (Date.now() - tapTime) + " ms"
                return
            }
            sentenceIndex = sentences.indexOf(data.id)
            var delivered = Date.now() - tapTime
            run("anchorman.highlight(" + JSON.stringify(data.id) + ")", function (r, ms) {
                status = "Tapped " + data.id + ": message " + delivered + " ms, highlight " + ms + " ms"
            })
        }
    }

    Column {
        id: toolbar
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * x
            text: status
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.highlightColor
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Theme.paddingSmall

            Button {
                width: Theme.itemSizeMedium
                text: "<"
                onClicked: run("anchorman.page(-1)", function (r, ms) {
                    status = "Page " + (r.page + 1) + "/" + r.pages + ", " + ms + " ms"
                })
            }
            Button {
                width: Theme.itemSizeMedium
                text: ">"
                onClicked: run("anchorman.page(1)", function (r, ms) {
                    status = "Page " + (r.page + 1) + "/" + r.pages + ", " + ms + " ms"
                })
            }
            Button {
                width: Theme.itemSizeLarge
                text: "Next"
                onClicked: nextSentence()
            }
            Button {
                width: Theme.itemSizeLarge
                text: autoTimer.running ? "Stop" : "Auto"
                onClicked: {
                    if (autoTimer.running) {
                        autoTimer.stop()
                        status = timeSummary()
                    } else {
                        highlightTimes = []
                        autoTimer.start()
                    }
                }
            }
            Button {
                width: Theme.itemSizeLarge
                text: "First"
                onClicked: run("anchorman.firstSentenceOnPage()", function (id, ms) {
                    status = "First sentence on page: " + id + ", " + ms + " ms"
                    if (id) {
                        sentenceIndex = sentences.indexOf(id)
                        run("anchorman.highlight(" + JSON.stringify(id) + ")", function () {})
                    }
                })
            }
        }
    }

    Timer {
        id: autoTimer
        interval: 300
        repeat: true
        onTriggered: nextSentence()
        onRunningChanged: if (!running && highlightTimes.length) status = timeSummary()
    }
}
