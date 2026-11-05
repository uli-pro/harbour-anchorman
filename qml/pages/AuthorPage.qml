import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The books of one author: each series in order, then the other books.
Page {
    id: page

    property var library
    property string name
    // Entries of bridge.library_view, already in this order.
    property var books: []
    // Shown in the middle at first, e.g. the book found by a search.
    property string focusPath

    readonly property bool hasSeries: books.some(function (book) { return book.series !== "" })

    function detail(book) {
        var parts = []
        if (book.index !== null)
            //: Place of the book in its series, e.g. "Book 3"
            parts.push(qsTr("Book %1").arg(book.index.toLocaleString(Qt.locale(), "f",
                                                                     book.index % 1 ? 1 : 0)))
        if (book.duplicate)
            parts.push(book.removable ? qsTr("SD card") : qsTr("Device"))
        return parts.join(" · ")
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        opacity: library.opening ? 0.3 : 1
        enabled: !library.opening
        model: ListModel { id: rows }

        header: PageHeader {
            title: page.name || qsTr("Unknown author")
        }

        section.property: page.hasSeries ? "series" : ""
        section.delegate: SectionHeader {
            text: section || qsTr("Other books")
        }

        delegate: BookItem {
            book: page.books[model.bookIndex]
            detail: page.detail(book)
            onClicked: page.library.openBook(book.path, false)
        }

        VerticalScrollDecorator { }
    }

    BusyLabel {
        running: library.opening
        text: qsTr("Opening book")
    }

    Component.onCompleted: {
        var focusIndex = -1
        for (var i = 0; i < books.length; ++i) {
            rows.append({ bookIndex: i, series: books[i].series })
            if (books[i].path === focusPath)
                focusIndex = i
        }
        if (focusIndex >= 0)
            listView.positionViewAtIndex(focusIndex, ListView.Center)
    }
}
