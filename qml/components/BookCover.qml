import QtQuick 2.0
import Sailfish.Silica 1.0

// The cover of a library book, taken out of the EPUB when first shown.
Item {
    id: coverItem

    // An entry of bridge.library_view.
    property var book
    property string file: ""

    function load() {
        file = ""
        if (!book || !book.cover)
            return
        var path = book.path
        py.call("anchorman.bridge.cover", [book.path, book.cover, book.key, app.coversFolder],
                function (result) {
            // The delegate may have been reused or destroyed meanwhile.
            if (typeof coverItem === "undefined" || !coverItem || !coverItem.book
                    || coverItem.book.path !== path)
                return
            coverItem.file = result
        })
    }

    onBookChanged: load()

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
