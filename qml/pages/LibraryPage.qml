import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.Pickers 1.0
import "../components"

Page {
    id: page

    property bool loaded: false
    property bool opening: false
    property bool resumed: false
    property bool scanning: false
    // Only the answer to the latest scan counts.
    property int scanSerial: 0
    property var defaultFolders: []
    // From bridge.library_view: books in order, authors with their group.
    property var books: []
    property var authors: []
    property var recent: []
    property string filter: ""

    // Python handles one call after the other: reading the library first
    // would delay the book read last. So that book opens first, and the
    // library is read when it is shown.
    function start() {
        if (!app.pythonReady || resumed)
            return
        resumed = true
        py.setHandler("library", page.scanned)
        py.call("anchorman.bridge.load_last_book", [app.positionsFile], function (path) {
            if (path)
                openBook(path, true)
            else
                showLibrary()
        })
    }

    // At once from the cache, then the books are looked at again; on a
    // memory card that can take a minute.
    function showLibrary() {
        var serial = ++scanSerial
        scanning = true
        py.call("anchorman.bridge.default_folders", [StandardPaths.documents], function (folders) {
            if (serial !== scanSerial)
                return
            defaultFolders = folders
            var chosen = app.libraryFolder ? [app.libraryFolder] : folders
            py.call("anchorman.bridge.cached_library", [app.libraryCache, chosen], function (view) {
                if (serial !== scanSerial)
                    return
                setLibrary(view)
                py.call("anchorman.bridge.scan_library",
                        [chosen, app.libraryCache, app.coversFolder, serial])
            })
        })
    }

    function scanned(serial, view) {
        if (serial !== scanSerial)
            return
        scanning = false
        if (view.error) {
            console.warn("Cannot read the library", view.error, view.detail)
            loaded = true
            return
        }
        // Nothing new: the list stays where the reader scrolled it.
        if (!view.unchanged)
            setLibrary(view)
    }

    function setLibrary(view) {
        books = view.books
        authors = view.authors
        loaded = true
        fillRows()
        updateRecent()
    }

    function updateRecent() {
        py.call("anchorman.bridge.recent_books", [app.positionsFile], function (paths) {
            var found = []
            for (var i = 0; i < paths.length; ++i) {
                for (var j = 0; j < books.length; ++j) {
                    if (books[j].path === paths[i]) {
                        found.push(books[j])
                        break
                    }
                }
            }
            recent = found
        })
    }

    // Authors, or with a search the books that have every word in their
    // authors, title or series. Python folds the words as it folded the books
    // (ä → a, č → c); JavaScript in Qt 5.6 has no Unicode normalisation.
    function fillRows() {
        if (filter.trim() === "") {
            showRows([])
            return
        }
        var asked = filter
        py.call("anchorman.bridge.fold", [filter], function (folded) {
            if (asked === filter)
                showRows(folded.split(/\s+/).filter(function (w) { return w !== "" }))
        })
    }

    function showRows(words) {
        rows.clear()
        if (words.length === 0) {
            for (var i = 0; i < authors.length; ++i) {
                var author = authors[i]
                rows.append({ group: author.group, name: author.name, count: author.count,
                              letter: author.letter || "?", bookIndex: -1 })
            }
            return
        }
        for (var j = 0; j < books.length; ++j) {
            var book = books[j]
            var matches = words.every(function (w) { return book.search.indexOf(w) >= 0 })
            if (matches)
                rows.append({ group: book.group, name: book.author, count: 0, letter: "",
                              bookIndex: j })
        }
    }

    function showAuthor(group, focusPath) {
        var list = books.filter(function (book) { return book.group === group })
        pageStack.push(Qt.resolvedUrl("AuthorPage.qml"), {
            library: page, name: list.length > 0 ? list[0].author : "", books: list,
            focusPath: focusPath || ""
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
                    showLibrary()
                return
            }
            py.call("anchorman.bridge.save_last_book", [app.positionsFile, path])
            pageStack.push(Qt.resolvedUrl("ReaderPage.qml"), { book: book },
                           resuming ? PageStackAction.Immediate : PageStackAction.Animated)
        })
    }

    onStatusChanged: {
        if (status !== PageStatus.Activating || !resumed || opening)
            return
        // Read once when first shown; again on Refresh or a new folder.
        if (!loaded && !scanning)
            showLibrary()
        else
            updateRecent()
    }

    Component.onCompleted: start()

    Connections {
        target: app
        onPythonReadyChanged: page.start()
        onLibraryFolderChanged: page.showLibrary()
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        opacity: opening ? 0.3 : 1
        enabled: !opening
        model: ListModel { id: rows }

        PullDownMenu {
            busy: scanning

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
                onClicked: showLibrary()
            }
        }

        header: Column {
            width: listView.width

            PageHeader {
                title: qsTr("Library")
                description: app.libraryFolder ? app.libraryFolder.replace(/\/+$/, "").split("/").pop()
                                               : qsTr("Documents and memory cards")
            }

            SearchField {
                width: parent.width
                //: Search field of the library
                placeholderText: qsTr("Author, title or series")
                inputMethodHints: Qt.ImhNoPredictiveText
                onTextChanged: {
                    page.filter = text
                    searchTimer.restart()
                }
                EnterKey.iconSource: "image://theme/icon-m-enter-close"
                EnterKey.onClicked: focus = false
            }

            SectionHeader {
                visible: page.filter === "" && page.recent.length > 0
                text: qsTr("Continue reading")
            }

            Repeater {
                model: page.filter === "" ? page.recent : []

                BookItem {
                    width: listView.width
                    book: modelData
                    detail: modelData.author
                    onClicked: page.openBook(modelData.path, false)
                }
            }
        }

        section.property: page.filter === "" ? "letter" : ""
        section.delegate: SectionHeader {
            text: section === "?" ? qsTr("Unknown author") : section
        }

        // An author, or with a search a book.
        delegate: Item {
            width: listView.width
            height: model.bookIndex < 0 ? authorRow.height : bookRow.height

            BackgroundItem {
                id: authorRow

                visible: model.bookIndex < 0
                width: parent.width
                height: Theme.itemSizeSmall
                onClicked: page.showAuthor(model.group, "")

                Label {
                    x: Theme.horizontalPageMargin
                    width: parent.width - 2 * x - countLabel.width - Theme.paddingMedium
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.name || qsTr("Unknown author")
                    truncationMode: TruncationMode.Fade
                    color: authorRow.highlighted ? Theme.highlightColor : Theme.primaryColor
                }

                Label {
                    id: countLabel

                    anchors {
                        right: parent.right
                        rightMargin: Theme.horizontalPageMargin
                        verticalCenter: parent.verticalCenter
                    }
                    text: model.count
                    font.pixelSize: Theme.fontSizeSmall
                    color: authorRow.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
                }
            }

            BookItem {
                id: bookRow

                visible: model.bookIndex >= 0
                width: parent.width
                book: model.bookIndex >= 0 ? page.books[model.bookIndex] : null
                detail: model.name || qsTr("Unknown author")
                onClicked: page.showAuthor(model.group, book.path)
            }
        }

        ViewPlaceholder {
            enabled: page.loaded && !scanning && listView.count === 0
            text: page.filter !== "" ? qsTr("Nothing found") : qsTr("No books")
            hintText: page.filter !== "" ? ""
                      : qsTr("Copy EPUB books to Documents or a memory card, or choose another book folder in the pulley menu")
        }

        VerticalScrollDecorator { }
    }

    // Typing fast filters once, not for every letter.
    Timer {
        id: searchTimer
        interval: 250
        onTriggered: page.fillRows()
    }

    BusyLabel {
        running: opening
        text: qsTr("Opening book")
    }

    BusyLabel {
        running: scanning && !opening && listView.count === 0
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
