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
            // Text from the book, never markup.
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
        }

        // A book to read, to hear, or both: a readaloud.
        Row {
            width: parent.width
            spacing: Theme.paddingSmall

            Icon {
                id: bookIcon

                visible: item.book !== null && item.book !== undefined && item.book.kind !== "audiobook"
                width: Theme.iconSizeExtraSmall
                height: width
                sourceSize.width: width
                sourceSize.height: height
                anchors.verticalCenter: parent.verticalCenter
                source: "image://theme/icon-m-document"
            }

            Icon {
                id: audioIcon

                visible: item.book !== null && item.book !== undefined && item.book.kind !== "epub"
                width: Theme.iconSizeExtraSmall
                height: width
                sourceSize.width: width
                sourceSize.height: height
                anchors.verticalCenter: parent.verticalCenter
                source: "image://theme/icon-m-headphone"
            }

            Label {
                width: parent.width - (bookIcon.visible ? bookIcon.width + parent.spacing : 0)
                       - (audioIcon.visible ? audioIcon.width + parent.spacing : 0)
                text: item.detail
                // Text from the book, never markup.
                textFormat: Text.PlainText
                truncationMode: TruncationMode.Fade
                font.pixelSize: Theme.fontSizeExtraSmall
                color: item.highlighted ? Theme.secondaryHighlightColor : Theme.secondaryColor
            }
        }
    }
}
