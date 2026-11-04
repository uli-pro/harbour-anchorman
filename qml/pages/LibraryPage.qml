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
    property int searchSerial: 0
    property var defaultFolders: []

    // Python handles one call after the other: searching a memory card
    // first would delay the book read last. So that book opens first, and
    // the library is searched when it is shown.
    function start() {
        if (!app.pythonReady || resumed)
            return
        resumed = true
        py.call("anchorman.bridge.load_last_book", [app.positionsFile], function (path) {
            if (path)
                openBook(path, true)
            else
                search()
        })
    }

    function search() {
        var serial = ++searchSerial
        searching = true
        py.call("anchorman.bridge.default_folders", [StandardPaths.documents], function (folders) {
            if (serial !== searchSerial)
                return
            defaultFolders = folders
            var chosen = app.libraryFolder ? [app.libraryFolder] : folders
            py.call("anchorman.bridge.list_books", [chosen], function (books) {
                if (serial !== searchSerial)
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
                else if (!loaded)
                    search()
                return
            }
            py.call("anchorman.bridge.save_last_book", [app.positionsFile, path])
            pageStack.push(Qt.resolvedUrl("ReaderPage.qml"), { book: book },
                           resuming ? PageStackAction.Immediate : PageStackAction.Animated)
        })
    }

    // Searched once when first shown; again on Refresh or a new folder.
    onStatusChanged: {
        if (status === PageStatus.Activating && resumed && !loaded && !searching && !opening)
            search()
    }

    Component.onCompleted: start()

    Connections {
        target: app
        onPythonReadyChanged: page.start()
        onLibraryFolderChanged: page.search()
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
                onClicked: app.setLibraryFolder("")
            }
            MenuItem {
                text: qsTr("Refresh")
                onClicked: search()
            }
        }

        header: PageHeader {
            title: qsTr("Library")
            description: app.libraryFolder ? app.libraryFolder.replace(/\/+$/, "").split("/").pop()
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
            // The new setting starts a search.
            onAccepted: app.setLibraryFolder(selectedPath)
        }
    }
}
