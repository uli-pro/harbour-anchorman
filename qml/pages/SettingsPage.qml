import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    // Store once when leaving: the book is laid out again, or the audio file
    // reloaded, only then.
    onStatusChanged: {
        if (status === PageStatus.Deactivating) {
            app.setFontSize(fontSlider.value)
            app.setPlaybackRate(rateSlider.value)
            app.setFontFamily(fontBox.currentIndex === 1 ? "serif" : "sans")
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                title: qsTr("Settings")
            }

            Slider {
                id: rateSlider
                width: parent.width
                minimumValue: app.minPlaybackRate
                maximumValue: app.maxPlaybackRate
                stepSize: 0.05
                value: app.playbackRate
                //: Playback speed, e.g. "1.25×"
                valueText: qsTr("%1×").arg(value.toLocaleString(Qt.locale(), "f", 2))
                label: qsTr("Speed")
            }

            Slider {
                id: fontSlider
                width: parent.width
                minimumValue: app.minFontSize
                maximumValue: app.maxFontSize
                stepSize: 2
                value: app.fontSize
                valueText: value
                //: Text size in pixels on the screen
                label: qsTr("Text size")
            }

            ComboBox {
                id: fontBox
                width: parent.width
                label: qsTr("Font")
                currentIndex: app.fontFamily === "serif" ? 1 : 0
                menu: ContextMenu {
                    MenuItem { text: qsTr("Sans serif") }
                    MenuItem { text: qsTr("Serif") }
                }
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                wrapMode: Text.Wrap
                font.family: fontBox.currentIndex === 1 ? "serif" : "sans-serif"
                font.pixelSize: fontSlider.value
                //: Sample text showing the chosen text size
                text: qsTr("High above the city, on a tall column, stood the statue of the Happy Prince.")
            }
        }
    }
}
