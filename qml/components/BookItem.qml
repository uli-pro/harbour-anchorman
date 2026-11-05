import QtQuick 2.0
import Sailfish.Silica 1.0

// A book in a list: cover, the whole title and a line of details.
ListItem {
    id: item

    property var book
    property string detail

    contentHeight: Math.max(Theme.itemSizeExtraLarge, column.height + 2 * Theme.paddingMedium)

    BookCover {
        id: cover

        x: Theme.horizontalPageMargin
        width: Theme.itemSizeLarge * 0.75
        height: Theme.itemSizeExtraLarge - 2 * Theme.paddingSmall
        anchors.verticalCenter: parent.verticalCenter
        book: item.book
    }

    Column {
        id: column

        anchors {
            left: cover.right
            leftMargin: Theme.paddingLarge
            right: parent.right
            rightMargin: Theme.horizontalPageMargin
            verticalCenter: parent.verticalCenter
        }

        Label {
            width: parent.width
            text: item.book ? item.book.title : ""
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
        }

        Row {
            width: parent.width
            spacing: Theme.paddingSmall

            Icon {
                id: audioIcon

                visible: item.book && item.book.audio
                width: Theme.iconSizeExtraSmall
                height: width
                sourceSize.width: width
                sourceSize.height: height
                anchors.verticalCenter: parent.verticalCenter
                source: "image://theme/icon-m-headphone"
            }

            Label {
                width: parent.width - (audioIcon.visible ? audioIcon.width + parent.spacing : 0)
                text: item.detail
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeExtraSmall
                color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
            }
        }
    }
}
