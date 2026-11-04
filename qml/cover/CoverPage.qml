import QtQuick 2.0
import Sailfish.Silica 1.0

CoverBackground {
    Label {
        anchors.centerIn: parent
        //: Application name, usually not translated
        text: qsTr("Anchorman")
    }

    CoverActionList {
        enabled: app.reader !== null

        CoverAction {
            iconSource: app.reader && app.reader.playing ? "image://theme/icon-cover-pause"
                                                          : "image://theme/icon-cover-play"
            onTriggered: app.reader.togglePlay()
        }
    }
}
