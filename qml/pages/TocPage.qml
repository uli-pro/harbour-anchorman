import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    property var toc: []
    property int currentChapter: -1

    signal selected(int chapter, string fragment)

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: toc

        header: PageHeader {
            title: qsTr("Contents")
        }

        delegate: ListItem {
            // Headings without a link, or links to files outside the
            // reading order, cannot be opened.
            enabled: modelData.spine >= 0

            Label {
                x: Theme.horizontalPageMargin + modelData.level * Theme.paddingLarge
                width: parent.width - x - Theme.horizontalPageMargin
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.title
                truncationMode: TruncationMode.Fade
                color: !parent.enabled ? Theme.secondaryColor
                     : (highlighted || modelData.spine === page.currentChapter)
                       ? Theme.highlightColor : Theme.primaryColor
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
