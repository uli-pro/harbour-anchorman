import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0

Page {
    id: page

    property bool loaded: false
    property bool opening: false
    property bool resumed: false
    property bool searching: false
    // Only the answer to the latest search counts.
    property int search: 0
    property var defaultFolders: []

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
        var serial = ++search
        searching = true
        py.call("anchorman.bridge.default_folders", [StandardPaths.documents], function (folders) {
            if (serial !== search)
                return
            defaultFolders = folders
            var chosen = app.libraryFolder ? [app.libraryFolder] : folders
            py.call("anchorman.bridge.list_books", [chosen], function (books) {
                if (serial !== search)
                    return
                listView.model = books
                loaded = true
                searching = false
            })
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

        PullDownMenu {
            busy: searching

            MenuItem {
                text: qsTr("Book folder")
                onClicked: pageStack.push(folderPicker, {
                    path: app.libraryFolder || defaultFolders[defaultFolders.length - 1]
                          || StandardPaths.documents
                })
            }
            MenuItem {
                visible: app.libraryFolder !== ""
                text: qsTr("All folders")
                onClicked: {
                    app.setLibraryFolder("")
                    refresh()
                }
            }
            MenuItem {
                text: qsTr("Refresh")
                onClicked: refresh()
            }
        }

        header: PageHeader {
            title: qsTr("Library")
            description: app.libraryFolder ? app.libraryFolder.split("/").pop()
                                           : qsTr("Documents and memory cards")
        }

        delegate: ListItem {
            contentHeight: Theme.itemSizeMedium

            Column {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                anchors.verticalCenter: parent.verticalCenter

                Label {
                    width: parent.width
                    text: modelData.name
                    truncationMode: TruncationMode.Fade
                    color: highlighted ? Theme.highlightColor : Theme.primaryColor
                }
                Label {
                    // Tells two copies of a book apart.
                    text: modelData.removable ? qsTr("SD card") : qsTr("Device")
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                }
            }

            onClicked: page.openBook(modelData.path, false)
        }

        ViewPlaceholder {
            enabled: page.loaded && !searching && listView.count === 0
            text: qsTr("No books")
            hintText: qsTr("Copy EPUB readalouds with narration to Documents or a memory card, or choose another book folder in the pulley menu")
        }

        VerticalScrollDecorator { }
    }

    BusyLabel {
        running: opening
        text: qsTr("Opening book")
    }

    BusyLabel {
        running: searching && !opening && listView.count === 0
        text: qsTr("Searching for books")
    }

    Component {
        id: folderPicker

        FolderPickerDialog {
            title: qsTr("Book folder")
            // The library page is activated afterwards and searches anew.
            onAccepted: app.setLibraryFolder(selectedPath)
        }
    }
}
