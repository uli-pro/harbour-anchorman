import QtQuick 2.0
import Amber.Mpris 1.0

// Controls on the lock screen, in the notifications and on headphones,
// for the open book. The Audio permission lets the app own the name.
MprisPlayer {
    readonly property var reader: app.reader

    serviceName: "anchorman"
    identity: "Anchorman"
    desktopEntry: "harbour-anchorman"

    // Fixed: Amber does not pass a later change of CanControl on, and false
    // also turns off CanPlay and CanPause (seen on the device).
    canControl: true
    canPlay: reader !== null
    canPause: reader !== null
    canGoNext: reader !== null
    canGoPrevious: reader !== null
    // The narration is a sequence of sentences across several files, not
    // one track with a position.
    canSeek: false
    playbackStatus: reader === null ? Mpris.Stopped
                  : reader.playing ? Mpris.Playing : Mpris.Paused

    metaData {
        title: reader !== null ? reader.book.title : ""
        contributingArtist: reader !== null ? reader.book.authors : []
        artUrl: reader !== null ? reader.coverUrl : ""
    }

    onPlayRequested: if (reader) reader.play()
    // A stop that forgot the place would help nobody listening to a book.
    onPauseRequested: if (reader) reader.pause()
    onStopRequested: if (reader) reader.pause()
    onPlayPauseRequested: {
        if (!reader)
            return
        if (reader.playing)
            reader.pause()
        else
            reader.play()
    }
    onNextRequested: if (reader) reader.nextSentence()
    onPreviousRequested: if (reader) reader.previousSentence()
}
