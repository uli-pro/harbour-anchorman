import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    // [{title, level, spine, fragment}]; in an audiobook also start, the
    // time in the book in ms, shown beside the title.
    property var toc: []
    property int currentChapter: -1

    signal selected(int chapter, string fragment)

    // "1:02:03", or "2:03" below an hour.
    function clock(ms) {
        var s = Math.floor(ms / 1000)
        var h = Math.floor(s / 3600)
        var m = Math.floor(s / 60) % 60
        s = s % 60
        return (h > 0 ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: toc

        // The current chapter in the middle; an audiobook may have hundreds.
        Component.onCompleted: {
            for (var i = 0; i < toc.length; ++i) {
                if (toc[i].spine === page.currentChapter) {
                    positionViewAtIndex(i, ListView.Center)
                    break
                }
            }
        }

        header: PageHeader {
            title: qsTr("Contents")
        }

        delegate: ListItem {
            // Headings without a link, or links to files outside the
            // reading order, cannot be opened.
            enabled: modelData.spine >= 0

            Label {
                x: Theme.horizontalPageMargin + Math.min(modelData.level, 4) * Theme.paddingLarge
                width: parent.width - x - Theme.horizontalPageMargin
                       - (timeLabel.visible ? timeLabel.width + Theme.paddingMedium : 0)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.title
                // Text from the book, never markup.
                textFormat: Text.PlainText
                truncationMode: TruncationMode.Fade
                color: !parent.enabled ? Theme.secondaryColor
                     : (highlighted || modelData.spine === page.currentChapter)
                       ? Theme.highlightColor : Theme.primaryColor
            }

            Label {
                id: timeLabel

                visible: modelData.start !== undefined
                anchors {
                    right: parent.right
                    rightMargin: Theme.horizontalPageMargin
                    verticalCenter: parent.verticalCenter
                }
                text: visible ? page.clock(modelData.start) : ""
                font.pixelSize: Theme.fontSizeSmall
                color: highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
            }

            onClicked: {
                page.selected(modelData.spine, modelData.fragment)
                pageStack.pop()
            }
        }

        ViewPlaceholder {
            enabled: listView.count === 0
            text: qsTr("No table of contents")
        }

        VerticalScrollDecorator { }
    }
}
