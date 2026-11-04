import QtQuick 2.0
import Sailfish.Silica 1.0
import io.thp.pyotherside 1.5

Page {
    allowedOrientations: Orientation.All

    PageHeader {
        id: header
        //: Application name, usually not translated
        title: qsTr("Anchorman")
    }

    Label {
        id: info
        anchors {
            top: header.bottom
            left: parent.left
            right: parent.right
            leftMargin: Theme.horizontalPageMargin
            rightMargin: Theme.horizontalPageMargin
        }
        wrapMode: Text.Wrap
        color: Theme.highlightColor
    }

    Label {
        id: hello
        anchors {
            top: info.bottom
            left: parent.left
            right: parent.right
            leftMargin: Theme.horizontalPageMargin
            rightMargin: Theme.horizontalPageMargin
        }
        wrapMode: Text.Wrap
        color: Theme.highlightColor
        text: qsTr("Hello, reader!")
    }

    Button {
        anchors {
            top: hello.bottom
            topMargin: Theme.paddingLarge
            horizontalCenter: parent.horizontalCenter
        }
        text: "Open test chapter"
        onClicked: pageStack.push(Qt.resolvedUrl("ReaderPage.qml"))
    }

    Python {
        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../../python"))
            importModule("anchorman.bridge", function () {
                call("anchorman.bridge.version_info", [], function (result) {
                    info.text = result
                })
            })
        }

        // Show failures on screen; on the device they are otherwise easy to miss.
        onError: info.text = traceback
    }
}
