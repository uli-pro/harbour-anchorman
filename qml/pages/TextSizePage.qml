import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                title: qsTr("Text size")
            }

            Slider {
                id: slider
                width: parent.width
                minimumValue: app.minFontSize
                maximumValue: app.maxFontSize
                stepSize: 2
                value: app.fontSize
                valueText: value
                //: Unit of the text size slider: pixels on the screen
                label: qsTr("Pixels")
                onReleased: app.setFontSize(value)
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                font.pixelSize: slider.value
                //: Sample text showing the chosen text size
                text: qsTr("High above the city, on a tall column, stood the statue of the Happy Prince.")
            }
        }
    }
}
