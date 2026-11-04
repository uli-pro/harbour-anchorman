import QtQuick 2.0
import Sailfish.Silica 1.0
import Sailfish.WebEngine 1.0
import io.thp.pyotherside 1.5
import "pages"

ApplicationWindow {
    id: app

    property bool pythonReady: false
    readonly property string libraryFolder: StandardPaths.documents + "/Readalouds"
    readonly property string cacheFolder: StandardPaths.cache + "/books"
    readonly property string positionsFile: StandardPaths.data + "/positions.json"

    function errorText(code) {
        switch (code) {
        case "not_zip":
        case "not_epub":
            return qsTr("This file is not an EPUB book.")
        case "too_many_files":
        case "too_large":
            return qsTr("This book is too large or damaged.")
        case "no_space":
            return qsTr("Not enough free space to open this book.")
        case "unsafe_path":
            return qsTr("This book contains unsafe file names and was not opened.")
        case "io":
            return qsTr("The book could not be read.")
        default:
            return qsTr("This book is damaged.")
        }
    }

    function showError(text) {
        Notices.show(text, Notice.Long, Notice.Center)
    }

    initialPage: Component { LibraryPage { } }
    cover: Qt.resolvedUrl("cover/CoverPage.qml")
    allowedOrientations: defaultAllowedOrientations

    Component.onCompleted: {
        // Only our frame script may run code in the book's pages; scripts
        // that came with a book never run.
        WebEngineSettings.javascriptEnabled = false
    }

    Python {
        id: py

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../python"))
            importModule("anchorman.bridge", function () {
                app.pythonReady = true
            })
        }

        onError: {
            console.warn(traceback)
            app.showError(qsTr("Internal error. Please report it with the log."))
        }
    }
}
