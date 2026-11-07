import QtQuick 2.0
import Sailfish.Silica 1.0

// Search in the open book: every paragraph holding all words typed.
Page {
    id: page

    property string root
    // The reader's place: {spine, id, fraction, heard}, see ReaderPage.here().
    property var here
    // The words searched last in this book, shown again.
    property string initialQuery: ""
    property int serial: 0
    property string query: ""
    property bool searching: false
    // {hits, total, before} of the last search, see search.py, and its words.
    property var result: null
    property string resultQuery: ""
    property string searchedQuery: ""

    // The hits and the one chosen, for going from hit to hit in the book.
    signal selected(var hits, int index, string query)

    // Hits in reading order, with a line where the reader's place is. A
    // ListModel, not an array: a new array resets the list's current item,
    // which then takes the focus from the search field.
    function fillRows() {
        rows.clear()
        if (!result || !result.hits)
            return
        var hits = result.hits
        for (var i = 0; i < hits.length; ++i) {
            if (i === result.before)
                rows.append({ here: true, html: "", chapter: "", hit: -1 })
            rows.append({ here: false, html: snippetText(hits[i].snippet), hit: i,
                          //: Chapter of a search hit without a title, e.g. "Chapter 12"
                          chapter: hits[i].chapter || qsTr("Chapter %1").arg(hits[i].spine + 1) })
        }
        // The place after the last hit; not if hits after it were left out.
        if (hits.length > 0 && result.before === hits.length && result.total === hits.length)
            rows.append({ here: true, html: "", chapter: "", hit: -1 })
    }

    function escaped(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    // The words of the book are plain text; only our own tags mark them.
    function snippetText(parts) {
        var color = Theme.highlightColor
        return parts.map(function (part) {
            var text = escaped(part.text)
            return part.match ? "<font color=\"" + color + "\"><b>" + text + "</b></font>" : text
        }).join("")
    }

    function search() {
        var text = query.trim()
        serial = ++app.searchSerial
        if (text.length < 2) {
            searching = false
            result = null
            fillRows()
            return
        }
        searching = true
        searchedQuery = text
        py.call("bookfish.bridge.search", [root, text, here, serial])
    }

    Component.onCompleted: py.call("bookfish.bridge.prepare_search", [root])
    onStatusChanged: {
        if (status === PageStatus.Active && query === "")
            listView.headerItem.field.forceActiveFocus()
    }

    Connections {
        target: app
        onSearchFinished: {
            if (serial !== page.serial)
                return
            searching = false
            if (result.error) {
                page.result = null
                app.showError(app.errorText(result.error))
            } else {
                page.result = result
                resultQuery = searchedQuery
            }
            fillRows()
        }
    }

    Timer {
        id: typingTimer
        interval: 300
        onTriggered: page.search()
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: ListModel { id: rows }
        // Otherwise the current item takes the focus from the search field
        // whenever the hits change.
        currentIndex: -1

        header: Column {
            property alias field: field

            width: listView.width

            PageHeader {
                //: Title of the page for searching the book
                title: qsTr("Find")
            }

            SearchField {
                id: field
                width: parent.width
                //: Placeholder of the search field
                placeholderText: qsTr("Words in the book")
                inputMethodHints: Qt.ImhNoPredictiveText
                Component.onCompleted: text = page.initialQuery
                onTextChanged: {
                    page.query = text
                    typingTimer.restart()
                }
                EnterKey.iconSource: "image://theme/icon-m-enter-close"
                EnterKey.onClicked: focus = false
            }
        }

        delegate: ListItem {
            id: item

            contentHeight: model.here ? Theme.itemSizeExtraSmall
                                      : column.height + 2 * Theme.paddingMedium
            enabled: !model.here

            // The reader's place among the hits.
            SectionHeader {
                visible: model.here
                anchors.verticalCenter: parent.verticalCenter
                text: page.here && page.here.heard
                      //: Line in the search hits: hits below it have not been heard yet
                      ? qsTr("Last heard")
                      //: Line in the search hits: hits below it come after the page shown
                      : qsTr("Current page")
            }

            Column {
                id: column

                visible: !model.here
                x: Theme.horizontalPageMargin
                y: Theme.paddingMedium
                width: parent.width - 2 * x

                Label {
                    width: parent.width
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                    textFormat: Text.StyledText
                    text: model.html
                    color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                }

                Label {
                    width: parent.width
                    truncationMode: TruncationMode.Fade
                    font.pixelSize: Theme.fontSizeExtraSmall
                    color: Theme.secondaryColor
                    text: model.chapter
                    // Text from the book, never markup.
                    textFormat: Text.PlainText
                }
            }

            onClicked: {
                // The reader lays the chapter out for the full height.
                Qt.inputMethod.hide()
                page.selected(result.hits, model.hit, resultQuery)
                pageStack.pop()
            }
        }

        footer: Label {
            x: Theme.horizontalPageMargin
            width: listView.width - 2 * x
            height: visible ? implicitHeight + 2 * Theme.paddingLarge : 0
            verticalAlignment: Text.AlignVCenter
            visible: !!result && result.total > result.hits.length
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.secondaryHighlightColor
            //: Shown below a cut-off list of search hits, e.g. "200 of 1534 hits. Add a word to narrow them down."
            text: result ? qsTr("%1 of %2 hits. Add a word to narrow them down.")
                           .arg(result.hits.length).arg(result.total) : ""
        }

        ViewPlaceholder {
            enabled: !searching && rows.count === 0
            text: query.trim().length < 2
                  //: Hint on the empty search page
                  ? qsTr("Type words from the book")
                  //: The search found nothing
                  : qsTr("Nothing found")
            hintText: query.trim().length < 2
                      //: How the search works
                      ? qsTr("Finds paragraphs holding all words, in any order")
                      : ""
        }

        BusyIndicator {
            anchors.horizontalCenter: parent.horizontalCenter
            y: page.height / 2
            size: BusyIndicatorSize.Large
            running: searching && rows.count === 0
        }

        VerticalScrollDecorator { }
    }
}
