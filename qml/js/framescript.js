// Runs inside the WebView's content process. Reports taps on sentences to QML.

addEventListener("DOMContentLoaded", function () {
    var doc = content.document

    if (!doc.querySelector("meta[name=viewport]")) {
        var viewport = doc.createElement("meta")
        viewport.name = "viewport"
        viewport.content = "width=device-width, initial-scale=1"
        doc.head.appendChild(viewport)
    }

    doc.addEventListener("click", function (event) {
        // Book links (e.g. wrapped images) must not navigate away from the chapter.
        event.preventDefault()
        var node = event.target
        while (node && node.nodeType === 1) {
            if (node.id && /-s\d+$/.test(node.id)) {
                sendAsyncMessage("anchorman:tap", { "id": node.id, "time": Date.now() })
                return
            }
            node = node.parentNode
        }
        sendAsyncMessage("anchorman:tap", { "id": "", "time": Date.now() })
    }, true)
})
