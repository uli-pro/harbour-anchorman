import QtQuick 2.0
import Sailfish.Silica 1.0

// The cover of a library book, taken out of the EPUB when first shown.
Item {
    id: coverItem

    // An entry of bridge.library_view.
    property var book
    property string file: ""

    // A cover not yet taken out of the book comes later, as app.coverReady.
    function load() {
        file = ""
        if (!book || !book.cover)
            return
        var key = book.key
        py.call("anchorman.bridge.request_cover", [book.path, book.cover, key, app.coversFolder],
                function (result) {
            // The delegate may have been destroyed or given another book.
            if (typeof coverItem === "undefined" || !coverItem || !coverItem.book
                    || coverItem.book.key !== key)
                return
            if (result)
                coverItem.file = result
        })
    }

    onBookChanged: load()

    Connections {
        target: app
        onCoverReady: {
            if (coverItem.book && coverItem.book.key === key)
                coverItem.file = file
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: image.status !== Image.Ready
        color: Theme.rgba(Theme.highlightBackgroundColor, Theme.opacityFaint)

        Icon {
            anchors.centerIn: parent
            source: "image://theme/icon-m-document"
        }
    }

    Image {
        id: image

        anchors.fill: parent
        source: file ? "file://" + file.split("/").map(encodeURIComponent).join("/") : ""
        sourceSize.width: width
        sourceSize.height: height
        fillMode: Image.PreserveAspectFit
        asynchronous: true
    }
}
