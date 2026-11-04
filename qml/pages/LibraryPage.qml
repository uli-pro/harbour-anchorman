import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property bool loaded: false
    property bool opening: false
    property bool resumed: false

    function refresh() {
        if (!app.pythonReady)
            return
        if (!resumed) {
            resumed = true
            // Start with the book read last, like closing and opening a book.
            py.call("anchorman.bridge.load_last_book", [app.positionsFile], function (path) {
                if (path)
                    openBook(path, true)
            })
        }
        py.call("anchorman.bridge.list_books", [[app.libraryFolder]], function (books) {
            listView.model = books
            loaded = true
        })
    }

    // resuming: the app is starting; no message if the book cannot be opened.
    function openBook(path, resuming) {
        opening = true
        py.call("anchorman.bridge.open_book", [path, app.cacheFolder], function (book) {
            opening = false
            if (book.error) {
                console.warn("Cannot open", path, book.error, book.detail)
                if (!resuming)
                    app.showError(app.errorText(book.error))
                return
            }
            py.call("anchorman.bridge.save_last_book", [app.positionsFile, path])
            pageStack.push(Qt.resolvedUrl("ReaderPage.qml"), { book: book },
                           resuming ? PageStackAction.Immediate : PageStackAction.Animated)
        })
    }

    onStatusChanged: {
        if (status === PageStatus.Activating)
            refresh()
    }

    Connections {
        target: app
        onPythonReadyChanged: page.refresh()
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        opacity: opening ? 0.3 : 1
        enabled: !opening

        header: PageHeader {
            title: qsTr("Library")
        }

        delegate: ListItem {
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.name
                truncationMode: TruncationMode.Fade
                color: highlighted ? Theme.highlightColor : Theme.primaryColor
            }

            onClicked: page.openBook(modelData.path, false)
        }

        ViewPlaceholder {
            enabled: page.loaded && listView.count === 0
            text: qsTr("No books")
            //: %1 is a folder name
            hintText: qsTr("Copy EPUB readalouds to %1").arg("Documents/Readalouds")
        }

        VerticalScrollDecorator { }
    }

    BusyLabel {
        running: opening
        text: qsTr("Opening book")
    }
}
