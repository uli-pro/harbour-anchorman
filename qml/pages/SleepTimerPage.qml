import QtQuick 2.0
import Sailfish.Silica 1.0

// When listening ends: off, after some minutes, or at the end of the chapter.
Page {
    id: page

    // The SleepTimer of the reading page.
    property var timer
    // ms left in the chapter at the current speed, -1 if not known.
    property double chapterLeft: -1

    // 0 = off, -1 = end of chapter
    readonly property var choices: [0, 15, 30, 45, 60, -1]

    function chosen(choice) {
        return choice === 0 ? timer.mode === "off"
             : choice < 0 ? timer.mode === "chapter"
             : timer.mode === "minutes" && timer.minutes === choice
    }

    function label(choice) {
        if (choice === 0)
            //: Sleep timer turned off
            return qsTr("Off")
        if (choice > 0)
            //: Sleep timer, e.g. "15 min"
            return qsTr("%1 min").arg(choice)
        if (chapterLeft < 0)
            //: Sleep timer ends listening when the chapter is over
            return qsTr("End of chapter")
        //: Sleep timer at the end of the chapter, with the minutes left, e.g. "End of chapter (3 min)"
        return qsTr("End of chapter (%1 min)").arg(Math.max(1, Math.ceil(chapterLeft / 60000)))
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Title of the page for choosing when listening ends
                title: qsTr("Sleep timer")
                description: timer.mode === "minutes"
                             //: Time left on the running sleep timer, e.g. "23 min left"
                             ? qsTr("%1 min left").arg(Math.ceil(timer.remaining / 60000)) : ""
            }

            Repeater {
                model: page.choices

                BackgroundItem {
                    id: item

                    highlighted: down || page.chosen(modelData)
                    onClicked: {
                        if (modelData === 0)
                            timer.cancel()
                        else if (modelData > 0)
                            timer.setMinutes(modelData)
                        else
                            timer.setChapterEnd()
                        pageStack.pop()
                    }

                    Label {
                        x: Theme.horizontalPageMargin
                        width: parent.width - 2 * x
                        anchors.verticalCenter: parent.verticalCenter
                        color: item.highlighted ? Theme.highlightColor : Theme.primaryColor
                        text: page.label(modelData)
                    }
                }
            }
        }

        VerticalScrollDecorator { }
    }
}
